from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from windlens.mask_outage import mask_outage


CANONICAL_HEADER = (
    "timestamp_utc,turbine_id,wind_speed_ms,wind_direction_deg,active_power_kw\n"
)


def _write_canonical(path: Path) -> None:
    path.write_text(
        CANONICAL_HEADER
        + "2016-07-04T23:50:00Z,KWF1,6.0,180,500\n"
        + "2016-07-05T00:00:00Z,KWF1,6.1,181,510\n"
        + "2016-07-05T00:10:00Z,KWF1,6.2,181,520\n"
        + "2016-07-05T00:20:00Z,KWF1,6.3,182,530\n"
        + "2016-07-05T00:00:00Z,KWF2,5.9,180,490\n"
        + "2016-07-05T00:10:00Z,KWF2,6.0,181,500\n"
        + "2016-07-05T00:20:00Z,KWF2,6.1,182,510\n",
        encoding="utf-8",
    )


class MaskOutageTests(unittest.TestCase):
    def test_splits_only_the_target_turbines_rows_within_the_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "canonical.csv"
            masked_path = root / "masked.csv"
            hidden_path = root / "hidden_truth.csv"
            _write_canonical(input_path)

            report = mask_outage(
                input_path=input_path,
                masked_output_path=masked_path,
                hidden_truth_output_path=hidden_path,
                target_turbine="KWF1",
                start="2016-07-05T00:00:00Z",
                end="2016-07-05T00:20:00Z",
            )

            with masked_path.open(newline="") as handle:
                masked_rows = list(csv.DictReader(handle))
            with hidden_path.open(newline="") as handle:
                hidden_rows = list(csv.DictReader(handle))

        # The two KWF1 rows inside [start, end) move to hidden truth; everything
        # else -- the KWF1 row before the window and all KWF2 rows -- stays masked.
        self.assertEqual(
            [row["timestamp_utc"] for row in hidden_rows],
            ["2016-07-05T00:00:00Z", "2016-07-05T00:10:00Z"],
        )
        self.assertTrue(all(row["turbine_id"] == "KWF1" for row in hidden_rows))

        self.assertEqual(len(masked_rows), 5)
        self.assertNotIn(
            "2016-07-05T00:00:00Z",
            [row["timestamp_utc"] for row in masked_rows if row["turbine_id"] == "KWF1"],
        )
        kwf2_timestamps = [row["timestamp_utc"] for row in masked_rows if row["turbine_id"] == "KWF2"]
        self.assertEqual(len(kwf2_timestamps), 3)

        self.assertEqual(report["masked_rows_removed"], 2)
        self.assertEqual(report["masked_output_rows"], 5)
        self.assertEqual(report["mask_start_utc"], "2016-07-05T00:00:00Z")
        self.assertEqual(report["mask_end_utc"], "2016-07-05T00:20:00Z")

    def test_checksums_in_report_match_the_written_files(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "canonical.csv"
            masked_path = root / "masked.csv"
            hidden_path = root / "hidden_truth.csv"
            _write_canonical(input_path)

            report = mask_outage(
                input_path=input_path,
                masked_output_path=masked_path,
                hidden_truth_output_path=hidden_path,
                target_turbine="KWF1",
                start="2016-07-05T00:00:00Z",
                end="2016-07-05T00:20:00Z",
            )

            self.assertEqual(
                report["masked_output_md5"], hashlib.md5(masked_path.read_bytes()).hexdigest()
            )
            self.assertEqual(
                report["hidden_truth_output_md5"],
                hashlib.md5(hidden_path.read_bytes()).hexdigest(),
            )

    def test_raises_when_no_rows_fall_in_the_requested_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "canonical.csv"
            _write_canonical(input_path)

            with self.assertRaises(ValueError):
                mask_outage(
                    input_path=input_path,
                    masked_output_path=root / "masked.csv",
                    hidden_truth_output_path=root / "hidden_truth.csv",
                    target_turbine="KWF1",
                    start="2020-01-01T00:00:00Z",
                    end="2020-01-02T00:00:00Z",
                )


if __name__ == "__main__":
    unittest.main()
