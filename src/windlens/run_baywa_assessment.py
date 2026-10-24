"""Run the real BayWa r.e. hackathon assessment: wind-first single-reference
reconstruction for each target turbine (T1, T2, T3), self-validated against the
shown window (2026-09-04 .. 2026-09-10) and then run for real over the hidden
window (2026-09-01 .. 2026-09-04) -- the actual graded prediction.

Single-reference, not the shipped 3-turbine ensemble: the full method x scenario
matrix run earlier tonight (docs/DECISION_LOG.md's 2026-10-23 "running the entire
matrix" entries) found single-reference ties-or-beats the ensemble at real
cross-park distance, and the rubric explicitly rewards explainability when there
is a tradeoff -- this is the plan's explicit, already-made call, not re-derived here.

BayWa's own test_set/NaN column IS the outage mask -- used directly as the window
to predict, never re-synthesized via mask_outage.py.

Honesty note, load-bearing for how to read every number below: no BayWa source file
(for ANY turbine, target or reference) contains a power column at all. "Truth" power
for the shown-window self-validation is therefore a POWER-CURVE-DERIVED PROXY from
the real, shown wind-speed reading -- never an independent power measurement. This
isolates how much of the power/energy error comes from the wind-speed reconstruction
itself (a real, measurable error) rather than from the power curve (BayWa's own
measured curve, assumed exact here). The hidden window has no wind-speed truth at
all, by construction -- that is exactly what is being predicted -- so no error metric
is reported for it; only the prediction itself, which is what gets graded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from windlens.build_baywa_dataset import (
    HIDDEN_WINDOW_END,
    HIDDEN_WINDOW_START,
    OUTPUT_PATH as CANONICAL_PATH,
    REFERENCE_TURBINE_IDS,
    SHOWN_WINDOW_END,
    SHOWN_WINDOW_START,
    TARGET_TURBINE_IDS,
    TEST_SET_WINDOW_END,
    TEST_SET_WINDOW_START,
    build as build_canonical,
)
from windlens.loss_estimate import estimate_loss, integrate_energy_kwh, power_errors, wind_speed_errors
from windlens.power_curve import apply_power_curve
from windlens.reconstruct import reconstruct_wind_speed, select_reference_turbine

RESULT_PATH = Path("data/derived/baywa_assessment_result.json")
IMPLEMENTATION_VERSION = "run_baywa_assessment.v1"


def _load_power_curve(target_turbine: str) -> pd.DataFrame:
    path = Path(f"data/derived/baywa_{target_turbine.lower()}_power_curve.csv")
    return pd.read_csv(path)


def run_for_target(
    canonical_df: pd.DataFrame, target_turbine: str, power_curve: pd.DataFrame
) -> dict[str, Any]:
    pre_outage = canonical_df[canonical_df["timestamp_utc"] < TEST_SET_WINDOW_START]
    selection = select_reference_turbine(pre_outage, target_turbine, REFERENCE_TURBINE_IDS)
    selected_reference = selection["selected"]

    reconstruction = reconstruct_wind_speed(
        canonical_df, target_turbine, selected_reference, TEST_SET_WINDOW_START, TEST_SET_WINDOW_END
    )

    shown_reconstruction = reconstruction[
        (reconstruction["timestamp_utc"] >= SHOWN_WINDOW_START)
        & (reconstruction["timestamp_utc"] < SHOWN_WINDOW_END)
    ]
    shown_truth = canonical_df[
        (canonical_df["turbine_id"] == target_turbine)
        & (canonical_df["timestamp_utc"] >= SHOWN_WINDOW_START)
        & (canonical_df["timestamp_utc"] < SHOWN_WINDOW_END)
    ]

    wind_errors = wind_speed_errors(shown_reconstruction, shown_truth)

    joined_shown = shown_reconstruction.merge(
        shown_truth[["timestamp_utc", "wind_speed_ms"]], on="timestamp_utc", how="inner"
    )
    predicted_power_shown = apply_power_curve(
        power_curve, joined_shown["wind_speed_ms_reconstructed"].to_numpy()
    )
    proxy_truth_power_shown = apply_power_curve(power_curve, joined_shown["wind_speed_ms"].to_numpy())
    shown_power_errors = power_errors(predicted_power_shown, proxy_truth_power_shown)
    shown_loss = estimate_loss(predicted_power_shown, proxy_truth_power_shown)

    hidden_reconstruction = reconstruction[
        (reconstruction["timestamp_utc"] >= HIDDEN_WINDOW_START)
        & (reconstruction["timestamp_utc"] < HIDDEN_WINDOW_END)
    ]
    hidden_predicted_power = apply_power_curve(
        power_curve, hidden_reconstruction["wind_speed_ms_reconstructed"].to_numpy()
    )
    hidden_estimated_kwh = integrate_energy_kwh(hidden_predicted_power)

    return {
        "target_turbine": target_turbine,
        "method": "wind_first_single_reference",
        "selected_reference": selected_reference,
        "reference_ranking": selection["ranking"],
        "shown_window_utc": [SHOWN_WINDOW_START, SHOWN_WINDOW_END],
        "shown_window_self_validation": {
            "compared_observations": wind_errors["compared_observations"],
            "wind_speed_errors": wind_errors,
            "power_errors_vs_curve_derived_proxy_truth": shown_power_errors,
            "energy_loss_vs_curve_derived_proxy_truth": shown_loss,
            "caveat": (
                "'Truth' power here is the measured power curve applied to the real, "
                "shown wind-speed reading -- not an independent power measurement "
                "(none exists in the BayWa source files for any turbine)."
            ),
        },
        "hidden_window_utc": [HIDDEN_WINDOW_START, HIDDEN_WINDOW_END],
        "hidden_window_prediction": {
            "rows_predicted": int(len(hidden_reconstruction)),
            "estimated_lost_kwh": hidden_estimated_kwh,
            "predictions": [
                {
                    "timestamp_utc": row.timestamp_utc,
                    "wind_speed_ms_predicted": float(row.wind_speed_ms_reconstructed),
                }
                for row in hidden_reconstruction.itertuples(index=False)
            ],
            "caveat": (
                "No ground truth exists for this window by construction (BayWa's own "
                "held-out hidden window) -- no error metric can be reported here; this "
                "is the actual graded prediction, not a validated estimate."
            ),
        },
    }


def run() -> dict[str, Any]:
    build_canonical()
    canonical_df = pd.read_csv(CANONICAL_PATH, dtype={"timestamp_utc": str, "turbine_id": str})

    per_target = [
        run_for_target(canonical_df, target, _load_power_curve(target))
        for target in TARGET_TURBINE_IDS
    ]

    result = {
        "implementation_version": IMPLEMENTATION_VERSION,
        "dataset": "Official BayWa r.e. hackathon dataset",
        "method": "wind_first_single_reference",
        "method_choice_rationale": (
            "Single best-correlated reference turbine (pure behavioral ranking -- no "
            "lat/lon registry exists for this dataset), not the shipped 3-turbine "
            "ensemble: the full method x scenario matrix run earlier tonight found "
            "single-reference ties-or-beats the ensemble at real cross-park distance, "
            "and simpler is also what the challenge rubric rewards when there is a "
            "tradeoff. See docs/DECISION_LOG.md's 2026-10-23 'running the entire "
            "matrix' entries."
        ),
        "targets": per_target,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    out = run()
    for target in out["targets"]:
        shown = target["shown_window_self_validation"]
        print(target["target_turbine"], "reference=", target["selected_reference"])
        print(
            "  shown-window wind RMSE/MAE (m/s):",
            round(shown["wind_speed_errors"]["rmse_ms"], 3),
            round(shown["wind_speed_errors"]["mae_ms"], 3),
        )
        print(
            "  shown-window power RMSE/MAE (kW, vs curve-derived proxy truth):",
            round(shown["power_errors_vs_curve_derived_proxy_truth"]["rmse_kw"], 2),
            round(shown["power_errors_vs_curve_derived_proxy_truth"]["mae_kw"], 2),
        )
        print(
            "  shown-window energy relative error (%, vs curve-derived proxy truth):",
            round(shown["energy_loss_vs_curve_derived_proxy_truth"]["relative_error_pct"], 2),
        )
        print("  hidden-window rows predicted:", target["hidden_window_prediction"]["rows_predicted"])
    print("Result written to", RESULT_PATH)
