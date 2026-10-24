from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.dynamic_reference import haversine_km, select_dynamic_references


class DynamicReferenceTests(unittest.TestCase):
    def _data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        timestamps = pd.date_range("2020-01-01", periods=400, freq="12h", tz="UTC")
        base = np.linspace(3.0, 11.0, len(timestamps))
        target = base + np.sin(np.arange(len(base)) / 7) * 0.05
        rng = np.random.default_rng(2)
        good = target + rng.normal(0, 0.05, len(base))
        bad = target + rng.normal(0, 1.0, len(base))
        frames = [
            pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": "KWF1", "wind_speed_ms": target}),
            pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": "KWF2", "wind_speed_ms": good}),
            pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": "KWF3", "wind_speed_ms": bad}),
        ]
        metadata = pd.DataFrame(
            {
                "turbine_id": ["KWF1", "KWF2", "KWF3"],
                "latitude": [52.4, 52.401, 52.5],
                "longitude": [-0.94, -0.941, -0.95],
            }
        )
        return pd.concat(frames, ignore_index=True), metadata

    def test_ranks_by_holdout_behavior_with_geography_as_tie_breaker(self) -> None:
        df, metadata = self._data()
        result = select_dynamic_references(df, "KWF1", ["KWF2", "KWF3"], metadata, lookback_days=(30, 90))

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["selected"], "KWF2")
        self.assertIn(result["selected_window_days"], (30, 90))
        self.assertAlmostEqual(sum(item["weight"] for item in result["ensemble"]), 1.0)
        self.assertLess(result["ranking"][0]["rmse_ms"], result["ranking"][1]["rmse_ms"])

    def test_returns_abstention_when_no_candidate_has_enough_data(self) -> None:
        df, metadata = self._data()
        result = select_dynamic_references(
            df, "KWF1", ["KWF2"], metadata, lookback_days=(30,), min_paired_observations=1000
        )

        self.assertEqual(result["status"], "abstain")
        self.assertIsNone(result["selected"])

    def test_haversine_distance_is_positive_and_symmetric(self) -> None:
        distance = haversine_km(52.4, -0.94, 52.401, -0.941)
        self.assertGreater(distance, 0)
        self.assertAlmostEqual(distance, haversine_km(52.401, -0.941, 52.4, -0.94))

    def test_rejects_non_finite_target_coordinates(self) -> None:
        df, metadata = self._data()
        metadata.loc[metadata["turbine_id"] == "KWF1", "latitude"] = np.nan
        with self.assertRaises(ValueError):
            select_dynamic_references(df, "KWF1", ["KWF2"], metadata)

    def test_behavior_weight_controls_selection_when_distance_and_rmse_disagree(self) -> None:
        # 2026-10-23 reference-selection weighting ablation (Anna's request):
        # KWF3 has the worse RMSE (noisier) but is placed CLOSER than KWF2 (good
        # RMSE, farther), so behavior and geography disagree about which to pick.
        # This is the scenario the 0.8/0.2 default is supposed to resolve, and the
        # scenario any alternative weighting would resolve differently -- a
        # tautological assertion here couldn't tell the two apart.
        df, metadata = self._data()
        metadata.loc[metadata["turbine_id"] == "KWF3", ["latitude", "longitude"]] = [52.4005, -0.9405]
        metadata.loc[metadata["turbine_id"] == "KWF2", ["latitude", "longitude"]] = [53.5, -1.5]

        pure_behavior = select_dynamic_references(
            df, "KWF1", ["KWF2", "KWF3"], metadata, lookback_days=(30, 90), behavior_weight=1.0
        )
        pure_geography = select_dynamic_references(
            df, "KWF1", ["KWF2", "KWF3"], metadata, lookback_days=(30, 90), behavior_weight=0.0
        )

        self.assertEqual(pure_behavior["selected"], "KWF2")
        self.assertEqual(pure_geography["selected"], "KWF3")

    def test_default_behavior_weight_matches_shipped_80_20_blend(self) -> None:
        df, metadata = self._data()
        default_result = select_dynamic_references(df, "KWF1", ["KWF2", "KWF3"], metadata, lookback_days=(30, 90))
        explicit_result = select_dynamic_references(
            df, "KWF1", ["KWF2", "KWF3"], metadata, lookback_days=(30, 90), behavior_weight=0.8
        )

        self.assertEqual(default_result["selected"], explicit_result["selected"])
        default_scores = {c["turbine_id"]: c["selection_score"] for c in default_result["ranking"]}
        explicit_scores = {c["turbine_id"]: c["selection_score"] for c in explicit_result["ranking"]}
        self.assertEqual(default_scores, explicit_scores)

    def test_rejects_behavior_weight_outside_unit_interval(self) -> None:
        df, metadata = self._data()
        with self.assertRaises(ValueError):
            select_dynamic_references(df, "KWF1", ["KWF2"], metadata, behavior_weight=1.5)
        with self.assertRaises(ValueError):
            select_dynamic_references(df, "KWF1", ["KWF2"], metadata, behavior_weight=-0.1)


if __name__ == "__main__":
    unittest.main()
