"""Tier 1 of the "running the entire matrix" request (2026-10-23, Anna's request).

Fills the two methods never run at real cross-farm distance:
wind-first single-reference (baseline) and direct power-to-power regression.

Both run over the EXACT locked event set already scored by the real wind-first
cross-farm backtest (``run_kelmarsh_penmanshiel_crossfarm_backtest.py``'s own
output) -- the same (target, block_start) pairs, same target/reference-farm
assignments, for both directions. Nothing is re-derived or re-selected.

Wind-first single-reference needs NO new orchestration: ``run_backtest_event``
already computes the single-best-reference baseline alongside the ensemble on
every call (see ``backtest.py``'s ``baseline_score``/``aggregate_backtest``'s
"baseline" aggregate) -- it was simply never *reported* for the cross-farm
backtest. Those numbers were already sitting inside
``kelmarsh_penmanshiel_crossfarm_backtest.json``'s own
``directions.*.cross_farm.aggregate.baseline`` -- this script reads them back
from there directly rather than recomputing, for byte-identical numbers.

Direct power has no existing cross-farm run, so this adds one, following the
exact same per-block pattern as the same-farm
``run_direct_power_uncertainty_backtest.py`` (fit-before-the-event linear
regression, reference selected by the same behaviour+geo dynamic selection),
restricted so candidates are the OTHER farm's turbines only -- the same
whole-farm-outage constraint the wind-first cross-farm backtest already
enforces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.connectors import KelmarshConnector, PenmanshielConnector
from windlens.direct_power_uncertainty import fit_direct_power, predict_direct_power
from windlens.dynamic_reference import select_dynamic_references
from windlens.loss_estimate import energy_weighted_wape, integrate_energy_kwh, signed_aggregate_bias_pct
from windlens.run_kelmarsh_penmanshiel_crossfarm_backtest import (
    KELMARSH_CANONICAL,
    PENMANSHIEL_CANONICAL,
    OUTPUT_PATH as CROSSFARM_BACKTEST_PATH,
)

OUTPUT_PATH = Path("data/derived/validation/crossfarm_tier1_single_reference_and_direct_power.json")
BLOCK_DAYS = 5


def _block_end(start: str) -> str:
    return (pd.Timestamp(start) + pd.Timedelta(days=BLOCK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _select_baseline_reference(pre_outage: pd.DataFrame, target: str, candidates: list[str], metadata: pd.DataFrame) -> str:
    selection = select_dynamic_references(
        pre_outage, target, candidates, metadata, lookback_days=(30, 90, 180), top_k=3, min_paired_observations=20
    )
    if selection["status"] == "abstain":
        raise ValueError(f"Dynamic reference selection abstained: {selection['reason']}")
    return selection["selected"]


def _direct_power_events(
    df: pd.DataFrame,
    metadata: pd.DataFrame,
    rated_power: dict[str, float],
    locked_per_event: list[dict[str, Any]],
    reference_farm_turbines: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events, skipped = [], []
    for locked in locked_per_event:
        target, start = locked["target"], locked["block_start"]
        end = _block_end(start)
        pre_outage = df[df["timestamp_utc"] < start]
        try:
            reference = _select_baseline_reference(pre_outage, target, reference_farm_turbines, metadata)
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
            {
                "target": target,
                "block_start": start,
                "reference": reference,
                "estimated_lost_kwh": estimated_kwh,
                "actual_lost_kwh": actual_kwh,
            }
        )
    return events, skipped


def main() -> None:
    k, p = KelmarshConnector(KELMARSH_CANONICAL).load(), PenmanshielConnector(PENMANSHIEL_CANONICAL).load()
    df = pd.concat([k.data, p.data], ignore_index=True)
    metadata = pd.concat([k.registry.to_frame(), p.registry.to_frame()], ignore_index=True)
    k_ids, p_ids = sorted(set(k.data["turbine_id"])), sorted(set(p.data["turbine_id"]))
    rated_power: dict[str, float] = dict(zip(metadata["turbine_id"], metadata["rated_power_kw"]))

    locked_artifact = json.loads(CROSSFARM_BACKTEST_PATH.read_text(encoding="utf-8"))
    locked = locked_artifact["directions"]
    direction_refs = {
        "kelmarsh_masked_penmanshiel_reference": p_ids,
        "penmanshiel_masked_kelmarsh_reference": k_ids,
    }

    result: dict[str, Any] = {}
    for name, reference_farm_turbines in direction_refs.items():
        locked_per_event = locked[name]["per_event"]
        wf = locked[name]["cross_farm"]["aggregate"]

        dp_events, dp_skipped = _direct_power_events(df, metadata, rated_power, locked_per_event, reference_farm_turbines)
        dp_wape = energy_weighted_wape([e["estimated_lost_kwh"] for e in dp_events], [e["actual_lost_kwh"] for e in dp_events])
        dp_bias = signed_aggregate_bias_pct([e["estimated_lost_kwh"] for e in dp_events], [e["actual_lost_kwh"] for e in dp_events])

        result[name] = {
            "locked_event_count": len(locked_per_event),
            "wind_first_single_reference_baseline": {
                "source": "kelmarsh_penmanshiel_crossfarm_backtest.json: directions.*.cross_farm.aggregate.baseline "
                "(already computed by run_backtest_event on these exact locked events; read back, not recomputed)",
                "wape_pct": wf["baseline"]["energy_weighted_wape_pct"],
                "signed_bias_pct": wf["baseline"]["signed_aggregate_bias_pct"],
                "event_count": wf["event_count"],
            },
            "wind_first_ensemble_for_comparison": {
                "wape_pct": wf["ensemble"]["energy_weighted_wape_pct"],
                "signed_bias_pct": wf["ensemble"]["signed_aggregate_bias_pct"],
                "event_count": wf["event_count"],
            },
            "direct_power": {
                "scored_event_count": len(dp_events),
                "skipped_event_count": len(dp_skipped),
                "skipped": dp_skipped,
                "wape_pct": dp_wape,
                "signed_bias_pct": dp_bias,
                "per_event": dp_events,
            },
            "lazy_average_for_comparison": None,  # filled in below from the existing cross-farm lazy artifact
        }

    lazy_path = Path("data/derived/validation/crossfarm_lazy_baseline_comparison_2026_10_23.json")
    if lazy_path.exists():
        lazy = json.loads(lazy_path.read_text(encoding="utf-8"))
        for name in result:
            lazy_dir = lazy["directions"][name]
            result[name]["lazy_average_for_comparison"] = {
                "wape_pct": lazy_dir["wape_pct"],
                "signed_bias_pct": lazy_dir["signed_bias_pct"],
            }

    artifact = {
        "artifact_version": "crossfarm-tier1-single-reference-and-direct-power.v1",
        "locked_event_set_source": str(CROSSFARM_BACKTEST_PATH),
        "directions": result,
        "honesty_note": (
            "Runs the two methods never previously tested at real (~399 km) cross-farm "
            "distance -- wind-first single-reference and direct power -- over the exact "
            "locked (target, block_start) event set the real wind-first ensemble cross-farm "
            "backtest already scored. The wind-first single-reference numbers are read back "
            "from that backtest's own already-computed baseline aggregate (run_backtest_event "
            "scores both baseline and ensemble on every call), not recomputed, for byte-"
            "identical numbers and zero risk of re-deriving the event set. Direct power is a "
            "new per-block run over the same locked pairs, same reference-selection algorithm "
            "as the existing same-farm direct-power backtest, restricted to the other farm's "
            "turbines as candidates (same whole-farm-outage constraint already enforced "
            "by the wind-first cross-farm backtest)."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print("=== Tier 1: cross-farm single-reference wind-first + direct power ===")
    for name, r in result.items():
        bl, en, dp = r["wind_first_single_reference_baseline"], r["wind_first_ensemble_for_comparison"], r["direct_power"]
        print(f"\n{name} (n={r['locked_event_count']} locked):")
        print(f"  wind-first single-reference: WAPE {bl['wape_pct']:.2f}%  bias {bl['signed_bias_pct']:+.2f}%")
        print(f"  wind-first ensemble (known): WAPE {en['wape_pct']:.2f}%  bias {en['signed_bias_pct']:+.2f}%")
        print(f"  direct power:                WAPE {dp['wape_pct']:.2f}%  bias {dp['signed_bias_pct']:+.2f}%  (n={dp['scored_event_count']}/{r['locked_event_count']}, skipped {dp['skipped_event_count']})")
        if r["lazy_average_for_comparison"]:
            la = r["lazy_average_for_comparison"]
            print(f"  lazy average (known):        WAPE {la['wape_pct']:.2f}%  bias {la['signed_bias_pct']:+.2f}%")
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
