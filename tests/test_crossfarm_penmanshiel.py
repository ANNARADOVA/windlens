from __future__ import annotations

import csv
import re
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from windlens.farm_registry import FarmRegistry
from windlens.prepare_dataset import extract_canonical_slice
from windlens.run_kelmarsh_penmanshiel_crossfarm_backtest import (
    assert_references_from_other_farm,
    block_grid,
    block_is_eligible,
    coverage_table,
)


class PenmanshielRegistryTests(unittest.TestCase):
    def test_static_csv_with_blank_padding_rows_and_trailing_column_loads(self) -> None:
        header = "Wind Farm,Title,Alternative Title,Identity,Manufacturer,Model,Rated power (kW),Hub Height (m),Rotor Diameter (m),Latitude,Longitude,Elevation (m),Country,Commercial Operations Date,\n"
        row = "Penmanshiel,Penmanshiel 01,T01,x,Senvion,MM82,2050,59,82,55.902502,-2.306389,212.26,UK,01/09/2016,\n"
        blanks = ",,,,,,,,,,,,,,\n" * 3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "static.csv"
            path.write_text("﻿" + header + row + blanks, encoding="utf-8")
            registry = FarmRegistry.from_csv(path, data_source="test")
        self.assertEqual(registry.turbine_ids("Penmanshiel"), ["T01"])
        self.assertAlmostEqual(registry.get("Penmanshiel", "T01").latitude, 55.902502)


class GenericExtractionTests(unittest.TestCase):
    def test_pattern_and_id_format_produce_penmanshiel_ids(self) -> None:
        pattern = re.compile(r"Turbine_Data_Penmanshiel_(\d+)_")
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "a.zip", Path(tmp) / "out.csv"
            body = (
                "# header\n"
                "# Date and time,Wind speed (m/s),Wind direction (°),Power (kW)\n"
                "2016-09-01 00:00:00,5.0,200.0,300.0\n"
                "2016-09-01 00:10:00,5.0,200.0,-3.0\n"  # negative standby power -> dropped as implausible
            )
            with ZipFile(archive, "w") as z:
                z.writestr("Turbine_Data_Penmanshiel_01_2016-06-06_-_2017-01-01_1042.csv", body)
            report = extract_canonical_slice(
                archive, out, "2016-09-01T00:00:00Z", "2016-09-02T00:00:00Z",
                turbine_file_pattern=pattern, turbine_id_format="T{}",
            )
            with out.open() as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual([r["turbine_id"] for r in rows], ["T01"])
        self.assertEqual(report["dropped_implausible_rows"], 1)


def _frame(turbines: dict[str, float], start="2016-10-01T00:00:00Z", days=5) -> pd.DataFrame:
    stamps = pd.date_range(start, periods=days * 144, freq="10min", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    frames = []
    for turbine, coverage in turbines.items():
        keep = stamps[: int(len(stamps) * coverage)]
        frames.append(pd.DataFrame({"timestamp_utc": keep, "turbine_id": turbine}))
    return pd.concat(frames, ignore_index=True)


class BlockRuleTests(unittest.TestCase):
    def test_grid_is_non_overlapping_five_day_tiling(self) -> None:
        blocks = block_grid("2016-09-01T00:00:00Z", "2016-09-21T00:00:00Z")
        self.assertEqual(len(blocks), 4)
        for (_, end), (start, _) in zip(blocks, blocks[1:]):
            self.assertEqual(end, start)

    def test_eligibility_needs_target_and_five_reference_turbines_at_threshold(self) -> None:
        blocks = block_grid("2016-10-01T00:00:00Z", "2016-10-06T00:00:00Z")
        refs = [f"T0{i}" for i in range(1, 7)]
        good = _frame({"KWF1": 0.95, **{r: 0.95 for r in refs}})
        self.assertTrue(block_is_eligible(coverage_table(good, blocks), "KWF1", refs, blocks[0][0]))
        bad_target = _frame({"KWF1": 0.5, **{r: 0.95 for r in refs}})
        self.assertFalse(block_is_eligible(coverage_table(bad_target, blocks), "KWF1", refs, blocks[0][0]))
        few_refs = _frame({"KWF1": 0.95, **{r: (0.95 if i < 4 else 0.5) for i, r in enumerate(refs)}})
        self.assertFalse(block_is_eligible(coverage_table(few_refs, blocks), "KWF1", refs, blocks[0][0]))


class CrossFarmGuardTests(unittest.TestCase):
    def test_same_farm_reference_is_rejected(self) -> None:
        with self.assertRaises(AssertionError):
            assert_references_from_other_farm(
                {"baseline_reference": "KWF2", "ensemble_references": ["T01"]}, ["T01", "T02"]
            )
        assert_references_from_other_farm(
            {"baseline_reference": "T01", "ensemble_references": ["T01", "T02"]}, ["T01", "T02"]
        )


if __name__ == "__main__":
    unittest.main()
