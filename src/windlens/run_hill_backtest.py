"""Reproducible bounded Hill of Towie external-farm back-test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from windlens.backtest import aggregate_backtest, run_backtest_event
from windlens.checksums import file_md5


DEFAULT_BLOCKS = (
    ("2026-03-01T00:00:00Z", "2026-03-06T00:00:00Z"),
    ("2026-04-01T00:00:00Z", "2026-04-06T00:00:00Z"),
    ("2026-04-15T00:00:00Z", "2026-04-20T00:00:00Z"),
)


def run_hill_backtest(
    canonical_path: str | Path,
    registry_path: str | Path,
    output_path: str | Path,
    *,
    target_turbine: str = "T01",
) -> dict:
    canonical = pd.read_csv(canonical_path)
    canonical["timestamp_utc"] = pd.to_datetime(canonical["timestamp_utc"], utc=True)
    registry = pd.read_csv(registry_path)
    candidates = sorted(set(canonical["turbine_id"]) - {target_turbine})
    events = [
        run_backtest_event(
            canonical,
            target_turbine,
            candidates,
            block_start,
            block_end,
            ensemble_size=3,
            metadata_df=registry,
        )
        for block_start, block_end in DEFAULT_BLOCKS
    ]
    artifact = {
        "artifact_version": "external-backtest.v1",
        "validation_scope": "external_farm_only",
        "farm_id": "Hill of Towie",
        "target_turbine": target_turbine,
        "canonical_path": str(canonical_path),
        "canonical_md5": file_md5(Path(canonical_path)),
        "registry_path": str(registry_path),
        "registry_md5": file_md5(Path(registry_path)),
        "lookback_windows_days": [30, 90, 180],
        "candidate_count": len(candidates),
        "kelmarsh_training_used": False,
        "model_training_mixed_with_kelmarsh": False,
        "blocks": events,
        "aggregate": aggregate_backtest(events),
        "honesty_note": (
            "Each block hides healthy target data as a simulated outage. Hidden truth is used only for scoring; "
            "reference selection, fitting, power-curve construction, and interval calibration use pre-block data."
        ),
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2, default=str) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run_hill_backtest(args.canonical, args.registry, args.output), indent=2, default=str))


if __name__ == "__main__":
    main()
