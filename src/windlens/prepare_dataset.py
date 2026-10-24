"""Create a small, auditable working slice from the Kelmarsh SCADA archive."""

from __future__ import annotations

import csv
import math
import re
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from windlens.checksums import file_md5

IMPLEMENTATION_VERSION = "prepare_dataset.v2-section8"

CANONICAL_FIELDS = (
    "timestamp_utc",
    "turbine_id",
    "wind_speed_ms",
    "wind_direction_deg",
    "active_power_kw",
)
REQUIRED_SOURCE_COLUMNS = ("Wind speed (m/s)", "Wind direction (°)", "Power (kW)")
_TURBINE_FILE = re.compile(r"Turbine_Data_Kelmarsh_(\d+)_")


def _parse_requested_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Requested timestamps must include an explicit timezone")
    return parsed.astimezone(UTC)


def _source_rows(zip_file: ZipFile, member_name: str):
    with zip_file.open(member_name) as binary_file:
        text_file = TextIOWrapper(binary_file, encoding="utf-8-sig", newline="")
        for line in text_file:
            if line.startswith("# Date and time,"):
                headers = next(csv.reader([line]))
                missing = [column for column in REQUIRED_SOURCE_COLUMNS if column not in headers]
                if missing:
                    raise ValueError(
                        f"{member_name} is missing required source column(s): "
                        f"{', '.join(missing)}"
                    )
                yield from csv.DictReader(text_file, fieldnames=headers)
                return
    raise ValueError(f"No SCADA header found in {member_name}")


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_direction_deg(value: float) -> float:
    """Treat an exact 360 reading as the equivalent 0, per the `[0, 360)` policy."""

    return 0.0 if value == 360.0 else value


def extract_canonical_slice(
    archive_path: Path,
    output_path: Path,
    start: str,
    end: str,
    *,
    expected_archive_md5: str | None = None,
    min_wind_speed_ms: float = 0.0,
    max_wind_speed_ms: float = 50.0,
    rated_power_kw: float = 2050.0,
    power_overspeed_tolerance: float = 0.10,
    turbine_file_pattern: re.Pattern[str] = _TURBINE_FILE,
    turbine_id_format: str = "KWF{}",
) -> dict[str, Any]:
    """Extract valid 10-minute SCADA readings into the MVP's canonical CSV schema.

    The interval is start-inclusive and end-exclusive. Kelmarsh source timestamps are
    documented as UTC; the output makes that fact explicit by serialising ISO-8601 Z
    timestamps.

    Physical plausibility is enforced on top of pure parse validity: wind speed must
    fall in [min_wind_speed_ms, max_wind_speed_ms], wind direction is normalised to
    [0, 360), and power must fall in [0, rated_power_kw * (1 + power_overspeed_tolerance)]
    -- a documented overspeed tolerance above nameplate rating rather than a hard cap at
    rated power, since real turbines can briefly exceed rated output.

    If `expected_archive_md5` is given, the archive's observed checksum is verified
    before any extraction happens. The output is written atomically: a failure (bad
    archive checksum, missing source columns, zero valid records, or any other error)
    never touches a pre-existing output_path -- all writing happens to a temp file that
    is only renamed into place on full success.

    ``turbine_file_pattern`` / ``turbine_id_format`` (2026-10-23) let the same hardened
    extraction serve another Greenbyte-format farm (Penmanshiel) without duplicating it;
    the defaults reproduce the original Kelmarsh behaviour exactly.
    """

    start_utc = _parse_requested_timestamp(start)
    end_utc = _parse_requested_timestamp(end)
    if start_utc >= end_utc:
        raise ValueError("start must be before end")

    observed_archive_md5 = file_md5(archive_path)
    if expected_archive_md5 is not None and observed_archive_md5 != expected_archive_md5:
        raise ValueError(
            f"Archive checksum mismatch for {archive_path.name}: "
            f"expected {expected_archive_md5}, observed {observed_archive_md5}"
        )

    max_power_kw = rated_power_kw * (1 + power_overspeed_tolerance)

    report: dict[str, Any] = {
        "source_archive": archive_path.name,
        "observed_archive_md5": observed_archive_md5,
        "window_start_utc": start,
        "window_end_utc": end,
        "kept_rows": 0,
        "dropped_invalid_rows": 0,
        "dropped_implausible_rows": 0,
        "dropped_out_of_cadence_rows": 0,
        "dropped_out_of_window_rows": 0,
        "dropped_duplicate_rows": 0,
    }
    seen: set[tuple[str, datetime]] = set()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".tmp")

    try:
        with ZipFile(archive_path) as zip_file, temp_path.open(
            "w", newline="", encoding="utf-8"
        ) as output_file:
            writer = csv.DictWriter(output_file, fieldnames=CANONICAL_FIELDS)
            writer.writeheader()

            source_members = sorted(
                member for member in zip_file.namelist() if turbine_file_pattern.search(member)
            )
            if not source_members:
                raise ValueError("Archive does not contain matching turbine SCADA files")

            for member_name in source_members:
                turbine_number = turbine_file_pattern.search(member_name).group(1)  # type: ignore[union-attr]
                turbine_id = turbine_id_format.format(turbine_number)
                for row in _source_rows(zip_file, member_name):
                    try:
                        timestamp = datetime.strptime(
                            row["# Date and time"], "%Y-%m-%d %H:%M:%S"
                        ).replace(tzinfo=UTC)
                    except (KeyError, ValueError):
                        report["dropped_invalid_rows"] += 1
                        continue

                    if not start_utc <= timestamp < end_utc:
                        report["dropped_out_of_window_rows"] += 1
                        continue
                    if timestamp.second or timestamp.minute % 10:
                        report["dropped_out_of_cadence_rows"] += 1
                        continue

                    wind_speed = _as_float(row.get("Wind speed (m/s)"))
                    wind_direction = _as_float(row.get("Wind direction (°)"))
                    power = _as_float(row.get("Power (kW)"))
                    if wind_speed is None or wind_direction is None or power is None:
                        report["dropped_invalid_rows"] += 1
                        continue

                    wind_direction = _normalize_direction_deg(wind_direction)
                    if (
                        not min_wind_speed_ms <= wind_speed <= max_wind_speed_ms
                        or not 0.0 <= wind_direction < 360.0
                        or not 0.0 <= power <= max_power_kw
                    ):
                        report["dropped_implausible_rows"] += 1
                        continue

                    key = (turbine_id, timestamp)
                    if key in seen:
                        report["dropped_duplicate_rows"] += 1
                        continue
                    seen.add(key)

                    writer.writerow(
                        {
                            "timestamp_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "turbine_id": turbine_id,
                            "wind_speed_ms": wind_speed,
                            "wind_direction_deg": wind_direction,
                            "active_power_kw": power,
                        }
                    )
                    report["kept_rows"] += 1

        if report["kept_rows"] == 0:
            raise ValueError(
                "Extraction produced zero valid records; refusing to write output"
            )

        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    report["output_md5"] = file_md5(output_path)
    return report
