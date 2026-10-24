from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from windlens.prepare_dataset import extract_canonical_slice


# Mirrors the real Kelmarsh export: several comment lines, then the header row.
PREAMBLE = "\n".join(f"# comment line {i}" for i in range(9)) + "\n"
HEADER = "# Date and time,Wind speed (m/s),Wind direction (°),Power (kW)\n"


def _build_archive(archive_path: Path, member_name: str, body: str) -> None:
    with zipfile.ZipFile(archive_path, "w") as zip_file:
        zip_file.writestr(member_name, PREAMBLE + body)


class ExtractCanonicalSliceTests(unittest.TestCase):
    def test_extracts_only_valid_10_minute_records_in_the_requested_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            output = root / "slice.csv"
            _build_archive(
                archive,
                # Realistic Kelmarsh filename shape: turbine number + exported date range.
                "Turbine_Data_Kelmarsh_1_2016-01-01_-_2017-01-01_228.csv",
                HEADER
                + "2016-02-01 00:00:00,7.2,180,950\n"
                + "2016-02-01 00:10:00,NaN,181,960\n"  # unparseable -> invalid
                + "2016-02-01 00:20:00,7.4,181,-2\n"  # negative power -> implausible
                + "2016-02-01 00:25:00,7.5,182,970\n"  # off-cadence
                + "2016-02-01 00:30:00,7.6,182,980\n"  # valid
                + "2016-02-02 00:00:00,7.8,183,990\n",  # out of window
            )

            report = extract_canonical_slice(
                archive_path=archive,
                output_path=output,
                start="2016-02-01T00:00:00Z",
                end="2016-02-02T00:00:00Z",
            )

            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(
            [row["timestamp_utc"] for row in rows],
            ["2016-02-01T00:00:00Z", "2016-02-01T00:30:00Z"],
        )
        self.assertEqual(rows[0]["turbine_id"], "KWF1")
        self.assertEqual(report["kept_rows"], 2)
        self.assertEqual(report["dropped_invalid_rows"], 1)
        self.assertEqual(report["dropped_implausible_rows"], 1)
        self.assertEqual(report["dropped_out_of_cadence_rows"], 1)
        self.assertEqual(report["dropped_out_of_window_rows"], 1)
        self.assertIn("output_md5", report)
        self.assertIn("observed_archive_md5", report)

    def test_raises_when_a_required_source_column_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            bad_header = "# Date and time,Wind speed (m/s),Power (kW)\n"  # no direction column
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                bad_header + "2016-02-01 00:00:00,7.2,950\n",
            )

            with self.assertRaises(ValueError) as ctx:
                extract_canonical_slice(
                    archive_path=archive,
                    output_path=root / "slice.csv",
                    start="2016-02-01T00:00:00Z",
                    end="2016-02-02T00:00:00Z",
                )
            self.assertIn("Wind direction", str(ctx.exception))

    def test_raises_when_no_valid_records_are_produced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                HEADER + "2016-02-01 00:25:00,7.2,180,950\n",  # only an off-cadence row
            )

            with self.assertRaises(ValueError):
                extract_canonical_slice(
                    archive_path=archive,
                    output_path=root / "slice.csv",
                    start="2016-02-01T00:00:00Z",
                    end="2016-02-02T00:00:00Z",
                )

    def test_drops_duplicate_timestamp_turbine_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                HEADER
                + "2016-02-01 00:00:00,7.2,180,950\n"
                + "2016-02-01 00:00:00,7.3,181,955\n",  # same timestamp, same turbine
            )

            report = extract_canonical_slice(
                archive_path=archive,
                output_path=root / "slice.csv",
                start="2016-02-01T00:00:00Z",
                end="2016-02-02T00:00:00Z",
            )

            self.assertEqual(report["kept_rows"], 1)
            self.assertEqual(report["dropped_duplicate_rows"], 1)

    def test_normalizes_exact_360_degrees_and_rejects_out_of_range_directions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            output = root / "slice.csv"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                HEADER
                + "2016-02-01 00:00:00,7.2,360,950\n"  # exact 360 -> normalized to 0, kept
                + "2016-02-01 00:10:00,7.3,-5,955\n"  # negative -> implausible
                + "2016-02-01 00:20:00,7.4,361,960\n",  # >360 -> implausible
            )

            report = extract_canonical_slice(
                archive_path=archive,
                output_path=output,
                start="2016-02-01T00:00:00Z",
                end="2016-02-02T00:00:00Z",
            )

            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(report["kept_rows"], 1)
            self.assertEqual(report["dropped_implausible_rows"], 2)
            self.assertEqual(float(rows[0]["wind_direction_deg"]), 0.0)

    def test_rejects_physically_implausible_wind_speed_and_power(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                HEADER
                + "2016-02-01 00:00:00,999,180,950\n"  # wind speed far out of range
                + "2016-02-01 00:10:00,7.0,180,99999\n"  # power far over rated+tolerance
                + "2016-02-01 00:20:00,7.0,180,950\n",  # valid
            )

            report = extract_canonical_slice(
                archive_path=archive,
                output_path=root / "slice.csv",
                start="2016-02-01T00:00:00Z",
                end="2016-02-02T00:00:00Z",
            )

            self.assertEqual(report["kept_rows"], 1)
            self.assertEqual(report["dropped_implausible_rows"], 2)

    def test_power_overspeed_tolerance_is_configurable_above_rated_power(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                # 2100 kW: above the 2050 kW rating but within a 10% overspeed tolerance.
                HEADER + "2016-02-01 00:00:00,7.0,180,2100\n",
            )

            report = extract_canonical_slice(
                archive_path=archive,
                output_path=root / "slice.csv",
                start="2016-02-01T00:00:00Z",
                end="2016-02-02T00:00:00Z",
                rated_power_kw=2050.0,
                power_overspeed_tolerance=0.10,
            )

            self.assertEqual(report["kept_rows"], 1)
            self.assertEqual(report["dropped_implausible_rows"], 0)

    def test_raises_on_archive_checksum_mismatch_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            output = root / "slice.csv"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                HEADER + "2016-02-01 00:00:00,7.2,180,950\n",
            )

            with self.assertRaises(ValueError):
                extract_canonical_slice(
                    archive_path=archive,
                    output_path=output,
                    start="2016-02-01T00:00:00Z",
                    end="2016-02-02T00:00:00Z",
                    expected_archive_md5="0" * 32,
                )

            self.assertFalse(output.exists())

    def test_preserves_a_previous_valid_output_when_a_later_run_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "source.zip"
            output = root / "slice.csv"
            _build_archive(
                archive,
                "Turbine_Data_Kelmarsh_1_2016.csv",
                HEADER + "2016-02-01 00:00:00,7.2,180,950\n",
            )

            extract_canonical_slice(
                archive_path=archive,
                output_path=output,
                start="2016-02-01T00:00:00Z",
                end="2016-02-02T00:00:00Z",
            )
            original_bytes = output.read_bytes()
            original_md5 = hashlib.md5(original_bytes).hexdigest()

            # A broken archive (missing required column) run onto the same output path
            # must fail without touching the existing file.
            bad_archive = root / "bad.zip"
            bad_header = "# Date and time,Wind speed (m/s),Power (kW)\n"
            _build_archive(bad_archive, "Turbine_Data_Kelmarsh_1_2016.csv", bad_header + "x\n")

            with self.assertRaises(ValueError):
                extract_canonical_slice(
                    archive_path=bad_archive,
                    output_path=output,
                    start="2016-02-01T00:00:00Z",
                    end="2016-02-02T00:00:00Z",
                )

            self.assertEqual(output.read_bytes(), original_bytes)
            self.assertEqual(hashlib.md5(output.read_bytes()).hexdigest(), original_md5)
            self.assertFalse(output.with_name(output.name + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
