from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.direct_power_uncertainty import (
    calibrate_and_evaluate_direct_power_interval,
    fit_direct_power,
    predict_direct_power,
    reference_operating_state_check,
)


def _timestamps(n: int, start_hour: int = 0) -> list[str]:
    return [
        f"2016-07-{1 + (start_hour * 6 + i) // 144:02d}T"
        f"{((start_hour * 6 + i) // 6) % 24:02d}:{(i % 6) * 10:02d}:00Z"
        for i in range(n)
    ]


def _frame(
    timestamps: list[str], turbine_id: str, power: np.ndarray, wind_speed_ms: np.ndarray | None = None
) -> pd.DataFrame:
    # Default wind speed (8 m/s, well above cut-in) represents a healthy, not-stopped
    # reference by default, so existing fixtures pass the new operating-state check
    # unless a test deliberately overrides wind_speed_ms to simulate a stop.
    wind = np.full(len(power), 8.0) if wind_speed_ms is None else wind_speed_ms
    return pd.DataFrame(
        {
            "timestamp_utc": timestamps,
            "turbine_id": turbine_id,
            "active_power_kw": power,
            "wind_speed_ms": wind,
        }
    )


class FitDirectPowerTests(unittest.TestCase):
    def test_recovers_an_exact_linear_relationship(self) -> None:
        timestamps = _timestamps(50)
        reference_power = np.linspace(100.0, 1800.0, 50)
        target_power = 0.8 * reference_power + 50.0
        df = pd.concat(
            [_frame(timestamps, "target", target_power), _frame(timestamps, "reference", reference_power)]
        )

        fit = fit_direct_power(df, "target", "reference", fit_before=timestamps[-1], rated_power_kw=2050.0)

        self.assertAlmostEqual(fit.slope, 0.8, places=4)
        self.assertAlmostEqual(fit.intercept, 50.0, places=2)

    def test_raises_with_fewer_than_two_paired_observations(self) -> None:
        timestamps = _timestamps(1)
        df = pd.concat(
            [_frame(timestamps, "target", np.array([500.0])), _frame(timestamps, "reference", np.array([400.0]))]
        )
        with self.assertRaises(ValueError):
            fit_direct_power(df, "target", "reference", fit_before="2016-07-02T00:00:00Z", rated_power_kw=2050.0)


class PredictDirectPowerTests(unittest.TestCase):
    def test_clips_predictions_to_the_rated_power_band(self) -> None:
        timestamps = _timestamps(10)
        reference_power = np.linspace(100.0, 3000.0, 10)
        df = _frame(timestamps, "reference", reference_power)

        from windlens.direct_power_uncertainty import PowerLinearFit

        fit = PowerLinearFit(slope=1.0, intercept=0.0, rated_power_kw=2050.0)
        prediction = predict_direct_power(df, fit, "reference", timestamps[0], "2016-07-02T00:00:00Z")

        self.assertTrue((prediction["predicted_power_kw"] <= 2050.0).all())
        self.assertTrue((prediction["predicted_power_kw"] >= 0.0).all())


