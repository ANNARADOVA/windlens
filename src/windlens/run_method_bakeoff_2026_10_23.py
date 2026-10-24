"""Overnight method bake-off -- 2026-10-23.

Goal (Anna's brief): find the genuinely best-performing reconstruction +
uncertainty method, proven in a way that cannot repeat the exact selection-bias
trap docs/AUDIT_2026-10-22_uncertainty_calibration.md already caught once: a
calibration method (and, generalized here, ANY method choice) picked because it
scored best on the same blocks used to report its final number.

Fix: every available back-test block (19 Kelmarsh + 28 Hill of Towie = 47) is
split into a DEV subset (method selection -- every comparison in this file) and
a disjoint REPORT subset (the final number, computed exactly once, after the
method is already chosen). The split is locked below, by a performance-blind
rule decided before any block was scored this session, and is never revisited
after seeing results.

See docs/METHOD_BAKEOFF_2026-10-23.md for the full write-up, pre-mortem, and
locked-split block list this constant is checked against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.backtest import run_backtest_event
from windlens.connectors import KelmarshConnector
from windlens.direct_power_uncertainty import (
    calibrate_and_evaluate_direct_power_interval,
    fit_direct_power,
    predict_direct_power,
    reference_operating_state_check,
)
from windlens.dynamic_reference import select_dynamic_references
from windlens.loss_estimate import (
    energy_weighted_wape,
    integrate_energy_kwh,
    signed_aggregate_bias_pct,
)
from windlens.split_conformal import apply_split_conformal_interval, calibrate_split_conformal_interval
from windlens.uncertainty import evaluate_interval

from windlens.run_hill_uncertainty_multiyear import BLOCKS_BY_YEAR as HILL_BLOCKS_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import CANONICAL_BY_YEAR as HILL_CANONICAL_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import REGISTRY_PATH as HILL_REGISTRY_PATH
from windlens.run_hill_uncertainty_multiyear import TARGET_TURBINE as HILL_TARGET
from windlens.run_kelmarsh_extended_backtest import BLOCKS as KELMARSH_BLOCKS
from windlens.run_kelmarsh_extended_backtest import (
    CANDIDATE_REFERENCE_TURBINES as KELMARSH_CANDIDATES,
)
from windlens.run_kelmarsh_extended_backtest import CANONICAL_PATH as KELMARSH_CANONICAL_PATH
from windlens.run_kelmarsh_extended_backtest import METADATA_PATH as KELMARSH_METADATA_PATH
from windlens.run_kelmarsh_extended_backtest import TARGET_TURBINE as KELMARSH_TARGET

OUTPUT_PATH = Path("data/derived/validation/method_bakeoff_2026_10_23.json")


# ---------------------------------------------------------------------------
# LOCKED dev/report split. Criterion (decided before any comparison was run):
# sort each farm's already-existing, already-hard-coded block list
# chronologically; assign by index parity -- even index -> dev (selection),
# odd index -> report (final number). This is a fixed arithmetic rule applied
# to data that existed before tonight, not a performance-based choice, and it
# interleaves dev/report across the whole time range rather than putting
# "early" vs "late" history in different subsets.
# ---------------------------------------------------------------------------


def _split_by_parity(blocks: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    ordered = sorted(blocks, key=lambda b: b[0])
    dev = [b for i, b in enumerate(ordered) if i % 2 == 0]
    report = [b for i, b in enumerate(ordered) if i % 2 == 1]
    return dev, report


def _assert_disjoint_calendar_ranges(
    dev: list[tuple[str, str]], report: list[tuple[str, str]]
) -> None:
    """A real disjointness check on calendar time, not just list membership.

    2026-10-23, red-team review F9: the original parity split put two
    overlapping Kelmarsh block pairs (2016-05-17..05-22 / 2016-05-20..05-25,
    and 2016-05-27..06-01 / 2016-05-29..06-03) on opposite sides -- so
    ~720 hidden-truth rows were scored on both sides of a split documented as
    "locked, disjoint". A count-based assert (the old version of this
    function) cannot catch that; this checks actual date-range overlap.
    """

    for dev_start, dev_end in dev:
        for report_start, report_end in report:
            if dev_start < report_end and report_start < dev_end:
                raise AssertionError(
                    f"dev block [{dev_start}, {dev_end}) overlaps report block "
                    f"[{report_start}, {report_end}) -- split is not disjoint"
                )


# 2026-10-23, red-team review F9 fix: the parity split alone put two overlapping
# Kelmarsh block pairs on opposite sides of the "locked, disjoint" split (see
# _assert_disjoint_calendar_ranges's docstring). Rather than reassign the
# overlapping report-side block to dev (which would move it across the already-
# published dev/report boundary for every OTHER block too, since parity depends on
# sort order), the two overlapping report blocks are excluded from the split
# entirely -- the simplest fix that preserves every other block's dev/report side
# unchanged. Kelmarsh report narrows from 9 to 7 blocks; dev is untouched at 10.
_KELMARSH_DEV_RAW, _KELMARSH_REPORT_RAW = _split_by_parity(KELMARSH_BLOCKS)
_KELMARSH_OVERLAPPING_REPORT_BLOCKS = {
    ("2016-05-20T00:00:00Z", "2016-05-25T00:00:00Z"),
    ("2016-05-29T00:00:00Z", "2016-06-03T00:00:00Z"),
}
KELMARSH_DEV = _KELMARSH_DEV_RAW
KELMARSH_REPORT = [b for b in _KELMARSH_REPORT_RAW if b not in _KELMARSH_OVERLAPPING_REPORT_BLOCKS]

_HILL_ALL_BLOCKS = [block for blocks in HILL_BLOCKS_BY_YEAR.values() for block in blocks]
HILL_DEV, HILL_REPORT = _split_by_parity(_HILL_ALL_BLOCKS)

assert len(KELMARSH_DEV) == 10 and len(KELMARSH_REPORT) == 7, "Kelmarsh split drifted from the F9 fix"
assert len(HILL_DEV) == 14 and len(HILL_REPORT) == 14, "Hill of Towie split drifted from the locked doc"
_assert_disjoint_calendar_ranges(KELMARSH_DEV, KELMARSH_REPORT)
_assert_disjoint_calendar_ranges(HILL_DEV, HILL_REPORT)


def _hill_year_for_block(block_start: str) -> str:
    return block_start[:4]


# ---------------------------------------------------------------------------
# Step 2a: point-estimate comparison (wind-first baseline vs wind-first
# ensemble vs direct-power single-reference), scored on whichever block list
# is passed in. Called with DEV blocks only for method selection.
# ---------------------------------------------------------------------------


def _direct_power_block(
    canonical: pd.DataFrame,
    target: str,
    candidates: list[str],
    metadata: pd.DataFrame,
    rated_power_kw: float,
    block_start: str,
    block_end: str,
) -> dict[str, Any]:
    pre_outage = canonical[canonical["timestamp_utc"] < block_start]
    selection = select_dynamic_references(
        pre_outage, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20
    )
    if selection["status"] == "abstain":
        raise ValueError(f"Dynamic reference selection abstained: {selection['reason']}")
    reference = selection["selected"]

    hidden_truth = canonical[
        (canonical["turbine_id"] == target)
        & (canonical["timestamp_utc"] >= block_start)
        & (canonical["timestamp_utc"] < block_end)
    ][["timestamp_utc", "active_power_kw"]]
    if hidden_truth.empty:
        raise ValueError(f"No {target} rows in [{block_start}, {block_end})")

    masked = canonical[
        ~(
            (canonical["turbine_id"] == target)
            & (canonical["timestamp_utc"] >= block_start)
            & (canonical["timestamp_utc"] < block_end)
        )
    ]

    # 2026-10-22 red-team review (F8): abstain rather than silently predict ~0 kW
    # when the reference looks stopped-but-reporting during the event window.
    operating_state = reference_operating_state_check(masked, reference, block_start, block_end, rated_power_kw)
    if not operating_state["passed"]:
        raise ValueError(
            f"reference {reference} looks stopped for {operating_state['stopped_fraction']:.0%} "
            "of the event window"
        )

    fit = fit_direct_power(masked, target, reference, block_start, rated_power_kw)
    prediction = predict_direct_power(masked, fit, reference, block_start, block_end)
    joined = prediction.merge(hidden_truth, on="timestamp_utc", how="inner")
    expected_kwh = integrate_energy_kwh(joined["predicted_power_kw"].to_numpy())
    actual_kwh = integrate_energy_kwh(joined["active_power_kw"].to_numpy())

    current_uncertainty = calibrate_and_evaluate_direct_power_interval(
        masked, target, reference, block_start, block_end, rated_power_kw, hidden_truth
    )

    return {
        "block_start": block_start,
        "block_end": block_end,
        "reference": reference,
        "expected_kwh": expected_kwh,
        "actual_kwh": actual_kwh,
        "current_uncertainty": current_uncertainty,
    }


def run_point_estimate_comparison(block_set_name: str) -> dict[str, Any]:
    """Score wind-first baseline, wind-first ensemble, and direct-power
    single-reference on the named block subset ("dev" or "report")."""

    kelmarsh_blocks = KELMARSH_DEV if block_set_name == "dev" else KELMARSH_REPORT
    hill_blocks = HILL_DEV if block_set_name == "dev" else HILL_REPORT

    # Kelmarsh
    kelmarsh_dataset = KelmarshConnector(KELMARSH_CANONICAL_PATH, KELMARSH_METADATA_PATH).load()
    kelmarsh_canonical = kelmarsh_dataset.data
    kelmarsh_metadata = kelmarsh_dataset.registry.to_frame()
    kelmarsh_rated_kw = float(
        kelmarsh_metadata.loc[kelmarsh_metadata.turbine_id == KELMARSH_TARGET, "rated_power_kw"].iloc[0]
    )

    kelmarsh_wind_events = []
    kelmarsh_power_blocks = []
    kelmarsh_skipped = []
    for start, end in kelmarsh_blocks:
        try:
            kelmarsh_wind_events.append(
                run_backtest_event(
                    kelmarsh_canonical, KELMARSH_TARGET, KELMARSH_CANDIDATES, start, end, metadata_df=kelmarsh_metadata
                )
            )
        except ValueError as exc:
            kelmarsh_skipped.append({"farm": "Kelmarsh", "block_start": start, "reason": f"wind: {exc}"})
            continue
        try:
            kelmarsh_power_blocks.append(
                _direct_power_block(
                    kelmarsh_canonical, KELMARSH_TARGET, KELMARSH_CANDIDATES, kelmarsh_metadata, kelmarsh_rated_kw, start, end
                )
            )
        except ValueError as exc:
            kelmarsh_skipped.append({"farm": "Kelmarsh", "block_start": start, "reason": f"direct_power: {exc}"})

    # Hill of Towie
    hill_registry = pd.read_csv(HILL_REGISTRY_PATH)
    hill_wind_events = []
    hill_power_blocks = []
    hill_skipped = []
    for start, end in hill_blocks:
        year = _hill_year_for_block(start)
        canonical = pd.read_csv(HILL_CANONICAL_BY_YEAR[year])
        canonical["timestamp_utc"] = pd.to_datetime(canonical["timestamp_utc"], utc=True)
        candidates = sorted(set(canonical["turbine_id"]) - {HILL_TARGET})
        rated_kw = float(hill_registry.loc[hill_registry.turbine_id == HILL_TARGET, "rated_power_kw"].iloc[0])
        try:
            hill_wind_events.append(
                run_backtest_event(canonical, HILL_TARGET, candidates, start, end, ensemble_size=3, metadata_df=hill_registry)
            )
        except ValueError as exc:
            hill_skipped.append({"farm": "Hill of Towie", "block_start": start, "reason": f"wind: {exc}"})
            continue
        try:
            hill_power_blocks.append(
                _direct_power_block(canonical, HILL_TARGET, candidates, hill_registry, rated_kw, start, end)
            )
        except ValueError as exc:
            hill_skipped.append({"farm": "Hill of Towie", "block_start": start, "reason": f"direct_power: {exc}"})

    def _wind_wape(events: list[dict], key: str) -> dict[str, float]:
        estimated = [e[key]["loss"]["estimated_lost_kwh"] for e in events]
        actual = [e[key]["loss"]["actual_lost_kwh"] for e in events]
        return {
            "wape_pct": energy_weighted_wape(estimated, actual),
            "signed_bias_pct": signed_aggregate_bias_pct(estimated, actual),
            "n_blocks": len(events),
        }

    def _power_wape(blocks: list[dict]) -> dict[str, float]:
        estimated = [b["expected_kwh"] for b in blocks]
        actual = [b["actual_kwh"] for b in blocks]
        return {
            "wape_pct": energy_weighted_wape(estimated, actual),
            "signed_bias_pct": signed_aggregate_bias_pct(estimated, actual),
            "n_blocks": len(blocks),
        }

    return {
        "block_set": block_set_name,
        "kelmarsh": {
            "n_blocks_attempted": len(kelmarsh_blocks),
            "wind_first_baseline": _wind_wape(kelmarsh_wind_events, "baseline"),
            "wind_first_ensemble": _wind_wape(kelmarsh_wind_events, "ensemble"),
            "direct_power": _power_wape(kelmarsh_power_blocks),
        },
        "hill_of_towie": {
            "n_blocks_attempted": len(hill_blocks),
            "wind_first_baseline": _wind_wape(hill_wind_events, "baseline"),
            "wind_first_ensemble": _wind_wape(hill_wind_events, "ensemble"),
            "direct_power": _power_wape(hill_power_blocks),
        },
        "skipped": kelmarsh_skipped + hill_skipped,
        "_raw": {
            "kelmarsh_wind_events": kelmarsh_wind_events,
            "kelmarsh_power_blocks": kelmarsh_power_blocks,
            "hill_wind_events": hill_wind_events,
            "hill_power_blocks": hill_power_blocks,
        },
    }


def wilson_score_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95%-default Wilson score confidence interval on a binomial proportion.

    Pure-Python/NumPy (no scipy), matching the method already used in
    docs/DECISION_LOG.md's 2026-10-22 sample-expansion entry for the same
    reason (no new dependency).
    """

    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1.0 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = (z / denom) * ((phat * (1 - phat) / n + z**2 / (4 * n**2)) ** 0.5)
    return (max(0.0, center - margin), min(1.0, center + margin))


