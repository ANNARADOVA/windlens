"""Whole-site masking stress test on Kelmarsh (2026-10-23).

Framing, verbatim wherever these numbers appear: see
``windlens.evidence_tiers.WHOLE_SITE_FRAMING`` -- "whole-site masking stress test,
~300-400m reference separation -- a best-case ceiling bound, NOT a neighbouring-farm
validation."

What this tests that no earlier back-test did: ``run_backtest_event`` masks exactly
ONE target turbine while every other same-farm turbine stays up as a candidate
reference. A real whole-farm outage takes ALL of a site's turbines down at once, with
zero same-farm fallback. Here an entire half of Kelmarsh is treated as down and each
masked turbine is reconstructed using ONLY the surviving half as candidate references.

What it does NOT test: the two halves sit only ~300-400m apart (same ridge, same
inflow), far closer than any real neighbouring farm. This is a best-case bound on the
pipeline's whole-site-outage behaviour, not a neighbouring-farm validation.

Implementation: no reconstruction/gating/calibration logic is duplicated.
``run_backtest_event`` already takes an explicit ``candidate_reference_turbines`` list
and only ever draws references from it (ranking, dynamic selection, fits, domain
checks, alignment gate all iterate that list), so restricting the list to the
surviving half IS the whole-site mask for the reference side. ``assert_no_masked_peer``
re-verifies this on every event's output rather than trusting it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from windlens.backtest import aggregate_backtest, run_backtest_event
from windlens.connectors import KelmarshConnector
from windlens.dynamic_reference import haversine_km
from windlens.evidence_tiers import TIER_WHOLE_SITE, WHOLE_SITE_FRAMING
from windlens.run_kelmarsh_extended_backtest import (
    BLOCKS,
    CANONICAL_PATH,
    METADATA_PATH,
    _coverage_rows,
)
from windlens.uncertainty import pooled_coverage_summary

OUTPUT_PATH = Path("data/derived/validation/kelmarsh_whole_site_masking_backtest.json")

# Latitude-sorted split from data/raw/Kelmarsh_WT_static.csv (agreed 2026-10-23).
SOUTH = ["KWF1", "KWF4", "KWF6"]  # 52.3988-52.4007
NORTH = ["KWF2", "KWF3", "KWF5"]  # 52.4023-52.4038
SCENARIOS = {"south_masked_north_reference": (SOUTH, NORTH), "north_masked_south_reference": (NORTH, SOUTH)}


def assert_no_masked_peer(event: dict[str, Any], masked_group: list[str], target: str) -> None:
    """Fail loudly if any reference used by an event is in the masked half (or the target)."""

    used = {event["baseline_reference"], *event["ensemble_references"]}
    forbidden = set(masked_group) | {target}
    leaked = used & forbidden
    if leaked:
        raise AssertionError(f"whole-site mask violated: {sorted(leaked)} used as reference for {target}")


def run_whole_site_events(
    df, metadata, masked_group: list[str], surviving_group: list[str], blocks
) -> tuple[list[dict], list[dict]]:
    events, skipped = [], []
    for target in masked_group:
        for start, end in blocks:
            try:
                event = run_backtest_event(df, target, list(surviving_group), start, end, metadata_df=metadata)
            except ValueError as exc:
                skipped.append({"target": target, "block_start": start, "reason": str(exc)})
                continue
            assert_no_masked_peer(event, masked_group, target)
            event["target"] = target
            events.append(event)
    return events, skipped


def run_same_farm_comparison(df, metadata, targets: list[str], blocks) -> list[dict]:
    """The SAME targets and blocks with every other Kelmarsh turbine available -- the
    paired same-farm single-turbine number the whole-site result is compared against."""

    events = []
    all_turbines = sorted(set(df["turbine_id"]))
    for target in targets:
        for start, end in blocks:
            try:
                event = run_backtest_event(
                    df, target, [t for t in all_turbines if t != target], start, end, metadata_df=metadata
                )
            except ValueError:
                continue
            event["target"] = target
            events.append(event)
    return events


def _event_error_pct(event: dict) -> float | None:
    loss = event["ensemble"]["loss"]
    if not loss["actual_lost_kwh"]:
        return None
    return (loss["estimated_lost_kwh"] - loss["actual_lost_kwh"]) / loss["actual_lost_kwh"] * 100.0


def summarise(events: list[dict]) -> dict[str, Any]:
    aggregate = aggregate_backtest(events)
    rows = _coverage_rows(events)
    pooled = pooled_coverage_summary(
        [
            {"observations": r["observations"], "covered_observations": r["covered_observations"],
             "coverage_pct": r["coverage_pct"] or 0.0}
            for r in rows
        ]
    )
    distances = [
        item["distance_km"] * 1000.0
        for e in events
        for item in (e["dynamic_selection"] or {}).get("ranking", [])
        if item["turbine_id"] in e["ensemble_references"]
    ]
    errors = [x for x in (_event_error_pct(e) for e in events) if x is not None]
    return {
        "aggregate": aggregate,
        "pooled_coverage": pooled,
        "median_abs_event_error_pct": float(sorted(abs(x) for x in errors)[len(errors) // 2]) if errors else None,
        "reference_distance_m": {
            "min": min(distances), "mean": sum(distances) / len(distances), "max": max(distances),
        },
        "reviewable_count": aggregate["reviewable_count"],
        "event_count": aggregate["event_count"],
    }


def _group_distances_m(metadata) -> dict[str, float]:
    meta = metadata.set_index("turbine_id")
    pairs = [
        haversine_km(meta.loc[a, "latitude"], meta.loc[a, "longitude"], meta.loc[b, "latitude"], meta.loc[b, "longitude"]) * 1000
        for a in SOUTH for b in NORTH
    ]
    return {"min_m": min(pairs), "max_m": max(pairs), "mean_m": sum(pairs) / len(pairs)}


def main() -> None:
    dataset = KelmarshConnector(CANONICAL_PATH, METADATA_PATH).load()
    df, metadata = dataset.data, dataset.registry.to_frame()

    scenarios = {}
    for name, (masked, surviving) in SCENARIOS.items():
        events, skipped = run_whole_site_events(df, metadata, masked, surviving, BLOCKS)
        paired = run_same_farm_comparison(df, metadata, masked, BLOCKS)
        scenarios[name] = {
            "masked_turbines": masked,
            "surviving_reference_turbines": surviving,
            "skipped_events": skipped,
            "whole_site": summarise(events),
            "same_farm_single_turbine_same_targets_and_blocks": summarise(paired),
            "per_event": [
                {
                    "target": e["target"], "block_start": e["block_start"],
                    "estimated_lost_kwh": e["ensemble"]["loss"]["estimated_lost_kwh"],
                    "actual_lost_kwh": e["ensemble"]["loss"]["actual_lost_kwh"],
                    "error_pct": _event_error_pct(e),
                    "label": e["classification"]["label"],
                    "failed_gates": e["classification"]["failed_gates"],
                    "references": e["ensemble_references"],
                }
                for e in events
            ],
        }

    pooled_events_all = [
        pe for s in scenarios.values() for pe in s["per_event"]
    ]
    artifact = {
        "artifact_version": "kelmarsh-whole-site-masking.v1",
        "evidence_tier": TIER_WHOLE_SITE,
        "framing": WHOLE_SITE_FRAMING,
        "blocks": [list(b) for b in BLOCKS],
        "block_count": len(BLOCKS),
        "half_to_half_distance_m": _group_distances_m(metadata),
        "scenarios": scenarios,
        "n_events_total": len(pooled_events_all),
        "honesty_note": (
            "Whole-site masking is a stress test of the pipeline with zero same-farm "
            "fallback, run on references only ~300-400m (measured range above) away. It is "
            "a best-case ceiling bound. It is NOT a neighbouring-farm validation. Blocks "
            "were selected earlier (>=95% coverage of all Kelmarsh turbines) for the same-farm "
            "back-test, before this test existed; they were not re-selected here."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print(WHOLE_SITE_FRAMING)
    print("half-to-half distance (m):", {k: round(v) for k, v in artifact["half_to_half_distance_m"].items()})
    for name, s in scenarios.items():
        ws, sf = s["whole_site"], s["same_farm_single_turbine_same_targets_and_blocks"]
        print(f"\n{name}: masked {s['masked_turbines']} <- refs {s['surviving_reference_turbines']}")
        for label, x in (("whole-site", ws), ("same-farm paired", sf)):
            print(
                f"  {label:17s} n={x['event_count']:3d} WAPE {x['aggregate']['ensemble']['energy_weighted_wape_pct']:.1f}% "
                f"bias {x['aggregate']['ensemble']['signed_aggregate_bias_pct']:+.1f}% "
                f"reviewable {x['reviewable_count']}/{x['event_count']} "
                f"pooled cov {x['pooled_coverage']['pooled_coverage_pct']:.1f}% "
                f"refdist mean {x['reference_distance_m']['mean']:.0f}m"
            )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
