from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from windlens.excel_connector import EDPPortugalSCADAConnector, ExcelFarmConnector


MAPPING = {
    "timestamp_utc": "Time",
    "turbine_id": "Asset",
    "wind_speed_ms": "Wind speed",
    "wind_direction_deg": "Wind direction",
    "active_power_kw": "Power",
}
REGISTRY = [
    {
        "farm_id": "EDP_PT",
        "turbine_id": "T01",
        "latitude": 41.0,
        "longitude": -8.0,
        "rated_power_kw": 2000,
        "data_source": "fixture",
    }
]


class ExcelConnectorTests(unittest.TestCase):
    def _workbook(self, root: Path, frame: pd.DataFrame) -> Path:
        path = root / "fixture.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name="SCADA 2016", index=False)
        return path

    def test_normalizes_an_explicitly_mapped_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._workbook(
                Path(temp_dir),
                pd.DataFrame(
                    {
                        "Time": ["2016-01-01T00:00:00Z"],
                        "Asset": ["T01"],
                        "Wind speed": [7.2],
                        "Wind direction": [180],
                        "Power": [950],
                    }
                ),
            )
            dataset = ExcelFarmConnector(
                path,
                sheet_name="SCADA 2016",
                column_mapping=MAPPING,
                registry_records=REGISTRY,
                data_source="fixture",
            ).load()

        self.assertEqual(list(dataset.data.columns), [
            "timestamp_utc", "turbine_id", "wind_speed_ms", "wind_direction_deg", "active_power_kw"
        ])
        self.assertEqual(dataset.data.iloc[0]["timestamp_utc"], "2016-01-01T00:00:00Z")
        self.assertEqual(dataset.registry.farm_ids(), ["EDP_PT"])

    def test_rejects_missing_mapped_source_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._workbook(
                Path(temp_dir),
                pd.DataFrame({"Time": [], "Asset": [], "Wind speed": [], "Wind direction": []}),
            )
            with self.assertRaises(ValueError) as context:
                ExcelFarmConnector(
                    path,
                    sheet_name="SCADA 2016",
                    column_mapping=MAPPING,
                    registry_records=REGISTRY,
                    data_source="fixture",
                ).load()
        self.assertIn("Power", str(context.exception))

    def test_rejects_duplicate_turbine_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            frame = pd.DataFrame(
                {
                    "Time": ["2016-01-01T00:00:00Z"] * 2,
                    "Asset": ["T01"] * 2,
                    "Wind speed": [7.2, 7.3],
                    "Wind direction": [180, 181],
                    "Power": [950, 960],
                }
            )
            path = self._workbook(Path(temp_dir), frame)
            with self.assertRaises(ValueError) as context:
                ExcelFarmConnector(
                    path,
                    sheet_name="SCADA 2016",
                    column_mapping=MAPPING,
                    registry_records=REGISTRY,
                    data_source="fixture",
                ).load()
        self.assertIn("duplicate", str(context.exception))

    def test_edp_adapter_combines_explicit_turbine_workbooks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for turbine, power in (("T01", 320.3), ("T06", 410.2)):
                path = root / f"{turbine}_F95.xlsx"
                frame = pd.DataFrame(
                    {
                        "Turbine_ID": [turbine],
                        "Timestamp": ["2016-01-01T00:50:00+00:00"],
                        "Amb_WindSpeed_Avg": [6.0],
                        "Amb_WindDir_Abs_Avg": [213.7],
                        "Grd_Prod_Pwr_Avg": [power],
                    }
                )
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    frame.to_excel(writer, sheet_name=f"{turbine}_F95", index=False)
                frames.append(path)
            registry = [
                {**REGISTRY[0], "turbine_id": "T01"},
                {**REGISTRY[0], "turbine_id": "T06", "latitude": 41.1},
            ]
            dataset = EDPPortugalSCADAConnector(
                frames, registry_records=registry,
            ).load()

        self.assertEqual(len(dataset.data), 2)
        self.assertEqual(sorted(dataset.data["turbine_id"]), ["T01", "T06"])
        self.assertEqual(dataset.data.iloc[0]["active_power_kw"], 320.3)

    def test_edp_adapter_rejects_cross_file_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame = pd.DataFrame(
                {
                    "Turbine_ID": ["T01"],
                    "Timestamp": ["2016-01-01T00:50:00+00:00"],
                    "Amb_WindSpeed_Avg": [6.0],
                    "Amb_WindDir_Abs_Avg": [213.7],
                    "Grd_Prod_Pwr_Avg": [320.3],
                }
            )
            paths = []
            for index in range(2):
                path = root / f"copy_{index}.xlsx"
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    frame.to_excel(writer, sheet_name="SCADA", index=False)
                paths.append(path)
            with self.assertRaises(ValueError) as context:
                EDPPortugalSCADAConnector(paths, registry_records=REGISTRY).load()
        self.assertIn("duplicate", str(context.exception))

    def test_edp_adapter_duplicate_policy_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame = pd.DataFrame(
                {
                    "Turbine_ID": ["T01", "T01"],
                    "Timestamp": ["2016-01-01T00:50:00+00:00"] * 2,
                    "Amb_WindSpeed_Avg": [6.0, 6.1],
                    "Amb_WindDir_Abs_Avg": [213.7, 213.8],
                    "Grd_Prod_Pwr_Avg": [320.3, 321.0],
                }
            )
            path = root / "duplicate.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                frame.to_excel(writer, sheet_name="SCADA", index=False)
            with self.assertRaises(ValueError):
                EDPPortugalSCADAConnector([path], registry_records=REGISTRY).load()
            dataset = EDPPortugalSCADAConnector(
                [path], registry_records=REGISTRY, duplicate_policy="keep_first"
            ).load()
        self.assertEqual(len(dataset.data), 1)


if __name__ == "__main__":
    unittest.main()
