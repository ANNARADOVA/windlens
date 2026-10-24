"""Real distant cross-farm back-test: Kelmarsh <-> Penmanshiel (2026-10-23).

Framing: see ``windlens.evidence_tiers.CROSS_FARM_FRAMING`` -- a realistic-distance
FLOOR (~400 km), NOT a neighbouring-farm validation.

Design rules, fixed BEFORE any result was computed (and not changed afterwards):

* Whole-farm outage on the target side: when a Kelmarsh turbine is the target, ONLY
  Penmanshiel turbines are candidate references (no Kelmarsh peer is available), and
  vice versa. ``assert_references_from_other_farm`` verifies this on every event.
* Blocks: consecutive, non-overlapping 5-day windows tiling 2016-09-01 .. 2017-01-01
  (Penmanshiel's declared commercial-operations date is 2016-09-01; earlier data are
  commissioning-period and deliberately excluded). No block is chosen or dropped on
  outcome. A window is eligible only if (a) the target turbine has >=90% of its 720
  ten-minute slots and (b) at least 5 turbines of the reference farm each have >=90%.
  This is purely an input-availability rule. The threshold is 90% rather than the 95%
  the same-farm blocks used because (counts taken BEFORE any back-test was run) 95% left
  only 5 Kelmarsh-target blocks / 3 Penmanshiel-target blocks (22 / 32 events), too few
  to say anything; 90% gives 8 / 9 blocks (47 / 96 events) and equals the pipeline's own
  completeness-gate floor (MIN_RECONSTRUCTION_COMPLETENESS_PCT=90). 85% (11 / 13 blocks)
  was counted but not used. Coverage is thin mainly because the shared extraction drops
  negative standby-power rows (physically normal at standstill) as "implausible", which
  punches holes in calm windows for BOTH farms -- so eligible blocks skew toward windier,
  fully-operating periods; the same skew already exists in the same-farm blocks.
* Targets: all 6 Kelmarsh turbines (reference = Penmanshiel) and all 14 Penmanshiel
  turbines (reference = Kelmarsh).
* Method, gates, calibration, thresholds: exactly ``run_backtest_event`` as-is
  (dynamic geo+behaviour selection, inverse-RMSE ensemble, variance-ratio MCP, all
  gates, 90% empirical interval). Nothing is tuned for this test.
* A paired SAME-FARM run on the same targets and block grid (all same-farm peers
  available) is reported alongside. NOTE: eligibility is evaluated separately for it, so its event set is NOT identical to the cross-farm one (see DECISION_LOG); the cost of distance is measured on the same
  targets and calendar blocks, not event-for-event.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from windlens.backtest import run_backtest_event
from windlens.connectors import KelmarshConnector, PenmanshielConnector
from windlens.dynamic_reference import haversine_km
from windlens.evidence_tiers import CROSS_FARM_FRAMING, TIER_CROSS_FARM
from windlens.run_kelmarsh_whole_site_masking_backtest import _event_error_pct, summarise

KELMARSH_CANONICAL = Path("data/derived/kelmarsh_2016_full_year_canonical.csv")
PENMANSHIEL_CANONICAL = Path("data/derived/penmanshiel_2016_canonical.csv")
OUTPUT_PATH = Path("data/derived/validation/kelmarsh_penmanshiel_crossfarm_backtest.json")

GRID_START = "2016-09-01T00:00:00Z"
GRID_END = "2017-01-01T00:00:00Z"
BLOCK_DAYS = 5
MIN_BLOCK_COVERAGE = 0.90
MIN_REFERENCE_TURBINES_WITH_COVERAGE = 5
SLOTS_PER_BLOCK = BLOCK_DAYS * 144


def block_grid(start: str = GRID_START, end: str = GRID_END, days: int = BLOCK_DAYS) -> list[tuple[str, str]]:
    cursor, stop, blocks = pd.Timestamp(start), pd.Timestamp(end), []
    while cursor + pd.Timedelta(days=days) <= stop:
        nxt = cursor + pd.Timedelta(days=days)
        blocks.append((cursor.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
        cursor = nxt
    return blocks


def coverage_table(df: pd.DataFrame, blocks: list[tuple[str, str]]) -> pd.DataFrame:
    """Fraction of each block's 10-minute slots present, per turbine (rows) x block start (columns)."""

    table = {}
    for start, end in blocks:
        window = df[(df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)]
        expected = int((pd.Timestamp(end) - pd.Timestamp(start)) / pd.Timedelta(minutes=10))
        table[start] = window.groupby("turbine_id").size() / expected
    return pd.DataFrame(table).fillna(0.0)


