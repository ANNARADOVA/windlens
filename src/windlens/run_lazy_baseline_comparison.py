"""Lazy-baseline comparison -- 2026-10-23 "insurer's lens" quick fix #3.

Runs the lazy baseline (windlens.lazy_baseline) over the exact same Kelmarsh
19-block and Hill of Towie 28-block sets already used by
`run_kelmarsh_extended_backtest.py` / `run_hill_uncertainty_multiyear.py`, so
its WAPE is directly comparable to those scripts' own wind-first baseline/
ensemble numbers -- not a new, cherry-picked block set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.lazy_baseline import lazy_baseline_estimate_kwh
from windlens.loss_estimate import energy_weighted_wape, integrate_energy_kwh, signed_aggregate_bias_pct

from windlens.run_kelmarsh_extended_backtest import BLOCKS as KELMARSH_BLOCKS
from windlens.run_kelmarsh_extended_backtest import (
    CANDIDATE_REFERENCE_TURBINES as KELMARSH_CANDIDATES,
)
from windlens.run_kelmarsh_extended_backtest import CANONICAL_PATH as KELMARSH_CANONICAL_PATH
from windlens.run_kelmarsh_extended_backtest import METADATA_PATH as KELMARSH_METADATA_PATH
from windlens.run_kelmarsh_extended_backtest import TARGET_TURBINE as KELMARSH_TARGET
from windlens.connectors import KelmarshConnector
from windlens.run_hill_uncertainty_multiyear import BLOCKS_BY_YEAR as HILL_BLOCKS_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import CANONICAL_BY_YEAR as HILL_CANONICAL_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import REGISTRY_PATH as HILL_REGISTRY_PATH
from windlens.run_hill_uncertainty_multiyear import TARGET_TURBINE as HILL_TARGET

OUTPUT_PATH = Path("data/derived/validation/lazy_baseline_comparison_2026_10_23.json")


def _kelmarsh_events() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dataset = KelmarshConnector(KELMARSH_CANONICAL_PATH, KELMARSH_METADATA_PATH).load()
    canonical = dataset.data
    rated_power = dict(
        zip(dataset.registry.to_frame()["turbine_id"], dataset.registry.to_frame()["rated_power_kw"])
    )
    events, skipped = [], []
    for start, end in KELMARSH_BLOCKS:
        hidden_truth = canonical[
            (canonical["turbine_id"] == KELMARSH_TARGET)
            & (canonical["timestamp_utc"] >= start)
            & (canonical["timestamp_utc"] < end)
        ]
        masked = canonical[
            ~((canonical["turbine_id"] == KELMARSH_TARGET) & (canonical["timestamp_utc"] >= start) & (canonical["timestamp_utc"] < end))
        ]
        if hidden_truth.empty:
            skipped.append({"block_start": start, "block_end": end, "reason": "no hidden truth rows"})
            continue
        try:
            lazy = lazy_baseline_estimate_kwh(
                masked, KELMARSH_TARGET, KELMARSH_CANDIDATES, start, end, rated_power
            )
        except ValueError as exc:
            skipped.append({"block_start": start, "block_end": end, "reason": str(exc)})
            continue
        actual_kwh = integrate_energy_kwh(hidden_truth["active_power_kw"].to_numpy())
        events.append(
            {
                "block_start": start,
                "block_end": end,
                "estimated_lost_kwh": lazy["estimated_lost_kwh"],
                "actual_lost_kwh": actual_kwh,
                "turbines_used": lazy["turbines_used"],
            }
        )
    return events, skipped


def _hill_events() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = pd.read_csv(HILL_REGISTRY_PATH)
    rated_power = dict(zip(registry["turbine_id"], registry["rated_power_kw"]))
    events, skipped = [], []
    for year, canonical_path in HILL_CANONICAL_BY_YEAR.items():
        canonical = pd.read_csv(canonical_path)
        canonical["timestamp_utc"] = pd.to_datetime(canonical["timestamp_utc"], utc=True)
        candidates = sorted(set(canonical["turbine_id"]) - {HILL_TARGET})
        for start, end in HILL_BLOCKS_BY_YEAR[year]:
            hidden_truth = canonical[
                (canonical["turbine_id"] == HILL_TARGET)
                & (canonical["timestamp_utc"] >= start)
                & (canonical["timestamp_utc"] < end)
            ]
            masked = canonical[
                ~((canonical["turbine_id"] == HILL_TARGET) & (canonical["timestamp_utc"] >= start) & (canonical["timestamp_utc"] < end))
            ]
            if hidden_truth.empty:
                skipped.append({"year": year, "block_start": start, "block_end": end, "reason": "no hidden truth rows"})
                continue
            try:
                lazy = lazy_baseline_estimate_kwh(masked, HILL_TARGET, candidates, start, end, rated_power)
            except ValueError as exc:
                skipped.append({"year": year, "block_start": start, "block_end": end, "reason": str(exc)})
                continue
            actual_kwh = integrate_energy_kwh(hidden_truth["active_power_kw"].to_numpy())
            events.append(
                {
                    "year": year,
                    "block_start": start,
                    "block_end": end,
                    "estimated_lost_kwh": lazy["estimated_lost_kwh"],
                    "actual_lost_kwh": actual_kwh,
                    "turbines_used": lazy["turbines_used"],
                }
            )
    return events, skipped


def main() -> None:
    kelmarsh_events, kelmarsh_skipped = _kelmarsh_events()
    hill_events, hill_skipped = _hill_events()

    kelmarsh_wape = energy_weighted_wape(
        [e["estimated_lost_kwh"] for e in kelmarsh_events], [e["actual_lost_kwh"] for e in kelmarsh_events]
    )
    kelmarsh_bias = signed_aggregate_bias_pct(
        [e["estimated_lost_kwh"] for e in kelmarsh_events], [e["actual_lost_kwh"] for e in kelmarsh_events]
    )
    hill_wape = energy_weighted_wape(
        [e["estimated_lost_kwh"] for e in hill_events], [e["actual_lost_kwh"] for e in hill_events]
    )
    hill_bias = signed_aggregate_bias_pct(
        [e["estimated_lost_kwh"] for e in hill_events], [e["actual_lost_kwh"] for e in hill_events]
    )

    print("=== Lazy baseline (equal-weighted farm-average capacity factor) ===")
    print(f"Kelmarsh ({len(kelmarsh_events)}/{len(KELMARSH_BLOCKS)} blocks scored): WAPE {kelmarsh_wape:.2f}%, bias {kelmarsh_bias:+.2f}%")
    print(f"Hill of Towie ({len(hill_events)}/{sum(len(b) for b in HILL_BLOCKS_BY_YEAR.values())} blocks scored): WAPE {hill_wape:.2f}%, bias {hill_bias:+.2f}%")

    artifact = {
        "artifact_version": "lazy-baseline-comparison.v1",
        "method": "equal_weighted_farm_average_capacity_factor_scaled_to_target_rated_power",
        "kelmarsh": {
            "wape_pct": kelmarsh_wape,
            "signed_bias_pct": kelmarsh_bias,
            "n_blocks_scored": len(kelmarsh_events),
            "n_blocks_total": len(KELMARSH_BLOCKS),
            "skipped": kelmarsh_skipped,
        },
        "hill_of_towie": {
            "wape_pct": hill_wape,
            "signed_bias_pct": hill_bias,
            "n_blocks_scored": len(hill_events),
            "n_blocks_total": sum(len(b) for b in HILL_BLOCKS_BY_YEAR.values()),
            "skipped": hill_skipped,
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, default=str)
    print(f"\nArtifact written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
