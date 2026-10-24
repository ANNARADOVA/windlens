from __future__ import annotations

import unittest

import pandas as pd

from windlens.coverage import expected_slot_count, simultaneous_overlap, turbine_coverage


def _df(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"timestamp_utc": ts, "turbine_id": turbine} for ts, turbine in rows]
    )


class ExpectedSlotCountTests(unittest.TestCase):
    def test_counts_ten_minute_slots_in_a_one_hour_window(self) -> None:
        self.assertEqual(
            expected_slot_count("2016-07-05T00:00:00Z", "2016-07-05T01:00:00Z"), 6
        )

    def test_raises_when_start_is_not_before_end(self) -> None:
        with self.assertRaises(ValueError):
            expected_slot_count("2016-07-05T01:00:00Z", "2016-07-05T00:00:00Z")


class TurbineCoverageTests(unittest.TestCase):
    def test_full_coverage_has_no_gaps(self) -> None:
        timestamps = [
            "2016-07-05T00:00:00Z",
            "2016-07-05T00:10:00Z",
            "2016-07-05T00:20:00Z",
            "2016-07-05T00:30:00Z",
            "2016-07-05T00:40:00Z",
        ]
        df = _df([(ts, "KWF1") for ts in timestamps])

        result = turbine_coverage(df, "KWF1", "2016-07-05T00:00:00Z", "2016-07-05T00:50:00Z")

        self.assertEqual(result["expected_slots"], 5)
        self.assertEqual(result["actual_valid_slots"], 5)
        self.assertAlmostEqual(result["coverage_pct"], 100.0)
        self.assertEqual(result["contiguous_gaps"], [])

    def test_reports_internal_leading_and_trailing_gaps_separately(self) -> None:
        # Window covers slots at :00,:10,:20,:30,:40 (5 slots). Only :00 and :20 present,
        # giving an internal gap at :10 and a trailing gap covering :30 and :40.
        df = _df([("2016-07-05T00:00:00Z", "KWF1"), ("2016-07-05T00:20:00Z", "KWF1")])

        result = turbine_coverage(df, "KWF1", "2016-07-05T00:00:00Z", "2016-07-05T00:50:00Z")

        self.assertEqual(result["expected_slots"], 5)
        self.assertEqual(result["actual_valid_slots"], 2)
        self.assertEqual(
            result["contiguous_gaps"],
            [
                {
                    "gap_start_utc": "2016-07-05T00:10:00Z",
                    "gap_end_utc": "2016-07-05T00:20:00Z",
                    "missing_slots": 1,
                },
                {
                    "gap_start_utc": "2016-07-05T00:30:00Z",
                    "gap_end_utc": "2016-07-05T00:50:00Z",
                    "missing_slots": 2,
                },
            ],
        )

    def test_reports_a_leading_gap_when_the_first_reading_is_late(self) -> None:
        df = _df([("2016-07-05T00:20:00Z", "KWF1")])

        result = turbine_coverage(df, "KWF1", "2016-07-05T00:00:00Z", "2016-07-05T00:30:00Z")

        self.assertEqual(
            result["contiguous_gaps"],
            [
                {
                    "gap_start_utc": "2016-07-05T00:00:00Z",
                    "gap_end_utc": "2016-07-05T00:20:00Z",
                    "missing_slots": 2,
                }
            ],
        )

    def test_entirely_missing_turbine_is_one_gap_spanning_the_whole_window(self) -> None:
        df = _df([("2016-07-05T00:00:00Z", "KWF2")])

        result = turbine_coverage(df, "KWF1", "2016-07-05T00:00:00Z", "2016-07-05T00:30:00Z")

        self.assertEqual(result["actual_valid_slots"], 0)
        self.assertEqual(
            result["contiguous_gaps"],
            [
                {
                    "gap_start_utc": "2016-07-05T00:00:00Z",
                    "gap_end_utc": "2016-07-05T00:30:00Z",
                    "missing_slots": 3,
                }
            ],
        )


class SimultaneousOverlapTests(unittest.TestCase):
    def test_counts_only_timestamps_valid_for_both_turbines(self) -> None:
        df = _df(
            [
                ("2016-07-05T00:00:00Z", "KWF1"),
                ("2016-07-05T00:10:00Z", "KWF1"),
                ("2016-07-05T00:00:00Z", "KWF2"),
                ("2016-07-05T00:20:00Z", "KWF2"),
            ]
        )

        result = simultaneous_overlap(
            df, "KWF1", "KWF2", "2016-07-05T00:00:00Z", "2016-07-05T00:30:00Z"
        )

        self.assertEqual(result["target_valid_slots"], 2)
        self.assertEqual(result["reference_valid_slots"], 2)
        self.assertEqual(result["simultaneous_valid_slots"], 1)


if __name__ == "__main__":
    unittest.main()
