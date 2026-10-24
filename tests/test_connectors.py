from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from windlens.connectors import CsvFarmConnector, KelmarshConnector


class ConnectorTests(unittest.TestCase):
    def test_kelmarsh_connector_returns_canonical_data_and_registry(self) -> None:
        dataset = KelmarshConnector().load()

        self.assertEqual(set(dataset.data.columns), {
            "timestamp_utc",
            "turbine_id",
            "wind_speed_ms",
            "wind_direction_deg",
            "active_power_kw",
        })
        self.assertEqual(dataset.registry.farm_ids(), ["Kelmarsh"])
        self.assertEqual(dataset.registry.turbine_ids("Kelmarsh"), [
            "KWF1", "KWF2", "KWF3", "KWF4", "KWF5", "KWF6"
        ])
        self.assertEqual(dataset.registry.get("Kelmarsh", "KWF1").latitude, 52.400604)

    def test_generic_connector_rejects_turbine_missing_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canonical = root / "canonical.csv"
            canonical.write_text(
                "timestamp_utc,turbine_id,wind_speed_ms,wind_direction_deg,active_power_kw\n"
                "2020-01-01T00:00:00Z,T2,5,180,500\n",
                encoding="utf-8",
            )
            metadata = root / "metadata.csv"
            metadata.write_text(
                "farm_id,turbine_id,latitude,longitude,rated_power_kw\n"
                "F1,T1,52,-1,2000\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                CsvFarmConnector(canonical, metadata, data_source="fixture").load()

        self.assertIn("absent from metadata", str(context.exception))

    def test_generic_connector_requires_canonical_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canonical = root / "canonical.csv"
            canonical.write_text("timestamp_utc,turbine_id\n", encoding="utf-8")
            metadata = root / "metadata.csv"
            metadata.write_text(
                "farm_id,turbine_id,latitude,longitude,rated_power_kw\n"
                "F1,T1,52,-1,2000\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                CsvFarmConnector(canonical, metadata, data_source="fixture").load()

        self.assertIn("Canonical CSV missing required fields", str(context.exception))


if __name__ == "__main__":
    unittest.main()
