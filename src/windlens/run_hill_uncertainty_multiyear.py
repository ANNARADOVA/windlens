"""Expanded Hill of Towie uncertainty-coverage back-test: 28 non-overlapping 5-day
blocks across 2024, 2025, and 2026 (the original 3, 2026-only, re-run for pipeline
consistency, plus 25 new ones spanning three years), instead of just 3 blocks confined
to March-April 2026.

Why: 3 blocks is too small a sample to honestly claim a 90%-of-blocks coverage rate is
or isn't met (see cross-session brief, 2026-10-21/22). Each year's canonical dataset is
loaded and scored separately (pre-event history for a block never crosses a year
boundary into a different file), exactly as the existing multi-year WAPE sweep
(run_hill_multiyear_sweep.py) already does; the resulting events are then combined into
one aggregate, reusing the same calibrated pipeline (windlens.backtest) used for Kelmarsh
and for the original 3-block Hill of Towie run (run_hill_backtest.py).

Block selection: for each year, every 5-day window with >=95% coverage for the target
turbine T01 was found by scanning that year's canonical dataset (see
docs/DECISION_LOG.md, 2026-10-22 entry). One such window per calendar month was picked
for 2024 and 2025 (11 months each -- data effectively starts late January once a 30-day
calibration margin is required); for 2026, the original 3 blocks are kept and 3 more
added in months not already covered (Feb, a second March window, a second April window).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from windlens.backtest import aggregate_backtest, run_backtest_event
from windlens.checksums import file_md5
from windlens.uncertainty import pooled_coverage_summary

REGISTRY_PATH = Path("data/raw/hill_of_towie/hill_of_towie_registry.csv")
OUTPUT_PATH = Path("data/derived/validation/hill_of_towie_multiyear_uncertainty_backtest.json")
TARGET_TURBINE = "T01"

CANONICAL_BY_YEAR = {
    "2024": Path("data/derived/validation/hill_of_towie_2024_canonical.csv"),
    "2025": Path("data/derived/validation/hill_of_towie_2025_canonical.csv"),
    "2026": Path("data/derived/validation/hill_of_towie_2026_canonical.csv"),
}

BLOCKS_BY_YEAR = {
    "2024": [
        ("2024-02-05T00:00:00Z", "2024-02-10T00:00:00Z"),
        ("2024-03-11T00:00:00Z", "2024-03-16T00:00:00Z"),
        ("2024-04-15T00:00:00Z", "2024-04-20T00:00:00Z"),
        ("2024-05-20T00:00:00Z", "2024-05-25T00:00:00Z"),
        ("2024-06-14T00:00:00Z", "2024-06-19T00:00:00Z"),
        ("2024-07-14T00:00:00Z", "2024-07-19T00:00:00Z"),
        ("2024-08-13T00:00:00Z", "2024-08-18T00:00:00Z"),
        ("2024-09-12T00:00:00Z", "2024-09-17T00:00:00Z"),
        ("2024-10-12T00:00:00Z", "2024-10-17T00:00:00Z"),
        ("2024-11-11T00:00:00Z", "2024-11-16T00:00:00Z"),
        ("2024-12-11T00:00:00Z", "2024-12-16T00:00:00Z"),
    ],
    "2025": [
        ("2025-02-10T00:00:00Z", "2025-02-15T00:00:00Z"),
        ("2025-03-12T00:00:00Z", "2025-03-17T00:00:00Z"),
        ("2025-04-11T00:00:00Z", "2025-04-16T00:00:00Z"),
        ("2025-05-11T00:00:00Z", "2025-05-16T00:00:00Z"),
        ("2025-06-10T00:00:00Z", "2025-06-15T00:00:00Z"),
        ("2025-07-10T00:00:00Z", "2025-07-15T00:00:00Z"),
        ("2025-08-14T00:00:00Z", "2025-08-19T00:00:00Z"),
        ("2025-09-03T00:00:00Z", "2025-09-08T00:00:00Z"),
        ("2025-10-13T00:00:00Z", "2025-10-18T00:00:00Z"),
        ("2025-11-12T00:00:00Z", "2025-11-17T00:00:00Z"),
        ("2025-12-12T00:00:00Z", "2025-12-17T00:00:00Z"),
    ],
    "2026": [
        # Original 3 (run_hill_backtest.py, 2026-10-20/21):
        ("2026-03-01T00:00:00Z", "2026-03-06T00:00:00Z"),
        ("2026-04-01T00:00:00Z", "2026-04-06T00:00:00Z"),
        ("2026-04-15T00:00:00Z", "2026-04-20T00:00:00Z"),
        # New, in months not already covered:
        ("2026-02-10T00:00:00Z", "2026-02-15T00:00:00Z"),
        ("2026-03-17T00:00:00Z", "2026-03-22T00:00:00Z"),
        ("2026-04-21T00:00:00Z", "2026-04-26T00:00:00Z"),
    ],
}


def run_all_blocks() -> tuple[list[dict], dict, list[dict]]:
    events = []
    skipped = []
    for year, canonical_path in CANONICAL_BY_YEAR.items():
        canonical = pd.read_csv(canonical_path)
        canonical["timestamp_utc"] = pd.to_datetime(canonical["timestamp_utc"], utc=True)
        registry = pd.read_csv(REGISTRY_PATH)
        candidates = sorted(set(canonical["turbine_id"]) - {TARGET_TURBINE})
        for block_start, block_end in BLOCKS_BY_YEAR[year]:
            try:
                event = run_backtest_event(
                    canonical,
                    TARGET_TURBINE,
                    candidates,
                    block_start,
                    block_end,
                    ensemble_size=3,
                    metadata_df=registry,
                )
                event["year"] = year
                events.append(event)
            except ValueError as exc:
                skipped.append({"year": year, "block_start": block_start, "block_end": block_end, "reason": str(exc)})
    summary = aggregate_backtest(events)
    return events, summary, skipped


def _coverage_rows(events: list[dict]) -> list[dict]:
    rows = []
    for event in events:
        ev = event["ensemble"]["uncertainty"].get("event_evaluation", {})
        coverage_pct = ev.get("coverage_pct")
        rows.append(
            {
                "year": event["year"],
                "block_start": event["block_start"],
                "block_end": event["block_end"],
                "month": event["block_start"][5:7],
                "coverage_pct": coverage_pct,
                "observations": ev.get("observations", 0),
                "covered_observations": ev.get("covered_observations", 0),
                # Kept as a secondary diagnostic, not the headline (see F4 below).
                "meets_90pct_target": (coverage_pct or 0) >= 90.0,
            }
        )
    return rows


def main() -> None:
    events, summary, skipped = run_all_blocks()
    rows = _coverage_rows(events)
    meeting = sum(row["meets_90pct_target"] for row in rows)
    mean_coverage = sum(row["coverage_pct"] or 0 for row in rows) / len(rows)
    pooled = pooled_coverage_summary(
        [{"observations": row["observations"], "covered_observations": row["covered_observations"],
          "coverage_pct": row["coverage_pct"] or 0.0} for row in rows]
    )

    artifact = {
        "artifact_version": "hill-of-towie-multiyear-uncertainty-backtest.v1",
        "farm_id": "Hill of Towie",
        "target_turbine": TARGET_TURBINE,
        "registry_path": str(REGISTRY_PATH),
        "registry_md5": file_md5(REGISTRY_PATH),
        "canonical_paths": {year: str(path) for year, path in CANONICAL_BY_YEAR.items()},
        "block_count": sum(len(b) for b in BLOCKS_BY_YEAR.values()),
        "scored_event_count": len(events),
        "skipped_events": skipped,
        "aggregate": summary,
        "uncertainty_coverage": {
            # 2026-10-22 red-team review (F4): see run_kelmarsh_extended_backtest.py's
            # identical comment -- "% of blocks individually >= 90%" is not a
            # meaningful target; pooled coverage is the headline now.
            "pooled_coverage": pooled,
            "blocks_meeting_90pct_target_NOT_A_MEANINGFUL_TARGET": meeting,
            "total_blocks": len(rows),
            "pct_of_blocks_meeting_target_NOT_A_MEANINGFUL_TARGET": meeting / len(rows) * 100,
            "mean_coverage_pct": mean_coverage,
            "per_block": rows,
        },
        "kelmarsh_training_used": False,
        "model_training_mixed_with_kelmarsh": False,
        "honesty_note": (
            "28 blocks total across 2024, 2025, and 2026: the original 3 (2026-03/04, "
            "re-run here for pipeline consistency) plus 25 new non-overlapping held-out "
            "windows, roughly one per calendar month per year where >=95%-coverage data "
            "exists for the target turbine. Each block's pre-event history and reference "
            "selection use only data within that block's own calendar-year canonical "
            "file -- no cross-year or cross-farm leakage. "
            "CORRECTED 2026-10-22 (late), red-team review F3: the previous wording here "
            "('a genuinely external farm, not same-farm, unlike Kelmarsh') was misleading. "
            "Hill of Towie IS a different wind farm from Kelmarsh, but its REFERENCE "
            "turbines, like Kelmarsh's, are same-farm peers of the target (nearest four "
            "at 0.34-0.52 km, same turbine model) -- not turbines on a neighbouring farm. "
            "The BayWa challenge (WindLens_instructions.md) specifically asks for "
            "reconstruction from a NEIGHBOURING farm's reference data during a whole-farm "
            "outage, where same-farm peers would be dark too. Neither this back-test nor "
            "Kelmarsh's tests that scenario; both are single-turbine, same-farm proxy "
            "reconstruction. See README.md's 'Validated scope' section."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Scored {len(events)}/{artifact['block_count']} blocks ({len(skipped)} skipped)")
    for s in skipped:
        print(f"  skipped {s['year']} {s['block_start']}: {s['reason']}")
    print(
        f"Pooled coverage (headline, F4-corrected): {pooled['pooled_coverage_pct']:.1f}% "
        f"over {pooled['total_observations']} observations"
    )
    print(
        f"Per-block coverage spread: mean {pooled['per_block_coverage_mean_pct']:.1f}%, "
        f"std {pooled['per_block_coverage_std_pct']:.1f}pp, "
        f"range [{pooled['per_block_coverage_min_pct']:.1f}%, {pooled['per_block_coverage_max_pct']:.1f}%]"
    )
    print(
        f"(secondary, not a meaningful target) blocks individually >=90%: "
        f"{meeting}/{len(rows)} ({meeting / len(rows) * 100:.1f}%)"
    )
    print(f"Mean coverage: {mean_coverage:.1f}%")
    print(f"Ensemble WAPE: {summary['ensemble']['energy_weighted_wape_pct']:.1f}%")
    print(f"Baseline WAPE: {summary['baseline']['energy_weighted_wape_pct']:.1f}%")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
