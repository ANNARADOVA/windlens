"""Track B core: run WindLens's wind-first single-reference reconstruction against
an arbitrary uploaded wind-data file, with the outage window auto-detected from the
file's own NaN gaps (with a manual override). This is a thin wrapper over Track A's
pipeline pieces -- no new modeling, just file-shape normalization and orchestration
so `baywa_tool_server.py` has something simple to call per upload.

Accepted wind-data file shape (long format, one row per turbine per timestamp): either
the canonical columns (`timestamp_utc, turbine_id, wind_speed_ms`) or BayWa's raw
columns (`timestamp, turbine_name, wind_speed`) -- whichever the file actually has.
Accepted power-curve file shape: BayWa's raw columns (`wind_speed, power`), renamed to
`bin_center_ms`/`mean_power_kw` for the existing, unmodified `apply_power_curve` --
same adapter Track A's `build_baywa_dataset.py` already uses.

A target turbine is auto-detected as any turbine with at least one NaN wind-speed
reading; the outage window defaults to that turbine's single largest contiguous NaN
run (a documented simplification -- multiple separate gaps on one turbine are not
split into multiple events). A manual start/end override replaces auto-detection
entirely when given. Reference candidates are every other uploaded turbine that has
no NaN gap at all; if none qualify, every other turbine is used instead (a documented
fallback, not a silent failure).
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from windlens.loss_estimate import infer_interval_hours, integrate_energy_kwh
from windlens.power_curve import apply_power_curve
from windlens.reconstruct import (
    reconstruct_wind_speed,
    reference_within_training_domain,
    select_reference_turbine,
)

CANONICAL_WIND_COLUMNS = {
    "timestamp_utc": "timestamp_utc",
    "turbine_id": "turbine_id",
    "wind_speed_ms": "wind_speed_ms",
}
BAYWA_RAW_WIND_COLUMNS = {
    "timestamp": "timestamp_utc",
    "turbine_name": "turbine_id",
    "wind_speed": "wind_speed_ms",
}
BAYWA_RAW_CURVE_COLUMNS = {"wind_speed": "bin_center_ms", "power": "mean_power_kw"}
CANONICAL_CURVE_COLUMNS = {"bin_center_ms": "bin_center_ms", "mean_power_kw": "mean_power_kw"}


def _read_table(file_bytes: bytes, filename: str) -> pd.DataFrame:
    lowered = filename.lower()
    if lowered.endswith(".xlsx") or lowered.endswith(".xls"):
        return pd.read_excel(io.BytesIO(file_bytes))
    return pd.read_csv(io.BytesIO(file_bytes))


def load_wind_data(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Normalize an uploaded wind-data file (CSV or xlsx) to
    timestamp_utc/turbine_id/wind_speed_ms, preserving NaN gaps as-is."""

    raw = _read_table(file_bytes, filename)
    rename = (
        CANONICAL_WIND_COLUMNS
        if set(CANONICAL_WIND_COLUMNS) <= set(raw.columns)
        else BAYWA_RAW_WIND_COLUMNS
    )
    missing = set(rename) - set(raw.columns)
    if missing:
        raise ValueError(
            f"Uploaded wind-data file is missing required column(s): {sorted(missing)} "
            "(expected either timestamp_utc/turbine_id/wind_speed_ms or "
            "timestamp/turbine_name/wind_speed)"
        )

    normalized = raw.rename(columns=rename)[list(rename.values())].copy()
    normalized["turbine_id"] = normalized["turbine_id"].astype(str)
    normalized["wind_speed_ms"] = normalized["wind_speed_ms"].astype(float)
    if not pd.api.types.is_string_dtype(normalized["timestamp_utc"]):
        normalized["timestamp_utc"] = pd.to_datetime(normalized["timestamp_utc"]).dt.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return normalized.sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)


