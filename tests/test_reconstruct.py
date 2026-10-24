from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.reconstruct import (
    fit_linear,
    fit_weighted_references,
    predict_with_fitted_references,
    reconstruct_wind_speed,
    reconstruct_wind_speed_ensemble,
    reconstruct_wind_speed_weighted,
    reference_within_training_domain,
    select_reference_turbine,
)


def _timestamps(n: int, start_minute: int = 0) -> list[str]:
    return [f"2016-07-01T{(start_minute + 10 * i) // 60:02d}:{(start_minute + 10 * i) % 60:02d}:00Z" for i in range(n)]


class FitLinearTests(unittest.TestCase):
    def test_recovers_an_exact_linear_relationship(self) -> None:
        reference = np.linspace(2.0, 12.0, 20)
        target = 1.5 * reference + 0.5
        paired = pd.DataFrame({"reference": reference, "target": target})

        fit = fit_linear(paired)

        self.assertAlmostEqual(fit.slope, 1.5, places=6)
        self.assertAlmostEqual(fit.intercept, 0.5, places=6)
        self.assertEqual(fit.method, "ols")

    def test_variance_ratio_matches_ols_on_an_exact_noise_free_relationship(self) -> None:
        # With zero noise both estimators recover the same line exactly.
        reference = np.linspace(2.0, 12.0, 20)
        target = 1.5 * reference + 0.5
        paired = pd.DataFrame({"reference": reference, "target": target})

        fit = fit_linear(paired, method="variance_ratio")

        self.assertAlmostEqual(fit.slope, 1.5, places=6)
        self.assertAlmostEqual(fit.intercept, 0.5, places=6)
        self.assertEqual(fit.method, "variance_ratio")

    def test_variance_ratio_preserves_target_variance_under_noise_unlike_ols(self) -> None:
        # 2026-10-22 red-team review (F7): OLS shrinks predicted variance toward the
        # mean under noise; variance-ratio MCP is built specifically to preserve it.
        rng = np.random.default_rng(0)
        reference = np.linspace(2.0, 12.0, 500)
        target = 1.5 * reference + 0.5 + rng.normal(0, 1.5, 500)
        paired = pd.DataFrame({"reference": reference, "target": target})

        ols_fit = fit_linear(paired, method="ols")
        vr_fit = fit_linear(paired, method="variance_ratio")

        predicted_ols = ols_fit.predict(reference)
        predicted_vr = vr_fit.predict(reference)
        target_std = float(np.std(target))

        self.assertLess(float(np.std(predicted_ols)), target_std)
        self.assertAlmostEqual(float(np.std(predicted_vr)), target_std, delta=1e-6)

    def test_rejects_an_unknown_method(self) -> None:
        paired = pd.DataFrame({"reference": [1.0, 2.0], "target": [1.0, 2.0]})
        with self.assertRaises(ValueError):
            fit_linear(paired, method="nonsense")


