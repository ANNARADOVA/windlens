from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from windlens.registry_import import load_registry_csv


HEADERS = [
    "farm_id",
    "turbine_id",
    "latitude",
    "longitude",
    "rated_power_kw",
    "data_source",
    "quality_status",
]


def write_registry(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


class RegistryImportTests(unittest.TestCase):
    def valid_row(self, **overrides: str) -> dict[str, str]:
        row = {
            "farm_id": "EDP_PT",
            "turbine_id": "T01",
            "latitude": "41.0",
            "longitude": "-8.0",
            "rated_power_kw": "2000",
            "data_source": "operator survey 2026-10-20",
            "quality_status": "verified",
        }
        row.update(overrides)
        return row

    def test_imports_valid_registry_and_reports_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "edp_registry.csv"
            write_registry(path, [self.valid_row()])
            result = load_registry_csv(path)

        self.assertEqual(result.registry.farm_ids(), ["EDP_PT"])
        self.assertEqual(result.registry.turbine_ids("EDP_PT"), ["T01"])
        self.assertEqual(result.report["accepted_rows"], 1)
        self.assertEqual(result.report["rejected_rows"], 0)
        self.assertTrue(result.report["usable_for_geo_selection"])
        self.assertEqual(result.report["source_filename"], "edp_registry.csv")
        self.assertEqual(len(result.report["source_md5"]), 32)

    def test_rejects_missing_required_column_with_row_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=[header for header in HEADERS if header != "longitude"])
                writer.writeheader()
                writer.writerow({key: value for key, value in self.valid_row().items() if key != "longitude"})
            with self.assertRaises(ValueError) as context:
                load_registry_csv(path)

        self.assertIn("longitude", str(context.exception))

    def test_rejects_unverified_metadata_when_geo_selection_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unverified.csv"
            write_registry(path, [self.valid_row(quality_status="unverified")])
            result = load_registry_csv(path, require_verified=True)

        self.assertEqual(result.report["accepted_rows"], 1)
        self.assertFalse(result.report["usable_for_geo_selection"])
        self.assertTrue(any(issue["code"] == "unverified_metadata" for issue in result.report["issues"]))

    def test_rejects_duplicate_and_invalid_rows_without_fabricating_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mixed.csv"
            write_registry(
                path,
                [
                    self.valid_row(),
                    self.valid_row(),
                    self.valid_row(turbine_id="T02", latitude="91"),
                ],
            )
            result = load_registry_csv(path)

        self.assertEqual(result.report["accepted_rows"], 1)
        self.assertEqual(result.report["rejected_rows"], 2)
        self.assertFalse(result.report["usable_for_geo_selection"])
        codes = {issue["code"] for issue in result.report["issues"]}
        self.assertEqual(codes, {"duplicate_key", "invalid_record"})


if __name__ == "__main__":
    unittest.main()
