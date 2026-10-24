from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.power_curve import apply_power_curve
from windlens.uncertainty_business import (
    apply_conditional_intervals,
    calibrate_conditional_intervals,
    calculate_indicative_value,
    event_level_kwh_interval,
    propagate_power_interval,
    uncertainty_gate,
    validate_commercial_profile,
)


class ConditionalIntervalTests(unittest.TestCase):
    def test_calibrates_and_applies_conditioned_intervals(self) -> None:
        residuals = np.array([-1.0, -0.5, 0.0, 0.5, 1.0] * 10, dtype=float)
        wind = np.array([2.0] * 25 + [8.0] * 25)
        direction = np.array([10.0] * 50)
        calibration = calibrate_conditional_intervals(
            residuals, wind, direction, coverage=0.8, min_observations=5
        )
        lower, upper = apply_conditional_intervals(
            np.array([5.0, 5.0]), np.array([2.0, 8.0]), np.array([10.0, 10.0]), calibration
        )
        self.assertEqual(len(lower), 2)
        self.assertTrue(np.all(lower < upper))
        self.assertEqual(calibration["observations"], 50)

    def test_gate_rejects_too_few_calibration_observations(self) -> None:
        # 2026-10-22 red-team review (F1): the gate must read the CALIBRATION's own
        # observation count (available pre-event), not an event-scored-against-truth
        # dict -- that hidden-truth comparison cannot run in a real outage.
        result = uncertainty_gate(
            {"observations": 40, "lower_residual_ms": -1.0, "upper_residual_ms": 1.0},
            min_observations=100,
        )
        self.assertEqual(result["status"], "unverified")
        self.assertIn("insufficient_calibration_observations", result["failed_gates"])

    def test_gate_accepts_sufficient_calibration(self) -> None:
        result = uncertainty_gate(
            {"observations": 150, "lower_residual_ms": -1.0, "upper_residual_ms": 1.0},
            min_observations=100,
        )
        self.assertEqual(result["status"], "reviewable")
        self.assertEqual(result["failed_gates"], [])

    def test_gate_rejects_interval_wider_than_max_width(self) -> None:
        result = uncertainty_gate(
            {"observations": 150, "lower_residual_ms": -5.0, "upper_residual_ms": 5.0},
            min_observations=100,
            max_width_ms=2.0,
        )
        self.assertEqual(result["status"], "unverified")
        self.assertIn("interval_width", result["failed_gates"])


class EnergyPropagationTests(unittest.TestCase):
    def test_propagates_wind_bounds_through_power_curve(self) -> None:
        curve = pd.DataFrame(
            {"bin_center_ms": [1.0, 2.0, 3.0], "mean_power_kw": [0.0, 100.0, 200.0]}
        )
        result = propagate_power_interval(
            curve, np.array([2.0, 2.0]), np.array([1.0, 1.5]), np.array([2.5, 3.0])
        )
        self.assertLessEqual(result["lower_kwh"], result["point_kwh"])
        self.assertGreaterEqual(result["upper_kwh"], result["point_kwh"])


class EventLevelKwhIntervalTests(unittest.TestCase):
    def test_builds_a_symmetric_band_from_the_error_quantile(self) -> None:
        errors = [5.0, 8.0, 10.0, 12.0, 15.0, 9.0, 11.0, 7.0, 6.0, 13.0, 14.0, 20.0]
        result = event_level_kwh_interval(errors, 100000.0, quantile_pct=90.0)
        self.assertEqual(result["n_events"], 12)
        expected_half_width_pct = float(np.percentile(np.abs(errors), 90.0))
        self.assertAlmostEqual(result["half_width_pct"], expected_half_width_pct)
        self.assertAlmostEqual(result["point_kwh"], 100000.0)
        self.assertAlmostEqual(result["lower_kwh"], 100000.0 - expected_half_width_pct * 1000.0)
        self.assertAlmostEqual(result["upper_kwh"], 100000.0 + expected_half_width_pct * 1000.0)
        self.assertEqual(len(result["half_width_sampling_ci_pct"]), 2)
        self.assertLessEqual(
            result["half_width_sampling_ci_pct"][0], result["half_width_sampling_ci_pct"][1]
        )

    def test_lower_bound_never_goes_negative(self) -> None:
        errors = [150.0] * 10
        result = event_level_kwh_interval(errors, 1000.0, quantile_pct=90.0)
        self.assertEqual(result["lower_kwh"], 0.0)

    def test_rejects_too_few_events(self) -> None:
        with self.assertRaises(ValueError):
            event_level_kwh_interval([1.0, 2.0, 3.0], 1000.0)


class CommercialProfileTests(unittest.TestCase):
    def test_calculates_indicative_fixed_price_value(self) -> None:
        profile = {
            "profile_id": "demo-ppa",
            "currency": "EUR",
            "settlement_interval_minutes": 10,
            "price_basis": "fixed",
            "fixed_price_eur_per_mwh": 85.0,
            "source": "user-entered indicative profile",
        }
        validate_commercial_profile(profile)
        result = calculate_indicative_value(10000.0, profile)
        self.assertAlmostEqual(result["value"], 850.0)
        self.assertEqual(result["unit"], "EUR")
        self.assertEqual(result["claim_scope"], "indicative")

    def test_rejects_profile_without_price_basis(self) -> None:
        with self.assertRaises(ValueError):
            validate_commercial_profile({"profile_id": "bad", "currency": "EUR"})


if __name__ == "__main__":
    unittest.main()
