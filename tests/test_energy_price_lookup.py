from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from windlens import energy_price_lookup as epl
from windlens.energy_price_lookup import (
    PriceDataUnavailable,
    get_price_for_outage_window,
    monthly_average,
)


def _write_month_csv(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Datum", "Zeitzone", "von", "bis", "Einheit", "reBAP unterdeckt", "reBAP ueberdeckt"])
        for row in rows:
            writer.writerow(row)


class MonthlyAverageSyntheticTests(unittest.TestCase):
    def test_averages_a_small_synthetic_month(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "rebap_2099-01_raw.csv"
            _write_month_csv(
                data_file,
                [
                    ["01.01.2099", "CET", "00:00", "00:15", "EUR/MWh", "100,00", "100,00"],
                    ["01.01.2099", "CET", "00:15", "00:30", "EUR/MWh", "200,50", "200,50"],
                    ["01.01.2099", "CET", "00:30", "00:45", "EUR/MWh", "-50,50", "-50,50"],
                ],
            )
            with mock.patch.dict(epl._MONTH_FILES, {"2099-01": data_file}, clear=True):
                result = monthly_average("2099-01")

        self.assertEqual(result.month, "2099-01")
        self.assertEqual(result.n_price_points, 3)
        self.assertAlmostEqual(result.average_price_eur_per_mwh, 83.33, places=2)
        self.assertEqual(result.source_name, epl.SOURCE_NAME)
        self.assertEqual(result.source_url, epl.SOURCE_URL)

    def test_handles_german_decimal_comma_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "rebap_2099-02_raw.csv"
            _write_month_csv(
                data_file,
                [["01.02.2099", "CET", "00:00", "00:15", "EUR/MWh", "1234,56", "1234,56"]],
            )
            with mock.patch.dict(epl._MONTH_FILES, {"2099-02": data_file}, clear=True):
                result = monthly_average("2099-02")

        self.assertAlmostEqual(result.average_price_eur_per_mwh, 1234.56, places=2)

    def test_unavailable_month_raises_instead_of_fabricating(self) -> None:
        with mock.patch.dict(epl._MONTH_FILES, {}, clear=True):
            with self.assertRaises(PriceDataUnavailable):
                monthly_average("2099-03")

    def test_unavailable_month_error_names_the_month(self) -> None:
        with mock.patch.dict(epl._MONTH_FILES, {}, clear=True):
            with self.assertRaisesRegex(PriceDataUnavailable, "2099-03"):
                monthly_average("2099-03")


class GetPriceForOutageWindowSyntheticTests(unittest.TestCase):
    def test_single_month_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "rebap_2099-04_raw.csv"
            _write_month_csv(
                data_file,
                [
                    ["01.04.2099", "CEST", "00:00", "00:15", "EUR/MWh", "100,00", "100,00"],
                    ["02.04.2099", "CEST", "00:00", "00:15", "EUR/MWh", "300,00", "300,00"],
                ],
            )
            with mock.patch.dict(epl._MONTH_FILES, {"2099-04": data_file}, clear=True):
                result = get_price_for_outage_window("2099-04-01", "2099-04-04")

        self.assertEqual(result["average_price_eur_per_mwh"], 200.0)
        self.assertEqual(result["n_price_points"], 2)
        self.assertEqual(len(result["months"]), 1)
        self.assertEqual(result["months"][0]["month"], "2099-04")
        self.assertEqual(result["window_start"], "2099-04-01")
        self.assertEqual(result["window_end"], "2099-04-04")

    def test_window_spanning_two_months_is_point_weighted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            may_file = Path(temp_dir) / "rebap_2099-05_raw.csv"
            june_file = Path(temp_dir) / "rebap_2099-06_raw.csv"
            # May: a single 100 EUR/MWh point.
            _write_month_csv(
                may_file,
                [["31.05.2099", "CEST", "23:45", "00:00", "EUR/MWh", "100,00", "100,00"]],
            )
            # June: three 400 EUR/MWh points.
            _write_month_csv(
                june_file,
                [
                    ["01.06.2099", "CEST", "00:00", "00:15", "EUR/MWh", "400,00", "400,00"],
                    ["01.06.2099", "CEST", "00:15", "00:30", "EUR/MWh", "400,00", "400,00"],
                    ["01.06.2099", "CEST", "00:30", "00:45", "EUR/MWh", "400,00", "400,00"],
                ],
            )
            with mock.patch.dict(
                epl._MONTH_FILES, {"2099-05": may_file, "2099-06": june_file}, clear=True
            ):
                result = get_price_for_outage_window(date(2099, 5, 31), date(2099, 6, 1))

        self.assertEqual(len(result["months"]), 2)
        self.assertEqual(result["n_price_points"], 4)
        # Point-weighted: (1*100 + 3*400) / 4 = 325.0, not the naive 250.0 average of the two months.
        self.assertEqual(result["average_price_eur_per_mwh"], 325.0)

    def test_missing_month_in_window_raises(self) -> None:
        with mock.patch.dict(epl._MONTH_FILES, {}, clear=True):
            with self.assertRaises(PriceDataUnavailable):
                get_price_for_outage_window("2099-07-01", "2099-07-02")


class RealDataIntegrationTests(unittest.TestCase):
    """Exercises the actual downloaded September 2026 reBAP file for WindLens's real outage windows."""

    def test_hidden_outage_window_2026_09_01_to_04(self) -> None:
        result = get_price_for_outage_window("2026-09-01", "2026-09-04")

        self.assertEqual(result["months"], [epl.monthly_average("2026-09").as_dict()])
        self.assertGreater(result["n_price_points"], 0)
        self.assertGreater(result["average_price_eur_per_mwh"], 0.0)
        self.assertEqual(result["source_name"], epl.SOURCE_NAME)
        self.assertIn("netztransparenz.de", result["source_url"])

    def test_self_validation_window_2026_09_04_to_10(self) -> None:
        result = get_price_for_outage_window("2026-09-04", "2026-09-10")

        self.assertEqual(len(result["months"]), 1)
        self.assertEqual(result["months"][0]["month"], "2026-09")
        self.assertGreater(result["average_price_eur_per_mwh"], 0.0)

    def test_full_month_average_matches_known_value(self) -> None:
        # Independently verified against data/raw/netztransparenz_rebap/rebap_2026-09_raw.csv
        # (2,880 quarter-hour rows for the full month).
        result = monthly_average("2026-09")

        self.assertEqual(result.n_price_points, 2880)
        self.assertAlmostEqual(result.average_price_eur_per_mwh, 150.88, delta=0.1)
        self.assertEqual(result.data_file, "data/raw/netztransparenz_rebap/rebap_2026-09_raw.csv")


if __name__ == "__main__":
    unittest.main()
