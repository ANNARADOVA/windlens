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
import re
from typing import Any

import numpy as np
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


def _normalize_wind_data(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize an already-parsed wind-data table to
    timestamp_utc/turbine_id/wind_speed_ms, preserving NaN gaps as-is. Pure
    transform, no file I/O -- split out of ``load_wind_data`` (2026-10-24 perf
    fix) so a caller that has already parsed the file once (e.g. to classify
    it) can normalize that same in-memory table instead of re-reading it."""

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


def load_wind_data(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Normalize an uploaded wind-data file (CSV or xlsx) to
    timestamp_utc/turbine_id/wind_speed_ms, preserving NaN gaps as-is."""

    return _normalize_wind_data(_read_table(file_bytes, filename))


def _normalize_power_curve(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize an already-parsed power-curve table to
    bin_center_ms/mean_power_kw. Pure transform, no file I/O -- see
    ``_normalize_wind_data`` for why this is split out."""

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


def load_power_curve(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Normalize an uploaded power-curve file to bin_center_ms/mean_power_kw."""

    return _normalize_power_curve(_read_table(file_bytes, filename))


# A turbine's longest contiguous NaN run must reach at least this many rows before
# it is treated as an outage target. Isolated single-row sensor dropouts (normal on
# reference turbines too) are common and must NOT be mistaken for an outage -- that
# both misclassifies a healthy reference as a target and, if the dropout happens to
# sit near the very start of the file, leaves too little pre-window history for
# select_reference_turbine, crashing the whole run for no real reason.
MIN_OUTAGE_RUN_LENGTH = 3

# BayWa's own real challenge dataset ships these turbine ids as reference-pool
# turbines ONLY -- never targets -- regardless of any data-quality gaps they may
# have elsewhere in their own history. Confirmed against the real sample files
# (2026-10-24, Anna, from a colleague's own analysis of this exact dataset): H1
# has a genuine ~1.5-day gap in mid-July 2026 (two consecutive runs, 62 and 94
# rows), unrelated to the official September test window, that a reference
# implementation treats as a data-quality issue to interpolate from its park
# neighbors -- not as an outage to report a loss for. Before this fix, auto-
# detection had no way to know that and offered H1 as a "broken" target with
# its own loss estimate, which is wrong for this dataset. A real user's OWN
# uploaded data (different turbine ids) is unaffected -- this only excludes
# the specific ids BayWa's own challenge data uses for its reference pool.
KNOWN_REFERENCE_ONLY_TURBINE_IDS = {"H1", "H2", "H3", "H4", "H5", "O1", "O2"}


def _nan_runs(series: pd.DataFrame) -> list[pd.DataFrame]:
    """Every contiguous run of NaN wind_speed_ms rows in a single turbine's
    time-sorted series, in order, or an empty list if there is no NaN at all.
    (2026-10-24: split out of the old ``_longest_nan_run`` so a turbine with
    two or more SEPARATE qualifying outages can be detected as two or more
    instances, not just its single largest run.)"""

    is_nan = series["wind_speed_ms"].isna()
    if not is_nan.any():
        return []
    run_id = (is_nan != is_nan.shift()).cumsum()
    return [group for _, group in series[is_nan].groupby(run_id[is_nan])]


def _longest_nan_run(series: pd.DataFrame) -> pd.DataFrame | None:
    """The longest contiguous run of NaN wind_speed_ms rows in a single turbine's
    time-sorted series, or None if there is no NaN at all. Used only where a
    single per-turbine gap check is enough (the lightweight per-file preview in
    ``describe_uploaded_files``) -- the real detection/reconstruction path uses
    ``detect_outage_instances`` so a second, separate gap is not missed."""

    runs = _nan_runs(series)
    return max(runs, key=len) if runs else None


def _window_for_run(series: pd.DataFrame, nan_run: pd.DataFrame) -> tuple[str, str]:
    """[start, end) timestamp_utc strings for one specific contiguous NaN run,
    given the full time-sorted series it came from (needed to infer the file's
    own cadence for the exclusive end bound)."""

    gap_start = nan_run["timestamp_utc"].iloc[0]
    last_timestamp = series["timestamp_utc"].iloc[
        series.index[series["timestamp_utc"] == nan_run["timestamp_utc"].iloc[-1]][0]
    ]
    # End is exclusive: the next row after the run, or one cadence step past the last
    # row if the gap runs to the end of the file. Cadence is inferred from the
    # smallest gap between consecutive timestamps in the file.
    cadence_candidates = pd.to_datetime(series["timestamp_utc"]).diff().dropna()
    cadence = cadence_candidates[cadence_candidates > pd.Timedelta(0)].min()
    gap_end = (pd.Timestamp(last_timestamp) + cadence).strftime("%Y-%m-%dT%H:%M:%SZ")
    return gap_start, gap_end


def detect_outage_instances(wind_df: pd.DataFrame) -> list[dict[str, str]]:
    """Every qualifying outage INSTANCE across all uploaded turbines -- not just
    one per turbine. A turbine with two separate, independent NaN runs, each
    reaching MIN_OUTAGE_RUN_LENGTH rows, produces two separate instances here,
    each with its own [window_start, window_end). (2026-10-24: previously only
    the single LONGEST run per turbine was auto-detected; a second, distinct
    outage on the same turbine was silently invisible to auto-detection.)

    Each dict: {"target_turbine": ..., "window_start": ..., "window_end": ...}.
    A turbine id in ``KNOWN_REFERENCE_ONLY_TURBINE_IDS`` never produces an
    instance, regardless of its own internal gaps (2026-10-24 correctness fix).
    """

    instances: list[dict[str, str]] = []
    for turbine_id, group in wind_df.sort_values("timestamp_utc").groupby("turbine_id"):
        if turbine_id in KNOWN_REFERENCE_ONLY_TURBINE_IDS:
            continue
        series = group[["timestamp_utc", "wind_speed_ms"]].reset_index(drop=True)
        for run in _nan_runs(series):
            if len(run) >= MIN_OUTAGE_RUN_LENGTH:
                window_start, window_end = _window_for_run(series, run)
                instances.append(
                    {"target_turbine": turbine_id, "window_start": window_start, "window_end": window_end}
                )
    return sorted(instances, key=lambda instance: (instance["target_turbine"], instance["window_start"]))


def detect_target_turbines(wind_df: pd.DataFrame) -> list[str]:
    """Every distinct turbine_id with at least one qualifying outage instance
    (see ``detect_outage_instances``) -- not just any turbine with any NaN at
    all (see MIN_OUTAGE_RUN_LENGTH)."""

    return sorted({instance["target_turbine"] for instance in detect_outage_instances(wind_df)})


def detect_outage_window(wind_df: pd.DataFrame, target_turbine: str) -> tuple[str, str]:
    """The target turbine's single largest contiguous run of NaN wind_speed_ms,
    as [start, end) timestamp_utc strings. Kept for callers that only care about
    one window per turbine; ``run_pipeline``'s own auto-detection now uses
    ``detect_outage_instances`` instead, to catch a second, separate gap too."""

    series = (
        wind_df[wind_df["turbine_id"] == target_turbine]
        .sort_values("timestamp_utc")[["timestamp_utc", "wind_speed_ms"]]
        .reset_index(drop=True)
    )
    longest_run = _longest_nan_run(series)
    if longest_run is None:
        raise ValueError(f"{target_turbine} has no NaN wind-speed gap to auto-detect")
    return _window_for_run(series, longest_run)


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


def _classify_raw_table(raw: pd.DataFrame) -> str:
    """Decide whether an already-parsed table is a wind-data table or a
    power-curve table, from its own column headers. Returns "wind_data",
    "power_curve", or "unknown". Pure transform, no file I/O."""

    columns = set(raw.columns)
    if set(CANONICAL_WIND_COLUMNS) <= columns or set(BAYWA_RAW_WIND_COLUMNS) <= columns:
        return "wind_data"
    if set(CANONICAL_CURVE_COLUMNS) <= columns or set(BAYWA_RAW_CURVE_COLUMNS) <= columns:
        return "power_curve"
    return "unknown"


def classify_file_kind(file_bytes: bytes, filename: str) -> str:
    """Decide whether an uploaded file is a wind-data file or a power-curve file,
    from its own column headers -- so a user can drop every file into one box
    instead of having to know in advance which of two separate upload fields
    each file belongs in (this is what a real BayWa upload actually looks like:
    several per-turbine data files plus one power-curve file, all selected
    together). Returns "wind_data", "power_curve", or "unknown"."""

    return _classify_raw_table(_read_table(file_bytes, filename))


def read_and_classify(file_bytes: bytes, filename: str) -> tuple[str, pd.DataFrame]:
    """Parse an uploaded file's bytes exactly ONCE and return (kind, normalized
    table) -- "wind_data" or "power_curve" tables come back already normalized
    (timestamp_utc/turbine_id/wind_speed_ms, or bin_center_ms/mean_power_kw);
    an "unknown" file's raw, un-normalized table comes back for error-message
    purposes only.

    2026-10-24 perf fix: the upload server previously called
    ``classify_file_kind()`` (a full pandas parse) and then ``load_wind_data()``
    or ``load_power_curve()`` (another full parse of the SAME bytes) separately
    for every uploaded file. For BayWa's real 900KB+ per-turbine xlsx files,
    each parse costs roughly a second, so a whole-farm upload of 10 turbine
    files was silently paying for 20 parses instead of 10 -- the actual
    measured cause of a 16s /run request that profiling had assumed was
    reconstruction-side (the reconstruction itself took under 2s). This is the
    single entry point that fixes it: one parse per uploaded file, period."""

    raw = _read_table(file_bytes, filename)
    kind = _classify_raw_table(raw)
    if kind == "wind_data":
        return kind, _normalize_wind_data(raw)
    if kind == "power_curve":
        return kind, _normalize_power_curve(raw)
    return kind, raw


def concat_wind_data_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine one or more already-normalized wind-data frames (e.g. from
    ``read_and_classify``) into a single sorted frame -- the same combining
    step ``load_wind_data_files`` does, split out so a caller that already has
    normalized frames in hand doesn't have to re-read bytes to get one."""

    return pd.concat(frames, ignore_index=True).sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)


def load_wind_data_files(files: list[tuple[bytes, str]]) -> pd.DataFrame:
    """Normalize and concatenate one or more uploaded wind-data files into a single
    frame. BayWa's challenge data ships one turbine per file (e.g. ``T2_data.xlsx``
    has only T2's own readings, with no reference turbines in it at all) -- a
    real upload is commonly several of these files selected together, not one
    pre-combined file."""

    return concat_wind_data_frames([load_wind_data(file_bytes, filename) for file_bytes, filename in files])


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
        # A file is only previewed as a possible target if at least one of its
        # turbines is NOT in the known BayWa reference-only pool (2026-10-24,
        # matching detect_outage_instances()'s own exclusion -- otherwise this
        # preview would contradict what /run actually selects, e.g. guessing
        # H1 as a target from its own unrelated mid-July gap).
        eligible = any(t not in KNOWN_REFERENCE_ONLY_TURBINE_IDS for t in turbines)
        longest_run = _longest_nan_run(df.sort_values("timestamp_utc")[["timestamp_utc", "wind_speed_ms"]])
        has_gap = eligible and longest_run is not None and len(longest_run) >= MIN_OUTAGE_RUN_LENGTH
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


# Cap on overlay-chart points returned per target so a long real-world upload
# (BayWa's own sample files span ~3 months at 10-minute cadence) doesn't ship a
# huge per-point payload to the browser; evenly stepping down to this count still
# shows the gap and the reference's continuity through it clearly.
MAX_OVERLAY_POINTS = 400


def _overlay_series(
    wind_df: pd.DataFrame,
    target_turbine: str,
    reference_turbine: str,
    window_start: str,
    window_end: str,
    reconstruction: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Target's own actual readings (with its real gap), the selected
    reference's actual readings, AND the model's reconstructed wind speed
    during the outage window, over a window spanning as far before and after
    the outage as the outage itself is long -- so the Result chart can show
    all three together (target actual / reference actual / target
    reconstructed), not just two, with the outage window shaded.

    ``reconstruction`` (2026-10-24, a real gap Anna flagged: the chart showed
    the gap but never the model's own output for it) is the same DataFrame
    ``reconstruct_wind_speed()`` already returns -- passed in rather than
    recomputed, since the caller has already built it."""

    duration = pd.Timestamp(window_end) - pd.Timestamp(window_start)
    margin_start = (pd.Timestamp(window_start) - duration).strftime("%Y-%m-%dT%H:%M:%SZ")
    margin_end = (pd.Timestamp(window_end) + duration).strftime("%Y-%m-%dT%H:%M:%SZ")

    sliced = wind_df[(wind_df["timestamp_utc"] >= margin_start) & (wind_df["timestamp_utc"] < margin_end)]
    target = sliced[sliced["turbine_id"] == target_turbine].set_index("timestamp_utc")["wind_speed_ms"]
    reference = sliced[sliced["turbine_id"] == reference_turbine].set_index("timestamp_utc")["wind_speed_ms"]
    reconstructed = (
        reconstruction.set_index("timestamp_utc")["wind_speed_ms_reconstructed"]
        if reconstruction is not None and not reconstruction.empty
        else pd.Series(dtype=float)
    )
    timestamps = sorted(set(target.index) | set(reference.index))
    if len(timestamps) > MAX_OVERLAY_POINTS:
        step = max(1, len(timestamps) // MAX_OVERLAY_POINTS)
        timestamps = timestamps[::step]

    points = []
    for ts in timestamps:
        t_val = target.get(ts)
        r_val = reference.get(ts)
        p_val = reconstructed.get(ts)
        points.append(
            {
                "timestamp_utc": ts,
                "target_ms": None if pd.isna(t_val) else float(t_val),
                "reference_ms": None if pd.isna(r_val) else float(r_val),
                "reconstructed_ms": None if p_val is None or pd.isna(p_val) else float(p_val),
                "in_outage": bool(window_start <= ts < window_end),
            }
        )
    return points


def _find_clean_validation_window(
    wind_df: pd.DataFrame,
    target_turbine: str,
    reference_turbine: str,
    window_start: str,
    window_end: str,
) -> tuple[str, str] | None:
    """Find ONE same-duration window elsewhere in the upload where the target
    has a complete, gap-free run of real readings (so there's ground truth to
    check against) and the reference has at least some coverage. Tries right
    after the outage window first (the same shape the official BayWa record's
    own shown-window self-validation uses), then right before it. Returns
    None if neither side has a clean window -- never fabricates one.

    2026-10-24, Anna, high priority: a live upload previously had no accuracy
    figure at all for its own outage (by construction -- there's no ground
    truth for the actual gap). This finds a SINGLE extra window to check
    instead, deliberately bounded to one reconstruction run, not a loop over
    many historical blocks (the full-period backtest tried and reverted
    earlier this session over a measured 2x /run slowdown)."""

    duration = pd.Timestamp(window_end) - pd.Timestamp(window_start)
    target_rows = wind_df[wind_df["turbine_id"] == target_turbine]

    for candidate_start, candidate_end in (
        (window_end, (pd.Timestamp(window_end) + duration).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ((pd.Timestamp(window_start) - duration).strftime("%Y-%m-%dT%H:%M:%SZ"), window_start),
    ):
        in_window = target_rows[
            (target_rows["timestamp_utc"] >= candidate_start) & (target_rows["timestamp_utc"] < candidate_end)
        ]
        if in_window.empty or in_window["wind_speed_ms"].isna().any():
            continue
        reference_in_window = wind_df[
            (wind_df["turbine_id"] == reference_turbine)
            & (wind_df["timestamp_utc"] >= candidate_start)
            & (wind_df["timestamp_utc"] < candidate_end)
        ]["wind_speed_ms"].dropna()
        if reference_in_window.empty:
            continue
        return candidate_start, candidate_end
    return None


def _self_validate(
    wind_df: pd.DataFrame,
    target_turbine: str,
    reference_turbine: str,
    window_start: str,
    window_end: str,
    power_curve_df: pd.DataFrame | None,
    interval_hours: float | None,
) -> dict[str, Any] | None:
    """Run the SAME reconstruction on one clean validation window (see
    ``_find_clean_validation_window``) and compare it to the real readings
    there, to give a live upload an honest accuracy figure for its own data
    -- not just a cross-reference to the official record's n=3 targets.
    Returns None (never a fabricated number) if no clean window exists."""

    found = _find_clean_validation_window(wind_df, target_turbine, reference_turbine, window_start, window_end)
    if found is None:
        return None
    check_start, check_end = found

    try:
        reconstruction = reconstruct_wind_speed(wind_df, target_turbine, reference_turbine, check_start, check_end)
    except ValueError:
        return None
    if reconstruction.empty:
        return None

    actual = (
        wind_df[
            (wind_df["turbine_id"] == target_turbine)
            & (wind_df["timestamp_utc"] >= check_start)
            & (wind_df["timestamp_utc"] < check_end)
        ]
        .set_index("timestamp_utc")["wind_speed_ms"]
    )
    paired = pd.concat(
        [actual.rename("actual"), reconstruction.set_index("timestamp_utc")["wind_speed_ms_reconstructed"].rename("predicted")],
        axis=1,
        join="inner",
    ).dropna()
    if paired.empty:
        return None

    wind_residuals = paired["actual"].to_numpy(dtype=float) - paired["predicted"].to_numpy(dtype=float)
    result: dict[str, Any] = {
        "window_utc": [check_start, check_end],
        "wind_rmse_ms": float(np.sqrt(np.mean(wind_residuals**2))),
        "wind_mae_ms": float(np.mean(np.abs(wind_residuals))),
        "n_observations": int(len(paired)),
    }

    if power_curve_df is not None and interval_hours is not None:
        actual_power = apply_power_curve(power_curve_df, paired["actual"].to_numpy(dtype=float))
        predicted_power = apply_power_curve(power_curve_df, paired["predicted"].to_numpy(dtype=float))
        power_residuals = actual_power - predicted_power
        result["power_rmse_kw"] = float(np.sqrt(np.mean(power_residuals**2)))
        result["power_mae_kw"] = float(np.mean(np.abs(power_residuals)))
        actual_kwh = integrate_energy_kwh(actual_power, interval_hours=interval_hours)
        predicted_kwh = integrate_energy_kwh(predicted_power, interval_hours=interval_hours)
        if actual_kwh:
            result["energy_relative_error_pct"] = abs(actual_kwh - predicted_kwh) / actual_kwh * 100.0

    return result


def _find_power_curve_for_target(
    target_turbine: str, power_curve_items: list[tuple[bytes, str]]
) -> pd.DataFrame | None:
    """Match an uploaded power-curve file to a target turbine by filename (e.g.
    ``T2_power_curve.xlsx`` -> T2), the same filename-pattern idea BayWa's own
    file naming already follows. Returns None if no uploaded power-curve
    filename names this turbine.

    2026-10-24 correctness fix: a whole-farm-down upload (several targets at
    once, exactly BayWa's shape: one file per turbine) previously had every
    target silently use whichever power-curve file happened to be uploaded
    FIRST, regardless of which turbine it actually belonged to -- wrong kWh
    numbers with no error, for every target after the first. Matching by
    filename, with no match meaning "no curve for this target" rather than a
    silent fallback to someone else's curve, closes that gap.
    """

    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(target_turbine)}(?![A-Za-z0-9])", re.IGNORECASE)
    for file_bytes, filename in power_curve_items:
        if pattern.search(filename):
            return load_power_curve(file_bytes, filename)
    return None


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
    power_curve_items: list[tuple[bytes, str]] | None = None,
) -> dict[str, Any]:
    """Run the reconstruction for every auto-detected outage INSTANCE (a turbine
    with two separate, independent gaps in its uploaded history gets two entries
    here -- see ``detect_outage_instances``) -- or, when ``manual_start``/
    ``manual_end`` are given, for every turbine that has no reading at all inside
    that window -- and return per-instance predictions.

    ``power_curve_items``, when given (a whole-farm-down upload with one power-curve
    file per target, matched by filename via ``_find_power_curve_for_target`` --
    2026-10-24), takes priority over ``power_curve_df`` and is resolved separately
    for EACH target rather than applying one curve to every target. ``power_curve_df``
    alone remains for the simple single-target/single-curve case (used directly by
    callers that already know there is exactly one curve for exactly one target)."""

    # 2026-10-24: a manual window needs BOTH bounds to mean anything -- silently
    # falling back to auto-detection when only one was typed (e.g. a user fills in
    # the start field, changes their mind, and clears it, or a form bug drops one
    # field) would run a different reconstruction than what they asked for with no
    # indication anything was ignored.
    if bool(manual_start) != bool(manual_end):
        raise ValueError(
            "Both a manual outage-window start AND end are required together -- "
            f"received only {'a start' if manual_start else 'an end'}. Provide both, "
            "or leave both blank to auto-detect."
        )

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
        instances = [
            {"target_turbine": turbine_id, "window_start": manual_start, "window_end": manual_end}
            for turbine_id in targets
        ]
    else:
        # Every qualifying outage INSTANCE, not one window per turbine -- a turbine
        # with two separate, independent gaps in its uploaded history produces two
        # entries here (2026-10-24). ``targets`` (the distinct turbine ids) is still
        # needed below to exclude every instance's own turbine from being used as
        # someone ELSE's reference, regardless of how many instances it has.
        instances = detect_outage_instances(wind_df)
        if not instances:
            raise ValueError(
                "No NaN wind-speed gap found on any uploaded turbine, and no manual "
                "outage window was given -- nothing to reconstruct"
            )
        targets = sorted({instance["target_turbine"] for instance in instances})

    results = []
    for instance in instances:
        target_turbine = instance["target_turbine"]
        try:
            window_start, window_end = instance["window_start"], instance["window_end"]
            window_auto_detected = not (manual_start and manual_end)

            # pre_window below is this INSTANCE's own window_start -- for a turbine's
            # second outage, that naturally includes the turbine's first outage's own
            # NaN rows further back in time, but _paired_series() already dropna()s
            # unpaired/NaN rows when fitting, so the first gap simply contributes no
            # paired observations there rather than contaminating the fit; reference
            # selection and coverage are both computed against THIS instance's window
            # only (select_reference_turbine's window_start/window_end below, and the
            # expected_rows/domain_check calculations further down, all use these
            # instance-local window_start/window_end, never detect_outage_window()).
            candidates = _candidate_references(wind_df, target_turbine, targets)
            pre_window = wind_df[wind_df["timestamp_utc"] < window_start]
            selection = select_reference_turbine(
                pre_window,
                target_turbine,
                candidates,
                full_df=wind_df,
                window_start=window_start,
                window_end=window_end,
            )
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
            "reference_fallback_note": selection.get("reference_fallback_note"),
            "overlay_series": _overlay_series(
                wind_df, target_turbine, selected_reference, window_start, window_end, reconstruction
            ),
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

        # Resolve THIS target's own power curve -- when several targets are uploaded
        # together (a whole-farm-down upload), each gets matched to its own curve by
        # filename rather than all of them silently sharing whichever curve was
        # uploaded first (2026-10-24 correctness fix; see _find_power_curve_for_target).
        if power_curve_items:
            target_power_curve_df = _find_power_curve_for_target(target_turbine, power_curve_items)
            if target_power_curve_df is None:
                entry["estimated_lost_kwh_unavailable_reason"] = (
                    f"No power curve uploaded for {target_turbine} -- showing wind-speed "
                    "reconstruction only."
                )
        else:
            target_power_curve_df = power_curve_df

        if target_power_curve_df is not None and not reconstruction.empty:
            predicted_power = apply_power_curve(
                target_power_curve_df, reconstruction["wind_speed_ms_reconstructed"].to_numpy()
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

        # One bounded extra reconstruction run on a clean, same-duration window
        # elsewhere in this same upload (2026-10-24, Anna, high priority: a live
        # upload previously had no wind/power error figure at all, unlike the
        # official record). Deliberately a SINGLE window, not a historical loop --
        # see _self_validate()'s docstring for why.
        entry["self_validation"] = _self_validate(
            wind_df, target_turbine, selected_reference, window_start, window_end,
            target_power_curve_df, interval_hours,
        )

        results.append(entry)

    return {"targets": results}
