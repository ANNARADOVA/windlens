"""Build the Penmanshiel 2016 canonical slice (2026-10-23), for the Kelmarsh<->Penmanshiel
cross-farm back-test.

Source: Plumley, C. & Takeuchi, R. (2025), Penmanshiel wind farm data, Zenodo,
https://doi.org/10.5281/zenodo.16807304 -- released by Cubico Sustainable Investments
under CC BY 4.0 (the same publisher, licence, and Greenbyte export format as Kelmarsh).
Attribution to the authors and Cubico is required; the licence text is at
https://creativecommons.org/licenses/by/4.0/legalcode.

Reuses the hardened Kelmarsh extraction (``prepare_dataset.extract_canonical_slice``:
archive checksum verification, header validation, physical-plausibility filtering,
cadence/duplicate rules, atomic writes) via its pattern/id-format parameters -- the QA
rules are identical for both farms, deliberately.

Penmanshiel's 2016 archives start at commissioning (2016-06-02 .. 2016-07-27 per
turbine) and the farm's declared commercial-operations date is 2016-09-01, so
June-August 2016 data are commissioning-period data. The cross-farm back-test therefore
only draws blocks from 2016-09-01 onward (see run_kelmarsh_penmanshiel_crossfarm_backtest).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from windlens.checksums import file_md5
from windlens.coverage import turbine_coverage
from windlens.prepare_dataset import IMPLEMENTATION_VERSION, extract_canonical_slice

RAW_DIR = Path("data/raw/penmanshiel")
OUTPUT_PATH = Path("data/derived/penmanshiel_2016_canonical.csv")
MANIFEST_PATH = Path("data/derived/penmanshiel_2016_canonical.manifest.json")

SOURCE = (
    "Plumley, C. & Takeuchi, R. (2025), Penmanshiel wind farm data, Zenodo, "
    "https://doi.org/10.5281/zenodo.16807304"
)
LICENCE = "CC BY 4.0 (Cubico Sustainable Investments Ltd; attribution required)"
# MD5s published by Zenodo (zenodo_record_16807304.json, files[].checksum), verified at download.
ARCHIVES = {
    "Penmanshiel_SCADA_2016_WT01-10_3107.zip": "3819e1b2168b84da195b64e1e9d78b03",
    "Penmanshiel_SCADA_2016_WT11-15_3107.zip": "92c30453d43a38e985af3e2e305eedd4",
}
STATIC_CSV = RAW_DIR / "Penmanshiel_WT_static.csv"
STATIC_CSV_MD5 = "c4cd4191234c1a67a391fe5d2978256b"

WINDOW_START = "2016-01-01T00:00:00Z"
WINDOW_END = "2017-01-01T00:00:00Z"
TURBINE_FILE = re.compile(r"Turbine_Data_Penmanshiel_(\d+)_")
TURBINE_ID_FORMAT = "T{}"  # file number is already zero-padded -> "T01" (matches static CSV)


def build() -> dict:
    if file_md5(STATIC_CSV) != STATIC_CSV_MD5:
        raise ValueError("Penmanshiel_WT_static.csv checksum mismatch")
    part_paths, reports = [], []
    for archive, md5 in ARCHIVES.items():
        part = OUTPUT_PATH.with_name(f"_part_{archive}.csv")
        reports.append(
            extract_canonical_slice(
                archive_path=RAW_DIR / archive,
                output_path=part,
                start=WINDOW_START,
                end=WINDOW_END,
                expected_archive_md5=md5,
                turbine_file_pattern=TURBINE_FILE,
                turbine_id_format=TURBINE_ID_FORMAT,
            )
        )
        part_paths.append(part)

    frame = pd.concat([pd.read_csv(p, dtype={"timestamp_utc": str, "turbine_id": str}) for p in part_paths])
    frame = frame.sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)
    if frame.duplicated(["timestamp_utc", "turbine_id"]).any():
        raise ValueError("duplicate (timestamp, turbine) rows after merging Penmanshiel archives")
    frame.to_csv(OUTPUT_PATH, index=False)
    for p in part_paths:
        p.unlink()

    coverage = [
        {k: v for k, v in turbine_coverage(frame, t, WINDOW_START, WINDOW_END).items() if k != "contiguous_gaps"}
        for t in sorted(frame["turbine_id"].unique())
    ]
    manifest = {
        "source": SOURCE,
        "licence": LICENCE,
        "implementation_version": IMPLEMENTATION_VERSION,
        "archives": [
            {"file": a, "expected_md5": m, "observed_md5": r["observed_archive_md5"],
             "verified": m == r["observed_archive_md5"], "extraction_report": r}
            for (a, m), r in zip(ARCHIVES.items(), reports)
        ],
        "static_csv": {"file": STATIC_CSV.name, "md5": STATIC_CSV_MD5},
        "window_start_utc": WINDOW_START,
        "window_end_utc": WINDOW_END,
        "output_file": OUTPUT_PATH.name,
        "output_md5": file_md5(OUTPUT_PATH),
        "rows": int(len(frame)),
        "coverage_over_full_2016_window_note": (
            "Coverage is computed over the whole calendar-2016 window, but Penmanshiel "
            "turbines only start reporting at commissioning (June-July 2016); low percentages "
            "reflect that late start, not bad data."
        ),
        "coverage_by_turbine": coverage,
        "commissioning_caveat": (
            "Declared commercial operations date is 2016-09-01; data before that are "
            "commissioning-period and are not used as back-test events."
        ),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    m = build()
    print("rows", m["rows"], "md5", m["output_md5"])
    print([a["verified"] for a in m["archives"]])
    for c in m["coverage_by_turbine"]:
        print(c["turbine_id"], c["actual_valid_slots"], f"{c['coverage_pct']:.1f}%")
