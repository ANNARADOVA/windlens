"""Run the Section 9 back-test: 5 held-out blocks, single-reference baseline vs.
simple peer ensemble, scored and classified per WindLens_instructions.md Section 9.
"""

from __future__ import annotations

from pathlib import Path

from windlens.backtest import aggregate_backtest, run_backtest_event
from windlens.connectors import KelmarshConnector

CANONICAL_PATH = Path("data/derived/kelmarsh_2016_90d_canonical.csv")
METADATA_PATH = Path("data/raw/Kelmarsh_WT_static.csv")
TARGET_TURBINE = "KWF1"
CANDIDATE_REFERENCE_TURBINES = ["KWF2", "KWF3", "KWF4", "KWF5", "KWF6"]

# Held-out 5-day blocks spread across the available 90-day window (May-July 2016),
# picked by inspecting per-turbine daily coverage counts for near-full coverage.
# "Weather regime" diversity is limited to what three months of one UK farm offers --
# see docs/DECISION_LOG.md for why true regime diversity isn't available here.
# CORRECTION (2026-10-23, red-team review F9): this comment used to claim none of
# these blocks overlap the spike week 2016-07-05 to 2016-07-10. That is false -- the
# 2016-07-07 to 2016-07-12 block below (also the live demo's showcased block) overlaps
# it by 3 days. Not fixed by changing the block (it is the named demo block and many
# published numbers depend on it); flagged here so the claim is no longer wrong.
BLOCKS = [
    ("2016-05-17T00:00:00Z", "2016-05-22T00:00:00Z"),
    ("2016-05-29T00:00:00Z", "2016-06-03T00:00:00Z"),
    ("2016-06-26T00:00:00Z", "2016-07-01T00:00:00Z"),
    ("2016-07-07T00:00:00Z", "2016-07-12T00:00:00Z"),
    ("2016-07-13T00:00:00Z", "2016-07-18T00:00:00Z"),
]


def run_all_blocks() -> tuple[list[dict], dict]:
    dataset = KelmarshConnector(CANONICAL_PATH, METADATA_PATH).load()
    df = dataset.data
    metadata = dataset.registry.to_frame()

    events = [
        run_backtest_event(
            df,
            TARGET_TURBINE,
            CANDIDATE_REFERENCE_TURBINES,
            start,
            end,
            metadata_df=metadata,
        )
        for start, end in BLOCKS
    ]
    summary = aggregate_backtest(events)
    return events, summary


def _print_event(event: dict) -> None:
    print(f"=== Block {event['block_start']} to {event['block_end']} ===")
    print(f"Baseline reference: {event['baseline_reference']}")
    print(f"Ensemble references: {event['ensemble_references']}")
    baseline_loss = event["baseline"]["loss"]
    ensemble_loss = event["ensemble"]["loss"]
    print(
        f"Baseline -- est {baseline_loss['estimated_lost_kwh']:.1f} kWh vs "
        f"actual {baseline_loss['actual_lost_kwh']:.1f} kWh "
        f"(wind RMSE {event['baseline']['wind_errors']['rmse_ms']:.3f} m/s)"
    )
    print(
        f"Ensemble -- est {ensemble_loss['estimated_lost_kwh']:.1f} kWh vs "
        f"actual {ensemble_loss['actual_lost_kwh']:.1f} kWh "
        f"(wind RMSE {event['ensemble']['wind_errors']['rmse_ms']:.3f} m/s)"
    )
    print(
        f"Ensemble beats baseline (lower wind RMSE): {event['beats_baseline']} | "
        f"within validated domain: {event['within_domain']} | "
        f"reference/target aligned: {event['reference_target_aligned']}"
    )
    print(
        f"Classification: {event['classification']['label']} "
        f"(failed gates: {event['classification']['failed_gates']})"
    )
    print()


def _print_summary(summary: dict) -> None:
    print("=== Back-test summary across all blocks ===")
    print(
        f"Events: {summary['event_count']}, reviewable: {summary['reviewable_count']}, "
        f"abstention rate: {summary['abstention_rate_pct']:.1f}%"
    )
    print(
        f"Baseline -- energy-weighted WAPE {summary['baseline']['energy_weighted_wape_pct']:.1f}%, "
        f"signed aggregate bias {summary['baseline']['signed_aggregate_bias_pct']:+.1f}%"
    )
    print(
        f"Ensemble -- energy-weighted WAPE {summary['ensemble']['energy_weighted_wape_pct']:.1f}%, "
        f"signed aggregate bias {summary['ensemble']['signed_aggregate_bias_pct']:+.1f}%"
    )


def main() -> None:
    events, summary = run_all_blocks()
    for event in events:
        _print_event(event)
    _print_summary(summary)


if __name__ == "__main__":
    main()
