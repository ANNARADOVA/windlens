from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.power_curve import apply_power_curve, fit_power_curve, flag_likely_curtailed_rows


class FitPowerCurveTests(unittest.TestCase):
    def test_bins_wind_speed_and_averages_power_per_bin(self) -> None:
        df = pd.DataFrame(
            {
                "wind_speed_ms": [4.1, 4.2, 4.4, 5.1, 5.3, 9.9],
                "active_power_kw": [100.0, 120.0, 140.0, 300.0, 320.0, 999.0],
            }
        )

        curve = fit_power_curve(df, bin_width_ms=0.5)

        # 4.1/4.2/4.4 fall in the [4.0, 4.5) bin -> center 4.25, mean of 100/120/140.
        bin_4_25 = curve[np.isclose(curve["bin_center_ms"], 4.25)].iloc[0]
        self.assertAlmostEqual(bin_4_25["mean_power_kw"], 120.0)
        self.assertEqual(bin_4_25["observation_count"], 3)

        # 5.1/5.3 fall in the [5.0, 5.5) bin -> center 5.25, mean of 300/320.
        bin_5_25 = curve[np.isclose(curve["bin_center_ms"], 5.25)].iloc[0]
        self.assertAlmostEqual(bin_5_25["mean_power_kw"], 310.0)
        self.assertEqual(bin_5_25["observation_count"], 2)

        self.assertTrue(curve["bin_center_ms"].is_monotonic_increasing)

    def test_drops_rows_with_missing_values_and_raises_if_none_remain(self) -> None:
        df = pd.DataFrame({"wind_speed_ms": [None, None], "active_power_kw": [None, 50.0]})
        with self.assertRaises(ValueError):
            fit_power_curve(df)


class FlagLikelyCurtailedRowsTests(unittest.TestCase):
    def test_flags_a_low_outlier_within_its_bin(self) -> None:
        # Bin [6.0, 6.5): 8 normal rows clustered near 300 kW, one row way below
        # (curtailment-like).
        wind = [6.1] * 9
        power = [295.0, 298.0, 300.0, 302.0, 297.0, 303.0, 299.0, 301.0, 50.0]
        df = pd.DataFrame({"wind_speed_ms": wind, "active_power_kw": power})

        flagged = flag_likely_curtailed_rows(df)

        self.assertTrue(flagged.iloc[8])  # the 50.0 kW low outlier
        self.assertEqual(flagged.iloc[:8].sum(), 0)  # none of the normal-scatter rows

    def test_never_flags_a_high_outlier_even_though_it_is_also_a_statistical_outlier(self) -> None:
        # A row with unusually HIGH power for its wind speed is not curtailment and
        # must never be flagged, even though it is just as far from the mean as the
        # low-outlier case above -- the rule is explicitly one-sided.
        wind = [6.1] * 9
        power = [295.0, 298.0, 300.0, 302.0, 297.0, 303.0, 299.0, 301.0, 550.0]
        df = pd.DataFrame({"wind_speed_ms": wind, "active_power_kw": power})

        flagged = flag_likely_curtailed_rows(df)

        self.assertEqual(flagged.sum(), 0)

    def test_never_flags_bins_with_fewer_than_five_observations(self) -> None:
        # A real low outlier, but its bin only has 3 rows -- too few for a std estimate.
        df = pd.DataFrame({"wind_speed_ms": [6.1, 6.2, 6.1], "active_power_kw": [300.0, 305.0, 10.0]})

        flagged = flag_likely_curtailed_rows(df)

        self.assertFalse(flagged.any())

    def test_fit_power_curve_default_is_unchanged_by_the_new_parameter(self) -> None:
        # exclude_likely_curtailed defaults to False -- every existing caller and
        # already-published back-test number must reproduce unchanged.
        wind = [6.1] * 8 + [6.2]
        power = [295.0, 298.0, 300.0, 302.0, 297.0, 303.0, 299.0, 301.0, 50.0]
        df = pd.DataFrame({"wind_speed_ms": wind, "active_power_kw": power})

        default_curve = fit_power_curve(df)
        explicit_off_curve = fit_power_curve(df, exclude_likely_curtailed=False)

        pd.testing.assert_frame_equal(default_curve, explicit_off_curve)
        # The curtailed row pulls the mean down when NOT excluded.
        self.assertLess(default_curve["mean_power_kw"].iloc[0], 299.0)

    def test_fit_power_curve_excludes_flagged_rows_when_opted_in(self) -> None:
        wind = [6.1] * 8 + [6.2]
        power = [295.0, 298.0, 300.0, 302.0, 297.0, 303.0, 299.0, 301.0, 50.0]
        df = pd.DataFrame({"wind_speed_ms": wind, "active_power_kw": power})

        curve = fit_power_curve(df, exclude_likely_curtailed=True)

        self.assertAlmostEqual(curve["mean_power_kw"].iloc[0], np.mean(power[:8]))
        self.assertEqual(curve["observation_count"].iloc[0], 8)


class ApplyPowerCurveTests(unittest.TestCase):
    def test_interpolates_between_bin_centers(self) -> None:
        curve = pd.DataFrame(
            {
                "bin_center_ms": [4.0, 5.0, 6.0],
                "mean_power_kw": [100.0, 200.0, 300.0],
                "observation_count": [10, 10, 10],
            }
        )

        result = apply_power_curve(curve, np.array([4.0, 4.5, 6.0]))

        np.testing.assert_allclose(result, [100.0, 150.0, 300.0])

    def test_clamps_outside_the_observed_range(self) -> None:
        curve = pd.DataFrame(
            {
                "bin_center_ms": [4.0, 5.0],
                "mean_power_kw": [100.0, 200.0],
                "observation_count": [10, 10],
            }
        )

        result = apply_power_curve(curve, np.array([0.0, 50.0]))

        np.testing.assert_allclose(result, [100.0, 200.0])


if __name__ == "__main__":
    unittest.main()
