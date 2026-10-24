"""Small connector boundary for farm SCADA datasets.

Connectors keep source-specific loading separate from reconstruction.  Every
connector returns the same canonical dataframe plus a validated FarmRegistry, so
Kelmarsh can be replaced by an external farm without changing model code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from windlens.farm_registry import FarmRegistry
from windlens.prepare_dataset import CANONICAL_FIELDS


@dataclass(frozen=True)
class FarmDataset:
    data: pd.DataFrame
    registry: FarmRegistry
    data_source: str


class FarmDataConnector(Protocol):
    def load(self) -> FarmDataset:
        """Load one farm dataset into the canonical WindLens boundary."""


class CsvFarmConnector:
    """Load a canonical SCADA CSV and normalized turbine metadata CSV."""

    def __init__(
        self,
        canonical_path: str | Path,
        metadata_path: str | Path,
        *,
        data_source: str,
    ) -> None:
        self.canonical_path = Path(canonical_path)
        self.metadata_path = Path(metadata_path)
        self.data_source = data_source

    def load(self) -> FarmDataset:
        data = pd.read_csv(
            self.canonical_path,
            dtype={"timestamp_utc": str, "turbine_id": str},
        )
        missing = set(CANONICAL_FIELDS) - set(data.columns)
        if missing:
            raise ValueError(
                f"Canonical CSV missing required fields: {', '.join(sorted(missing))}"
            )
        if data.empty:
            raise ValueError("Canonical CSV contains no records")
        registry = FarmRegistry.from_csv(self.metadata_path, data_source=self.data_source)
        known_turbines = set(registry.to_frame()["turbine_id"])
        unknown = sorted(set(data["turbine_id"].dropna()) - known_turbines)
        if unknown:
            raise ValueError(
                "Canonical CSV contains turbines absent from metadata: "
                + ", ".join(unknown)
            )
        return FarmDataset(data=data, registry=registry, data_source=self.data_source)


class KelmarshConnector(CsvFarmConnector):
    """Connector for the already-derived Kelmarsh canonical slice."""

    def __init__(
        self,
        canonical_path: str | Path = "data/derived/kelmarsh_2016_90d_canonical.csv",
        metadata_path: str | Path = "data/raw/Kelmarsh_WT_static.csv",
    ) -> None:
        super().__init__(
            canonical_path,
            metadata_path,
            data_source="Zenodo 10.5281/zenodo.16807551 / Kelmarsh SCADA v4",
        )


class PenmanshielConnector(CsvFarmConnector):
    """Connector for the derived Penmanshiel canonical slice (Cubico, CC-BY-4.0).

    Same publisher, signal conventions and 10-minute UTC Greenbyte export format as
    Kelmarsh, so the canonical frame is schema-identical; only the turbine ids
    (T01..T15, no T03) and the static registry differ.
    """

    def __init__(
        self,
        canonical_path: str | Path = "data/derived/penmanshiel_2016_canonical.csv",
        metadata_path: str | Path = "data/raw/penmanshiel/Penmanshiel_WT_static.csv",
    ) -> None:
        super().__init__(
            canonical_path,
            metadata_path,
            data_source="Zenodo 10.5281/zenodo.16807304 / Penmanshiel wind farm data",
        )