def block_is_eligible(
    table: pd.DataFrame, target: str, reference_turbines: list[str], start: str,
    min_coverage: float = MIN_BLOCK_COVERAGE,
) -> bool:
    if table.at[target, start] < min_coverage:
        return False
    good = sum(table.at[t, start] >= min_coverage for t in reference_turbines if t in table.index)
    return good >= MIN_REFERENCE_TURBINES_WITH_COVERAGE


def assert_references_from_other_farm(event: dict[str, Any], reference_farm_turbines: list[str]) -> None:
    used = {event["baseline_reference"], *event["ensemble_references"]}
    if not used <= set(reference_farm_turbines):
        raise AssertionError(f"cross-farm test used a non-reference-farm turbine: {sorted(used - set(reference_farm_turbines))}")


def run_direction(df, metadata, targets, candidates, blocks, same_farm: bool = False):
    events, skipped = [], []
    table = coverage_table(df, blocks)
    for target in targets:
        cand = [c for c in candidates if c != target] if same_farm else list(candidates)
        for start, end in blocks:
            if not block_is_eligible(table, target, cand, start):
                skipped.append({"target": target, "block_start": start, "reason": "input-availability rule"})
                continue
            try:
                event = run_backtest_event(df, target, cand, start, end, metadata_df=metadata)
            except ValueError as exc:
                skipped.append({"target": target, "block_start": start, "reason": str(exc)})
                continue
            if not same_farm:
                assert_references_from_other_farm(event, candidates)
            event["target"] = target
            events.append(event)
    return events, skipped


def _per_event(events):
    return [
        {
            "target": e["target"], "block_start": e["block_start"],
            "estimated_lost_kwh": e["ensemble"]["loss"]["estimated_lost_kwh"],
            "actual_lost_kwh": e["ensemble"]["loss"]["actual_lost_kwh"],
            "error_pct": _event_error_pct(e),
            "wind_rmse_ms": e["ensemble"]["wind_errors"]["rmse_ms"],
            "wind_bias_ms": e["ensemble"]["wind_errors"]["signed_bias_ms"],
            "label": e["classification"]["label"],
            "failed_gates": e["classification"]["failed_gates"],
            "references": e["ensemble_references"],
            "completeness_pct": e["completeness"]["completeness_pct"],
        }
        for e in events
    ]


def wind_correlation_diagnostic(df, kelmarsh, penmanshiel, start=GRID_START, end=GRID_END) -> dict[str, Any]:
    """Descriptive only -- nothing here feeds the method. Concurrent 10-min wind-speed
    Pearson r: cross-farm pairs vs. within-farm pairs, over the same window."""

    window = df[(df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)]
    wide = window.pivot_table(index="timestamp_utc", columns="turbine_id", values="wind_speed_ms", aggfunc="mean")
    corr = wide.corr()

    def _mean(a, b, same):
        vals = [corr.loc[x, y] for x in a for y in b if x in corr.index and y in corr.columns and (x != y if same else True)]
        return float(np.nanmean(vals)), float(np.nanmin(vals)), float(np.nanmax(vals))

    cross = _mean(kelmarsh, penmanshiel, False)
    within_k, within_p = _mean(kelmarsh, kelmarsh, True), _mean(penmanshiel, penmanshiel, True)
    return {
        "window": [start, end],
        "cross_farm_r": {"mean": cross[0], "min": cross[1], "max": cross[2]},
        "within_kelmarsh_r": {"mean": within_k[0], "min": within_k[1], "max": within_k[2]},
        "within_penmanshiel_r": {"mean": within_p[0], "min": within_p[1], "max": within_p[2]},
        "note": "Diagnostic only; lag-0 correlation of 10-minute turbine wind speeds. Not used by the method.",
    }


