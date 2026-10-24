"""Simulate an outage by masking a contiguous interval of a target turbine's records."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from windlens.checksums import file_md5


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def mask_outage(
    input_path: Path,
    masked_output_path: Path,
    hidden_truth_output_path: Path,
    target_turbine: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Remove `target_turbine` rows within [start, end) from the canonical dataset.

    Writes two CSVs with the input's schema: `masked_output_path` keeps every row
    except the removed ones, `hidden_truth_output_path` keeps only the removed ones.
    All other turbines are left untouched. The interval is start-inclusive,
    end-exclusive, matching the canonical extraction convention.
    """

    start_utc = _parse_ts(start)
    end_utc = _parse_ts(end)
    if start_utc >= end_utc:
        raise ValueError("start must be before end")

    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        fieldnames = reader.fieldnames
        rows = list(reader)

    masked_rows = []
    hidden_rows = []
    for row in rows:
        timestamp = _parse_ts(row["timestamp_utc"])
        if row["turbine_id"] == target_turbine and start_utc <= timestamp < end_utc:
            hidden_rows.append(row)
        else:
            masked_rows.append(row)

    if not hidden_rows:
        raise ValueError(
            f"No {target_turbine} rows found in [{start}, {end}); nothing to mask"
        )

    def _write(path: Path, out_rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as out_file:
            writer = csv.DictWriter(out_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(out_rows)

    _write(masked_output_path, masked_rows)
    _write(hidden_truth_output_path, hidden_rows)

    return {
        "target_turbine": target_turbine,
        "mask_start_utc": start,
        "mask_end_utc": end,
        "masked_rows_removed": len(hidden_rows),
        "masked_output_rows": len(masked_rows),
        "masked_output_path": str(masked_output_path),
        "masked_output_md5": file_md5(masked_output_path),
        "hidden_truth_output_path": str(hidden_truth_output_path),
        "hidden_truth_output_md5": file_md5(hidden_truth_output_path),
    }
