"""Generate the canonical reviewable demo assessment JSON artifact."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from windlens.assessment import build_assessment_record
from windlens.checksums import file_md5
from windlens.farm_registry import FarmRegistry
from windlens.reconstruct import reconstruct_wind_speed_weighted
from windlens.run_backtest import run_all_blocks
from windlens.run_kelmarsh_extended_backtest import run_all_blocks as run_extended_blocks
from windlens.uncertainty import apply_residual_interval
from windlens.uncertainty_business import event_level_kwh_interval

OUTPUT_PATH = Path("data/derived/assessment/kwf1_2016-07-07_assessment.json")
SERIES_OUTPUT_PATH = Path("data/derived/assessment/kwf1_2016-07-07_timeseries.json")
WORKSPACE_DATA_PATH = Path("workspace/assessment-data.js")
COMMERCIAL_PROFILE_PATH = Path("data/derived/commercial_profiles/demo_ppa_profile.json")
CANONICAL_PATH = Path("data/derived/kelmarsh_2016_90d_canonical.csv")


def main() -> None:
    events, _ = run_all_blocks()
    # Select the block this artifact's filenames (kwf1_2016-07-07_*) actually name,
    # not whichever block happens to have the fewest failed gates. 2026-10-22: the
    # old `min(..., key=len(failed_gates))` silently started picking a *different*
    # block (2016-06-26) once the trust-gate redesign (F1/F2) changed which blocks
    # pass -- three of the five original blocks now tie at zero failed gates, and
    # `min` breaks ties by list order, not by the name this artifact promises.
    DEMO_BLOCK_START = "2016-07-07T00:00:00Z"
    reviewable = next(event for event in events if event["block_start"] == DEMO_BLOCK_START)

    # 2026-10-22 red-team review (F5): event-level kWh interval, built from the
    # empirical distribution of |relative kWh error| this method (wind-first
    # ensemble) actually produced across the Kelmarsh 19-block extended back-test
    # -- not the dead, near-uninformative propagate_power_interval path.
    extended_events, _extended_summary, _extended_skipped = run_extended_blocks()
    extended_errors = [
        extended_event["ensemble"]["loss"]["relative_error_pct"] for extended_event in extended_events
    ]
    kwh_interval = event_level_kwh_interval(
        extended_errors, reviewable["ensemble"]["loss"]["estimated_lost_kwh"], quantile_pct=90.0
    )

    record = build_assessment_record(
        event=reviewable,
        target_turbine="KWF1",
        model_key="ensemble",
        source={
            "doi": "10.5281/zenodo.16807551",
            "licence": "CC BY 4.0",
            "dataset_checksum_md5": "15abb74500b414bff35f21e313da6827",
            "method_version": "reconstruct.v1",
        },
        data_quality={
            "canonical_dataset": "data/derived/kelmarsh_2016_90d_canonical.csv",
            "qa_manifest": "data/derived/kelmarsh_2016_90d_canonical.manifest.md",
        },
        kwh_interval=kwh_interval,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    canonical = pd.read_csv(CANONICAL_PATH, dtype={"timestamp_utc": str, "turbine_id": str})
    # 2026-10-22 red-team review (F11): this used to call reconstruct_wind_speed_ensemble
    # (an unweighted equal-mean of the references), which is NOT the model that was
    # actually scored and calibrated in backtest.py -- that uses
    # reconstruct_wind_speed_weighted with the dynamic selector's inverse-RMSE
    # reference_weights (0.45/0.30/0.25 for the demo block). The chart line, interval,
    # and printed coverage % must come from the same model; using the equal-weight mean
    # made the drawn band's actual empirical coverage (95.1%) differ from the number
    # printed beside it (95.9%, the weighted model's true coverage).
    reconstruction = reconstruct_wind_speed_weighted(
        canonical,
        "KWF1",
        reviewable["reference_weights"],
        reviewable["block_start"],
        reviewable["block_end"],
    )
    truth = canonical[
        (canonical["turbine_id"] == "KWF1")
        & (canonical["timestamp_utc"] >= reviewable["block_start"])
        & (canonical["timestamp_utc"] < reviewable["block_end"])
    ][["timestamp_utc", "wind_speed_ms"]]
    joined = reconstruction.merge(truth, on="timestamp_utc", how="inner").sort_values("timestamp_utc")
    calibration = reviewable["ensemble"]["uncertainty"]["calibration"]
    lower, upper = apply_residual_interval(joined["wind_speed_ms_reconstructed"], calibration)
    joined["lower_ms"], joined["upper_ms"] = lower, upper
    stride = max(1, int(np.ceil(len(joined) / 96)))
    points = [
        {
            "timestamp_utc": row.timestamp_utc,
            "reconstructed_ms": float(row.wind_speed_ms_reconstructed),
            "truth_ms": float(row.wind_speed_ms),
            "lower_ms": float(row.lower_ms),
            "upper_ms": float(row.upper_ms),
        }
        for row in joined.iloc[::stride].itertuples(index=False)
    ]
    SERIES_OUTPUT_PATH.write_text(
        json.dumps({"interval_minutes": 10, "points": points}, indent=2) + "\n",
        encoding="utf-8",
    )
    commercial_profile = json.loads(COMMERCIAL_PROFILE_PATH.read_text(encoding="utf-8"))
    registry_path = Path("data/raw/Kelmarsh_WT_static.csv")
    registry = FarmRegistry.from_csv(registry_path, data_source="Kelmarsh static turbine registry")
    registry_evidence = {
        "report_version": "registry-import.v1",
        "source_filename": registry_path.name,
        "source_md5": file_md5(registry_path),
        "accepted_rows": len(registry.to_frame()),
        "rejected_rows": 0,
        "farm_ids": registry.farm_ids(),
        "turbine_ids": registry.to_frame()["turbine_id"].tolist(),
        "quality_status": "verified",
        "usable_for_geo_selection": True,
        "issues": [],
    }
    workspace_data = {
        "assessment": record,
        "series": {"interval_minutes": 10, "points": points},
        "commercial": commercial_profile,
        "registry_evidence": registry_evidence,
    }
    WORKSPACE_DATA_PATH.write_text(
        "window.WINDLENS_DATA = "
        + json.dumps(workspace_data, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {SERIES_OUTPUT_PATH}")
    print(f"Wrote {WORKSPACE_DATA_PATH}")


if __name__ == "__main__":
    main()
