"""Cross-farm counterpart of the lazy baseline (2026-10-23, Anna's request).

Anna, verbatim: "test whether the lazy baseline still wins at cross-farm
distance". The same-farm lazy baseline (``run_lazy_baseline_comparison.py``)
averages *surviving same-farm* turbines -- but in the real challenge
scenario (a whole farm down), there are no surviving same-farm turbines to
average, which is exactly why a neighbouring-farm method is needed at all.
So the fair, analogous cross-farm lazy baseline averages the *reference
farm's* available turbines instead (Penmanshiel's, when reconstructing
Kelmarsh; Kelmarsh's, when reconstructing Penmanshiel) -- same mechanism,
same ``lazy_baseline_estimate_kwh`` capacity-factor logic, just drawing its
average from the other farm.

Runs over the EXACT locked event set already used by the real wind-first
cross-farm backtest (``run_kelmarsh_penmanshiel_crossfarm_backtest.py``'s own
output, ``kelmarsh_penmanshiel_crossfarm_backtest.json``) -- the same
(target, block_start) pairs for both directions, read back from that
artifact rather than re-derived, so this is apples-to-apples against its
13.1% / 14.2% wind-first cross-farm WAPE numbers, not a new event selection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.connectors import KelmarshConnector, PenmanshielConnector
from windlens.lazy_baseline import lazy_baseline_estimate_kwh
from windlens.loss_estimate import energy_weighted_wape, integrate_energy_kwh, signed_aggregate_bias_pct
from windlens.run_kelmarsh_penmanshiel_crossfarm_backtest import (
    KELMARSH_CANONICAL,
    PENMANSHIEL_CANONICAL,
    OUTPUT_PATH as CROSSFARM_BACKTEST_PATH,
)

OUTPUT_PATH = Path("data/derived/validation/crossfarm_lazy_baseline_comparison_2026_10_23.json")
BLOCK_DAYS = 5


def _direction_events(
    df: pd.DataFrame,
    rated_power: dict[str, float],
    locked_per_event: list[dict[str, Any]],
    available_turbines: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events, skipped = [], []
    for locked in locked_per_event:
        target, start = locked["target"], locked["block_start"]
        end = (pd.Timestamp(start) + pd.Timedelta(days=BLOCK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        hidden_truth = df[(df["turbine_id"] == target) & (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)]
        if hidden_truth.empty:
            skipped.append({"target": target, "block_start": start, "reason": "no hidden truth rows"})
            continue
        try:
            lazy = lazy_baseline_estimate_kwh(df, target, available_turbines, start, end, rated_power)
        except ValueError as exc:
            skipped.append({"target": target, "block_start": start, "reason": str(exc)})
            continue
        actual_kwh = integrate_energy_kwh(hidden_truth["active_power_kw"].to_numpy())
        events.append(
            {
                "target": target,
                "block_start": start,
                "block_end": end,
                "estimated_lost_kwh": lazy["estimated_lost_kwh"],
                "actual_lost_kwh": actual_kwh,
                "turbines_used": lazy["turbines_used"],
            }
        )
    return events, skipped


def main() -> None:
    k, p = KelmarshConnector(KELMARSH_CANONICAL).load(), PenmanshielConnector(PENMANSHIEL_CANONICAL).load()
    df = pd.concat([k.data, p.data], ignore_index=True)
    k_ids, p_ids = sorted(set(k.data["turbine_id"])), sorted(set(p.data["turbine_id"]))
    rated_power: dict[str, float] = {}
    for dataset in (k, p):
        reg = dataset.registry.to_frame()
        rated_power.update(dict(zip(reg["turbine_id"], reg["rated_power_kw"])))

    locked = json.loads(CROSSFARM_BACKTEST_PATH.read_text(encoding="utf-8"))["directions"]
    direction_refs = {
        "kelmarsh_masked_penmanshiel_reference": p_ids,
        "penmanshiel_masked_kelmarsh_reference": k_ids,
    }

    result: dict[str, Any] = {}
    for name, available_turbines in direction_refs.items():
        locked_per_event = locked[name]["per_event"]
        events, skipped = _direction_events(df, rated_power, locked_per_event, available_turbines)
        wape = energy_weighted_wape(
            [e["estimated_lost_kwh"] for e in events], [e["actual_lost_kwh"] for e in events]
        )
        bias = signed_aggregate_bias_pct(
            [e["estimated_lost_kwh"] for e in events], [e["actual_lost_kwh"] for e in events]
        )
        result[name] = {
            "reference_farm_turbines": available_turbines,
            "locked_event_count": len(locked_per_event),
            "scored_event_count": len(events),
            "skipped_event_count": len(skipped),
            "skipped": skipped,
            "wape_pct": wape,
            "signed_bias_pct": bias,
            "per_event": events,
        }

    artifact = {
        "artifact_version": "crossfarm-lazy-baseline-comparison.v1",
        "method": "equal_weighted_reference_farm_average_capacity_factor_scaled_to_target_rated_power",
        "locked_event_set_source": str(CROSSFARM_BACKTEST_PATH),
        "wind_first_crossfarm_wape_pct_for_comparison": {
            "kelmarsh_masked_penmanshiel_reference": locked["kelmarsh_masked_penmanshiel_reference"]["cross_farm"][
                "aggregate"
            ]["ensemble"]["energy_weighted_wape_pct"],
            "penmanshiel_masked_kelmarsh_reference": locked["penmanshiel_masked_kelmarsh_reference"]["cross_farm"][
                "aggregate"
            ]["ensemble"]["energy_weighted_wape_pct"],
        },
        "directions": result,
        "honesty_note": (
            "This is the cross-farm analogue of the same-farm lazy baseline: it averages "
            "the REFERENCE FARM's available turbines (not surviving same-farm peers, since "
            "none exist in the real whole-farm-outage scenario this method targets), scaled "
            "to the target's own nameplate power. Runs over the exact locked (target, "
            "block_start) pairs already scored by the real wind-first cross-farm backtest -- "
            "same blocks, same target/reference assignments, same eligibility rule -- so the "
            "WAPE numbers above are directly comparable to that backtest's 13.1% / 14.2%."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print("=== Cross-farm lazy baseline (equal-weighted REFERENCE-FARM average capacity factor) ===")
    for name, r in result.items():
        wf = artifact["wind_first_crossfarm_wape_pct_for_comparison"][name]
        print(
            f"{name}: lazy WAPE {r['wape_pct']:.2f}% (bias {r['signed_bias_pct']:+.2f}%) "
            f"n={r['scored_event_count']}/{r['locked_event_count']}  vs. wind-first cross-farm WAPE {wf:.2f}%"
        )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
