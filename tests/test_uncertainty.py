from __future__ import annotations

import unittest

import numpy as np

from windlens.uncertainty import (
    apply_residual_interval,
    calibrate_residual_interval,
    evaluate_interval,
    pooled_coverage_summary,
)


class ResidualIntervalTests(unittest.TestCase):
    def test_calibration_uses_symmetric_empirical_quantiles(self) -> None:
        result = calibrate_residual_interval(
            [-2.0, -1.0, 0.0, 1.0, 2.0], coverage=0.8, min_observations=5
        )

        self.assertEqual(result["method"], "empirical_residual_quantiles")
        self.assertEqual(result["observations"], 5)
        self.assertAlmostEqual(result["coverage_target"], 0.8)
        self.assertLessEqual(result["lower_residual_ms"], 0.0)
        self.assertGreaterEqual(result["upper_residual_ms"], 0.0)

    def test_applies_interval_to_predictions(self) -> None:
        calibration = calibrate_residual_interval(
            [-1.0, 0.0, 1.0], coverage=0.8, min_observations=3
        )
        lower, upper = apply_residual_interval([5.0, 6.0], calibration)

        self.assertEqual(len(lower), 2)
        self.assertEqual(len(upper), 2)
        self.assertTrue(np.all(lower <= [5.0, 6.0]))
        self.assertTrue(np.all(upper >= [5.0, 6.0]))

    def test_evaluates_coverage_and_mean_width(self) -> None:
        result = evaluate_interval(
            actual=[4.0, 7.0, 10.0], lower=[3.0, 6.0, 9.0], upper=[5.0, 8.0, 9.5]
        )

        self.assertEqual(result["observations"], 3)
        self.assertAlmostEqual(result["coverage_pct"], 2 / 3 * 100)
        self.assertAlmostEqual(result["mean_width_ms"], (2.0 + 2.0 + 0.5) / 3)

    def test_rejects_insufficient_calibration_observations(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_residual_interval([0.1, -0.1], min_observations=3)

    def test_rejects_invalid_coverage(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_residual_interval([0.0, 1.0, -1.0], coverage=1.0, min_observations=3)


class PooledCoverageSummaryTests(unittest.TestCase):
    def test_pools_observations_across_blocks_not_just_block_pass_fail(self) -> None:
        # 2026-10-22 red-team review (F4): a block-level pass/fail average would say
        # "0/2 blocks meet 90%" here (95% and 85%), hiding that pooled coverage is
        # actually a healthy 91.7% -- the point of this function.
        evaluations = [
            {"observations": 100, "covered_observations": 95, "coverage_pct": 95.0},
            {"observations": 20, "covered_observations": 17, "coverage_pct": 85.0},
        ]
        result = pooled_coverage_summary(evaluations)
        self.assertEqual(result["n_blocks"], 2)
        self.assertEqual(result["total_observations"], 120)
        self.assertAlmostEqual(result["pooled_coverage_pct"], 112 / 120 * 100)
        self.assertAlmostEqual(result["per_block_coverage_mean_pct"], 90.0)
        self.assertGreater(result["per_block_coverage_std_pct"], 0.0)
        self.assertEqual(result["per_block_coverage_min_pct"], 85.0)
        self.assertEqual(result["per_block_coverage_max_pct"], 95.0)

    def test_rejects_empty_input(self) -> None:
        with self.assertRaises(ValueError):
            pooled_coverage_summary([])


if __name__ == "__main__":
    unittest.main()
