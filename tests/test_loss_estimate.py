from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.loss_estimate import (
    energy_weighted_wape,
    estimate_loss,
    infer_interval_hours,
    integrate_energy_kwh,
    signed_aggregate_bias_pct,
    wind_speed_errors,
)


class IntegrateEnergyKwhTests(unittest.TestCase):
    def test_sums_power_readings_at_ten_minute_cadence(self) -> None:
        # Six readings of 600 kW each, 10 minutes apart = 1 hour total = 600 kWh.
        power_kw = [600.0] * 6
        self.assertAlmostEqual(integrate_energy_kwh(power_kw), 600.0)

    def test_zero_power_gives_zero_energy(self) -> None:
        self.assertEqual(integrate_energy_kwh([0.0, 0.0, 0.0]), 0.0)

    def test_accepts_a_non_default_interval(self) -> None:
        # 2026-10-24 independent review finding #5: the cadence must be an
        # explicit parameter, not always the hardcoded 10-minute constant --
        # six hourly readings of 600 kW is 3600 kWh, not the 600 kWh that the
        # default 10-minute assumption would silently produce.
        power_kw = [600.0] * 6
        self.assertAlmostEqual(integrate_energy_kwh(power_kw, interval_hours=1.0), 3600.0)


class InferIntervalHoursTests(unittest.TestCase):
    def test_infers_ten_minute_cadence(self) -> None:
        timestamps = [f"2026-01-01T00:{10 * i:02d}:00Z" for i in range(6)]
        self.assertAlmostEqual(infer_interval_hours(timestamps), 10 / 60)

    def test_infers_hourly_cadence(self) -> None:
        timestamps = [f"2026-01-01T{h:02d}:00:00Z" for h in range(5)]
        self.assertAlmostEqual(infer_interval_hours(timestamps), 1.0)

    def test_order_of_input_does_not_matter(self) -> None:
        timestamps = ["2026-01-01T02:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]
        self.assertAlmostEqual(infer_interval_hours(timestamps), 1.0)

    def test_raises_on_fewer_than_two_distinct_timestamps(self) -> None:
        with self.assertRaises(ValueError):
            infer_interval_hours(["2026-01-01T00:00:00Z"])
        with self.assertRaises(ValueError):
            infer_interval_hours(["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"])

    def test_rejects_irregular_spacing(self) -> None:
        # Mostly 10-minute gaps, but one 60-minute gap -- an uploaded file with
        # a real hole in it, not a genuine hourly cadence; must be rejected
        # rather than averaged into a meaningless median.
        timestamps = [
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:10:00Z",
            "2026-01-01T00:20:00Z",
            "2026-01-01T01:20:00Z",
            "2026-01-01T01:30:00Z",
        ]
        with self.assertRaises(ValueError):
            infer_interval_hours(timestamps)

    def test_tolerates_a_single_one_off_gap_among_many(self) -> None:
        # 2026-10-24 live-verification finding: the real BayWa sample files have
        # exactly 1 irregular gap out of 12,959 (a dropped/duplicate reading, not
        # a wrong cadence) -- this must NOT raise, unlike test_rejects_irregular_spacing
        # above where 1 of just 4 gaps (25%) is irregular. 500 ten-minute gaps plus
        # one 60-minute gap is well under the 2% irregular-fraction threshold.
        base = pd.Timestamp("2026-01-01T00:00:00Z")
        timestamps = [(base + pd.Timedelta(minutes=10 * i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(300)]
        # Insert one 60-minute gap by skipping 5 of the regular 10-minute slots.
        skip_from = 150
        timestamps = timestamps[:skip_from] + [
            (base + pd.Timedelta(minutes=10 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            for i in range(skip_from + 5, 300 + 5)
        ]
        self.assertAlmostEqual(infer_interval_hours(timestamps), 10 / 60, places=4)


class WindSpeedErrorsTests(unittest.TestCase):
    def test_computes_mae_rmse_and_signed_bias_on_overlapping_timestamps(self) -> None:
        reconstructed = pd.DataFrame(
            {
                "timestamp_utc": ["t0", "t1", "t2"],
                "wind_speed_ms_reconstructed": [5.0, 6.0, 7.0],
            }
        )
        hidden_truth = pd.DataFrame(
            {"timestamp_utc": ["t0", "t1", "t2"], "wind_speed_ms": [6.0, 6.0, 6.0]}
        )

        result = wind_speed_errors(reconstructed, hidden_truth)

        # errors: -1, 0, +1
        self.assertEqual(result["compared_observations"], 3)
        self.assertAlmostEqual(result["mae_ms"], 2 / 3)
        self.assertAlmostEqual(result["rmse_ms"], (2 / 3) ** 0.5)
        self.assertAlmostEqual(result["signed_bias_ms"], 0.0)

    def test_raises_when_no_timestamps_overlap(self) -> None:
        reconstructed = pd.DataFrame(
            {"timestamp_utc": ["t0"], "wind_speed_ms_reconstructed": [5.0]}
        )
        hidden_truth = pd.DataFrame({"timestamp_utc": ["t9"], "wind_speed_ms": [5.0]})

        with self.assertRaises(ValueError):
            wind_speed_errors(reconstructed, hidden_truth)


class EstimateLossTests(unittest.TestCase):
    def test_compares_estimated_and_actual_kwh(self) -> None:
        expected_power_kw = np.array([600.0] * 6)  # 600 kWh
        actual_power_kw = np.array([660.0] * 6)  # 660 kWh

        result = estimate_loss(expected_power_kw, actual_power_kw)

        self.assertAlmostEqual(result["estimated_lost_kwh"], 600.0)
        self.assertAlmostEqual(result["actual_lost_kwh"], 660.0)
        self.assertAlmostEqual(result["absolute_error_kwh"], 60.0)
        self.assertAlmostEqual(result["relative_error_pct"], 60.0 / 660.0 * 100)

    def test_silently_integrates_mismatched_length_arrays_independently(self) -> None:
        # 2026-10-22 red-team review (F6/F13): estimate_loss has NO timestamp
        # awareness -- it just integrates whatever two arrays it is given, even
        # different lengths, as this test demonstrates directly (documenting the
        # hazard, not asserting it is desirable). This is exactly what let the F6
        # bug happen: backtest.py's old scorer passed a short (gappy) estimated
        # array and a full-length hidden-truth array straight into this function
        # with no inner join first, so the actual_lost_kwh silently covered more
        # timestamps than estimated_lost_kwh ever reconstructed. The fix lives in
        # the caller (backtest.py's `_score` now inner-joins on timestamp_utc
        # before calling this function -- see tests/test_backtest.py's
        # `test_mislabels_an_incompletely_covered_block_without_the_completeness_
        # gate` for that caller-level regression test); this function's contract
        # is, and must stay, "the caller is responsible for alignment".
        expected_power_kw = np.array([600.0, 600.0])  # 2 readings -> 200 kWh
        actual_power_kw = np.array([600.0, 600.0, 600.0, 600.0, 600.0, 600.0])  # 6 -> 600 kWh

        result = estimate_loss(expected_power_kw, actual_power_kw)

        self.assertAlmostEqual(result["estimated_lost_kwh"], 200.0)
        self.assertAlmostEqual(result["actual_lost_kwh"], 600.0)
        self.assertAlmostEqual(result["absolute_error_kwh"], 400.0)


class EnergyWeightedWapeTests(unittest.TestCase):
    def test_divides_by_total_actual_not_per_event_actual(self) -> None:
        # Event 1: actual near-zero (would blow up MAPE), event 2: actual large.
        estimated = [5.0, 100.0]
        actual = [0.1, 110.0]

        result = energy_weighted_wape(estimated, actual)

        # sum(|est-actual|) = |5-0.1| + |100-110| = 4.9 + 10 = 14.9
        # sum(actual) = 110.1 -> WAPE = 14.9/110.1*100
        self.assertAlmostEqual(result, 14.9 / 110.1 * 100)

    def test_raises_when_total_actual_is_zero(self) -> None:
        with self.assertRaises(ValueError):
            energy_weighted_wape([1.0], [0.0])


class SignedAggregateBiasPctTests(unittest.TestCase):
    def test_positive_bias_means_systematic_overestimate(self) -> None:
        result = signed_aggregate_bias_pct([110.0, 110.0], [100.0, 100.0])
        self.assertAlmostEqual(result, 10.0)

    def test_negative_bias_means_systematic_underestimate(self) -> None:
        result = signed_aggregate_bias_pct([90.0, 90.0], [100.0, 100.0])
        self.assertAlmostEqual(result, -10.0)


if __name__ == "__main__":
    unittest.main()
