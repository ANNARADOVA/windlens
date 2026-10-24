"""Reference-selection weighting ablation -- 2026-10-23.

Anna's brief, verbatim: "I think we should test different behaviors when
choosing the method for the most alike turbines. then we can check that we
thought about different things." The shipped `select_dynamic_references`
ranks candidate reference turbines by
``selection_score = 0.8 * behavior + 0.2 * geography`` (behavior = holdout
RMSE from a time-ordered fit; geography = inverse distance). That weighting
was never tested against alternatives before tonight -- it was chosen and
shipped. This script tests it honestly, reusing the exact same dev/report
discipline already established by `run_method_bakeoff_2026_10_23.py`:

- Reuses the LOCKED split from
  `data/derived/validation/method_bakeoff_2026_10_23.json`'s `locked_split`
  key verbatim (same blocks, same dev/report assignment) -- not a new split,
  for direct comparability with the existing bake-off results.
- All four candidate weightings are compared on the DEV subset only.
- Only after a weighting is chosen (by a stated principle, not by whichever
  dev number happens to look best) are final numbers computed, exactly once,
  on the untouched REPORT subset.

Candidates: current shipped blend (0.8/0.2), 100% behavior / 0% geography,
50/50, and 0% behavior / 100% geography (a floor/sanity check -- expected to
perform worst, included anyway per the brief, not skipped because it was
expected to lose).

Reference selection feeds every downstream number (which turbine is "the"
reference, which three form the ensemble, and their ensemble weights), so
this re-runs the full wind-first back-test pipeline (`run_backtest_event`)
per candidate weighting, on both farms, rather than inspecting the selector
in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.backtest import aggregate_backtest, run_backtest_event
from windlens.connectors import KelmarshConnector
from windlens.uncertainty import pooled_coverage_summary

from windlens.run_kelmarsh_extended_backtest import CANDIDATE_REFERENCE_TURBINES as KELMARSH_CANDIDATES
from windlens.run_kelmarsh_extended_backtest import CANONICAL_PATH as KELMARSH_CANONICAL_PATH
from windlens.run_kelmarsh_extended_backtest import METADATA_PATH as KELMARSH_METADATA_PATH
from windlens.run_kelmarsh_extended_backtest import TARGET_TURBINE as KELMARSH_TARGET
from windlens.run_hill_uncertainty_multiyear import BLOCKS_BY_YEAR as HILL_BLOCKS_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import CANONICAL_BY_YEAR as HILL_CANONICAL_BY_YEAR
from windlens.run_hill_uncertainty_multiyear import REGISTRY_PATH as HILL_REGISTRY_PATH
from windlens.run_hill_uncertainty_multiyear import TARGET_TURBINE as HILL_TARGET

LOCKED_SPLIT_PATH = Path("data/derived/validation/method_bakeoff_2026_10_23.json")
OUTPUT_PATH = Path("data/derived/validation/reference_weighting_ablation_2026_10_23.json")

# Candidates, in the order Anna specified. Each is (label, behavior_weight).
CANDIDATES: list[tuple[str, float]] = [
    ("current_80_20", 0.8),
    ("100_behavior_0_geography", 1.0),
    ("50_50", 0.5),
    ("0_behavior_100_geography", 0.0),
]


def _load_locked_split() -> dict[str, list[tuple[str, str]]]:
    """Reuse the method bake-off's locked dev/report split verbatim -- not a
    new split constructed here, so results are directly comparable."""

    with open(LOCKED_SPLIT_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)["locked_split"]
    return {
        key: [(start, end) for start, end in blocks] for key, blocks in raw.items()
    }


def _year_for_block(block_start: str) -> str:
    return block_start[:4]


def _run_kelmarsh_blocks(
    blocks: list[tuple[str, str]], behavior_weight: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dataset = KelmarshConnector(KELMARSH_CANONICAL_PATH, KELMARSH_METADATA_PATH).load()
    canonical = dataset.data
    metadata = dataset.registry.to_frame()
    events, skipped = [], []
    for start, end in blocks:
        try:
            events.append(
                run_backtest_event(
                    canonical,
                    KELMARSH_TARGET,
                    KELMARSH_CANDIDATES,
                    start,
                    end,
                    metadata_df=metadata,
                    behavior_weight=behavior_weight,
                )
            )
        except ValueError as exc:
            skipped.append({"block_start": start, "block_end": end, "reason": str(exc)})
    return events, skipped


def _run_hill_blocks(
    blocks: list[tuple[str, str]], behavior_weight: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    registry = pd.read_csv(HILL_REGISTRY_PATH)
    canonical_by_year = {
        year: pd.read_csv(path).assign(
            timestamp_utc=lambda df: pd.to_datetime(df["timestamp_utc"], utc=True)
        )
        for year, path in HILL_CANONICAL_BY_YEAR.items()
    }
    events, skipped = [], []
    for start, end in blocks:
        year = _year_for_block(start)
        canonical = canonical_by_year[year]
        candidates = sorted(set(canonical["turbine_id"]) - {HILL_TARGET})
        try:
            event = run_backtest_event(
                canonical,
                HILL_TARGET,
                candidates,
                start,
                end,
                metadata_df=registry,
                behavior_weight=behavior_weight,
            )
            event["year"] = year
            events.append(event)
        except ValueError as exc:
            skipped.append({"year": year, "block_start": start, "block_end": end, "reason": str(exc)})
    return events, skipped


def _pooled_coverage(events: list[dict[str, Any]]) -> dict[str, Any]:
    available = [
        event["ensemble"]["uncertainty"]["event_evaluation"]
        for event in events
        if event["ensemble"]["uncertainty"]["status"] == "available"
    ]
    if not available:
        return {"n_available": 0, "pooled_coverage_pct": None}
    pooled = pooled_coverage_summary(available)
    pooled["n_available"] = len(available)
    pooled["n_total"] = len(events)
    return pooled


def _per_event_kwh(events: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Compact per-block (estimated, actual) lost-kWh pairs, ensemble model --
    kept alongside the aggregate so a block-level bootstrap can check whether
    a candidate's WAPE edge over another is distinguishable from noise at
    this sample size (n=10-14 per farm), rather than asserting it."""

    return [
        {
            "block_start": event["block_start"],
            "estimated_lost_kwh": event["ensemble"]["loss"]["estimated_lost_kwh"],
            "actual_lost_kwh": event["ensemble"]["loss"]["actual_lost_kwh"],
        }
        for event in events
    ]


