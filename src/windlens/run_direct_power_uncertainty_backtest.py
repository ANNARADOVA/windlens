"""Calibrate and evaluate an uncertainty interval for the direct power-to-power
regression method, across the same expanded block sets used for the wind-speed
uncertainty expansion (19 Kelmarsh blocks, 28 Hill of Towie blocks -- see
docs/DECISION_LOG.md, 2026-10-22 entries).

Per block, the reference turbine is the SAME baseline (single best) reference the
existing wind-speed pipeline already selects (via windlens.dynamic_reference's
behaviour+geo scoring, run here identically to backtest.run_backtest_event's own
internal selection) -- this keeps the direct-power and wind-first comparisons
apples-to-apples per block, not a different reference-selection process.

Does NOT change production, does NOT touch workspace/: this is additional
back-test evidence only, per the explicit instruction not to promote direct power
or touch the demo this session.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from windlens.checksums import file_md5
from windlens.connectors import KelmarshConnector
from windlens.direct_power_uncertainty import calibrate_and_evaluate_direct_power_interval
from windlens.dynamic_reference import select_dynamic_references
from windlens.loss_estimate import energy_weighted_wape, signed_aggregate_bias_pct
from windlens.run_hill_uncertainty_multiyear import BLOCKS_BY_YEAR as HILL_BLOCKS_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import CANONICAL_BY_YEAR as HILL_CANONICAL_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import REGISTRY_PATH as HILL_REGISTRY_PATH
from windlens.run_hill_uncertainty_multiyear import TARGET_TURBINE as HILL_TARGET
from windlens.run_kelmarsh_extended_backtest import BLOCKS as KELMARSH_BLOCKS
from windlens.run_kelmarsh_extended_backtest import CANDIDATE_REFERENCE_TURBINES as KELMARSH_CANDIDATES
from windlens.run_kelmarsh_extended_backtest import CANONICAL_PATH as KELMARSH_CANONICAL_PATH
from windlens.run_kelmarsh_extended_backtest import METADATA_PATH as KELMARSH_METADATA_PATH
from windlens.run_kelmarsh_extended_backtest import TARGET_TURBINE as KELMARSH_TARGET

OUTPUT_PATH = Path("data/derived/validation/direct_power_uncertainty_backtest.json")


def _select_baseline_reference(pre_outage: pd.DataFrame, target: str, candidates: list[str], metadata: pd.DataFrame) -> str:
    selection = select_dynamic_references(
        pre_outage, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20
    )
    if selection["status"] == "abstain":
        raise ValueError(f"Dynamic reference selection abstained: {selection['reason']}")
    return selection["selected"]


def _run_block(
    canonical: pd.DataFrame,
    target: str,
    candidates: list[str],
    metadata: pd.DataFrame,
    rated_power_kw: float,
    block_start: str,
    block_end: str,
) -> dict:
    pre_outage = canonical[canonical["timestamp_utc"] < block_start]
    reference = _select_baseline_reference(pre_outage, target, candidates, metadata)

    hidden_truth = canonical[
        (canonical["turbine_id"] == target)
        & (canonical["timestamp_utc"] >= block_start)
        & (canonical["timestamp_utc"] < block_end)
    ][["timestamp_utc", "active_power_kw"]]
    if hidden_truth.empty:
        raise ValueError(f"No {target} rows in [{block_start}, {block_end})")

    masked = canonical[
        ~((canonical["turbine_id"] == target) & (canonical["timestamp_utc"] >= block_start) & (canonical["timestamp_utc"] < block_end))
    ]

    uncertainty = calibrate_and_evaluate_direct_power_interval(
        masked, target, reference, block_start, block_end, rated_power_kw, hidden_truth
    )

    from windlens.direct_power_uncertainty import fit_direct_power, predict_direct_power

    fit = fit_direct_power(masked, target, reference, block_start, rated_power_kw)
    prediction = predict_direct_power(masked, fit, reference, block_start, block_end)
    joined = prediction.merge(hidden_truth, on="timestamp_utc", how="inner")
    from windlens.loss_estimate import integrate_energy_kwh

    expected_kwh = integrate_energy_kwh(joined["predicted_power_kw"].to_numpy())
    actual_kwh = integrate_energy_kwh(joined["active_power_kw"].to_numpy())

    return {
        "block_start": block_start,
        "block_end": block_end,
        "reference": reference,
        "expected_kwh": expected_kwh,
        "actual_kwh": actual_kwh,
        "uncertainty": uncertainty,
    }


def _aggregate(blocks: list[dict]) -> dict:
    estimated = [b["expected_kwh"] for b in blocks]
    actual = [b["actual_kwh"] for b in blocks]
    coverage_rows = [
        {
            "block_start": b["block_start"],
            "coverage_pct": b["uncertainty"].get("event_evaluation", {}).get("coverage_pct"),
            "status": b["uncertainty"]["status"],
        }
        for b in blocks
    ]
    available = [r for r in coverage_rows if r["status"] == "available"]
    meeting = sum(1 for r in available if (r["coverage_pct"] or 0) >= 90.0)
    mean_coverage = sum(r["coverage_pct"] or 0 for r in available) / max(len(available), 1)
    return {
        "energy_weighted_wape_pct": energy_weighted_wape(estimated, actual),
        "signed_aggregate_bias_pct": signed_aggregate_bias_pct(estimated, actual),
        "blocks_meeting_90pct_target": meeting,
        "total_available_blocks": len(available),
        "total_blocks": len(blocks),
        "pct_of_blocks_meeting_target": meeting / max(len(available), 1) * 100,
        "mean_coverage_pct": mean_coverage,
        "per_block": coverage_rows,
    }


def run_kelmarsh() -> dict:
    dataset = KelmarshConnector(KELMARSH_CANONICAL_PATH, KELMARSH_METADATA_PATH).load()
    canonical = dataset.data
    metadata = dataset.registry.to_frame()
    rated_power_kw = float(metadata.loc[metadata.turbine_id == KELMARSH_TARGET, "rated_power_kw"].iloc[0])

    blocks = []
    skipped = []
    for block_start, block_end in KELMARSH_BLOCKS:
        try:
            blocks.append(
                _run_block(canonical, KELMARSH_TARGET, KELMARSH_CANDIDATES, metadata, rated_power_kw, block_start, block_end)
            )
        except ValueError as exc:
            skipped.append({"block_start": block_start, "block_end": block_end, "reason": str(exc)})
    return {"farm_id": "Kelmarsh", "blocks": blocks, "skipped": skipped, "aggregate": _aggregate(blocks)}


def run_hill_of_towie() -> dict:
    registry = pd.read_csv(HILL_REGISTRY_PATH)
    blocks = []
    skipped = []
    for year, canonical_path in HILL_CANONICAL_BY_YEAR.items():
        canonical = pd.read_csv(canonical_path)
        canonical["timestamp_utc"] = pd.to_datetime(canonical["timestamp_utc"], utc=True)
        candidates = sorted(set(canonical["turbine_id"]) - {HILL_TARGET})
        rated_power_kw = float(registry.loc[registry.turbine_id == HILL_TARGET, "rated_power_kw"].iloc[0])
        for block_start, block_end in HILL_BLOCKS_BY_YEAR[year]:
            try:
                block = _run_block(canonical, HILL_TARGET, candidates, registry, rated_power_kw, block_start, block_end)
                block["year"] = year
                blocks.append(block)
            except ValueError as exc:
                skipped.append({"year": year, "block_start": block_start, "block_end": block_end, "reason": str(exc)})
    return {"farm_id": "Hill of Towie", "blocks": blocks, "skipped": skipped, "aggregate": _aggregate(blocks)}


def main() -> None:
    kelmarsh = run_kelmarsh()
    hill = run_hill_of_towie()

    artifact = {
        "artifact_version": "direct-power-uncertainty-backtest.v1",
        "method": "direct power-to-power regression (reference active_power_kw -> target active_power_kw)",
        "calibration_methodology": (
            "Same fit-once/score-over-full-pre-event-history pattern as the wind-speed "
            "interval fix (2026-10-21), applied to power-domain residuals. Same reference "
            "turbine per block as the existing wind-speed baseline (behaviour+geo dynamic "
            "selection), so the two methods are compared like-for-like per block."
        ),
        "kelmarsh": kelmarsh,
        "hill_of_towie": hill,
        "honesty_note": (
            "This is additional evidence only -- direct power is not promoted to production "
            "and workspace/ is untouched this session, per explicit instruction. Carries the "
            "same unresolved methodology caveat as the wind-speed interval: calibration "
            "residuals are scored on near-training data, not a fully independent holdout "
            "(see docs/AUDIT_2026-10-22_uncertainty_calibration.md)."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    for name, result in (("Kelmarsh", kelmarsh), ("Hill of Towie", hill)):
        agg = result["aggregate"]
        print(f"=== {name} ===")
        print(f"Scored {len(result['blocks'])} blocks ({len(result['skipped'])} skipped)")
        print(f"Direct-power WAPE: {agg['energy_weighted_wape_pct']:.1f}%, bias {agg['signed_aggregate_bias_pct']:+.1f}%")
        print(
            f"Uncertainty: {agg['blocks_meeting_90pct_target']}/{agg['total_available_blocks']} blocks "
            f"meet 90% coverage ({agg['pct_of_blocks_meeting_target']:.1f}%), mean coverage {agg['mean_coverage_pct']:.1f}%"
        )
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
