"""Build the canonical-schema dataset from the official BayWa r.e. hackathon files.

Source: ``data_hackathon_baywa_re (1)/*_data.xlsx`` -- T1-T3 are target turbines (no
power time series, each ships its own power-curve file), H1-H5/O1-O2 are reference
turbines (no power curves, no lat/lon registry). 90 days at 10-minute cadence. A
``test_set`` column flags the held-out assessment window (2026-09-01 .. 2026-09-10);
within it, 2026-09-04 .. 2026-09-10 is "shown" (ground-truth wind speed present, for
self-validation) and 2026-09-01 .. 2026-09-04 is "hidden" (wind speed NaN'd out for
targets only -- the actual graded prediction target). Reference turbines report
normally throughout the whole window; only target wind speed is masked.

Pandas already parses the source ``timestamp`` column as a real datetime (openpyxl
resolves the underlying Excel serial dates itself), so no manual serial-date math is
needed here -- only re-serialising to the canonical ISO-8601 ``...Z`` string format
the rest of the pipeline compares lexicographically.

No real power measurement exists for ANY BayWa turbine (targets included) -- unlike
Kelmarsh/Penmanshiel, there is no power column in the source files at all, so
``active_power_kw`` is written as NaN for every row of every turbine. Any power-level
"truth" used later in this pipeline is always a power-curve-derived proxy from a real
wind-speed reading, never an independent power measurement -- see run_baywa_assessment.py.

This is a standalone connector, not a parameterisation of
``prepare_dataset.extract_canonical_slice``: that extraction drops invalid/implausible
rows, which would be wrong here (the test_set NaN gaps are exactly the signal this
dataset defines its own masked window with, and must be preserved, not treated as bad
data), and its source format (a zipped Greenbyte SCADA CSV export) has nothing in common
with BayWa's per-turbine Excel files.

No registry (lat/lon) file exists for this dataset. Reference selection therefore uses
the pure-behavioral path (``metadata_df=None`` in ``backtest.run_backtest_event`` /
direct ``select_reference_turbine`` calls) -- there is no coordinate data to feed the
geography-aware path, and tonight's own ablation found geography barely moves the
needle anyway.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from windlens.checksums import file_md5

IMPLEMENTATION_VERSION = "build_baywa_dataset.v1"

RAW_DIR = Path("data_hackathon_baywa_re (1)")
OUTPUT_PATH = Path("data/derived/baywa_canonical.csv")
MANIFEST_PATH = Path("data/derived/baywa_canonical.manifest.json")

TARGET_TURBINE_IDS = ["T1", "T2", "T3"]
REFERENCE_TURBINE_IDS = ["H1", "H2", "H3", "H4", "H5", "O1", "O2"]
ALL_TURBINE_IDS = TARGET_TURBINE_IDS + REFERENCE_TURBINE_IDS

TEST_SET_WINDOW_START = "2026-09-01T00:00:00Z"
TEST_SET_WINDOW_END = "2026-09-10T00:00:00Z"
SHOWN_WINDOW_START = "2026-09-04T00:00:00Z"
SHOWN_WINDOW_END = "2026-09-10T00:00:00Z"
HIDDEN_WINDOW_START = "2026-09-01T00:00:00Z"
HIDDEN_WINDOW_END = "2026-09-04T00:00:00Z"

REQUIRED_SOURCE_COLUMNS = {"turbine_name", "timestamp", "wind_speed", "wind_direction", "test_set"}
REQUIRED_CURVE_COLUMNS = {"wind_speed", "power"}


def _load_one_turbine(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path)
    missing = REQUIRED_SOURCE_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} is missing required column(s): {sorted(missing)}")

    return pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(frame["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "turbine_id": frame["turbine_name"].astype(str),
            "wind_speed_ms": frame["wind_speed"].astype(float),
            "wind_direction_deg": frame["wind_direction"].astype(float),
            "active_power_kw": np.nan,
            "test_set": frame["test_set"].astype(bool),
        }
    )


def build() -> dict:
    frames = []
    per_turbine_report = []
    for turbine_id in ALL_TURBINE_IDS:
        path = RAW_DIR / f"{turbine_id}_data.xlsx"
        frame = _load_one_turbine(path)
        per_turbine_report.append(
            {
                "turbine_id": turbine_id,
                "source_file": path.name,
                "observed_md5": file_md5(path),
                "rows": int(len(frame)),
                "nan_wind_speed_rows": int(frame["wind_speed_ms"].isna().sum()),
                "test_set_rows": int(frame["test_set"].sum()),
            }
        )
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["turbine_id", "timestamp_utc"]).reset_index(drop=True)
    if combined.duplicated(["timestamp_utc", "turbine_id"]).any():
        raise ValueError("duplicate (timestamp, turbine) rows after merging BayWa turbine files")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_PATH, index=False)

    power_curve_report = []
    for target_id in TARGET_TURBINE_IDS:
        curve_path = RAW_DIR / f"{target_id}_power_curve.xlsx"
        curve_frame = pd.read_excel(curve_path)
        missing = REQUIRED_CURVE_COLUMNS - set(curve_frame.columns)
        if missing:
            raise ValueError(f"{curve_path.name} is missing required column(s): {sorted(missing)}")

        curve = (
            curve_frame.rename(columns={"wind_speed": "bin_center_ms", "power": "mean_power_kw"})[
                ["bin_center_ms", "mean_power_kw"]
            ]
            .astype(float)
            .sort_values("bin_center_ms")
            .reset_index(drop=True)
        )
        curve_output_path = Path(f"data/derived/baywa_{target_id.lower()}_power_curve.csv")
        curve.to_csv(curve_output_path, index=False)
        power_curve_report.append(
            {
                "turbine_id": target_id,
                "source_file": curve_path.name,
                "observed_md5": file_md5(curve_path),
                "bins": int(len(curve)),
                "output_file": curve_output_path.name,
            }
        )

    manifest = {
        "source": "Official BayWa r.e. hackathon dataset",
        "implementation_version": IMPLEMENTATION_VERSION,
        "output_file": OUTPUT_PATH.name,
        "output_md5": file_md5(OUTPUT_PATH),
        "rows": int(len(combined)),
        "turbines": per_turbine_report,
        "power_curves": power_curve_report,
        "target_turbine_ids": TARGET_TURBINE_IDS,
        "reference_turbine_ids": REFERENCE_TURBINE_IDS,
        "test_set_window_utc": [TEST_SET_WINDOW_START, TEST_SET_WINDOW_END],
        "shown_window_utc": [SHOWN_WINDOW_START, SHOWN_WINDOW_END],
        "hidden_window_utc": [HIDDEN_WINDOW_START, HIDDEN_WINDOW_END],
        "no_power_ground_truth_note": (
            "No BayWa source file (target or reference) contains a power column -- "
            "active_power_kw is NaN for every row of every turbine. Power-level "
            "'truth' used anywhere in this pipeline is always a power-curve-derived "
            "proxy from a real wind-speed reading, never an independent power "
            "measurement."
        ),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build()
    print("rows", result["rows"], "md5", result["output_md5"])
    for turbine in result["turbines"]:
        print(
            turbine["turbine_id"],
            turbine["rows"],
            "nan_wind_speed_rows=", turbine["nan_wind_speed_rows"],
            "test_set_rows=", turbine["test_set_rows"],
        )
    for curve in result["power_curves"]:
        print(curve["turbine_id"], "power_curve_bins=", curve["bins"])
