"""Tier 3 of the "running the entire matrix" request (2026-10-23, Anna's request).

Ensemble-WEIGHTING ablation: inverse-holdout-error weighting (current,
shipped) vs. equal weighting (1/3 each) for the already-selected top-3
reference turbines. This is a different question from the already-tested
80/20 behavior/geography SELECTION criterion
(`run_reference_weighting_ablation.py`) -- that ablation is about which
turbines get chosen; this one is about how the chosen three are combined.

Expected, stated upfront per the brief: low-value. The selection-criterion
ablation already found weighting-style differences are mostly noise at this
sample size (n=10-14 dev blocks per farm, all four candidates statistically
indistinguishable). Run anyway for completeness; no extra effort spent
chasing a marginal result here.

Same discipline as the selection-criterion ablation:
- Reuses the LOCKED split from `method_bakeoff_2026_10_23.json`'s
  `locked_split` key verbatim (same blocks, same dev/report assignment).
- Both weighting schemes compared on the DEV subset only.
- Final numbers computed exactly once on the untouched REPORT subset, after
  the dev-only decision.

No production code is touched: `select_dynamic_references` already returns
the chosen top-3 ensemble with its inverse-error weights attached (unchanged
call, same `behavior_weight=0.8` default). This script only substitutes an
equal-weight dict for the same three turbines and re-scores with the
existing, unmodified `reconstruct_wind_speed_weighted` -- mirroring
`backtest.py`'s own `_score` closure for the power-curve fit / loss /
wind-error scoring, since that step is private to `run_backtest_event` and
not separately callable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.dynamic_reference import select_dynamic_references
from windlens.loss_estimate import energy_weighted_wape, estimate_loss, signed_aggregate_bias_pct, wind_speed_errors
from windlens.power_curve import apply_power_curve, fit_power_curve
from windlens.reconstruct import reconstruct_wind_speed_weighted
from windlens.run_hill_uncertainty_multiyear import BLOCKS_BY_YEAR as HILL_BLOCKS_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import CANONICAL_BY_YEAR as HILL_CANONICAL_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import REGISTRY_PATH as HILL_REGISTRY_PATH
from windlens.run_hill_uncertainty_multiyear import TARGET_TURBINE as HILL_TARGET
from windlens.run_kelmarsh_extended_backtest import CANDIDATE_REFERENCE_TURBINES as KELMARSH_CANDIDATES
from windlens.run_kelmarsh_extended_backtest import CANONICAL_PATH as KELMARSH_CANONICAL_PATH
from windlens.run_kelmarsh_extended_backtest import METADATA_PATH as KELMARSH_METADATA_PATH
from windlens.run_kelmarsh_extended_backtest import TARGET_TURBINE as KELMARSH_TARGET
from windlens.connectors import KelmarshConnector

LOCKED_SPLIT_PATH = Path("data/derived/validation/method_bakeoff_2026_10_23.json")
OUTPUT_PATH = Path("data/derived/validation/ensemble_weighting_ablation_2026_10_23.json")


def _load_locked_split() -> dict[str, list[tuple[str, str]]]:
    with open(LOCKED_SPLIT_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)["locked_split"]
    return {key: [(start, end) for start, end in blocks] for key, blocks in raw.items()}


def _score_weighted(
    canonical: pd.DataFrame, target: str, weights: dict[str, float], start: str, end: str,
) -> dict[str, Any]:
    pre_outage = canonical[canonical["timestamp_utc"] < start]
    hidden_truth = canonical[
        (canonical["turbine_id"] == target) & (canonical["timestamp_utc"] >= start) & (canonical["timestamp_utc"] < end)
    ]
    if hidden_truth.empty:
        raise ValueError(f"No {target} rows in [{start}, {end})")
    masked = canonical[~((canonical["turbine_id"] == target) & (canonical["timestamp_utc"] >= start) & (canonical["timestamp_utc"] < end))]
    power_curve = fit_power_curve(pre_outage[pre_outage["turbine_id"] == target])
    reconstruction = reconstruct_wind_speed_weighted(masked, target, weights, start, end)
    joined = reconstruction.merge(hidden_truth[["timestamp_utc", "active_power_kw"]], on="timestamp_utc", how="inner")
    if joined.empty:
        raise ValueError("No overlapping timestamps between reconstruction and hidden truth")
    expected_power = apply_power_curve(power_curve, joined["wind_speed_ms_reconstructed"].to_numpy())
    loss = estimate_loss(expected_power, joined["active_power_kw"].to_numpy())
    errors = wind_speed_errors(reconstruction, hidden_truth)
    return {"loss": loss, "wind_errors": errors}


def _run_blocks(
    canonical: pd.DataFrame, target: str, candidates: list[str], metadata: pd.DataFrame, blocks: list[tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events, skipped = [], []
    for start, end in blocks:
        pre_outage = canonical[canonical["timestamp_utc"] < start]
        try:
            selection = select_dynamic_references(
                pre_outage, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20,
            )
            if selection["status"] == "abstain":
                raise ValueError(f"Dynamic reference selection abstained: {selection['reason']}")
            current_weights = {entry["turbine_id"]: entry["weight"] for entry in selection["ensemble"]}
            equal_weights = {turbine: 1.0 / len(current_weights) for turbine in current_weights}
            current_score = _score_weighted(canonical, target, current_weights, start, end)
            equal_score = _score_weighted(canonical, target, equal_weights, start, end)
        except ValueError as exc:
            skipped.append({"block_start": start, "block_end": end, "reason": str(exc)})
            continue
        events.append(
            {
                "block_start": start,
                "ensemble_turbines": sorted(current_weights),
                "current_inverse_error_weights": current_weights,
                "current": current_score,
                "equal": equal_score,
            }
        )
    return events, skipped


def _aggregate(events: list[dict[str, Any]], key: str) -> dict[str, float]:
    estimated = [e[key]["loss"]["estimated_lost_kwh"] for e in events]
    actual = [e[key]["loss"]["actual_lost_kwh"] for e in events]
    return {
        "energy_weighted_wape_pct": energy_weighted_wape(estimated, actual),
        "signed_aggregate_bias_pct": signed_aggregate_bias_pct(estimated, actual),
    }


def _score_farm_blocks(blocks: list[tuple[str, str]]) -> dict[str, Any]:
    kelmarsh = KelmarshConnector(KELMARSH_CANONICAL_PATH, KELMARSH_METADATA_PATH).load()
    k_events, k_skipped = _run_blocks(kelmarsh.data, KELMARSH_TARGET, KELMARSH_CANDIDATES, kelmarsh.registry.to_frame(), blocks)
    return {"n_blocks": len(blocks), "skipped": k_skipped, "events": k_events,
            "current_aggregate": _aggregate(k_events, "current") if k_events else None,
            "equal_aggregate": _aggregate(k_events, "equal") if k_events else None}


def _score_hill_blocks(blocks: list[tuple[str, str]]) -> dict[str, Any]:
    registry = pd.read_csv(HILL_REGISTRY_PATH)
    canonical_by_year = {
        year: pd.read_csv(path).assign(timestamp_utc=lambda df: pd.to_datetime(df["timestamp_utc"], utc=True))
        for year, path in HILL_CANONICAL_BY_YEAR.items()
    }
    events, skipped = [], []
    for start, end in blocks:
        year = start[:4]
        canonical = canonical_by_year[year]
        candidates = sorted(set(canonical["turbine_id"]) - {HILL_TARGET})
        evts, skp = _run_blocks(canonical, HILL_TARGET, candidates, registry, [(start, end)])
        events.extend(evts)
        skipped.extend(skp)
    return {"n_blocks": len(blocks), "skipped": skipped, "events": events,
            "current_aggregate": _aggregate(events, "current") if events else None,
            "equal_aggregate": _aggregate(events, "equal") if events else None}


def main() -> None:
    split = _load_locked_split()

    dev = {"kelmarsh": _score_farm_blocks(split["kelmarsh_dev"]), "hill_of_towie": _score_hill_blocks(split["hill_of_towie_dev"])}
    report = {"kelmarsh": _score_farm_blocks(split["kelmarsh_report"]), "hill_of_towie": _score_hill_blocks(split["hill_of_towie_report"])}

    artifact = {
        "artifact_version": "ensemble-weighting-ablation.v1",
        "locked_split_source": str(LOCKED_SPLIT_PATH),
        "question": "inverse-holdout-error weighting (current, shipped) vs. equal (1/3 each) weighting of the already-selected top-3 ensemble turbines",
        "expectation_stated_upfront": (
            "Expected to be low-value: the related reference-SELECTION-criterion ablation "
            "already found weighting differences are mostly noise at this sample size. "
            "Run anyway for completeness, per the brief."
        ),
        "dev": dev,
        "report": report,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print("=== Tier 3: ensemble-weighting ablation (inverse-error vs equal) ===")
    for phase_name, phase in (("DEV", dev), ("REPORT", report)):
        print(f"\n--- {phase_name} ---")
        for farm, r in phase.items():
            if r["current_aggregate"] is None:
                print(f"  {farm}: no scored events")
                continue
            cur, eq = r["current_aggregate"], r["equal_aggregate"]
            print(
                f"  {farm:14s} n={len(r['events']):2d}  "
                f"inverse-error WAPE {cur['energy_weighted_wape_pct']:.2f}% bias {cur['signed_aggregate_bias_pct']:+.2f}%  |  "
                f"equal WAPE {eq['energy_weighted_wape_pct']:.2f}% bias {eq['signed_aggregate_bias_pct']:+.2f}%"
            )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