class SelectReferenceTurbineTests(unittest.TestCase):
    def test_prefers_the_turbine_that_correlates_better_with_the_target(self) -> None:
        n = 60
        timestamps = _timestamps(n)
        rng = np.random.default_rng(0)
        target_wind = np.linspace(3.0, 10.0, n)

        good_reference = target_wind + rng.normal(0, 0.05, n)
        bad_reference = target_wind + rng.normal(0, 5.0, n)

        df = pd.concat(
            [
                pd.DataFrame(
                    {"timestamp_utc": timestamps, "turbine_id": "KWF1", "wind_speed_ms": target_wind}
                ),
                pd.DataFrame(
                    {"timestamp_utc": timestamps, "turbine_id": "KWF2", "wind_speed_ms": good_reference}
                ),
                pd.DataFrame(
                    {"timestamp_utc": timestamps, "turbine_id": "KWF3", "wind_speed_ms": bad_reference}
                ),
            ],
            ignore_index=True,
        )

        result = select_reference_turbine(df, "KWF1", ["KWF2", "KWF3"])

        self.assertEqual(result["selected"], "KWF2")
        self.assertEqual([entry["turbine_id"] for entry in result["ranking"]], ["KWF2", "KWF3"])

    def test_raises_when_no_candidate_has_enough_paired_observations(self) -> None:
        df = pd.DataFrame(
            {
                "timestamp_utc": _timestamps(3),
                "turbine_id": ["KWF1"] * 3,
                "wind_speed_ms": [5.0, 5.5, 6.0],
            }
        )

        with self.assertRaises(ValueError):
            select_reference_turbine(df, "KWF1", ["KWF2"], min_paired_observations=10)

    def test_falls_back_to_next_best_reference_when_top_pick_has_no_window_coverage(self) -> None:
        # 2026-10-24 correctness fix: the top-ranked candidate by historical fit can
        # still be a turbine that has no readings at all during the actual outage
        # window (down itself, or simply never uploaded for that period) -- the
        # selection must not silently hand back a reference with zero coverage
        # there when a worse-but-covered candidate exists.
        n = 60
        pre_timestamps = _timestamps(n)
        window_timestamps = _timestamps(5, start_minute=10 * n)
        rng = np.random.default_rng(0)
        target_wind = np.linspace(3.0, 10.0, n)
        best_reference = target_wind + rng.normal(0, 0.05, n)  # best historical fit
        worse_reference = target_wind + rng.normal(0, 5.0, n)  # worse fit, but covers the window

        df = pd.concat(
            [
                pd.DataFrame({"timestamp_utc": pre_timestamps, "turbine_id": "KWF1", "wind_speed_ms": target_wind}),
                pd.DataFrame({"timestamp_utc": pre_timestamps, "turbine_id": "KWF2", "wind_speed_ms": best_reference}),
                pd.DataFrame({"timestamp_utc": pre_timestamps, "turbine_id": "KWF3", "wind_speed_ms": worse_reference}),
                # KWF2 (the best historical fit) has NO readings at all during the
                # outage window itself -- only KWF3 does.
                pd.DataFrame({"timestamp_utc": window_timestamps, "turbine_id": "KWF3", "wind_speed_ms": [6.0] * 5}),
            ],
            ignore_index=True,
        )

        pre_outage = df[df["timestamp_utc"].isin(pre_timestamps)]
        result = select_reference_turbine(
            pre_outage,
            "KWF1",
            ["KWF2", "KWF3"],
            full_df=df,
            window_start=window_timestamps[0],
            window_end="2099-01-01T00:00:00Z",
        )

        self.assertEqual([entry["turbine_id"] for entry in result["ranking"]], ["KWF2", "KWF3"])
        self.assertEqual(result["selected"], "KWF3")
        self.assertIn("KWF2", result["reference_fallback_note"])
        self.assertIn("KWF3", result["reference_fallback_note"])

    def test_no_fallback_note_when_top_pick_already_covers_the_window(self) -> None:
        n = 60
        timestamps = _timestamps(n)
        window_timestamps = _timestamps(5, start_minute=10 * n)
        rng = np.random.default_rng(0)
        target_wind = np.linspace(3.0, 10.0, n)
        good_reference = target_wind + rng.normal(0, 0.05, n)

        df = pd.concat(
            [
                pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": "KWF1", "wind_speed_ms": target_wind}),
                pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": "KWF2", "wind_speed_ms": good_reference}),
                pd.DataFrame({"timestamp_utc": window_timestamps, "turbine_id": "KWF2", "wind_speed_ms": [6.0] * 5}),
            ],
            ignore_index=True,
        )

        result = select_reference_turbine(
            df[df["timestamp_utc"].isin(timestamps)],
            "KWF1",
            ["KWF2"],
            full_df=df,
            window_start=window_timestamps[0],
            window_end="2099-01-01T00:00:00Z",
        )

        self.assertEqual(result["selected"], "KWF2")
        self.assertNotIn("reference_fallback_note", result)


class ReconstructWindSpeedTests(unittest.TestCase):
    def test_predicts_using_only_pre_outage_fit_and_in_window_reference_data(self) -> None:
        pre_outage_timestamps = _timestamps(10)
        masked_timestamps = _timestamps(3, start_minute=100)

        reference_pre = np.linspace(4.0, 8.0, 10)
        target_pre = 2.0 * reference_pre + 1.0  # exact relationship, no noise
        reference_during = np.array([5.0, 6.0, 7.0])

        df = pd.concat(
            [
                pd.DataFrame(
                    {
                        "timestamp_utc": pre_outage_timestamps,
                        "turbine_id": "KWF1",
                        "wind_speed_ms": target_pre,
                    }
                ),
                pd.DataFrame(
                    {
                        "timestamp_utc": pre_outage_timestamps,
                        "turbine_id": "KWF2",
                        "wind_speed_ms": reference_pre,
                    }
                ),
                pd.DataFrame(
                    {
                        "timestamp_utc": masked_timestamps,
                        "turbine_id": "KWF2",
                        "wind_speed_ms": reference_during,
                    }
                ),
            ],
            ignore_index=True,
        )

        mask_start = masked_timestamps[0]
        mask_end = "2016-07-02T00:00:00Z"

        result = reconstruct_wind_speed(df, "KWF1", "KWF2", mask_start, mask_end)

        expected = 2.0 * reference_during + 1.0
        np.testing.assert_allclose(
            result["wind_speed_ms_reconstructed"].to_numpy(), expected, rtol=1e-6
        )
        self.assertEqual(list(result["timestamp_utc"]), masked_timestamps)


