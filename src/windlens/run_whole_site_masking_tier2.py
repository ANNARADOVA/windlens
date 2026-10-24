"""Tier 2 of the "running the entire matrix" request (2026-10-23, Anna's request).

Confirms what the whole-site masking stress test (Kelmarsh south/north halves,
`run_kelmarsh_whole_site_masking_backtest.py`) already covers, then fills the
real gaps: direct power and the lazy (equal-weighted) baseline, run over the
exact same masked-half setup, for the same paired comparability this project
has used all night.

**Confirmed by inspecting ``kelmarsh_whole_site_masking_backtest.json``
directly (not assumed): wind-first single-reference (baseline) AND ensemble
are BOTH already computed** -- ``run_backtest_event``'s ``aggregate_backtest``
always reports both, and the existing whole-site artifact's
``scenarios.*.whole_site.aggregate`` already has `baseline` and `ensemble`
keys with real numbers. So there is no wind-first gap here; the real gaps
are direct power and the lazy baseline, which this script adds.

Design mirrors the existing script exactly: SOUTH is masked with only NORTH
as candidate references (and vice versa), over the same ``BLOCKS`` from
``run_kelmarsh_extended_backtest``, with the same same-farm-paired comparison
(same targets/blocks, every other Kelmarsh turbine available) reported
alongside for direct comparability -- same discipline as the existing
whole-site script and the Tier 1 cross-farm script.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.connectors import KelmarshConnector
from windlens.direct_power_uncertainty import fit_direct_power, predict_direct_power
from windlens.dynamic_reference import select_dynamic_references
from windlens.lazy_baseline import lazy_baseline_estimate_kwh
from windlens.loss_estimate import energy_weighted_wape, integrate_energy_kwh, signed_aggregate_bias_pct
from windlens.run_kelmarsh_extended_backtest import BLOCKS, CANONICAL_PATH, METADATA_PATH
from windlens.run_kelmarsh_whole_site_masking_backtest import NORTH, SOUTH, OUTPUT_PATH as WHOLE_SITE_PATH

OUTPUT_PATH = Path("data/derived/validation/kelmarsh_whole_site_masking_tier2_direct_power_and_lazy.json")
SCENARIOS = {"south_masked_north_reference": (SOUTH, NORTH), "north_masked_south_reference": (NORTH, SOUTH)}


def _select_baseline_reference(pre_outage: pd.DataFrame, target: str, candidates: list[str], metadata: pd.DataFrame) -> str:
    selection = select_dynamic_references(
        pre_outage, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20
    )
    if selection["status"] == "abstain":
        raise ValueError(f"Dynamic reference selection abstained: {selection['reason']}")
    return selection["selected"]


def _direct_power_events(
    df: pd.DataFrame, metadata: pd.DataFrame, rated_power: dict[str, float],
    targets: list[str], candidates: list[str], blocks,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events, skipped = [], []
    for target in targets:
        for start, end in blocks:
            pre_outage = df[df["timestamp_utc"] < start]
            try:
                reference = _select_baseline_reference(pre_outage, target, candidates, metadata)
                hidden_truth = df[
                    (df["turbine_id"] == target) & (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)
                ][["timestamp_utc", "active_power_kw"]]
                if hidden_truth.empty:
                    raise ValueError("No hidden-truth rows in window")
                masked = df[~((df["turbine_id"] == target) & (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end))]
                fit = fit_direct_power(masked, target, reference, start, rated_power[target])
                prediction = predict_direct_power(masked, fit, reference, start, end)
                joined = prediction.merge(hidden_truth, on="timestamp_utc", how="inner")
                if joined.empty:
                    raise ValueError("No overlapping timestamps between prediction and hidden truth")
                estimated_kwh = integrate_energy_kwh(joined["predicted_power_kw"].to_numpy())
                actual_kwh = integrate_energy_kwh(joined["active_power_kw"].to_numpy())
            except ValueError as exc:
                skipped.append({"target": target, "block_start": start, "reason": str(exc)})
                continue
            events.append(
                {"target": target, "block_start": start, "reference": reference,
                 "estimated_lost_kwh": estimated_kwh, "actual_lost_kwh": actual_kwh}
            )
    return events, skipped


def _lazy_events(
    df: pd.DataFrame, rated_power: dict[str, float], targets: list[str], available_turbines: list[str], blocks,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events, skipped = [], []
    for target in targets:
        for start, end in blocks:
            hidden_truth = df[
                (df["turbine_id"] == target) & (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)
            ]
            if hidden_truth.empty:
                skipped.append({"target": target, "block_start": start, "reason": "no hidden truth rows"})
                continue
            masked = df[~((df["turbine_id"] == target) & (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end))]
            try:
                lazy = lazy_baseline_estimate_kwh(masked, target, available_turbines, start, end, rated_power)
            except ValueError as exc:
                skipped.append({"target": target, "block_start": start, "reason": str(exc)})
                continue
            actual_kwh = integrate_energy_kwh(hidden_truth["active_power_kw"].to_numpy())
            events.append(
                {"target": target, "block_start": start, "estimated_lost_kwh": lazy["estimated_lost_kwh"],
                 "actual_lost_kwh": actual_kwh, "turbines_used": lazy["turbines_used"]}
            )
    return events, skipped


def _wape_bias(events: list[dict[str, Any]]) -> tuple[float, float]:
    estimated = [e["estimated_lost_kwh"] for e in events]
    actual = [e["actual_lost_kwh"] for e in events]
    return energy_weighted_wape(estimated, actual), signed_aggregate_bias_pct(estimated, actual)


def main() -> None:
    dataset = KelmarshConnector(CANONICAL_PATH, METADATA_PATH).load()
    df, metadata = dataset.data, dataset.registry.to_frame()
    rated_power: dict[str, float] = dict(zip(metadata["turbine_id"], metadata["rated_power_kw"]))
    all_turbines = sorted(set(df["turbine_id"]))

    known_whole_site = json.loads(WHOLE_SITE_PATH.read_text(encoding="utf-8"))["scenarios"]

    result: dict[str, Any] = {}
    for name, (masked, surviving) in SCENARIOS.items():
        dp_whole, dp_whole_skipped = _direct_power_events(df, metadata, rated_power, masked, surviving, BLOCKS)
        dp_paired, _ = _direct_power_events(
            df, metadata, rated_power, masked, [t for t in all_turbines if t not in masked], BLOCKS
        )
        lazy_whole, lazy_whole_skipped = _lazy_events(df, rated_power, masked, surviving, BLOCKS)
        lazy_paired, _ = _lazy_events(df, rated_power, masked, [t for t in all_turbines if t not in masked], BLOCKS)

        dp_whole_wape, dp_whole_bias = _wape_bias(dp_whole)
        dp_paired_wape, dp_paired_bias = _wape_bias(dp_paired)
        lazy_whole_wape, lazy_whole_bias = _wape_bias(lazy_whole)
        lazy_paired_wape, lazy_paired_bias = _wape_bias(lazy_paired)

        known = known_whole_site[name]
        result[name] = {
            "masked_turbines": masked,
            "surviving_reference_turbines": surviving,
            "wind_first_single_reference_baseline_already_known": {
                "whole_site_wape_pct": known["whole_site"]["aggregate"]["baseline"]["energy_weighted_wape_pct"],
                "whole_site_bias_pct": known["whole_site"]["aggregate"]["baseline"]["signed_aggregate_bias_pct"],
                "same_farm_paired_wape_pct": known["same_farm_single_turbine_same_targets_and_blocks"]["aggregate"]["baseline"]["energy_weighted_wape_pct"],
            },
            "wind_first_ensemble_already_known": {
                "whole_site_wape_pct": known["whole_site"]["aggregate"]["ensemble"]["energy_weighted_wape_pct"],
                "whole_site_bias_pct": known["whole_site"]["aggregate"]["ensemble"]["signed_aggregate_bias_pct"],
                "same_farm_paired_wape_pct": known["same_farm_single_turbine_same_targets_and_blocks"]["aggregate"]["ensemble"]["energy_weighted_wape_pct"],
            },
            "direct_power": {
                "whole_site": {
                    "scored_event_count": len(dp_whole), "skipped_event_count": len(dp_whole_skipped),
                    "wape_pct": dp_whole_wape, "signed_bias_pct": dp_whole_bias,
                },
                "same_farm_paired_same_targets_and_blocks": {
                    "scored_event_count": len(dp_paired), "wape_pct": dp_paired_wape, "signed_bias_pct": dp_paired_bias,
                },
                "per_event_whole_site": dp_whole,
                "skipped_whole_site": dp_whole_skipped,
            },
            "lazy_baseline": {
                "whole_site": {
                    "scored_event_count": len(lazy_whole), "skipped_event_count": len(lazy_whole_skipped),
                    "wape_pct": lazy_whole_wape, "signed_bias_pct": lazy_whole_bias,
                },
                "same_farm_paired_same_targets_and_blocks": {
                    "scored_event_count": len(lazy_paired), "wape_pct": lazy_paired_wape, "signed_bias_pct": lazy_paired_bias,
                },
                "per_event_whole_site": lazy_whole,
                "skipped_whole_site": lazy_whole_skipped,
            },
        }

    artifact = {
        "artifact_version": "kelmarsh-whole-site-masking-tier2.v1",
        "confirmation": (
            "Confirmed by reading kelmarsh_whole_site_masking_backtest.json directly "
            "(not assumed): wind-first single-reference baseline AND ensemble were "
            "BOTH already computed and reported there (aggregate_backtest always "
            "aggregates both). The real gaps filled by this script are direct power "
            "and the lazy (equal-weighted) baseline, on the identical masked-half setup."
        ),
        "locked_scenario_source": str(WHOLE_SITE_PATH),
        "scenarios": result,
        "honesty_note": (
            "Same south/north half-masking setup as the existing whole-site stress "
            "test: ~300-400m reference separation, a best-case ceiling bound, NOT a "
            "neighbouring-farm validation. Direct power and lazy baseline here use "
            "the same blocks and masked/surviving groups as the known wind-first "
            "numbers, for the same paired comparability used throughout this session."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print("=== Tier 2: whole-site masking -- direct power + lazy baseline gap-fill ===")
    for name, r in result.items():
        wf_bl, wf_en = r["wind_first_single_reference_baseline_already_known"], r["wind_first_ensemble_already_known"]
        dp, lazy = r["direct_power"]["whole_site"], r["lazy_baseline"]["whole_site"]
        print(f"\n{name}:")
        print(f"  wind-first single-ref (known): WAPE {wf_bl['whole_site_wape_pct']:.2f}%  bias {wf_bl['whole_site_bias_pct']:+.2f}%")
        print(f"  wind-first ensemble (known):   WAPE {wf_en['whole_site_wape_pct']:.2f}%  bias {wf_en['whole_site_bias_pct']:+.2f}%")
        print(f"  direct power:                  WAPE {dp['wape_pct']:.2f}%  bias {dp['signed_bias_pct']:+.2f}%  (n={dp['scored_event_count']}, skipped {dp['skipped_event_count']})")
        print(f"  lazy baseline:                 WAPE {lazy['wape_pct']:.2f}%  bias {lazy['signed_bias_pct']:+.2f}%  (n={lazy['scored_event_count']}, skipped {lazy['skipped_event_count']})")
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
