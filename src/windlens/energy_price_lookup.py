"""Real historical German balancing-energy price (reBAP) lookup.

Looks up the netztransparenz.de reBAP ("Ausgleichsenergiepreis") monthly
average for the calendar month(s) an outage window falls in, so an outage's
"indicative financial impact" can use a real published price instead of a
manually chosen illustrative one.

Only covers months for which a downloaded, provenance-documented source file
exists under ``data/raw/netztransparenz_rebap/`` (see that directory's
README for the download details). A month with no downloaded file raises
``PriceDataUnavailable`` rather than inventing a plausible-looking number.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

SOURCE_NAME = "netztransparenz.de reBAP (quality-assured)"
SOURCE_URL = (
    "https://www.netztransparenz.de/en/Balancing-Capacity/"
    "Imbalance-price/Uniform-imbalance-price-reBAP"
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data" / "raw" / "netztransparenz_rebap"

# One downloaded, provenance-noted source file per calendar month covered so far.
_MONTH_FILES: dict[str, Path] = {
    "2026-09": _DATA_DIR / "rebap_2026-09_raw.csv",
}

_PRICE_COLUMN = "reBAP unterdeckt"  # identical to "reBAP ueberdeckt" in this export; see README


class PriceDataUnavailable(Exception):
    """Raised when no downloaded reBAP source file covers a requested month."""


@dataclass(frozen=True)
class MonthlyPrice:
    """The real reBAP average for one calendar month, with provenance."""

    month: str  # "YYYY-MM"
    average_price_eur_per_mwh: float
    n_price_points: int
    source_name: str
    source_url: str
    data_file: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "average_price_eur_per_mwh": self.average_price_eur_per_mwh,
            "n_price_points": self.n_price_points,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "data_file": self.data_file,
        }


def _parse_de_float(value: str) -> float:
    return float(value.strip().replace(",", "."))


def _to_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _months_spanned(window_start: date, window_end: date) -> list[str]:
    if window_end < window_start:
        raise ValueError("window_end must not be before window_start")
    months: list[str] = []
    cursor = window_start.replace(day=1)
    end_marker = window_end.replace(day=1)
    while cursor <= end_marker:
        key = f"{cursor.year:04d}-{cursor.month:02d}"
        months.append(key)
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


def monthly_average(month: str) -> MonthlyPrice:
    """Return the real reBAP average for one calendar month ("YYYY-MM").

    Raises ``PriceDataUnavailable`` if no source file has been downloaded
    for that month (this never estimates or fabricates a price).
    """

    data_file = _MONTH_FILES.get(month)
    if data_file is None or not data_file.exists():
        raise PriceDataUnavailable(
            f"No downloaded netztransparenz.de reBAP data for {month}. "
            "Download it (see data/raw/netztransparenz_rebap/README.md) "
            "before this month can be looked up -- this lookup never "
            "fabricates a price for a month it has no real data for."
        )

    prices: list[float] = []
    with data_file.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            prices.append(_parse_de_float(row[_PRICE_COLUMN]))

    if not prices:
        raise PriceDataUnavailable(f"Source file for {month} contained no price rows: {data_file}")

    average = sum(prices) / len(prices)
    try:
        data_file_display = str(data_file.relative_to(_REPO_ROOT))
    except ValueError:
        data_file_display = str(data_file)
    return MonthlyPrice(
        month=month,
        average_price_eur_per_mwh=round(average, 2),
        n_price_points=len(prices),
        source_name=SOURCE_NAME,
        source_url=SOURCE_URL,
        data_file=data_file_display,
    )


def get_price_for_outage_window(
    window_start: date | str, window_end: date | str
) -> dict[str, Any]:
    """Return the real reBAP monthly average(s) covering an outage window.

    ``window_start``/``window_end`` may be ``date`` objects or "YYYY-MM-DD"
    strings; both are inclusive calendar dates. If the window spans more
    than one calendar month, each month's average is returned separately in
    ``months``, and ``average_price_eur_per_mwh`` is the price-point-weighted
    average across all of them (the right single number to multiply lost
    MWh by when the window straddles a month boundary).

    Raises ``PriceDataUnavailable`` if any touched month has no downloaded
    source file -- it never fabricates a number for a missing month.
    """

    start = _to_date(window_start)
    end = _to_date(window_end)
    months = [monthly_average(m) for m in _months_spanned(start, end)]

    total_points = sum(m.n_price_points for m in months)
    weighted_average = (
        sum(m.average_price_eur_per_mwh * m.n_price_points for m in months) / total_points
    )

    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "average_price_eur_per_mwh": round(weighted_average, 2),
        "n_price_points": total_points,
        "months": [m.as_dict() for m in months],
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
    }
