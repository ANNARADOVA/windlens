"""Select the new default jury-facing showcase record (2026-10-23, Anna's request).

Anna's converged decision: "i would show the best method based on performance
according to the challenge and then show other scenarios", and for which specific
event: "do representative (median-performing) event." -- explicitly NOT the best, per
the F10 lesson (the prior default, kwf1_2016-07-07, was flagged by the red-team for
being cherry-picked as the best-of-five).

Selection rule, stated here so it is auditable rather than asserted:
1. Scenario = the real challenge scenario: cross-farm, Kelmarsh masked / Penmanshiel
   reference (the ``kelmarsh_masked_penmanshiel_reference`` direction, n=47 locked
   events -- the direction named in the brief).
2. Method = single-reference wind-first (the ``baseline`` key of ``run_backtest_event``),
   per tonight's full-matrix finding that single-reference ties-or-slightly-beats the
   3-turbine ensemble at real cross-farm distance.
3. Ranking metric = each event's single-reference baseline ABSOLUTE relative kWh error
   (``baseline.loss.relative_error_pct``, already an absolute percentage -- see
   ``loss_estimate.estimate_loss``).
4. Pick the MEDIAN-ranked event (the 24th of 47 when sorted ascending by that metric),
   not the best (1st) and not the worst (47th). For n=47 (odd) this is the exact middle
   element, not an interpolated value.

The 47 locked (target, block_start) pairs are read back verbatim from
``kelmarsh_penmanshiel_crossfarm_backtest.json``'s own per_event list for this
direction -- nothing is re-derived or re-selected. Each event is re-run through
``run_backtest_event`` (deterministic, same canonical data and metadata) to recover the
baseline-specific loss/wind_errors/uncertainty detail that direction's per_event list
only stored for the ensemble.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from windlens.assessment import build_assessment_record
from windlens.backtest import run_backtest_event
from windlens.checksums import file_md5
from windlens.connectors import KelmarshConnector, PenmanshielConnector
from windlens.farm_registry import FarmRegistry
from windlens.reconstruct import reconstruct_wind_speed
from windlens.run_kelmarsh_penmanshiel_crossfarm_backtest import (
    KELMARSH_CANONICAL,
    PENMANSHIEL_CANONICAL,
    OUTPUT_PATH as CROSSFARM_BACKTEST_PATH,
)
from windlens.uncertainty import apply_residual_interval
from windlens.uncertainty_business import event_level_kwh_interval

DIRECTION = "kelmarsh_masked_penmanshiel_reference"
OUTPUT_DIR = Path("data/derived/assessment")
WORKSPACE_DATA_PATH = Path("workspace/assessment-data.js")
COMMERCIAL_PROFILE_PATH = Path("data/derived/commercial_profiles/demo_ppa_profile.json")
SELECTION_LOG_PATH = Path("data/derived/validation/crossfarm_showcase_event_selection.json")


def _rerun_locked_events(df: pd.DataFrame, metadata: pd.DataFrame, reference_farm_turbines: list[str], locked_per_event: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-run run_backtest_event for every locked (target, block_start) pair, in order."""

    events = []
    for locked in locked_per_event:
        target, start = locked["target"], locked["block_start"]
        end = (pd.Timestamp(start) + pd.Timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        event = run_backtest_event(df, target, reference_farm_turbines, start, end, metadata_df=metadata)
        event["target"] = target
        events.append(event)
    return events


def main() -> None:
    k, p = KelmarshConnector(KELMARSH_CANONICAL).load(), PenmanshielConnector(PENMANSHIEL_CANONICAL).load()
    df = pd.concat([k.data, p.data], ignore_index=True)
    metadata = pd.concat([k.registry.to_frame(), p.registry.to_frame()], ignore_index=True)
    p_ids = sorted(set(p.data["turbine_id"]))

    locked_artifact = json.loads(CROSSFARM_BACKTEST_PATH.read_text(encoding="utf-8"))
    locked_per_event = locked_artifact["directions"][DIRECTION]["per_event"]
    assert len(locked_per_event) == 47, f"expected 47 locked events, found {len(locked_per_event)}"

    events = _rerun_locked_events(df, metadata, p_ids, locked_per_event)

    ranked = sorted(events, key=lambda e: abs(e["baseline"]["loss"]["relative_error_pct"]))
    median_index = len(ranked) // 2  # n=47 (odd) -> index 23, the exact middle element
    chosen = ranked[median_index]

    selection_log = {
        "selection_rule": (
            "Scenario: cross-farm, Kelmarsh masked / Penmanshiel reference (the real "
            "challenge scenario). Method: single-reference wind-first (baseline). "
            "Ranking metric: each event's absolute relative kWh error "
            "(baseline.loss.relative_error_pct). Selection: the median-ranked event "
            "(index 23 of 47 sorted ascending), not the best and not the worst -- per "
            "Anna's explicit instruction and the F10 lesson against best-of-N cherry-picking."
        ),
        "direction": DIRECTION,
        "locked_event_set_source": str(CROSSFARM_BACKTEST_PATH),
        "n_events": len(ranked),
        "median_rank_index_0based": median_index,
        "ranked_abs_relative_error_pct": [
            {"target": e["target"], "block_start": e["block_start"], "abs_relative_error_pct": abs(e["baseline"]["loss"]["relative_error_pct"])}
            for e in ranked
        ],
        "chosen_event": {
            "target": chosen["target"],
            "block_start": chosen["block_start"],
            "block_end": chosen["block_end"],
            "baseline_reference": chosen["baseline_reference"],
            "abs_relative_error_pct": abs(chosen["baseline"]["loss"]["relative_error_pct"]),
        },
    }
    SELECTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SELECTION_LOG_PATH.write_text(json.dumps(selection_log, indent=2, default=str) + "\n", encoding="utf-8")

    # Event-level kWh uncertainty band: empirical distribution of |relative error| this
    # method (single-reference wind-first, cross-farm, Kelmarsh-masked) actually produced
    # across the same locked 47-event set -- same discipline as the existing same-farm
    # record (run_assessment.py), just drawn from the matching cross-farm/baseline history
    # instead of the same-farm/ensemble one.
    baseline_errors = [abs(e["baseline"]["loss"]["relative_error_pct"]) for e in events]
    kwh_interval = event_level_kwh_interval(
        baseline_errors, chosen["baseline"]["loss"]["estimated_lost_kwh"], quantile_pct=90.0
    )

    k_checksum = file_md5(KELMARSH_CANONICAL)
    p_checksum = file_md5(PENMANSHIEL_CANONICAL)
    record = build_assessment_record(
        event=chosen,
        target_turbine=chosen["target"],
        model_key="baseline",
        source={
            "doi": "10.5281/zenodo.16807551 (Kelmarsh, target farm); 10.5281/zenodo.16807304 (Penmanshiel, reference farm)",
            "licence": "CC BY 4.0 (both datasets)",
            "dataset_checksum_md5": f"kelmarsh={k_checksum}; penmanshiel={p_checksum}",
            "method_version": "reconstruct.v1 / crossfarm-tier1-single-reference.v1",
        },
        data_quality={
            "canonical_dataset": f"{KELMARSH_CANONICAL} + {PENMANSHIEL_CANONICAL}",
            "qa_manifest": "Cross-farm whole-farm-outage constraint: Penmanshiel turbines only as candidates "
            "(windlens.run_kelmarsh_penmanshiel_crossfarm_backtest.assert_references_from_other_farm).",
        },
        kwh_interval=kwh_interval,
        limitations=[
            "This is the real challenge scenario (cross-farm, ~399 km, Kelmarsh target / Penmanshiel "
            "reference) -- not a same-farm proxy. See docs/DECISION_LOG.md's 2026-10-23 cross-farm entries.",
            "This record is a simulated outage back-test; a data gap alone does not prove an outage.",
            "This event is the MEDIAN-ranked of 47 locked cross-farm events by single-reference absolute "
            "relative kWh error -- a representative result, not the best case. See "
            "data/derived/validation/crossfarm_showcase_event_selection.json for the full ranking and rule.",
            "The kWh interval is an event-level band from this method's own cross-farm back-test error "
            "history (n=47 locked events, Kelmarsh-masked direction), not a per-point statistical guarantee.",
            "WindLens estimates the counterfactual production during an outage; it does not determine or "
            "classify the cause (mechanical failure vs. grid curtailment vs. other) -- that must come from "
            "an external source.",
        ],
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assessment_path = OUTPUT_DIR / f"crossfarm_{chosen['target']}_{chosen['block_start'][:10]}_assessment.json"
    assessment_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reconstruction = reconstruct_wind_speed(
        df, chosen["target"], chosen["baseline_reference"], chosen["block_start"], chosen["block_end"]
    )
    truth = df[
        (df["turbine_id"] == chosen["target"])
        & (df["timestamp_utc"] >= chosen["block_start"])
        & (df["timestamp_utc"] < chosen["block_end"])
    ][["timestamp_utc", "wind_speed_ms"]]
    joined = reconstruction.merge(truth, on="timestamp_utc", how="inner").sort_values("timestamp_utc")
    calibration = chosen["baseline"]["uncertainty"]["calibration"]
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
    series = {"interval_minutes": 10, "points": points}
    series_path = OUTPUT_DIR / f"crossfarm_{chosen['target']}_{chosen['block_start'][:10]}_timeseries.json"
    series_path.write_text(json.dumps(series, indent=2) + "\n", encoding="utf-8")

    commercial_profile = json.loads(COMMERCIAL_PROFILE_PATH.read_text(encoding="utf-8"))
    k_registry = FarmRegistry.from_csv(Path("data/raw/Kelmarsh_WT_static.csv"), data_source="Kelmarsh static turbine registry")
    registry_evidence = {
        "report_version": "registry-import.v1",
        "source_filename": "Kelmarsh_WT_static.csv (target farm; Penmanshiel reference-farm registry used internally for selection, not re-shown here)",
        "source_md5": file_md5(Path("data/raw/Kelmarsh_WT_static.csv")),
        "accepted_rows": len(k_registry.to_frame()),
        "rejected_rows": 0,
        "farm_ids": k_registry.farm_ids(),
        "turbine_ids": k_registry.to_frame()["turbine_id"].tolist(),
        "quality_status": "verified",
        "usable_for_geo_selection": True,
        "issues": [],
    }
    workspace_data = {
        "assessment": record,
        "series": series,
        "commercial": commercial_profile,
        "registry_evidence": registry_evidence,
    }
    WORKSPACE_DATA_PATH.write_text(
        "window.WINDLENS_DATA = " + json.dumps(workspace_data, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

    print(f"Chosen event: target={chosen['target']} block_start={chosen['block_start']} "
          f"abs_relative_error_pct={abs(chosen['baseline']['loss']['relative_error_pct']):.2f}% "
          f"(median rank {median_index + 1} of {len(ranked)})")
    print(f"Wrote {assessment_path}")
    print(f"Wrote {series_path}")
    print(f"Wrote {SELECTION_LOG_PATH}")
    print(f"Wrote {WORKSPACE_DATA_PATH}")


if __name__ == "__main__":
    main()
