from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from windlens.backtest import (
    aggregate_backtest,
    input_qa_check,
    reconstruction_completeness,
    run_backtest_event,
)
from windlens.review_gate import REVIEWABLE, UNVERIFIED

_EPOCH = datetime(2016, 7, 1, tzinfo=timezone.utc)


def _timestamps(n: int, start_minute: int = 0) -> list[str]:
    start = _EPOCH + timedelta(minutes=start_minute)
    return [
        (start + timedelta(minutes=10 * i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(n)
    ]


def _synthetic_canonical_df() -> pd.DataFrame:
    """A target turbine plus three references, all linearly related pre-outage, with
    enough paired observations to clear the alignment threshold, and a held-out block
    squarely inside the references' observed training range.
    """

    n_pre = 1000
    n_block = 6
    pre_timestamps = _timestamps(n_pre)
    block_timestamps = _timestamps(n_block, start_minute=10000)

    rng = np.random.default_rng(42)
    reference_speeds = {
        "KWF2": np.linspace(3.0, 10.0, n_pre),
        "KWF3": np.linspace(3.5, 9.5, n_pre) + rng.normal(0, 0.1, n_pre),
        "KWF4": np.linspace(2.5, 10.5, n_pre) + rng.normal(0, 0.2, n_pre),
    }
    target_speed_pre = reference_speeds["KWF2"] * 1.0  # exact relationship to KWF2

    rated_power = 2050.0

    def _power(wind_speed: np.ndarray) -> np.ndarray:
        return np.clip(wind_speed * 150.0, 0.0, rated_power)

    frames = [
        pd.DataFrame(
            {
                "timestamp_utc": pre_timestamps,
                "turbine_id": "KWF1",
                "wind_speed_ms": target_speed_pre,
                "active_power_kw": _power(target_speed_pre),
            }
        )
    ]
    for turbine, speeds in reference_speeds.items():
        frames.append(
            pd.DataFrame(
                {
                    "timestamp_utc": pre_timestamps,
                    "turbine_id": turbine,
                    "wind_speed_ms": speeds,
                    "active_power_kw": _power(speeds),
                }
            )
        )

    # Held-out block: KWF1 "hidden truth" plus in-domain reference readings.
    block_target_speed = np.array([5.0, 5.5, 6.0, 6.5, 7.0, 7.5])
    frames.append(
        pd.DataFrame(
            {
                "timestamp_utc": block_timestamps,
                "turbine_id": "KWF1",
                "wind_speed_ms": block_target_speed,
                "active_power_kw": _power(block_target_speed),
            }
        )
    )
    for turbine in reference_speeds:
        frames.append(
            pd.DataFrame(
                {
                    "timestamp_utc": block_timestamps,
                    "turbine_id": turbine,
                    "wind_speed_ms": block_target_speed,  # same values -> in-domain
                    "active_power_kw": _power(block_target_speed),
                }
            )
        )

    return pd.concat(frames, ignore_index=True)


class RunBacktestEventTests(unittest.TestCase):
    def test_runs_end_to_end_with_sane_structure_on_a_well_behaved_block(self) -> None:
        # The synthetic target is an exact function of KWF2, so KWF2 is the (perfect)
        # baseline here -- this test exercises the full wiring and the domain/alignment
        # gates, not whether the ensemble beats an unbeatable baseline (that gate logic
        # is already covered directly in tests/test_review_gate.py).
        df = _synthetic_canonical_df()
        block_timestamps = _timestamps(6, start_minute=10000)
        block_start = block_timestamps[0]
        block_end = (
            datetime.strptime(block_timestamps[-1], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            + timedelta(minutes=10)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        event = run_backtest_event(df, "KWF1", ["KWF2", "KWF3", "KWF4"], block_start, block_end)

        self.assertEqual(event["baseline_reference"], "KWF2")
        self.assertIn("KWF2", event["ensemble_references"])
        self.assertTrue(event["within_domain"])
        self.assertTrue(event["reference_target_aligned"])
        # 2026-10-22 red-team review (F13): `assertIn(label, (REVIEWABLE, UNVERIFIED))`
        # can't fail on a real calibration/gating bug since it accepts either outcome.
        # This fixture is fully clean (exact linear target, in-domain block, complete
        # coverage, 1000 pre-event calibration observations), so the only honest
        # expectation is REVIEWABLE with no failed gates -- asserted directly.
        self.assertEqual(event["classification"]["label"], REVIEWABLE)
        self.assertEqual(event["classification"]["failed_gates"], [])
        self.assertIn("estimated_lost_kwh", event["baseline"]["loss"])
        self.assertIn("estimated_lost_kwh", event["ensemble"]["loss"])
        self.assertIn("uncertainty", event["baseline"])
        self.assertIn("coverage_pct", event["baseline"]["uncertainty"]["event_evaluation"])
        self.assertAlmostEqual(event["baseline"]["wind_errors"]["rmse_ms"], 0.0, places=6)

    def test_raises_when_the_target_has_no_rows_in_the_block(self) -> None:
        df = _synthetic_canonical_df()
        with self.assertRaises(ValueError):
            run_backtest_event(
                df, "KWF1", ["KWF2", "KWF3", "KWF4"], "2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"
            )

    def test_mislabels_an_incompletely_covered_block_without_the_completeness_gate(self) -> None:
        # 2026-10-22 red-team review (F2) reproduced directly: a reference that only
        # reports for a fraction of the event window must not be labelled reviewable.
        df = _synthetic_canonical_df()
        block_timestamps = _timestamps(6, start_minute=10000)
        block_start = block_timestamps[0]
        block_end = (
            datetime.strptime(block_timestamps[-1], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            + timedelta(minutes=10)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Drop every reference reading after the first two timestamps in the block, so
        # the reconstruction can only cover 2 of the 6 expected rows (33%).
        sparse_block_timestamps = set(block_timestamps[2:])
        sparse_df = df[
            ~(
                df["turbine_id"].isin(["KWF2", "KWF3", "KWF4"])
                & df["timestamp_utc"].isin(sparse_block_timestamps)
            )
        ]

        event = run_backtest_event(
            sparse_df, "KWF1", ["KWF2", "KWF3", "KWF4"], block_start, block_end
        )

        self.assertLess(event["completeness"]["completeness_pct"], 90.0)
        self.assertIn("completeness", event["classification"]["failed_gates"])
        self.assertEqual(event["classification"]["label"], UNVERIFIED)

        # 2026-10-22 red-team review (F6): estimated and actual kWh must be
        # integrated over the SAME (matched) timestamps. Before the fix, actual_kwh
        # was integrated over the full 6-row window regardless of how few rows the
        # reconstruction covered, so a sparse reference silently deflated the
        # estimate relative to a full-window truth it was never trying to match.
        # The first 2 of 6 block timestamps are [5.0, 5.5] m/s (see
        # _synthetic_canonical_df's block_target_speed) -- only those 2 rows have a
        # surviving reference reading, so only those 2 should count as "actual".
        matched_power_kw = np.clip(np.array([5.0, 5.5]) * 150.0, 0.0, 2050.0)
        expected_actual_kwh = float(np.sum(matched_power_kw) * (10 / 60))
        self.assertAlmostEqual(
            event["ensemble"]["loss"]["actual_lost_kwh"], expected_actual_kwh, places=2
        )


class RunBacktestEventDynamicSelectionTests(unittest.TestCase):
    # 2026-10-22 red-team review (F13): "No test exercises
    # run_backtest_event(..., metadata_df=...), the dynamic-selection path every
    # published number uses. test_backtest only runs the metadata_df=None branch."
    # This fixture mirrors _synthetic_canonical_df but adds turbine metadata so
    # the metadata_df branch (select_dynamic_references) actually runs end to end.

    def _metadata(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "turbine_id": ["KWF1", "KWF2", "KWF3", "KWF4"],
                "latitude": [52.4, 52.401, 52.45, 52.5],
                "longitude": [-0.94, -0.941, -0.95, -0.96],
            }
        )

    def test_dynamic_selection_path_runs_end_to_end_and_picks_the_best_behaved_reference(
        self,
    ) -> None:
        df = _synthetic_canonical_df()
        metadata = self._metadata()
        block_timestamps = _timestamps(6, start_minute=10000)
        block_start = block_timestamps[0]
        block_end = (
            datetime.strptime(block_timestamps[-1], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            + timedelta(minutes=10)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        event = run_backtest_event(
            df, "KWF1", ["KWF2", "KWF3", "KWF4"], block_start, block_end, metadata_df=metadata
        )

        # KWF2 is the target's exact linear function (zero RMSE); the dynamic
        # selector must pick it as the baseline reference and the path must
        # actually populate dynamic_selection (proving metadata_df=None was not
        # silently still in effect).
        self.assertIsNotNone(event["dynamic_selection"])
        self.assertEqual(event["dynamic_selection"]["status"], "selected")
        self.assertEqual(event["baseline_reference"], "KWF2")
        self.assertEqual(event["dynamic_selection"]["selected"], "KWF2")
        self.assertAlmostEqual(sum(event["reference_weights"].values()), 1.0)
        self.assertEqual(event["classification"]["label"], REVIEWABLE)


class ReconstructionCompletenessTests(unittest.TestCase):
    def test_full_coverage_is_100_percent(self) -> None:
        reconstruction = pd.DataFrame({"timestamp_utc": _timestamps(6, start_minute=10000)})
        result = reconstruction_completeness(
            reconstruction, "2016-07-07T22:40:00Z", "2016-07-07T23:40:00Z"
        )
        self.assertEqual(result["expected_rows"], 6)
        self.assertEqual(result["covered_rows"], 6)
        self.assertAlmostEqual(result["completeness_pct"], 100.0)

    def test_partial_coverage_is_reported_honestly(self) -> None:
        reconstruction = pd.DataFrame({"timestamp_utc": _timestamps(2, start_minute=10000)})
        result = reconstruction_completeness(
            reconstruction, "2016-07-07T22:40:00Z", "2016-07-07T23:40:00Z"
        )
        self.assertAlmostEqual(result["completeness_pct"], 2 / 6 * 100.0)


class InputQaCheckTests(unittest.TestCase):
    def test_passes_on_clean_data(self) -> None:
        df = _synthetic_canonical_df()
        result = input_qa_check(df, {"KWF1", "KWF2"})
        self.assertTrue(result["passed"])
        self.assertEqual(result["duplicate_count"], 0)

    def test_fails_on_duplicate_timestamp_rows_for_a_used_turbine(self) -> None:
        df = _synthetic_canonical_df()
        duplicated_row = df[df["turbine_id"] == "KWF2"].iloc[[0]]
        dirty_df = pd.concat([df, duplicated_row], ignore_index=True)
        result = input_qa_check(dirty_df, {"KWF1", "KWF2"})
        self.assertFalse(result["passed"])
        self.assertEqual(result["duplicate_count"], 2)

    def test_ignores_duplicates_on_turbines_the_event_does_not_use(self) -> None:
        df = _synthetic_canonical_df()
        duplicated_row = df[df["turbine_id"] == "KWF3"].iloc[[0]]
        dirty_df = pd.concat([df, duplicated_row], ignore_index=True)
        result = input_qa_check(dirty_df, {"KWF1", "KWF2"})
        self.assertTrue(result["passed"])


class AggregateBacktestTests(unittest.TestCase):
    def test_aggregates_wape_and_bias_and_counts_reviewable_events(self) -> None:
        def _event(estimated, actual, label):
            return {
                "baseline": {"loss": {"estimated_lost_kwh": estimated, "actual_lost_kwh": actual}},
                "ensemble": {"loss": {"estimated_lost_kwh": estimated, "actual_lost_kwh": actual}},
                "classification": {"label": label, "failed_gates": [] if label == REVIEWABLE else ["x"]},
            }

        events = [
            _event(110.0, 100.0, REVIEWABLE),
            _event(90.0, 100.0, "Unverified -- manual evidence required"),
        ]

        summary = aggregate_backtest(events)

        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["reviewable_count"], 1)
        self.assertAlmostEqual(summary["abstention_rate_pct"], 50.0)
        self.assertAlmostEqual(summary["baseline"]["signed_aggregate_bias_pct"], 0.0)

    def test_raises_on_empty_event_list(self) -> None:
        with self.assertRaises(ValueError):
            aggregate_backtest([])


if __name__ == "__main__":
    unittest.main()
