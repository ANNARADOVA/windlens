"""End-to-end WindLens spike: mask -> reconstruct -> power curve -> loss estimate.

Rough, deliberately un-hardened pass to validate the core idea on the canonical
Kelmarsh slice before the full Section 8 QA-hardening work. See
docs/DECISION_LOG.md for why this ordering was chosen.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from windlens.loss_estimate import estimate_loss, wind_speed_errors
from windlens.mask_outage import mask_outage
from windlens.power_curve import apply_power_curve, fit_power_curve
from windlens.reconstruct import reconstruct_wind_speed, select_reference_turbine

CANONICAL_PATH = Path("data/derived/kelmarsh_2016_90d_canonical.csv")
MASKED_PATH = Path("data/derived/spike/kelmarsh_2016_90d_kwf1_masked.csv")
HIDDEN_TRUTH_PATH = Path("data/derived/spike/kelmarsh_2016_90d_kwf1_hidden_truth.csv")

TARGET_TURBINE = "KWF1"
CANDIDATE_REFERENCE_TURBINES = ["KWF2", "KWF3", "KWF4", "KWF5", "KWF6"]
MASK_START = "2016-07-05T00:00:00Z"
MASK_END = "2016-07-10T00:00:00Z"


def run_spike() -> dict:
    mask_report = mask_outage(
        input_path=CANONICAL_PATH,
        masked_output_path=MASKED_PATH,
        hidden_truth_output_path=HIDDEN_TRUTH_PATH,
        target_turbine=TARGET_TURBINE,
        start=MASK_START,
        end=MASK_END,
    )

    masked_df = pd.read_csv(MASKED_PATH, dtype={"timestamp_utc": str, "turbine_id": str})
    hidden_truth_df = pd.read_csv(
        HIDDEN_TRUTH_PATH, dtype={"timestamp_utc": str, "turbine_id": str}
    )
    pre_outage_df = masked_df[masked_df["timestamp_utc"] < MASK_START]

    selection = select_reference_turbine(
        pre_outage_df, TARGET_TURBINE, CANDIDATE_REFERENCE_TURBINES
    )
    reference_turbine = selection["selected"]

    reconstruction = reconstruct_wind_speed(
        masked_df, TARGET_TURBINE, reference_turbine, MASK_START, MASK_END
    )

    target_pre_outage = pre_outage_df[pre_outage_df["turbine_id"] == TARGET_TURBINE]
    power_curve = fit_power_curve(target_pre_outage)
    expected_power_kw = apply_power_curve(
        power_curve, reconstruction["wind_speed_ms_reconstructed"].to_numpy()
    )

    loss = estimate_loss(expected_power_kw, hidden_truth_df["active_power_kw"].to_numpy())
    wind_errors = wind_speed_errors(reconstruction, hidden_truth_df)

    return {
        "mask_report": mask_report,
        "reference_selection": selection,
        "loss": loss,
        "wind_errors": wind_errors,
        "reconstructed_observations": len(reconstruction),
        "hidden_truth_observations": len(hidden_truth_df),
    }


def _print_report(report: dict) -> None:
    mask_report = report["mask_report"]
    loss = report["loss"]
    wind_errors = report["wind_errors"]

    print("=== WindLens spike: end-to-end ===")
    print(
        f"Masked interval: {mask_report['mask_start_utc']} to {mask_report['mask_end_utc']} "
        f"(target={mask_report['target_turbine']}, {mask_report['masked_rows_removed']} rows removed)"
    )
    print(
        f"Reference turbine selected: {report['reference_selection']['selected']} "
        f"(ranking: {report['reference_selection']['ranking']})"
    )
    print(
        f"Reconstructed observations: {report['reconstructed_observations']} / "
        f"hidden-truth observations: {report['hidden_truth_observations']}"
    )
    print()
    print(f"Estimated lost kWh (from reconstruction): {loss['estimated_lost_kwh']:.1f}")
    print(f"Actual lost kWh (from hidden truth):       {loss['actual_lost_kwh']:.1f}")
    print(
        f"Absolute kWh error: {loss['absolute_error_kwh']:.1f} "
        f"({loss['relative_error_pct']:.1f}% relative)"
    )
    print()
    print(
        f"Wind reconstruction vs. hidden truth over {wind_errors['compared_observations']} "
        "shared timestamps:"
    )
    print(f"  MAE:         {wind_errors['mae_ms']:.3f} m/s")
    print(f"  RMSE:        {wind_errors['rmse_ms']:.3f} m/s")
    print(f"  Signed bias: {wind_errors['signed_bias_ms']:.3f} m/s")
    print()
    print(f"Masked dataset:      {mask_report['masked_output_path']} (md5 {mask_report['masked_output_md5']})")
    print(
        f"Hidden-truth dataset: {mask_report['hidden_truth_output_path']} "
        f"(md5 {mask_report['hidden_truth_output_md5']})"
    )


def main() -> None:
    report = run_spike()
    _print_report(report)


if __name__ == "__main__":
    main()