class ReconstructWindSpeedEnsembleTests(unittest.TestCase):
    def test_averages_the_individual_single_reference_predictions(self) -> None:
        pre_outage_timestamps = _timestamps(10)
        masked_timestamps = _timestamps(3, start_minute=100)

        reference_a_pre = np.linspace(4.0, 8.0, 10)
        reference_b_pre = np.linspace(2.0, 6.0, 10)
        target_pre = 2.0 * reference_a_pre + 1.0  # exact vs. reference A
        # Reference B isn't exactly linear-consistent with the target; that's fine --
        # the ensemble is the average of each reference's own (imperfect) prediction.
        reference_a_during = np.array([5.0, 6.0, 7.0])
        reference_b_during = np.array([3.0, 4.0, 5.0])

        df = pd.concat(
            [
                pd.DataFrame(
                    {"timestamp_utc": pre_outage_timestamps, "turbine_id": "KWF1", "wind_speed_ms": target_pre}
                ),
                pd.DataFrame(
                    {"timestamp_utc": pre_outage_timestamps, "turbine_id": "KWF2", "wind_speed_ms": reference_a_pre}
                ),
                pd.DataFrame(
                    {"timestamp_utc": pre_outage_timestamps, "turbine_id": "KWF3", "wind_speed_ms": reference_b_pre}
                ),
                pd.DataFrame(
                    {"timestamp_utc": masked_timestamps, "turbine_id": "KWF2", "wind_speed_ms": reference_a_during}
                ),
                pd.DataFrame(
                    {"timestamp_utc": masked_timestamps, "turbine_id": "KWF3", "wind_speed_ms": reference_b_during}
                ),
            ],
            ignore_index=True,
        )

        mask_start = masked_timestamps[0]
        mask_end = "2016-07-02T00:00:00Z"

        single_a = reconstruct_wind_speed(df, "KWF1", "KWF2", mask_start, mask_end)
        single_b = reconstruct_wind_speed(df, "KWF1", "KWF3", mask_start, mask_end)
        ensemble = reconstruct_wind_speed_ensemble(df, "KWF1", ["KWF2", "KWF3"], mask_start, mask_end)

        expected = (
            single_a["wind_speed_ms_reconstructed"].to_numpy()
            + single_b["wind_speed_ms_reconstructed"].to_numpy()
        ) / 2
        np.testing.assert_allclose(
            ensemble["wind_speed_ms_reconstructed"].to_numpy(), expected, rtol=1e-6
        )

    def test_raises_with_no_reference_turbines(self) -> None:
        df = pd.DataFrame({"timestamp_utc": [], "turbine_id": [], "wind_speed_ms": []})
        with self.assertRaises(ValueError):
            reconstruct_wind_speed_ensemble(df, "KWF1", [], "t0", "t1")

    def test_weighted_ensemble_respects_reference_weights(self) -> None:
        pre = _timestamps(10)
        during = _timestamps(2, start_minute=100)
        reference = np.linspace(4.0, 8.0, 10)
        target = reference.copy()
        df = pd.concat([
            pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF1", "wind_speed_ms": target}),
            pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF2", "wind_speed_ms": reference}),
            pd.DataFrame({"timestamp_utc": during, "turbine_id": "KWF2", "wind_speed_ms": [4.0, 5.0]}),
        ], ignore_index=True)
        result = reconstruct_wind_speed_weighted(
            df, "KWF1", {"KWF2": 1.0}, during[0], "2016-07-02T00:00:00Z"
        )
        np.testing.assert_allclose(result["wind_speed_ms_reconstructed"].to_numpy(), [4.0, 5.0])


