from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from windlens.run_external_validation import run_edp_validation


REGISTRY_HEADERS = [
    "farm_id", "turbine_id", "latitude", "longitude", "rated_power_kw", "data_source", "quality_status"
]


def write_registry(path: Path, farm_id: str = "EDP_PT") -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_HEADERS)
        writer.writeheader()
        writer.writerow({
            "farm_id": farm_id, "turbine_id": "T01", "latitude": "41", "longitude": "-8",
            "rated_power_kw": "2000", "data_source": "operator registry", "quality_status": "verified",
        })


def write_workbook(path: Path, duplicate: bool = False) -> None:
    rows = {
        "Turbine_ID": ["T01", "T01"] if duplicate else ["T01"],
        "Timestamp": ["2016-01-01T00:50:00+00:00"] * (2 if duplicate else 1),
        "Amb_WindSpeed_Avg": [6.0, 6.1] if duplicate else [6.0],
        "Amb_WindDir_Abs_Avg": [213.7, 213.8] if duplicate else [213.7],
        "Grd_Prod_Pwr_Avg": [320.3, 321.0] if duplicate else [320.3],
    }
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="T01_F95", index=False)


class ExternalValidationTests(unittest.TestCase):
    def test_writes_standalone_edp_validation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workbook = root / "T01_F95.xlsx"
            registry = root / "registry.csv"
            output = root / "edp_validation.json"
            write_workbook(workbook)
            write_registry(registry)
            result = run_edp_validation([workbook], registry, output)
            artifact = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result["farm_id"], "EDP_PT")
        self.assertEqual(artifact["validation_scope"], "external_farm_only")
        self.assertEqual(artifact["row_count"], 1)
        self.assertTrue(artifact["registry_evidence"]["usable_for_geo_selection"])
        self.assertEqual(artifact["status"], "validated_input")

    def test_refuses_to_run_kelmarsh_as_external_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workbook = root / "T01_F95.xlsx"
            registry = root / "registry.csv"
            write_workbook(workbook)
            write_registry(registry, farm_id="KELMARSH")
            with self.assertRaises(ValueError) as context:
                run_edp_validation([workbook], registry, root / "output.json")

        self.assertIn("separate external farm", str(context.exception))

    def test_duplicate_policy_is_visible_in_validation_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workbook = root / "T01_F95.xlsx"
            registry = root / "registry.csv"
            write_workbook(workbook, duplicate=True)
            write_registry(registry)
            artifact = run_edp_validation(
                [workbook], registry, root / "output.json", duplicate_policy="keep_first"
            )

        self.assertEqual(artifact["duplicate_policy"], "keep_first")
        self.assertEqual(artifact["status"], "unverified_data_quality")
        self.assertEqual(artifact["duplicate_record_count"], 1)

    def test_can_write_blocked_preflight_when_registry_is_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workbook = root / "T01_F95.xlsx"
            registry = root / "empty_registry.csv"
            write_workbook(workbook)
            registry.write_text(",".join(REGISTRY_HEADERS) + "\n", encoding="utf-8")
            artifact = run_edp_validation(
                [workbook], registry, root / "preflight.json", allow_blocked=True
            )

        self.assertEqual(artifact["status"], "blocked_missing_registry")
        self.assertFalse(artifact["registry_evidence"]["usable_for_geo_selection"])
        self.assertFalse(artifact["kelmarsh_training_used"])


if __name__ == "__main__":
    unittest.main()
