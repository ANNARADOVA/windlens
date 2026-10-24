from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from windlens.farm_registry import FarmRegistry


class FarmRegistryTests(unittest.TestCase):
    def test_builds_registry_with_explicit_farm_and_turbine_metadata(self) -> None:
        registry = FarmRegistry.from_records(
            [
                {
                    "farm_id": "KELMARSH",
                    "turbine_id": "KWF1",
                    "latitude": 52.400604,
                    "longitude": -0.947133,
                    "elevation_m": 145.598,
                    "hub_height_m": 78.5,
                    "rated_power_kw": 2050,
                    "data_source": "zenodo:16807551",
                    "time_coverage_start": "2016-01-01T00:00:00Z",
                    "time_coverage_end": "2016-12-31T23:50:00Z",
                    "quality_status": "verified",
                }
            ]
        )

        self.assertEqual(registry.farm_ids(), ["KELMARSH"])
        self.assertEqual(registry.turbine_ids("KELMARSH"), ["KWF1"])
        self.assertEqual(registry.get("KELMARSH", "KWF1").rated_power_kw, 2050)

    def test_rejects_duplicate_farm_turbine_keys(self) -> None:
        record = {
            "farm_id": "F1", "turbine_id": "T1", "latitude": 1, "longitude": 2,
            "rated_power_kw": 100, "data_source": "test", "quality_status": "verified",
        }
        with self.assertRaises(ValueError):
            FarmRegistry.from_records([record, record])

    def test_loads_kelmarsh_style_static_csv_with_normalized_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "static.csv"
            pd.DataFrame(
                {
                    "Wind Farm": ["Kelmarsh"], "Alternative Title": ["KWF1"],
                    "Latitude": [52.4], "Longitude": [-0.94], "Elevation (m)": [145.6],
                    "Hub Height (m)": [78.5], "Rated power (kW)": [2050],
                }
            ).to_csv(path, index=False)
            registry = FarmRegistry.from_csv(path, data_source="kelmarsh-static")

        turbine = registry.get("Kelmarsh", "KWF1")
        self.assertAlmostEqual(turbine.latitude, 52.4)
        self.assertEqual(turbine.quality_status, "unverified")

    def test_rejects_invalid_coordinates(self) -> None:
        with self.assertRaises(ValueError):
            FarmRegistry.from_records([
                {"farm_id": "F1", "turbine_id": "T1", "latitude": 95, "longitude": 2,
                 "rated_power_kw": 100, "data_source": "test", "quality_status": "verified"}
            ])


if __name__ == "__main__":
    unittest.main()
