"""Validated farm/turbine metadata shared by all WindLens data connectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class TurbineMetadata:
    farm_id: str
    turbine_id: str
    latitude: float
    longitude: float
    rated_power_kw: float
    data_source: str
    elevation_m: float | None = None
    hub_height_m: float | None = None
    time_coverage_start: str | None = None
    time_coverage_end: str | None = None
    quality_status: str = "unverified"


class FarmRegistry:
    """A validated registry; farms remain separate by construction."""

    def __init__(self, records: Iterable[TurbineMetadata]):
        self._records = {(record.farm_id, record.turbine_id): record for record in records}

    @classmethod
    def from_records(cls, records: Iterable[dict[str, Any]]) -> "FarmRegistry":
        parsed: list[TurbineMetadata] = []
        seen: set[tuple[str, str]] = set()
        for raw in records:
            try:
                record = TurbineMetadata(
                    farm_id=str(raw["farm_id"]),
                    turbine_id=str(raw["turbine_id"]),
                    latitude=float(raw["latitude"]),
                    longitude=float(raw["longitude"]),
                    rated_power_kw=float(raw["rated_power_kw"]),
                    data_source=str(raw["data_source"]),
                    elevation_m=_optional_float(raw.get("elevation_m")),
                    hub_height_m=_optional_float(raw.get("hub_height_m")),
                    time_coverage_start=_optional_text(raw.get("time_coverage_start")),
                    time_coverage_end=_optional_text(raw.get("time_coverage_end")),
                    quality_status=str(raw.get("quality_status", "unverified")),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid turbine registry record: {raw}") from exc
            if not -90 <= record.latitude <= 90 or not -180 <= record.longitude <= 180:
                raise ValueError(f"Invalid coordinates for {record.farm_id}/{record.turbine_id}")
            if record.rated_power_kw <= 0:
                raise ValueError(f"Rated power must be positive for {record.turbine_id}")
            key = (record.farm_id, record.turbine_id)
            if key in seen:
                raise ValueError(f"Duplicate registry key: {record.farm_id}/{record.turbine_id}")
            seen.add(key)
            parsed.append(record)
        if not parsed:
            raise ValueError("Farm registry cannot be empty")
        return cls(parsed)

    @classmethod
    def from_csv(cls, path: str | Path, *, data_source: str) -> "FarmRegistry":
        frame = pd.read_csv(path, encoding="utf-8-sig")
        # Some publisher CSVs (Penmanshiel_WT_static.csv) end with blank padding rows and
        # an unnamed trailing column; drop wholly empty rows/columns, never fill values.
        frame = frame.dropna(how="all").dropna(axis="columns", how="all")
        frame = frame.loc[:, ~frame.columns.astype(str).str.startswith("Unnamed")]
        columns = {
            "Wind Farm": "farm_id", "Alternative Title": "turbine_id",
            "Latitude": "latitude", "Longitude": "longitude",
            "Elevation (m)": "elevation_m", "Hub Height (m)": "hub_height_m",
            "Rated power (kW)": "rated_power_kw",
        }
        frame = frame.rename(columns=columns)
        missing = {"farm_id", "turbine_id", "latitude", "longitude", "rated_power_kw"} - set(frame.columns)
        if missing:
            raise ValueError(f"Registry CSV missing required columns: {', '.join(sorted(missing))}")
        records = frame.to_dict(orient="records")
        for record in records:
            record["data_source"] = data_source
        return cls.from_records(records)

    def get(self, farm_id: str, turbine_id: str) -> TurbineMetadata:
        try:
            return self._records[(farm_id, turbine_id)]
        except KeyError as exc:
            raise KeyError(f"Unknown turbine {farm_id}/{turbine_id}") from exc

    def farm_ids(self) -> list[str]:
        return sorted({farm_id for farm_id, _ in self._records})

    def turbine_ids(self, farm_id: str) -> list[str]:
        return sorted(turbine_id for current_farm, turbine_id in self._records if current_farm == farm_id)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(record) for record in self._records.values()])


def _optional_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


def _optional_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value)
