"""Schema-driven Excel connector for external farm SCADA sources.

The connector deliberately requires an explicit sheet name and column mapping.
External workbooks vary too much for filename or fuzzy-column inference to be a
safe ingestion strategy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from windlens.connectors import FarmDataset
from windlens.farm_registry import FarmRegistry
from windlens.prepare_dataset import CANONICAL_FIELDS


class ExcelFarmConnector:
    """Normalize one Excel SCADA sheet into the WindLens farm boundary.

    ``column_mapping`` maps canonical field names to exact source column names.
    Values are expected to already be in the canonical units (UTC timestamps,
    m/s, degrees, and kW); unit conversion belongs in a source-specific adapter.
    ``registry_records`` supplies the independently verified farm/turbine metadata
    needed for geographic reference selection.
    """

    def __init__(
        self,
        workbook_path: str | Path,
        *,
        sheet_name: str,
        column_mapping: dict[str, str],
        registry_records: Iterable[dict[str, Any]],
        data_source: str,
        duplicate_policy: str = "reject",
    ) -> None:
        self.workbook_path = Path(workbook_path)
        self.sheet_name = sheet_name
        self.column_mapping = dict(column_mapping)
        self.registry_records = list(registry_records)
        self.data_source = data_source
        if duplicate_policy not in {"reject", "keep_first"}:
            raise ValueError("duplicate_policy must be 'reject' or 'keep_first'")
        self.duplicate_policy = duplicate_policy

    def load(self) -> FarmDataset:
        missing_mapping = set(CANONICAL_FIELDS) - set(self.column_mapping)
        if missing_mapping:
            raise ValueError(
                "Column mapping missing canonical fields: "
                + ", ".join(sorted(missing_mapping))
            )
        source = pd.read_excel(self.workbook_path, sheet_name=self.sheet_name)
        missing_columns = {
            source_name
            for canonical, source_name in self.column_mapping.items()
            if source_name not in source.columns
        }
        if missing_columns:
            raise ValueError(
                "Excel sheet missing mapped source columns: "
                + ", ".join(sorted(missing_columns))
            )
        data = source[[self.column_mapping[field] for field in CANONICAL_FIELDS]].rename(
            columns={source_name: canonical for canonical, source_name in self.column_mapping.items()}
        )
        data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True, errors="coerce")
        for field in CANONICAL_FIELDS[2:]:
            data[field] = pd.to_numeric(data[field], errors="coerce")
        if data[list(CANONICAL_FIELDS)].isna().any().any():
            raise ValueError("Excel source contains missing or unparseable canonical values")
        data["timestamp_utc"] = data["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if data.empty:
            raise ValueError("Excel sheet contains no records")
        duplicate_mask = data.duplicated(["timestamp_utc", "turbine_id"], keep=False)
        if duplicate_mask.any():
            if self.duplicate_policy == "reject":
                raise ValueError("Excel source contains duplicate turbine/timestamp records")
            data = data.loc[
                ~data.duplicated(["timestamp_utc", "turbine_id"], keep="first")
            ].copy()

        registry = FarmRegistry.from_records(self.registry_records)
        known_turbines = set(registry.to_frame()["turbine_id"])
        unknown = sorted(set(data["turbine_id"]) - known_turbines)
        if unknown:
            raise ValueError(
                "Excel source contains turbines absent from registry: " + ", ".join(unknown)
            )
        return FarmDataset(data=data, registry=registry, data_source=self.data_source)


class EDPExcelConnector(ExcelFarmConnector):
    """Named source boundary for the EDP Portugal workbook.

    The actual 219 MB EDP workbook is intentionally not bundled. Callers must
    provide its path, exact sheet, source mappings, and verified metadata records.
    """

    DEFAULT_DATA_SOURCE = "EDP Portugal SCADA, 2016-2017, CC BY 4.0"

    def __init__(self, workbook_path: str | Path, **kwargs: Any) -> None:
        kwargs.setdefault("data_source", self.DEFAULT_DATA_SOURCE)
        super().__init__(workbook_path, **kwargs)


class EDPPortugalSCADAConnector:
    """Load the published EDP Portugal turbine workbooks as one farm.

    The archive contains one workbook per turbine and year.  This adapter keeps
    the source mapping explicit and combines only files supplied by the caller;
    it never discovers files by fuzzy name matching.  Coordinates and rated
    power still come from the separately verified registry records because the
    public SCADA workbooks do not provide turbine geolocation.
    """

    DEFAULT_MAPPING = {
        "timestamp_utc": "Timestamp",
        "turbine_id": "Turbine_ID",
        "wind_speed_ms": "Amb_WindSpeed_Avg",
        "wind_direction_deg": "Amb_WindDir_Abs_Avg",
        "active_power_kw": "Grd_Prod_Pwr_Avg",
    }

    def __init__(
        self,
        workbook_paths: Sequence[str | Path],
        *,
        registry_records: Iterable[dict[str, Any]],
        sheet_names: dict[str | Path, str] | None = None,
        column_mapping: dict[str, str] | None = None,
        data_source: str = EDPExcelConnector.DEFAULT_DATA_SOURCE,
        duplicate_policy: str = "reject",
    ) -> None:
        self.workbook_paths = [Path(path) for path in workbook_paths]
        self.registry_records = list(registry_records)
        self.sheet_names = {Path(path): name for path, name in (sheet_names or {}).items()}
        self.column_mapping = dict(column_mapping or self.DEFAULT_MAPPING)
        self.data_source = data_source
        if duplicate_policy not in {"reject", "keep_first"}:
            raise ValueError("duplicate_policy must be 'reject' or 'keep_first'")
        self.duplicate_policy = duplicate_policy

    def load(self) -> FarmDataset:
        if not self.workbook_paths:
            raise ValueError("EDP connector requires at least one workbook")
        datasets: list[FarmDataset] = []
        for path in self.workbook_paths:
            if not path.exists():
                raise FileNotFoundError(path)
            sheet = self.sheet_names.get(path, 0)
            datasets.append(
                ExcelFarmConnector(
                    path,
                    sheet_name=sheet,
                    column_mapping=self.column_mapping,
                    registry_records=self.registry_records,
                    data_source=self.data_source,
                    duplicate_policy=self.duplicate_policy,
                ).load()
            )
        data = pd.concat([dataset.data for dataset in datasets], ignore_index=True)
        duplicate_mask = data.duplicated(["timestamp_utc", "turbine_id"], keep=False)
        if duplicate_mask.any():
            if self.duplicate_policy == "reject":
                raise ValueError("EDP workbooks contain duplicate turbine/timestamp records")
            data = data.loc[
                ~data.duplicated(["timestamp_utc", "turbine_id"], keep="first")
            ].copy()
        return FarmDataset(data=data, registry=datasets[0].registry, data_source=self.data_source)