# ---------------------------------------------------------------------------
# Step 2b: uncertainty-calibration comparison, direct-power domain (the
# winning point-estimate method per the dev-subset comparison above). Current
# (shipped, near-training-data) calibration vs. two split-conformal variants
# differing only in how much of the pre-event history is held back,
# disjointly, as the calibration slice (30% vs 50%). The variant choice
# itself happens only on dev blocks -- this is the "cheap selection-bias fix"
# from docs/RESEARCH_2026-10-22_due_diligence.md applied to picking between
# split-conformal configurations, not just to picking calibration families.
# ---------------------------------------------------------------------------


def _direct_power_split_conformal_block(
    canonical: pd.DataFrame,
    target: str,
    candidates: list[str],
    metadata: pd.DataFrame,
    rated_power_kw: float,
    block_start: str,
    block_end: str,
    calib_fraction: float,
    coverage: float = 0.90,
) -> dict[str, Any]:
    pre_outage = canonical[canonical["timestamp_utc"] < block_start]
    selection = select_dynamic_references(
        pre_outage, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20
    )
    if selection["status"] == "abstain":
        return {"status": "unavailable", "reason": f"reference selection abstained: {selection['reason']}"}
    reference = selection["selected"]

    hidden_truth = canonical[
        (canonical["turbine_id"] == target)
        & (canonical["timestamp_utc"] >= block_start)
        & (canonical["timestamp_utc"] < block_end)
    ][["timestamp_utc", "active_power_kw"]]
    if hidden_truth.empty:
        return {"status": "unavailable", "reason": "no target rows in block"}

    masked = canonical[
        ~(
            (canonical["turbine_id"] == target)
            & (canonical["timestamp_utc"] >= block_start)
            & (canonical["timestamp_utc"] < block_end)
        )
    ]

    pre_target = (
        masked[(masked["turbine_id"] == target) & (masked["timestamp_utc"] < block_start)][
            ["timestamp_utc", "active_power_kw"]
        ]
        .dropna()
        .sort_values("timestamp_utc")
    )
    if len(pre_target) < 50:
        return {"status": "unavailable", "reason": "insufficient pre-event target history for a disjoint split"}

    fit_cutoff_idx = int(len(pre_target) * (1 - calib_fraction))
    if fit_cutoff_idx < 2 or fit_cutoff_idx >= len(pre_target):
        return {"status": "unavailable", "reason": "calib_fraction leaves no room for fit or calibration window"}
    fit_cutoff = pre_target.iloc[fit_cutoff_idx]["timestamp_utc"]

    try:
        fit = fit_direct_power(masked, target, reference, fit_cutoff, rated_power_kw)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    try:
        calibration_prediction = predict_direct_power(masked, fit, reference, fit_cutoff, block_start)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    calibration_joined = calibration_prediction.merge(
        pre_target.rename(columns={"active_power_kw": "actual_power_kw"}), on="timestamp_utc", how="inner"
    )
    residuals = (calibration_joined["predicted_power_kw"] - calibration_joined["actual_power_kw"]).to_numpy(dtype=float)
    if len(residuals) < 20:
        return {
            "status": "unavailable",
            "reason": f"need at least 20 disjoint calibration observations; got {len(residuals)}",
        }

    conformal = calibrate_split_conformal_interval(residuals, coverage=coverage, min_observations=20)

    try:
        event_prediction = predict_direct_power(masked, fit, reference, block_start, block_end)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    event_joined = event_prediction.merge(
        hidden_truth[["timestamp_utc", "active_power_kw"]], on="timestamp_utc", how="inner"
    )
    if event_joined.empty:
        return {"status": "unavailable", "reason": "no overlapping event timestamps"}

    lower, upper = apply_split_conformal_interval(
        event_joined["predicted_power_kw"].to_numpy(dtype=float), conformal
    )
    evaluation = evaluate_interval(
        actual=event_joined["active_power_kw"].to_numpy(dtype=float), lower=lower, upper=upper
    )
    return {
        "status": "available",
        "calibration": conformal,
        "event_evaluation": evaluation,
        "reference": reference,
        "calib_fraction": calib_fraction,
        "fit_window_observations": fit_cutoff_idx,
        "calibration_window_observations": len(pre_target) - fit_cutoff_idx,
    }