class CalibrateAndEvaluateDirectPowerIntervalTests(unittest.TestCase):
    def test_returns_available_with_plausible_coverage_on_synthetic_noisy_data(self) -> None:
        rng = np.random.default_rng(42)
        pre_timestamps = _timestamps(400)
        event_timestamps = _timestamps(30, start_hour=400 // 6)
        all_timestamps = pre_timestamps + event_timestamps
        reference_power = rng.uniform(200.0, 1800.0, len(all_timestamps))
        noise = rng.normal(0.0, 40.0, len(all_timestamps))
        target_power = np.clip(0.9 * reference_power + 30.0 + noise, 0.0, 2050.0)

        masked_df = pd.concat(
            [
                _frame(pre_timestamps, "target", target_power[: len(pre_timestamps)]),
                _frame(all_timestamps, "reference", reference_power),
            ]
        )
        hidden_truth = _frame(event_timestamps, "target", target_power[len(pre_timestamps):])

        result = calibrate_and_evaluate_direct_power_interval(
            masked_df,
            "target",
            "reference",
            block_start=event_timestamps[0],
            block_end="2016-07-10T00:00:00Z",
            rated_power_kw=2050.0,
            hidden_truth=hidden_truth,
        )

        self.assertEqual(result["status"], "available")
        # 2026-10-22 red-team review (F13): `0 <= coverage <= 100` is true by
        # construction (coverage_pct is always a percentage) and can't fail on a
        # real calibration bug. With a fixed seed this fixture is fully
        # deterministic, so pin the actual computed values -- a sign flip, wrong
        # quantile, or wrong window would change these and fail the test.
        self.assertEqual(result["event_evaluation"]["observations"], 34)
        self.assertEqual(result["event_evaluation"]["covered_observations"], 24)
        self.assertAlmostEqual(result["event_evaluation"]["coverage_pct"], 70.588235, places=4)
        self.assertAlmostEqual(result["event_evaluation"]["mean_width_ms"], 134.392230, places=4)

    def test_unavailable_when_pre_event_history_is_too_short(self) -> None:
        timestamps = _timestamps(5)
        event_timestamps = _timestamps(5, start_hour=1)
        masked_df = pd.concat(
            [
                _frame(timestamps, "target", np.linspace(100.0, 200.0, 5)),
                _frame(timestamps + event_timestamps, "reference", np.linspace(100.0, 300.0, 10)),
            ]
        )
        hidden_truth = _frame(event_timestamps, "target", np.linspace(150.0, 250.0, 5))

        result = calibrate_and_evaluate_direct_power_interval(
            masked_df,
            "target",
            "reference",
            block_start=event_timestamps[0],
            block_end="2016-07-02T00:00:00Z",
            rated_power_kw=2050.0,
            hidden_truth=hidden_truth,
        )

        self.assertEqual(result["status"], "unavailable")


class ReferenceOperatingStateCheckTests(unittest.TestCase):
    def test_passes_when_reference_is_generating_normally(self) -> None:
        timestamps = _timestamps(30)
        df = _frame(timestamps, "reference", np.linspace(200.0, 1800.0, 30))
        result = reference_operating_state_check(df, "reference", timestamps[0], "2016-07-02T00:00:00Z", 2050.0)
        self.assertTrue(result["passed"])
        self.assertEqual(result["stopped_fraction"], 0.0)

    def test_fails_when_reference_is_stopped_despite_wind_above_cut_in(self) -> None:
        # 2026-10-22 red-team review (F8) reproduced directly: wind well above cut-in
        # but the reference reports ~0 kW throughout -- a stopped-but-reporting turbine.
        timestamps = _timestamps(30)
        df = _frame(
            timestamps, "reference", np.zeros(30), wind_speed_ms=np.full(30, 9.0)
        )
        result = reference_operating_state_check(df, "reference", timestamps[0], "2016-07-02T00:00:00Z", 2050.0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["stopped_fraction"], 1.0)

    def test_does_not_flag_legitimate_low_wind_near_zero_power(self) -> None:
        # Near-zero power with wind BELOW cut-in is normal operation, not a stop.
        timestamps = _timestamps(30)
        df = _frame(timestamps, "reference", np.zeros(30), wind_speed_ms=np.full(30, 2.0))
        result = reference_operating_state_check(df, "reference", timestamps[0], "2016-07-02T00:00:00Z", 2050.0)
        self.assertTrue(result["passed"])

    def test_calibration_abstains_when_reference_looks_stopped(self) -> None:
        rng = np.random.default_rng(42)
        pre_timestamps = _timestamps(400)
        event_timestamps = _timestamps(30, start_hour=400 // 6)
        all_timestamps = pre_timestamps + event_timestamps
        reference_power = rng.uniform(200.0, 1800.0, len(all_timestamps))
        noise = rng.normal(0.0, 40.0, len(all_timestamps))
        target_power = np.clip(0.9 * reference_power + 30.0 + noise, 0.0, 2050.0)

        masked_df = pd.concat(
            [
                _frame(pre_timestamps, "target", target_power[: len(pre_timestamps)]),
                # Reference is stopped (power ~0) throughout, including the event window.
                _frame(all_timestamps, "reference", np.zeros(len(all_timestamps)), wind_speed_ms=np.full(len(all_timestamps), 9.0)),
            ]
        )
        hidden_truth = _frame(event_timestamps, "target", target_power[len(pre_timestamps):])

        result = calibrate_and_evaluate_direct_power_interval(
            masked_df,
            "target",
            "reference",
            block_start=event_timestamps[0],
            block_end="2016-07-10T00:00:00Z",
            rated_power_kw=2050.0,
            hidden_truth=hidden_truth,
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("stopped", result["reason"])


if __name__ == "__main__":
    unittest.main()
