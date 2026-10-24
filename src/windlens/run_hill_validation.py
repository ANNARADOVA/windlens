"""Run Hill of Towie as an independent external-farm input validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from windlens.checksums import file_md5
from windlens.connectors import CsvFarmConnector
from windlens.registry_import import load_registry_csv


def run_hill_validation(
    canonical_path: str | Path,
    registry_path: str | Path,
    preparation_audit_path: str | Path,
    output_path: str | Path,
) -> dict:
    registry_result = load_registry_csv(registry_path)
    farm_ids = registry_result.registry.farm_ids()
    if farm_ids != ["Hill of Towie"]:
        raise ValueError("Hill of Towie validation requires only the Hill of Towie registry")
    dataset = CsvFarmConnector(
        canonical_path,
        registry_path,
        data_source="Zenodo 10.5281/zenodo.22662930 / Hill of Towie SCADA",
    ).load()
    audit = json.loads(Path(preparation_audit_path).read_text(encoding="utf-8"))
    artifact = {
        "artifact_version": "external-validation.v1",
        "validation_scope": "external_farm_only",
        "farm_id": "Hill of Towie",
        "data_source": dataset.data_source,
        "canonical_path": str(canonical_path),
        "row_count": int(len(dataset.data)),
        "turbine_ids": sorted(dataset.data["turbine_id"].unique().tolist()),
        "time_range": {
            "start": str(dataset.data["timestamp_utc"].min()),
            "end": str(dataset.data["timestamp_utc"].max()),
        },
        "registry_evidence": registry_result.report,
        "preparation_audit": audit,
        "status": (
            "validated_input_with_source_quality_findings"
            if audit["status"] != "prepared"
            else "validated_input"
        ),
        "kelmarsh_training_used": False,
        "model_training_mixed_with_kelmarsh": False,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--preparation-audit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run_hill_validation(
        canonical_path=args.canonical,
        registry_path=args.registry,
        preparation_audit_path=args.preparation_audit,
        output_path=args.output,
    ), indent=2))


if __name__ == "__main__":
    main()
