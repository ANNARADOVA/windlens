"""Auditable import boundary for operator-supplied turbine metadata."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from windlens.checksums import file_md5
from windlens.farm_registry import FarmRegistry


REQUIRED_COLUMNS = {
    "farm_id",
    "turbine_id",
    "latitude",
    "longitude",
    "rated_power_kw",
    "data_source",
    "quality_status",
}


def load_registry_csv(
    path: str | Path,
    *,
    require_verified: bool = True,
) -> "RegistryImportResult":
    """Load and validate a registry without inventing missing metadata.

    Invalid rows are retained in the report and excluded from the registry. A
    report with any issue is not usable for geo-aware selection, even when some
    rows are valid.
    """

    source_path = Path(path)
    with source_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - headers)
        if missing:
            raise ValueError("Registry CSV missing required columns: " + ", ".join(missing))
        raw_rows = list(reader)

    issues: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row_number, raw in enumerate(raw_rows, start=2):
        farm_id = str(raw.get("farm_id", "")).strip()
        turbine_id = str(raw.get("turbine_id", "")).strip()
        key = (farm_id, turbine_id)
        if key in seen:
            issues.append({"row": row_number, "code": "duplicate_key", "message": f"Duplicate registry key {farm_id}/{turbine_id}"})
            continue
        seen.add(key)
        parsed = dict(raw)
        parsed["farm_id"] = farm_id
        parsed["turbine_id"] = turbine_id
        parsed["data_source"] = str(raw.get("data_source", "")).strip()
        parsed["quality_status"] = str(raw.get("quality_status", "")).strip().lower()
        try:
            # Validate one row through the same domain model used by all connectors.
            FarmRegistry.from_records([parsed])
        except ValueError as exc:
            issues.append({"row": row_number, "code": "invalid_record", "message": str(exc)})
            continue
        valid_rows.append(parsed)
        if require_verified and parsed["quality_status"] != "verified":
            issues.append({"row": row_number, "code": "unverified_metadata", "message": "quality_status must be verified for geo-aware selection"})

    if not valid_rows:
        raise ValueError("Registry CSV contains no valid metadata rows")

    registry = FarmRegistry.from_records(valid_rows)
    usable = not issues and all(row["quality_status"] == "verified" for row in valid_rows)
    report = {
        "report_version": "registry-import.v1",
        "source_filename": source_path.name,
        "source_md5": file_md5(source_path),
        "accepted_rows": len(valid_rows),
        "rejected_rows": len(raw_rows) - len(valid_rows),
        "farm_ids": registry.farm_ids(),
        "turbine_ids": sorted({row["turbine_id"] for row in valid_rows}),
        "quality_status": "verified" if usable else "needs_review",
        "usable_for_geo_selection": usable,
        "issues": issues,
    }
    return RegistryImportResult(registry=registry, report=report)


class RegistryImportResult:
    def __init__(self, *, registry: FarmRegistry, report: dict[str, Any]) -> None:
        self.registry = registry
        self.report = report
