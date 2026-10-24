"""Standalone validation runner for external farms."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from windlens.excel_connector import EDPPortugalSCADAConnector
from windlens.checksums import file_md5
from windlens.registry_import import load_registry_csv


def run_edp_validation(
    workbook_paths: Sequence[str | Path],
    registry_path: str | Path,
    output_path: str | Path,
    *,
    duplicate_policy: str = "reject",
    allow_blocked: bool = False,
) -> dict:
    """Validate EDP input as an independent farm and write an evidence artifact."""

    registry_path = Path(registry_path)
    try:
        registry_result = load_registry_csv(registry_path)
    except ValueError as exc:
        if not allow_blocked:
            raise
        artifact = {
            "artifact_version": "external-validation.v1",
            "validation_scope": "external_farm_only",
            "farm_id": None,
            "data_source": "EDP Portugal SCADA",
            "workbook_paths": [str(Path(path)) for path in workbook_paths],
            "registry_evidence": {
                "report_version": "registry-import.v1",
                "source_filename": registry_path.name,
                "source_md5": file_md5(registry_path),
                "accepted_rows": 0,
                "rejected_rows": 0,
                "farm_ids": [],
                "turbine_ids": [],
                "quality_status": "needs_review",
                "usable_for_geo_selection": False,
                "issues": [{"row": 0, "code": "missing_verified_registry", "message": str(exc)}],
            },
            "duplicate_policy": duplicate_policy,
            "duplicate_record_count": None,
            "status": "blocked_missing_registry",
            "kelmarsh_training_used": False,
        }
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        return artifact
    farm_ids = registry_result.registry.farm_ids()
    if len(farm_ids) != 1:
        raise ValueError("External validation requires exactly one farm registry")
    if farm_ids[0].upper() in {"KELMARSH", "KWF"}:
        raise ValueError("Kelmarsh must not be used as the separate external farm")

    paths = [Path(path) for path in workbook_paths]
    duplicate_count = _count_duplicate_source_records(paths)
    dataset = EDPPortugalSCADAConnector(
        paths,
        registry_records=registry_result.registry.to_frame().to_dict(orient="records"),
        duplicate_policy=duplicate_policy,
    ).load()
    status = "validated_input" if duplicate_count == 0 else "unverified_data_quality"
    artifact = {
        "artifact_version": "external-validation.v1",
        "validation_scope": "external_farm_only",
        "farm_id": farm_ids[0],
        "data_source": dataset.data_source,
        "workbook_paths": [str(path) for path in paths],
        "row_count": int(len(dataset.data)),
        "turbine_ids": sorted(dataset.data["turbine_id"].unique().tolist()),
        "time_range": {
            "start": str(dataset.data["timestamp_utc"].min()),
            "end": str(dataset.data["timestamp_utc"].max()),
        },
        "registry_evidence": registry_result.report,
        "duplicate_policy": duplicate_policy,
        "duplicate_record_count": duplicate_count,
        "status": status,
        "kelmarsh_training_used": False,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def _count_duplicate_source_records(paths: Sequence[Path]) -> int:
    frames = []
    for path in paths:
        source = pd.read_excel(path, sheet_name=0, usecols=["Timestamp", "Turbine_ID"])
        source["Timestamp"] = pd.to_datetime(source["Timestamp"], utc=True, errors="coerce")
        frames.append(source)
    combined = pd.concat(frames, ignore_index=True)
    return int(combined.duplicated(["Timestamp", "Turbine_ID"], keep="first").sum())
