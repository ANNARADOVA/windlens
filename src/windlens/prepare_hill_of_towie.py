"""Prepare a bounded Hill of Towie SCADA archive for WindLens validation.

The source archive keeps turbine measurements and grid power in separate
tables. This script joins them by the documented ``TimeStamp``/``StationId``
key, maps StationId to T01..T21, and writes the canonical WindLens columns.
It deliberately records duplicate and incomplete source rows in an audit
report instead of hiding them in a generic cleanup step.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from windlens.checksums import file_md5


SCADA_COLUMNS = [
    "TimeStamp",
    "StationId",
    "wtc_AcWindSp_mean",
    "wtc_ActualWindDirection_mean",
]
GRID_COLUMNS = ["TimeStamp", "StationId", "wtc_ActPower_mean"]
CANONICAL_COLUMNS = [
    "timestamp_utc",
    "turbine_id",
    "wind_speed_ms",
    "wind_direction_deg",
    "active_power_kw",
]


def prepare_archive(
    archive_path: str | Path,
    metadata_path: str | Path,
    output_path: str | Path,
    audit_path: str | Path,
) -> dict:
    archive = Path(archive_path)
    metadata = pd.read_csv(metadata_path, encoding="utf-8-sig")
    required_metadata = {"Turbine Name", "Station ID"}
    missing = required_metadata - set(metadata.columns)
    if missing:
        raise ValueError(f"Hill of Towie metadata missing: {', '.join(sorted(missing))}")
    station_to_turbine = {
        str(int(row["Station ID"])): str(row["Turbine Name"])
        for _, row in metadata.iterrows()
    }
    if len(station_to_turbine) != 21 or set(station_to_turbine.values()) != {f"T{i:02d}" for i in range(1, 22)}:
        raise ValueError("Hill of Towie metadata does not contain exactly T01..T21")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", prefix=f".{output.name}.",
        dir=output.parent, delete=False, encoding="utf-8", newline="",
    )
    temp_path = Path(temp_handle.name)
    temp_handle.close()

    audit = {
        "artifact_version": "hill-of-towie-preparation.v1",
        "source_archive": str(archive),
        "source_archive_md5": file_md5(archive),
        "metadata_source": str(metadata_path),
        "canonical_columns": CANONICAL_COLUMNS,
        "source_files": [],
        "source_rows": 0,
        "written_rows": 0,
        "duplicate_source_rows": 0,
        "incomplete_source_rows": 0,
        "unknown_station_rows": 0,
        "timestamp_range_utc": {"start": None, "end": None},
        "station_ids": sorted(station_to_turbine),
        "turbine_ids": sorted(station_to_turbine.values()),
        "status": "prepared",
    }
    seen: set[tuple[str, str]] = set()
    first_write = True
    with zipfile.ZipFile(archive) as bundle:
        turbine_files = sorted(
            name for name in bundle.namelist()
            if name.startswith("tblSCTurbine_") and name.endswith(".csv")
        )
        for turbine_name in turbine_files:
            month = turbine_name.removeprefix("tblSCTurbine_").removesuffix(".csv")
            grid_name = f"tblSCTurGrid_{month}.csv"
            if grid_name not in bundle.namelist():
                raise ValueError(f"Missing matching grid table for {turbine_name}")
            audit["source_files"].append({"turbine": turbine_name, "grid": grid_name})
            with bundle.open(turbine_name) as turbine_handle, bundle.open(grid_name) as grid_handle:
                turbine = pd.read_csv(turbine_handle, usecols=SCADA_COLUMNS)
                grid = pd.read_csv(grid_handle, usecols=GRID_COLUMNS)
            frame = turbine.merge(grid, on=["TimeStamp", "StationId"], how="inner")
            audit["source_rows"] += int(len(frame))
            frame["StationId"] = frame["StationId"].astype(str)
            unknown = ~frame["StationId"].isin(station_to_turbine)
            audit["unknown_station_rows"] += int(unknown.sum())
            frame = frame.loc[~unknown].copy()
            frame["timestamp_utc"] = pd.to_datetime(frame["TimeStamp"], utc=True, errors="coerce")
            frame["wind_speed_ms"] = pd.to_numeric(frame["wtc_AcWindSp_mean"], errors="coerce")
            frame["wind_direction_deg"] = pd.to_numeric(frame["wtc_ActualWindDirection_mean"], errors="coerce")
            frame["active_power_kw"] = pd.to_numeric(frame["wtc_ActPower_mean"], errors="coerce")
            incomplete = frame[["timestamp_utc", "wind_speed_ms", "wind_direction_deg", "active_power_kw"]].isna().any(axis=1)
            audit["incomplete_source_rows"] += int(incomplete.sum())
            frame = frame.loc[~incomplete].copy()
            frame["turbine_id"] = frame["StationId"].map(station_to_turbine)
            frame["timestamp_utc"] = frame["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            frame["key"] = list(zip(frame["turbine_id"], frame["timestamp_utc"]))
            duplicate = frame["key"].isin(seen)
            audit["duplicate_source_rows"] += int(duplicate.sum())
            frame = frame.loc[~duplicate].copy()
            seen.update(frame["key"])
            if frame.empty:
                continue
            frame = frame[CANONICAL_COLUMNS]
            frame.to_csv(temp_path, mode="a", header=first_write, index=False)
            first_write = False
            audit["written_rows"] += int(len(frame))

    if audit["written_rows"] == 0:
        raise ValueError("Hill of Towie preparation produced no canonical rows")
    audit["timestamp_range_utc"] = {
        "start": min(seen, key=lambda item: item[1])[1],
        "end": max(seen, key=lambda item: item[1])[1],
    }
    audit["status"] = "prepared_with_source_quality_findings" if (
        audit["duplicate_source_rows"] or audit["incomplete_source_rows"] or audit["unknown_station_rows"]
    ) else "prepared"
    os.replace(temp_path, output)
    destination = Path(audit_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_archive(args.archive, args.metadata, args.output, args.audit), indent=2))


if __name__ == "__main__":
    main()