class FitWeightedReferencesTests(unittest.TestCase):
    def test_predicting_over_the_fit_window_matches_reconstruct_wind_speed_weighted(self) -> None:
        pre = _timestamps(10)
        during = _timestamps(3, start_minute=100)
        reference_a = np.linspace(4.0, 8.0, 10)
        reference_b = np.linspace(2.0, 6.0, 10)
        target = 2.0 * reference_a + 1.0
        reference_a_during = np.array([5.0, 6.0, 7.0])
        reference_b_during = np.array([3.0, 4.0, 5.0])
        df = pd.concat(
            [
                pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF1", "wind_speed_ms": target}),
                pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF2", "wind_speed_ms": reference_a}),
                pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF3", "wind_speed_ms": reference_b}),
                pd.DataFrame(
                    {"timestamp_utc": during, "turbine_id": "KWF2", "wind_speed_ms": reference_a_during}
                ),
                pd.DataFrame(
                    {"timestamp_utc": during, "turbine_id": "KWF3", "wind_speed_ms": reference_b_during}
                ),
            ],
            ignore_index=True,
        )
        weights = {"KWF2": 2.0, "KWF3": 1.0}
        mask_start, mask_end = during[0], "2016-07-02T00:00:00Z"

        expected = reconstruct_wind_speed_weighted(df, "KWF1", weights, mask_start, mask_end)
        fits = fit_weighted_references(df, "KWF1", weights, mask_start)
        actual = predict_with_fitted_references(df, fits, mask_start, mask_end)

        np.testing.assert_allclose(
            actual["wind_speed_ms_reconstructed"].to_numpy(),
            expected["wind_speed_ms_reconstructed"].to_numpy(),
            rtol=1e-6,
        )

    def test_can_score_a_fitted_model_over_a_different_window_without_refitting(self) -> None:
        pre = _timestamps(10)
        calibration_window = _timestamps(3, start_minute=100)
        reference = np.linspace(4.0, 8.0, 10)
        target = 2.0 * reference + 1.0
        reference_calibration = np.array([5.0, 6.0, 7.0])
        df = pd.concat(
            [
                pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF1", "wind_speed_ms": target}),
                pd.DataFrame({"timestamp_utc": pre, "turbine_id": "KWF2", "wind_speed_ms": reference}),
                pd.DataFrame(
                    {"timestamp_utc": calibration_window, "turbine_id": "KWF2", "wind_speed_ms": reference_calibration}
                ),
            ],
            ignore_index=True,
        )
        fit_before = "2016-07-02T00:00:00Z"
        fits = fit_weighted_references(df, "KWF1", {"KWF2": 1.0}, fit_before)

        result = predict_with_fitted_references(df, fits, calibration_window[0], fit_before)

        expected = 2.0 * reference_calibration + 1.0
        np.testing.assert_allclose(result["wind_speed_ms_reconstructed"].to_numpy(), expected, rtol=1e-6)

    def test_raises_when_no_reference_has_a_positive_weight(self) -> None:
        df = pd.DataFrame({"timestamp_utc": [], "turbine_id": [], "wind_speed_ms": []})
        with self.assertRaises(ValueError):
            fit_weighted_references(df, "KWF1", {"KWF2": 0.0}, "2016-07-01T00:00:00Z")


class ReferenceWithinTrainingDomainTests(unittest.TestCase):
    def test_flags_observations_outside_the_pre_outage_training_range(self) -> None:
        pre_outage_timestamps = _timestamps(5)
        masked_timestamps = _timestamps(2, start_minute=50)

        df = pd.concat(
            [
                pd.DataFrame(
                    {
                        "timestamp_utc": pre_outage_timestamps,
                        "turbine_id": "KWF2",
                        "wind_speed_ms": [4.0, 5.0, 6.0, 7.0, 8.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "timestamp_utc": masked_timestamps,
                        "turbine_id": "KWF2",
                        "wind_speed_ms": [6.0, 20.0],  # second value is far outside [4, 8]
                    }
                ),
            ],
            ignore_index=True,
        )

        result = reference_within_training_domain(
            df, "KWF2", masked_timestamps[0], "2016-07-02T00:00:00Z"
        )

        self.assertEqual(result["training_min_ms"], 4.0)
        self.assertEqual(result["training_max_ms"], 8.0)
        self.assertEqual(result["observations_out_of_domain"], 1)
        self.assertFalse(result["within_domain"])

    def test_within_domain_when_everything_is_inside_the_training_range(self) -> None:
        pre_outage_timestamps = _timestamps(5)
        masked_timestamps = _timestamps(2, start_minute=50)

        df = pd.concat(
            [
                pd.DataFrame(
                    {
                        "timestamp_utc": pre_outage_timestamps,
                        "turbine_id": "KWF2",
                        "wind_speed_ms": [4.0, 5.0, 6.0, 7.0, 8.0],
                    }
                ),
                pd.DataFrame(
                    {
                        "timestamp_utc": masked_timestamps,
                        "turbine_id": "KWF2",
                        "wind_speed_ms": [5.0, 6.0],
                    }
                ),
            ],
            ignore_index=True,
        )

        result = reference_within_training_domain(
            df, "KWF2", masked_timestamps[0], "2016-07-02T00:00:00Z"
        )

        self.assertTrue(result["within_domain"])
        self.assertEqual(result["observations_out_of_domain"], 0)


if __name__ == "__main__":
    unittest.main()
