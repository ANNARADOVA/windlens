from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.lazy_baseline import lazy_baseline_estimate_kwh


def _frame(timestamps: list[str], turbine_id: str, power_kw: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": turbine_id, "active_power_kw": power_kw})


class LazyBaselineEstimateKwhTests(unittest.TestCase):
    def test_averages_capacity_factor_equally_across_turbines_of_different_sizes(self) -> None:
        # Two references at different nameplate sizes but the SAME capacity factor
        # (0.5) -- the lazy baseline must average capacity factor, not raw power, so
        # both contribute equally despite ref_small's power being tiny.
        timestamps = ["t0", "t1"]
        masked = pd.concat(
            [
                _frame(timestamps, "ref_small", np.array([50.0, 50.0])),  # 100 kW rated, cf=0.5
                _frame(timestamps, "ref_big", np.array([1000.0, 1000.0])),  # 2000 kW rated, cf=0.5
            ]
        )
        rated_power = {"target": 500.0, "ref_small": 100.0, "ref_big": 2000.0}

        result = lazy_baseline_estimate_kwh(
            masked, "target", ["ref_small", "ref_big"], "t0", "t2", rated_power
        )

        # mean cf = 0.5 both timestamps -> predicted power = 0.5 * 500 = 250 kW
        # 2 readings * 250 kW * (10/60) h = 83.333... kWh
        self.assertAlmostEqual(result["estimated_lost_kwh"], 250.0 * 2 * (10 / 60))
        self.assertEqual(result["covered_timestamps"], 2)
        self.assertEqual(result["turbines_used"], ["ref_big", "ref_small"])

    def test_uses_only_turbines_actually_present_in_the_window(self) -> None:
        timestamps = ["t0"]
        masked = _frame(timestamps, "ref_a", np.array([100.0]))  # cf = 0.5 at rated 200
        rated_power = {"target": 200.0, "ref_a": 200.0, "ref_b": 200.0}

        result = lazy_baseline_estimate_kwh(masked, "target", ["ref_a", "ref_b"], "t0", "t1", rated_power)

        self.assertEqual(result["turbines_used"], ["ref_a"])

    def test_raises_when_no_available_turbine_rows_exist_in_the_window(self) -> None:
        masked = _frame(["t0"], "ref_a", np.array([100.0]))
        rated_power = {"target": 200.0, "ref_a": 200.0}

        with self.assertRaises(ValueError):
            lazy_baseline_estimate_kwh(masked, "target", ["ref_a"], "t5", "t6", rated_power)

    def test_raises_on_missing_rated_power(self) -> None:
        masked = _frame(["t0"], "ref_a", np.array([100.0]))

        with self.assertRaises(ValueError):
            lazy_baseline_estimate_kwh(masked, "target", ["ref_a"], "t0", "t1", {"ref_a": 200.0})
        with self.assertRaises(ValueError):
            lazy_baseline_estimate_kwh(masked, "target", ["ref_a"], "t0", "t1", {"target": 200.0})


if __name__ == "__main__":
    unittest.main()
