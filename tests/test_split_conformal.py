from __future__ import annotations

import unittest

import numpy as np

from windlens.split_conformal import (
    apply_split_conformal_interval,
    calibrate_split_conformal_interval,
)


class SplitConformalIntervalTests(unittest.TestCase):
    def test_half_width_is_a_calibration_order_statistic(self) -> None:
        # n=19, coverage=0.90 -> rank = ceil(20*0.90) = 18th smallest |residual|.
        residuals = list(range(1, 20))  # 1..19, already sorted absolute values
        result = calibrate_split_conformal_interval(residuals, coverage=0.90, min_observations=19)

        self.assertEqual(result["method"], "split_conformal_symmetric")
        self.assertEqual(result["observations"], 19)
        self.assertTrue(result["coverage_guaranteed_at_this_n"])
        self.assertAlmostEqual(result["half_width"], 18.0)

    def test_widens_to_unbounded_when_n_too_small_for_target_coverage(self) -> None:
        # n=5, coverage=0.99 -> rank = ceil(6*0.99) = 6 > n=5: not guaranteed.
        result = calibrate_split_conformal_interval(
            [1.0, 2.0, 3.0, 4.0, 5.0], coverage=0.99, min_observations=5
        )

        self.assertFalse(result["coverage_guaranteed_at_this_n"])
        self.assertEqual(result["half_width"], float("inf"))

    def test_apply_produces_symmetric_bounds(self) -> None:
        calibration = calibrate_split_conformal_interval(
            [-2.0, -1.0, 0.0, 1.0, 2.0], coverage=0.6, min_observations=5
        )
        lower, upper = apply_split_conformal_interval([10.0, 20.0], calibration)

        width_lower = np.asarray([10.0, 20.0]) - lower
        width_upper = upper - np.asarray([10.0, 20.0])
        np.testing.assert_allclose(width_lower, width_upper)

    def test_rejects_insufficient_calibration_observations(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_split_conformal_interval([0.1, -0.1], min_observations=3)

    def test_rejects_invalid_coverage(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_split_conformal_interval([0.0, 1.0, -1.0], coverage=1.0, min_observations=3)

    def test_apply_rejects_negative_half_width(self) -> None:
        with self.assertRaises(ValueError):
            apply_split_conformal_interval([1.0], {"half_width": -1.0})


if __name__ == "__main__":
    unittest.main()
