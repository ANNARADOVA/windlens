from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from windlens.lookback_report import evaluate_lookback_windows


class LookbackReportTests(unittest.TestCase):
    def test_each_origin_is_reported_and_aggregated(self) -> None:
        timestamps = pd.date_range("2020-01-01", periods=400, freq="12h", tz="UTC")
        base = np.linspace(3.0, 11.0, len(timestamps))
        frames = []
        for turbine, values in {
            "KWF1": base,
            "KWF2": base + 0.01,
            "KWF3": base + 0.7 + np.sin(np.arange(len(base)) / 3) * 0.4,
        }.items():
            frames.append(pd.DataFrame({"timestamp_utc": timestamps, "turbine_id": turbine, "wind_speed_ms": values}))
        data = pd.concat(frames, ignore_index=True)
        metadata = pd.DataFrame({
            "turbine_id": ["KWF1", "KWF2", "KWF3"],
            "latitude": [52.4, 52.401, 52.402],
            "longitude": [-0.94, -0.941, -0.942],
        })

        report = evaluate_lookback_windows(
            data,
            "KWF1",
            ["KWF2", "KWF3"],
            metadata,
            ["2020-03-15T00:00:00Z", "2020-05-01T00:00:00Z"],
            lookback_days=(30, 90),
            min_paired_observations=20,
        )

        self.assertEqual(report["event_count"], 2)
        self.assertEqual(report["selected_count"], 2)
        self.assertEqual(report["abstention_rate_pct"], 0.0)
        self.assertEqual(len(report["events"]), 2)
        self.assertTrue(all(event["selected_reference"] == "KWF2" for event in report["events"]))

    def test_reports_abstention_without_hiding_it(self) -> None:
        timestamps = pd.date_range("2020-01-01", periods=10, freq="12h", tz="UTC")
        data = pd.DataFrame({
            "timestamp_utc": list(timestamps) * 2,
            "turbine_id": ["KWF1"] * 10 + ["KWF2"] * 10,
            "wind_speed_ms": [5.0] * 20,
        })
        metadata = pd.DataFrame({
            "turbine_id": ["KWF1", "KWF2"],
            "latitude": [52.4, 52.401],
            "longitude": [-0.94, -0.941],
        })
        report = evaluate_lookback_windows(
            data, "KWF1", ["KWF2"], metadata, ["2020-01-05T00:00:00Z"], min_paired_observations=20
        )

        self.assertEqual(report["selected_count"], 0)
        self.assertEqual(report["abstention_rate_pct"], 100.0)
        self.assertEqual(report["events"][0]["status"], "abstain")


if __name__ == "__main__":
    unittest.main()
