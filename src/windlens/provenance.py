"""Provenance manifest generation for a canonical-dataset extraction run."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_manifest(
    *,
    source_doi: str,
    licence: str,
    archive_path: Path,
    expected_archive_md5: str,
    observed_archive_md5: str,
    window_start: str,
    window_end: str,
    implementation_version: str,
    output_path: Path,
    output_md5: str,
    extraction_report: dict[str, Any],
    coverage_by_turbine: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the structured manifest for one extraction run. Writes nothing."""

    return {
        "source_doi": source_doi,
        "licence": licence,
        "source_archive": archive_path.name,
        "expected_archive_md5": expected_archive_md5,
        "observed_archive_md5": observed_archive_md5,
        "archive_checksum_verified": expected_archive_md5 == observed_archive_md5,
        "window_start_utc": window_start,
        "window_end_utc": window_end,
        "implementation_version": implementation_version,
        "output_file": output_path.name,
        "output_md5": output_md5,
        "extraction_report": extraction_report,
        "coverage_by_turbine": coverage_by_turbine,
    }


def render_manifest_markdown(manifest: dict[str, Any]) -> str:
    """Render a manifest dict (from build_manifest) as the dataset's .manifest.md text."""

    report = manifest["extraction_report"]
    checksum_note = (
        "(verified)"
        if manifest["archive_checksum_verified"]
        else "(MISMATCH -- do not trust this run)"
    )

    lines = [
        f"# {manifest['output_file']} -- canonical demo slice",
        "",
        "_Generated programmatically by `src/windlens/build_canonical_dataset.py`. "
        "Do not hand-edit; rerun the script instead._",
        "",
        "## Provenance",
        "",
        f"- Source: {manifest['source_doi']}",
        f"- Licence: {manifest['licence']}",
        f"- Raw archive: `{manifest['source_archive']}`",
        f"- Raw archive MD5 expected: `{manifest['expected_archive_md5']}`",
        f"- Raw archive MD5 observed: `{manifest['observed_archive_md5']}` {checksum_note}",
        f"- Extraction implementation: `src/windlens/prepare_dataset.py` "
        f"(`{manifest['implementation_version']}`)",
        "",
        "## Working interval",
        "",
        f"- Start (inclusive): `{manifest['window_start_utc']}`",
        f"- End (exclusive): `{manifest['window_end_utc']}`",
        "- Cadence: 10 minutes, UTC",
        "",
        "## Extracted artefact",
        "",
        f"- File: `{manifest['output_file']}`",
        f"- MD5: `{manifest['output_md5']}`",
        f"- Valid records: {report['kept_rows']:,}",
        f"- Invalid (unparseable/missing-field) source readings excluded: {report['dropped_invalid_rows']:,}",
        f"- Physically implausible readings excluded: {report['dropped_implausible_rows']:,}",
        f"- Records outside the working interval excluded: {report['dropped_out_of_window_rows']:,}",
        f"- Records outside the 10-minute cadence excluded: {report['dropped_out_of_cadence_rows']:,}",
        f"- Duplicate records excluded: {report['dropped_duplicate_rows']:,}",
        "",
        "## Coverage",
        "",
        "| Turbine | Expected slots | Valid slots | Coverage | Contiguous gaps |",
        "|---|---:|---:|---:|---:|",
    ]
    for entry in manifest["coverage_by_turbine"]:
        lines.append(
            f"| {entry['turbine_id']} | {entry['expected_slots']:,} | "
            f"{entry['actual_valid_slots']:,} | {entry['coverage_pct']:.1f}% | "
            f"{len(entry['contiguous_gaps'])} |"
        )
    lines.extend(
        [
            "",
            "This derived dataset supports a simulated missing-data test only. It must "
            "not be described as a real outage or a final energy-loss claim. Kelmarsh's "
            "reference turbines are in the *same* farm, not a separate neighbouring farm "
            "-- see docs/DECISION_LOG.md.",
            "",
        ]
    )
    return "\n".join(lines)


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_manifest_markdown(manifest), encoding="utf-8")
