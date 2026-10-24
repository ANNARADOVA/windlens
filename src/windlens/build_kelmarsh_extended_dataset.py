"""Build an EXTENDED Kelmarsh canonical slice spanning the full raw archive (2016-01-03
to 2017-01-01), separate from the 90-day slice the live demo uses.

Why a separate file: `data/derived/kelmarsh_2016_90d_canonical.csv` and its manifest are
read by `run_assessment.py` to generate the live workspace demo artifact. Overwriting that
file to extend its window would silently change what the demo shows. This script instead
produces `kelmarsh_2016_full_year_canonical.csv`, used only for back-test sample-size
expansion (see docs/DECISION_LOG.md, 2026-10-22 entry). The demo's inputs are untouched.
"""

from __future__ import annotations

from pathlib import Path

from windlens.coverage import simultaneous_overlap, turbine_coverage
from windlens.prepare_dataset import IMPLEMENTATION_VERSION, extract_canonical_slice
from windlens.provenance import build_manifest, write_manifest

ARCHIVE_PATH = Path("data/raw/Kelmarsh_SCADA_2016_3082.zip")
OUTPUT_PATH = Path("data/derived/kelmarsh_2016_full_year_canonical.csv")
MANIFEST_PATH = Path("data/derived/kelmarsh_2016_full_year_canonical.manifest.md")

SOURCE_DOI = "Plumley, C. & Takeuchi, R. (2025), Kelmarsh wind farm data v4, Zenodo, https://doi.org/10.5281/zenodo.16807551"
LICENCE = "CC BY 4.0"
EXPECTED_ARCHIVE_MD5 = "ca8efbb6dbcfae3516583937eb5b5402"

# Full span the raw archive's filenames declare: "2016-01-03_-_2017-01-01".
WINDOW_START = "2016-01-03T00:00:00Z"
WINDOW_END = "2017-01-01T00:00:00Z"

TARGET_TURBINE = "KWF1"
REFERENCE_TURBINES = ["KWF2", "KWF3", "KWF4", "KWF5", "KWF6"]
ALL_TURBINES = [TARGET_TURBINE, *REFERENCE_TURBINES]


def build_canonical_dataset() -> dict:
    import pandas as pd

    report = extract_canonical_slice(
        archive_path=ARCHIVE_PATH,
        output_path=OUTPUT_PATH,
        start=WINDOW_START,
        end=WINDOW_END,
        expected_archive_md5=EXPECTED_ARCHIVE_MD5,
    )

    df = pd.read_csv(OUTPUT_PATH, dtype={"timestamp_utc": str, "turbine_id": str})
    coverage_by_turbine = [
        turbine_coverage(df, turbine, WINDOW_START, WINDOW_END) for turbine in ALL_TURBINES
    ]
    overlap_with_target = [
        simultaneous_overlap(df, TARGET_TURBINE, reference, WINDOW_START, WINDOW_END)
        for reference in REFERENCE_TURBINES
    ]

    manifest = build_manifest(
        source_doi=SOURCE_DOI,
        licence=LICENCE,
        archive_path=ARCHIVE_PATH,
        expected_archive_md5=EXPECTED_ARCHIVE_MD5,
        observed_archive_md5=report["observed_archive_md5"],
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        implementation_version=IMPLEMENTATION_VERSION,
        output_path=OUTPUT_PATH,
        output_md5=report["output_md5"],
        extraction_report=report,
        coverage_by_turbine=coverage_by_turbine,
    )
    write_manifest(MANIFEST_PATH, manifest)

    return {
        "report": report,
        "manifest": manifest,
        "overlap_with_target": overlap_with_target,
    }


def _print_summary(result: dict) -> None:
    report = result["report"]
    print("=== Extended (full-year) canonical dataset built ===")
    print(f"Output: {OUTPUT_PATH} (md5 {report['output_md5']})")
    print(f"Archive checksum verified: {report['observed_archive_md5'] == EXPECTED_ARCHIVE_MD5}")
    print(f"Kept rows: {report['kept_rows']:,}")
    print(
        f"Dropped -- invalid: {report['dropped_invalid_rows']:,}, "
        f"implausible: {report['dropped_implausible_rows']:,}, "
        f"out-of-window: {report['dropped_out_of_window_rows']:,}, "
        f"out-of-cadence: {report['dropped_out_of_cadence_rows']:,}, "
        f"duplicates: {report['dropped_duplicate_rows']:,}"
    )
    print(f"Manifest written to: {MANIFEST_PATH}")
    print()
    print("Simultaneous target/reference overlap:")
    for entry in result["overlap_with_target"]:
        print(
            f"  {TARGET_TURBINE} & {entry['reference_turbine']}: "
            f"{entry['simultaneous_valid_slots']:,} shared valid slots"
        )


def main() -> None:
    result = build_canonical_dataset()
    _print_summary(result)


if __name__ == "__main__":
    main()