def load_power_curve(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Normalize an uploaded power-curve file to bin_center_ms/mean_power_kw."""

    raw = _read_table(file_bytes, filename)
    rename = (
        CANONICAL_CURVE_COLUMNS
        if set(CANONICAL_CURVE_COLUMNS) <= set(raw.columns)
        else BAYWA_RAW_CURVE_COLUMNS
    )
    missing = set(rename) - set(raw.columns)
    if missing:
        raise ValueError(
            f"Uploaded power-curve file is missing required column(s): {sorted(missing)} "
            "(expected either bin_center_ms/mean_power_kw or wind_speed/power)"
        )
    return (
        raw.rename(columns=rename)[list(rename.values())]
        .astype(float)
        .sort_values("bin_center_ms")
        .reset_index(drop=True)
    )


# A turbine's longest contiguous NaN run must reach at least this many rows before
# it is treated as an outage target. Isolated single-row sensor dropouts (normal on
# reference turbines too) are common and must NOT be mistaken for an outage -- that
# both misclassifies a healthy reference as a target and, if the dropout happens to
# sit near the very start of the file, leaves too little pre-window history for
# select_reference_turbine, crashing the whole run for no real reason.
MIN_OUTAGE_RUN_LENGTH = 3


def _longest_nan_run(series: pd.DataFrame) -> pd.DataFrame | None:
    """The longest contiguous run of NaN wind_speed_ms rows in a single turbine's
    time-sorted series, or None if there is no NaN at all."""

    is_nan = series["wind_speed_ms"].isna()
    if not is_nan.any():
        return None
    run_id = (is_nan != is_nan.shift()).cumsum()
    nan_runs = series[is_nan].groupby(run_id[is_nan])
    return max((group for _, group in nan_runs), key=len)


def detect_target_turbines(wind_df: pd.DataFrame) -> list[str]:
    """Every turbine_id whose longest contiguous NaN run reaches
    MIN_OUTAGE_RUN_LENGTH rows -- not just any turbine with any NaN at all (see
    MIN_OUTAGE_RUN_LENGTH)."""

    targets = []
    for turbine_id, group in wind_df.sort_values("timestamp_utc").groupby("turbine_id"):
        longest_run = _longest_nan_run(group[["timestamp_utc", "wind_speed_ms"]])
        if longest_run is not None and len(longest_run) >= MIN_OUTAGE_RUN_LENGTH:
            targets.append(turbine_id)
    return sorted(targets)


def detect_outage_window(wind_df: pd.DataFrame, target_turbine: str) -> tuple[str, str]:
    """The target turbine's single largest contiguous run of NaN wind_speed_ms,
    as [start, end) timestamp_utc strings."""

    series = (
        wind_df[wind_df["turbine_id"] == target_turbine]
        .sort_values("timestamp_utc")[["timestamp_utc", "wind_speed_ms"]]
        .reset_index(drop=True)
    )
    longest_run = _longest_nan_run(series)
    if longest_run is None:
        raise ValueError(f"{target_turbine} has no NaN wind-speed gap to auto-detect")
    gap_start = longest_run["timestamp_utc"].iloc[0]
    last_timestamp = series["timestamp_utc"].iloc[
        series.index[series["timestamp_utc"] == longest_run["timestamp_utc"].iloc[-1]][0]
    ]
    # End is exclusive: the next row after the run, or one cadence step past the last
    # row if the gap runs to the end of the file. Cadence is inferred from the
    # smallest gap between consecutive timestamps in the file.
    cadence_candidates = pd.to_datetime(series["timestamp_utc"]).diff().dropna()
    cadence = cadence_candidates[cadence_candidates > pd.Timedelta(0)].min()
    gap_end = (pd.Timestamp(last_timestamp) + cadence).strftime("%Y-%m-%dT%H:%M:%SZ")
    return gap_start, gap_end


def _candidate_references(wind_df: pd.DataFrame, target_turbine: str, detected_targets: list[str]) -> list[str]:
    """Every other uploaded turbine not itself flagged as an outage target.

    An incidental, short NaN dropout on a reference turbine does not disqualify it
    (``_paired_series`` already drops unpaired/NaN rows when fitting) -- only
    turbines that cross MIN_OUTAGE_RUN_LENGTH are excluded, matching
    ``detect_target_turbines``'s own definition of "target" exactly.
    """

    other_turbines = sorted(t for t in wind_df["turbine_id"].unique() if t != target_turbine)
    clean = [t for t in other_turbines if t not in detected_targets]
    return clean if clean else other_turbines


def classify_file_kind(file_bytes: bytes, filename: str) -> str:
    """Decide whether an uploaded file is a wind-data file or a power-curve file,
    from its own column headers -- so a user can drop every file into one box
    instead of having to know in advance which of two separate upload fields
    each file belongs in (this is what a real BayWa upload actually looks like:
    several per-turbine data files plus one power-curve file, all selected
    together). Returns "wind_data", "power_curve", or "unknown"."""

    raw = _read_table(file_bytes, filename)
    columns = set(raw.columns)
    if set(CANONICAL_WIND_COLUMNS) <= columns or set(BAYWA_RAW_WIND_COLUMNS) <= columns:
        return "wind_data"
    if set(CANONICAL_CURVE_COLUMNS) <= columns or set(BAYWA_RAW_CURVE_COLUMNS) <= columns:
        return "power_curve"
    return "unknown"


def load_wind_data_files(files: list[tuple[bytes, str]]) -> pd.DataFrame:
    """Normalize and concatenate one or more uploaded wind-data files into a single
    frame. BayWa's challenge data ships one turbine per file (e.g. ``T2_data.xlsx``
    has only T2's own readings, with no reference turbines in it at all) -- a
    real upload is commonly several of these files selected together, not one
    pre-combined file."""

    frames = [load_wind_data(file_bytes, filename) for file_bytes, filename in files]
    return pd.concat(frames, ignore_index=True).sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)


def describe_uploaded_files(
    wind_data_items: list[tuple[bytes, str]],
    power_curve_items: list[tuple[bytes, str]],
) -> list[dict[str, Any]]:
    """Per-file role preview for the upload form's pre-run confirmation summary
    (2026-10-24, Category 8) -- lightweight (one file parsed at a time, no
    reference selection, no model fit), so a mis-assigned file (e.g. the power
    curve dropped in as if it were wind data) can be caught before Run is
    clicked, not only from the result afterward.

    "target (has a data gap)" is a per-file guess from that file alone -- the
    real target/reference split (``detect_target_turbines``) only happens once
    every uploaded wind-data file is combined. Uses the SAME
    MIN_OUTAGE_RUN_LENGTH-based gap test as ``detect_target_turbines`` (a run of
    isolated/scattered NaN readings too short to be a real outage does not count
    -- real reference-turbine files commonly have a handful of these without
    being disqualified as a reference) so this preview's guess does not
    contradict what the actual run then does. Confirmed against the real BayWa
    sample files (2026-10-24 live verification): O1_data.xlsx has isolated NaN
    readings elsewhere in its history but no run long enough to count, so it
    correctly previews as a reference candidate, matching what /run selects.
    """

    described: list[dict[str, Any]] = []
    for file_bytes, filename in wind_data_items:
        try:
            df = load_wind_data(file_bytes, filename)
        except ValueError as exc:
            described.append({"filename": filename, "kind": "wind_data", "error": str(exc)})
            continue
        turbines = sorted(df["turbine_id"].unique().tolist())
        longest_run = _longest_nan_run(df.sort_values("timestamp_utc")[["timestamp_utc", "wind_speed_ms"]])
        has_gap = longest_run is not None and len(longest_run) >= MIN_OUTAGE_RUN_LENGTH
        described.append(
            {
                "filename": filename,
                "kind": "wind_data",
                "turbines": turbines,
                "role_guess": "target (has a data gap)" if has_gap else "reference candidate (no gap in this file)",
            }
        )
    for file_bytes, filename in power_curve_items:
        described.append({"filename": filename, "kind": "power_curve", "role_guess": "power curve"})
    return described


def _targets_missing_in_window(wind_df: pd.DataFrame, start: str, end: str) -> list[str]:
    """Every turbine with zero valid (non-NaN) wind_speed_ms readings inside
    [start, end) -- whether that's because the rows are missing entirely or
    present but NaN. Used for the manual-window override path, where the user
    is telling us a turbine was down for a specific window regardless of
    whether auto-detection's own NaN-run heuristic would have found it (e.g.
    a gap shorter than MIN_OUTAGE_RUN_LENGTH, or one that the uploader wants
    to test counterfactually)."""

    in_window = wind_df[(wind_df["timestamp_utc"] >= start) & (wind_df["timestamp_utc"] < end)]
    missing = []
    for turbine_id, group in wind_df.groupby("turbine_id"):
        rows_in_window = in_window[in_window["turbine_id"] == turbine_id]
        if rows_in_window.empty or rows_in_window["wind_speed_ms"].notna().sum() == 0:
            missing.append(turbine_id)
    return sorted(missing)


def run_pipeline(
    wind_df: pd.DataFrame,
    power_curve_df: pd.DataFrame | None = None,
    manual_start: str | None = None,
    manual_end: str | None = None,
) -> dict[str, Any]:
    """Run the reconstruction for every auto-detected target turbine (or, when
    ``manual_start``/``manual_end`` are given, for every turbine that has no reading
    at all inside that window) and return per-target predictions."""

    uploaded_turbines = wind_df["turbine_id"].nunique()
    if uploaded_turbines < 2:
        only = wind_df["turbine_id"].iloc[0] if uploaded_turbines else "none"
        raise ValueError(
            f"Only one turbine ({only}) was found across the uploaded file(s). "
            "BayWa's challenge data ships one turbine per file -- select the "
            "target turbine's file together with at least one other turbine's "
            "file to use as a reference (e.g. T2_data.xlsx + O1_data.xlsx)."
        )

    if manual_start and manual_end:
        # A manual window must be able to identify a target turbine even when
        # detect_target_turbines() finds no NaN run -- e.g. a gap shorter than
        # MIN_OUTAGE_RUN_LENGTH, or a counterfactual "what if this turbine had
        # been down here" test. Previously this function always ran
        # detect_target_turbines() first and raised before ever reaching the
        # manual-window case below, so a manual override could never rescue a
        # turbine with no NaN gap -- fixed by branching on the window instead.
        targets = _targets_missing_in_window(wind_df, manual_start, manual_end)
        if not targets:
            raise ValueError(
                f"No turbine has a missing or NaN wind-speed reading inside the "
                f"manual window {manual_start} to {manual_end} -- nothing to "
                "reconstruct for that window."
            )
    else:
        targets = detect_target_turbines(wind_df)
        if not targets:
            raise ValueError(
                "No NaN wind-speed gap found on any uploaded turbine, and no manual "
                "outage window was given -- nothing to reconstruct"
            )

    results = []
    for target_turbine in targets:
        try:
            window_start, window_end = (
                (manual_start, manual_end)
                if manual_start and manual_end
                else detect_outage_window(wind_df, target_turbine)
            )
            window_auto_detected = not (manual_start and manual_end)

            candidates = _candidate_references(wind_df, target_turbine, targets)
            pre_window = wind_df[wind_df["timestamp_utc"] < window_start]
            selection = select_reference_turbine(pre_window, target_turbine, candidates)
            selected_reference = selection["selected"]

            reconstruction = reconstruct_wind_speed(
                wind_df, target_turbine, selected_reference, window_start, window_end
            )
        except ValueError as exc:
            # One target's gap being too close to the start of the file (not enough
            # pre-window history) must not abort the other targets in the same upload.
            results.append({"target_turbine": target_turbine, "error": str(exc)})
            continue

        # How much of the outage window the reference actually had usable readings
        # for -- the denominator is the target's own row count in that window (its
        # sampling grid, NaN or not), so a reference with gaps of its own shows up
        # as < 100% rather than silently producing fewer predicted rows with no
        # explanation (2026-10-24, Category 8).
        expected_rows = int(
            (
                (wind_df["turbine_id"] == target_turbine)
                & (wind_df["timestamp_utc"] >= window_start)
                & (wind_df["timestamp_utc"] < window_end)
            ).sum()
        )
        reference_coverage_pct = (
            round(100.0 * len(reconstruction) / expected_rows, 1) if expected_rows else None
        )

        # Same wind-speed domain check the official BayWa record's review gate uses
        # (src/windlens/reconstruct.py::reference_within_training_domain) -- the live
        # upload path must hold itself to the same honesty standard as the official
        # record, not feel like a lesser, unvalidated calculator by comparison.
        try:
            domain_check = reference_within_training_domain(wind_df, selected_reference, window_start, window_end)
        except ValueError:
            domain_check = None

        # Cadence is inferred unconditionally now (previously only when a power curve
        # was uploaded) so it's always surfaced, and a per-target try/except so one
        # target's irregular reference timestamps can't abort the whole upload (the
        # existing error-isolation pattern a few lines above, extended to this step).
        try:
            reference_timestamps = wind_df.loc[wind_df["turbine_id"] == selected_reference, "timestamp_utc"]
            interval_hours = infer_interval_hours(reference_timestamps)
            inferred_cadence_minutes = interval_hours * 60
        except ValueError:
            interval_hours = None
            inferred_cadence_minutes = None

        entry: dict[str, Any] = {
            "target_turbine": target_turbine,
            "selected_reference": selected_reference,
            "reference_ranking": selection["ranking"],
            "outage_window_utc": [window_start, window_end],
            "window_auto_detected": window_auto_detected,
            "rows_predicted": int(len(reconstruction)),
            "reference_coverage_pct": reference_coverage_pct,
            "domain_check": domain_check,
            "inferred_cadence_minutes": inferred_cadence_minutes,
            "raw_reconstruction_notice": (
                "This is a raw reconstruction from your uploaded data, not validated "
                "against ground truth for this event -- the same evidence standard as "
                "the official record, not a lesser calculator."
            ),
            "predictions": [
                {
                    "timestamp_utc": row.timestamp_utc,
                    "wind_speed_ms_predicted": float(row.wind_speed_ms_reconstructed),
                }
                for row in reconstruction.itertuples(index=False)
            ],
        }

        if power_curve_df is not None and not reconstruction.empty:
            predicted_power = apply_power_curve(
                power_curve_df, reconstruction["wind_speed_ms_reconstructed"].to_numpy()
            )
            entry["estimated_power_kw"] = [float(value) for value in predicted_power]
            if interval_hours is not None:
                entry["estimated_lost_kwh"] = integrate_energy_kwh(predicted_power, interval_hours=interval_hours)
            else:
                # Power curve applied fine, but the reference's own timestamps were too
                # irregular to infer a reliable cadence -- don't guess a sample width.
                entry["estimated_lost_kwh_unavailable_reason"] = (
                    "The reference turbine's timestamps are too irregular to infer a "
                    "reliable sampling interval, so energy could not be integrated."
                )

        results.append(entry)

    return {"targets": results}
