"""Combine separately-scored Hill of Towie yearly method sweeps."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from windlens.checksums import file_md5
from windlens.run_hill_method_sweep import run_sweep


def run_multiyear(canonical_by_year: dict[str, str], registry_path: str, output_path: str) -> dict:
    yearly = {}
    all_blocks = []
    for year, canonical in sorted(canonical_by_year.items()):
        blocks = tuple(
            (f"{year}-{month}-01T00:00:00Z", f"{year}-{month}-06T00:00:00Z")
            for month in ("03", "04")
        ) + ((f"{year}-04-15T00:00:00Z", f"{year}-04-20T00:00:00Z"),)
        with tempfile.NamedTemporaryFile(suffix=".json") as handle:
            result = run_sweep(canonical, registry_path, handle.name, blocks=blocks)
        yearly[year] = {
            "canonical_path": canonical,
            "canonical_md5": file_md5(Path(canonical)),
            "target_count": result["target_count"],
            "scored_event_count": result["scored_event_count"],
            "unscorable_event_count": result["unscorable_event_count"],
            "abstention_count": result["abstention_count"],
            "aggregate": result["aggregate"],
        }
        for block in result["blocks"]:
            block = dict(block)
            block["year"] = year
            all_blocks.append(block)
    scored = [block for block in all_blocks if block["status"] == "scored"]
    aggregate = {}
    for method in ("direct_power", "wind_first"):
        total_actual = sum(block[method]["actual_kwh"] for block in scored)
        total_abs_error = sum(abs(block[method]["expected_kwh"] - block[method]["actual_kwh"]) for block in scored)
        total_bias = sum(block[method]["expected_kwh"] - block[method]["actual_kwh"] for block in scored)
        aggregate[method] = {
            "energy_weighted_wape_pct": total_abs_error / max(total_actual, 1e-9) * 100,
            "signed_aggregate_bias_pct": total_bias / max(total_actual, 1e-9) * 100,
        }
    artifact = {
        "artifact_version": "method-multiyear-sweep.v1",
        "farm_id": "Hill of Towie",
        "registry_path": registry_path,
        "registry_md5": file_md5(Path(registry_path)),
        "years": yearly,
        "scored_event_count": len(scored),
        "abstention_count": len(all_blocks) - len(scored),
        "unscorable_event_count": sum(block["status"] == "unscorable" for block in all_blocks),
        "aggregate": aggregate,
        "blocks": all_blocks,
        "kelmarsh_training_used": False,
        "model_training_mixed_with_kelmarsh": False,
        "honesty_note": (
            "Each year was scored separately. The yearly outputs were combined only after reference selection, "
            "fitting, and held-out scoring. The same pre-declared March/April blocks and method rules were used."
        ),
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--canonical", action="append", nargs=2, metavar=("YEAR", "PATH"), required=True)
    args = parser.parse_args()
    print(json.dumps(run_multiyear(dict(args.canonical), args.registry, args.output), indent=2))


if __name__ == "__main__":
    main()