def main() -> None:
    k, p = KelmarshConnector(KELMARSH_CANONICAL).load(), PenmanshielConnector(PENMANSHIEL_CANONICAL).load()
    df = pd.concat([k.data, p.data], ignore_index=True)
    metadata = pd.concat([k.registry.to_frame(), p.registry.to_frame()], ignore_index=True)
    k_ids, p_ids = sorted(set(k.data["turbine_id"])), sorted(set(p.data["turbine_id"]))
    blocks = block_grid()

    meta = metadata.set_index("turbine_id")
    dists = [haversine_km(meta.loc[a, "latitude"], meta.loc[a, "longitude"], meta.loc[b, "latitude"], meta.loc[b, "longitude"]) for a in k_ids for b in p_ids]
    distance_km = float(np.mean(dists))

    directions = {
        "kelmarsh_masked_penmanshiel_reference": (k_ids, p_ids),
        "penmanshiel_masked_kelmarsh_reference": (p_ids, k_ids),
    }
    result = {}
    for name, (targets, refs) in directions.items():
        events, skipped = run_direction(df, metadata, targets, refs, blocks)
        paired, _ = run_direction(df, metadata, targets, targets, blocks, same_farm=True)
        entry: dict[str, Any] = {
            "targets": targets, "reference_farm_turbines": refs,
            "skipped_event_count": len(skipped), "scored_event_count": len(events),
            "per_event": _per_event(events),
        }
        if events:
            entry["cross_farm"] = summarise(events)
            entry["cross_farm"]["median_wind_rmse_ms"] = float(np.median([e["ensemble"]["wind_errors"]["rmse_ms"] for e in events]))
        if paired:
            entry["same_farm_paired_same_targets_and_blocks"] = summarise(paired)
        result[name] = entry

    artifact = {
        "artifact_version": "kelmarsh-penmanshiel-crossfarm.v1",
        "evidence_tier": TIER_CROSS_FARM,
        "framing": CROSS_FARM_FRAMING.format(distance_km=distance_km),
        "farm_to_farm_distance_km": {"mean_turbine_pair": distance_km, "min": float(min(dists)), "max": float(max(dists))},
        "grid": {"start": GRID_START, "end": GRID_END, "block_days": BLOCK_DAYS, "block_count": len(blocks)},
        "wind_correlation_diagnostic": wind_correlation_diagnostic(df, k_ids, p_ids),
        "directions": result,
        "hardware_and_terrain_differences": (
            "Kelmarsh: Senvion MM92, 78.5 m hub, 92 m rotor, ~145-157 m elevation, gentle terrain. "
            "Penmanshiel: Senvion MM82, 59 m hub, 82 m rotor, ~180-228 m elevation, hillier Scottish Borders terrain."
        ),
        "honesty_note": (
            "Different regions, climates and terrain ~400 km apart: this tests how far reconstruction "
            "degrades when the only reference is a genuinely independent farm, it is not the challenge's "
            "neighbouring-farm scenario. Events within a direction are not independent (shared blocks and weather)."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print(artifact["framing"])
    print("correlation:", json.dumps({k_: v for k_, v in artifact["wind_correlation_diagnostic"].items() if k_.endswith("_r")}, default=float))
    for name, e in result.items():
        print(f"\n{name}: scored {e['scored_event_count']}, skipped {e['skipped_event_count']}")
        for label in ("cross_farm", "same_farm_paired_same_targets_and_blocks"):
            x = e.get(label)
            if x:
                print(
                    f"  {label:42s} n={x['event_count']:3d} WAPE {x['aggregate']['ensemble']['energy_weighted_wape_pct']:.1f}% "
                    f"bias {x['aggregate']['ensemble']['signed_aggregate_bias_pct']:+.1f}% "
                    f"reviewable {x['reviewable_count']}/{x['event_count']} "
                    f"cov {x['pooled_coverage']['pooled_coverage_pct']:.1f}% medAbsErr {x['median_abs_event_error_pct']:.1f}%"
                )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