def _score_candidate(
    kelmarsh_blocks: list[tuple[str, str]],
    hill_blocks: list[tuple[str, str]],
    behavior_weight: float,
) -> dict[str, Any]:
    kelmarsh_events, kelmarsh_skipped = _run_kelmarsh_blocks(kelmarsh_blocks, behavior_weight)
    hill_events, hill_skipped = _run_hill_blocks(hill_blocks, behavior_weight)
    return {
        "behavior_weight": behavior_weight,
        "kelmarsh": {
            "n_blocks": len(kelmarsh_blocks),
            "skipped": kelmarsh_skipped,
            "aggregate": aggregate_backtest(kelmarsh_events) if kelmarsh_events else None,
            "pooled_coverage": _pooled_coverage(kelmarsh_events),
            "per_event_kwh": _per_event_kwh(kelmarsh_events),
        },
        "hill_of_towie": {
            "n_blocks": len(hill_blocks),
            "skipped": hill_skipped,
            "aggregate": aggregate_backtest(hill_events) if hill_events else None,
            "pooled_coverage": _pooled_coverage(hill_events),
            "per_event_kwh": _per_event_kwh(hill_events),
        },
    }


def run_dev_comparison(split: dict[str, list[tuple[str, str]]]) -> dict[str, Any]:
    """All four candidates, dev subset only -- method selection happens here."""

    results = {}
    for label, weight in CANDIDATES:
        results[label] = _score_candidate(split["kelmarsh_dev"], split["hill_of_towie_dev"], weight)
    return results


def run_report_once(
    split: dict[str, list[tuple[str, str]]], chosen_label: str, chosen_weight: float
) -> dict[str, Any]:
    """The winner's (or current's) numbers, computed exactly once on the
    untouched report subset, after the dev-only decision above is locked in."""

    return {
        "chosen_label": chosen_label,
        "chosen_behavior_weight": chosen_weight,
        "result": _score_candidate(split["kelmarsh_report"], split["hill_of_towie_report"], chosen_weight),
    }


def main() -> None:
    split = _load_locked_split()
    dev_results = run_dev_comparison(split)

    print("=== Reference-selection weighting ablation: DEV subset ===")
    for label, result in dev_results.items():
        k, h = result["kelmarsh"], result["hill_of_towie"]
        k_agg, h_agg = k["aggregate"], h["aggregate"]
        print(f"\n{label} (behavior_weight={result['behavior_weight']}):")
        if k_agg:
            print(
                f"  Kelmarsh      ensemble WAPE {k_agg['ensemble']['energy_weighted_wape_pct']:.2f}%  "
                f"bias {k_agg['ensemble']['signed_aggregate_bias_pct']:+.2f}%  "
                f"pooled coverage {k['pooled_coverage'].get('pooled_coverage_pct', 'n/a')}"
            )
        if h_agg:
            print(
                f"  Hill of Towie ensemble WAPE {h_agg['ensemble']['energy_weighted_wape_pct']:.2f}%  "
                f"bias {h_agg['ensemble']['signed_aggregate_bias_pct']:+.2f}%  "
                f"pooled coverage {h['pooled_coverage'].get('pooled_coverage_pct', 'n/a')}"
            )

    # Decision is made by hand after reading the printed dev table (see
    # docs/DECISION_LOG.md's 2026-10-23 entry for the stated principle used);
    # this script does not auto-pick a winner from the numbers.
    artifact = {
        "artifact_version": "reference-weighting-ablation.v1",
        "locked_split_source": str(LOCKED_SPLIT_PATH),
        "candidates": [label for label, _ in CANDIDATES],
        "dev": dev_results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, default=str)
    print(f"\nDev-subset artifact written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