def _aggregate_uncertainty(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = [r for r in rows if r["status"] == "available"]
    n_total = len(rows)
    n_available = len(available)
    meeting = sum(1 for r in available if r["event_evaluation"]["coverage_pct"] >= 90.0)
    mean_coverage = (
        sum(r["event_evaluation"]["coverage_pct"] for r in available) / n_available if n_available else float("nan")
    )
    mean_width = (
        sum(r["event_evaluation"]["mean_width_ms"] for r in available) / n_available if n_available else float("nan")
    )
    ci_low, ci_high = wilson_score_interval(meeting, n_available) if n_available else (0.0, 0.0)
    return {
        "n_blocks_total": n_total,
        "n_blocks_available": n_available,
        "n_blocks_abstained": n_total - n_available,
        "blocks_meeting_90pct_target": meeting,
        "pct_of_blocks_meeting_target": (meeting / n_available * 100) if n_available else float("nan"),
        "wilson_95ci_pct_meeting_target": [round(ci_low * 100, 1), round(ci_high * 100, 1)],
        "mean_coverage_pct": mean_coverage,
        "mean_interval_width_kw": mean_width,
    }


def run_uncertainty_comparison(block_set_name: str, calib_fractions: tuple[float, ...] = (0.3, 0.5)) -> dict[str, Any]:
    """Score current (shipped) vs. each split-conformal variant, direct-power
    domain, on the named block subset."""

    kelmarsh_blocks = KELMARSH_DEV if block_set_name == "dev" else KELMARSH_REPORT
    hill_blocks = HILL_DEV if block_set_name == "dev" else HILL_REPORT

    kelmarsh_dataset = KelmarshConnector(KELMARSH_CANONICAL_PATH, KELMARSH_METADATA_PATH).load()
    kelmarsh_canonical = kelmarsh_dataset.data
    kelmarsh_metadata = kelmarsh_dataset.registry.to_frame()
    kelmarsh_rated_kw = float(
        kelmarsh_metadata.loc[kelmarsh_metadata.turbine_id == KELMARSH_TARGET, "rated_power_kw"].iloc[0]
    )
    hill_registry = pd.read_csv(HILL_REGISTRY_PATH)

    methods = ["current"] + [f"split_conformal_{int(f * 100)}pct" for f in calib_fractions]
    rows_by_method: dict[str, list[dict[str, Any]]] = {m: [] for m in methods}

    def _score_kelmarsh_block(start: str, end: str) -> None:
        pre_outage = kelmarsh_canonical[kelmarsh_canonical["timestamp_utc"] < start]
        selection = select_dynamic_references(
            pre_outage, KELMARSH_TARGET, KELMARSH_CANDIDATES, kelmarsh_metadata,
            lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20,
        )
        if selection["status"] == "abstain":
            for m in methods:
                rows_by_method[m].append({"status": "unavailable", "reason": selection["reason"]})
            return
        reference = selection["selected"]
        hidden_truth = kelmarsh_canonical[
            (kelmarsh_canonical["turbine_id"] == KELMARSH_TARGET)
            & (kelmarsh_canonical["timestamp_utc"] >= start)
            & (kelmarsh_canonical["timestamp_utc"] < end)
        ][["timestamp_utc", "active_power_kw"]]
        masked = kelmarsh_canonical[
            ~(
                (kelmarsh_canonical["turbine_id"] == KELMARSH_TARGET)
                & (kelmarsh_canonical["timestamp_utc"] >= start)
                & (kelmarsh_canonical["timestamp_utc"] < end)
            )
        ]
        rows_by_method["current"].append(
            calibrate_and_evaluate_direct_power_interval(masked, KELMARSH_TARGET, reference, start, end, kelmarsh_rated_kw, hidden_truth)
        )
        for frac in calib_fractions:
            rows_by_method[f"split_conformal_{int(frac * 100)}pct"].append(
                _direct_power_split_conformal_block(
                    kelmarsh_canonical, KELMARSH_TARGET, KELMARSH_CANDIDATES, kelmarsh_metadata, kelmarsh_rated_kw, start, end, frac
                )
            )

    def _score_hill_block(start: str, end: str) -> None:
        year = _hill_year_for_block(start)
        canonical = pd.read_csv(HILL_CANONICAL_BY_YEAR[year])
        canonical["timestamp_utc"] = pd.to_datetime(canonical["timestamp_utc"], utc=True)
        candidates = sorted(set(canonical["turbine_id"]) - {HILL_TARGET})
        rated_kw = float(hill_registry.loc[hill_registry.turbine_id == HILL_TARGET, "rated_power_kw"].iloc[0])
        pre_outage = canonical[canonical["timestamp_utc"] < start]
        selection = select_dynamic_references(
            pre_outage, HILL_TARGET, candidates, hill_registry, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20
        )
        if selection["status"] == "abstain":
            for m in methods:
                rows_by_method[m].append({"status": "unavailable", "reason": selection["reason"]})
            return
        reference = selection["selected"]
        hidden_truth = canonical[
            (canonical["turbine_id"] == HILL_TARGET) & (canonical["timestamp_utc"] >= start) & (canonical["timestamp_utc"] < end)
        ][["timestamp_utc", "active_power_kw"]]
        masked = canonical[
            ~((canonical["turbine_id"] == HILL_TARGET) & (canonical["timestamp_utc"] >= start) & (canonical["timestamp_utc"] < end))
        ]
        rows_by_method["current"].append(
            calibrate_and_evaluate_direct_power_interval(masked, HILL_TARGET, reference, start, end, rated_kw, hidden_truth)
        )
        for frac in calib_fractions:
            rows_by_method[f"split_conformal_{int(frac * 100)}pct"].append(
                _direct_power_split_conformal_block(
                    canonical, HILL_TARGET, candidates, hill_registry, rated_kw, start, end, frac
                )
            )

    for start, end in kelmarsh_blocks:
        _score_kelmarsh_block(start, end)
    kelmarsh_summary = {m: _aggregate_uncertainty(rows_by_method[m][: len(kelmarsh_blocks)]) for m in methods}

    rows_by_method_hill: dict[str, list[dict[str, Any]]] = {m: [] for m in methods}
    for start, end in hill_blocks:
        before = {m: len(rows_by_method[m]) for m in methods}
        _score_hill_block(start, end)
        for m in methods:
            rows_by_method_hill[m].append(rows_by_method[m][before[m]])
    hill_summary = {m: _aggregate_uncertainty(rows_by_method_hill[m]) for m in methods}

    return {"block_set": block_set_name, "kelmarsh": kelmarsh_summary, "hill_of_towie": hill_summary}


def main() -> None:
    dev_result = run_point_estimate_comparison("dev")
    for farm_key, farm_name in (("kelmarsh", "Kelmarsh"), ("hill_of_towie", "Hill of Towie")):
        farm = dev_result[farm_key]
        print(f"=== {farm_name} (dev, n={farm['n_blocks_attempted']}) ===")
        for method in ("wind_first_baseline", "wind_first_ensemble", "direct_power"):
            m = farm[method]
            print(f"  {method}: WAPE {m['wape_pct']:.2f}%, signed bias {m['signed_bias_pct']:+.2f}%, n={m['n_blocks']}")
    if dev_result["skipped"]:
        print("Skipped blocks:", dev_result["skipped"])

    print()
    uncertainty_dev = run_uncertainty_comparison("dev")
    for farm_key, farm_name in (("kelmarsh", "Kelmarsh"), ("hill_of_towie", "Hill of Towie")):
        print(f"=== {farm_name} uncertainty (dev) ===")
        for method, summary in uncertainty_dev[farm_key].items():
            print(
                f"  {method}: {summary['blocks_meeting_90pct_target']}/{summary['n_blocks_available']} meet target "
                f"({summary['pct_of_blocks_meeting_target']:.1f}%, 95% CI {summary['wilson_95ci_pct_meeting_target']}), "
                f"mean coverage {summary['mean_coverage_pct']:.1f}%, mean width {summary['mean_interval_width_kw']:.1f} kW, "
                f"abstained {summary['n_blocks_abstained']}/{summary['n_blocks_total']}"
            )


if __name__ == "__main__":
    main()
