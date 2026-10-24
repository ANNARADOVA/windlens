"""Multi-block back-test: baseline vs. peer-ensemble reconstruction across several
held-out outage-like blocks, scored and classified per WindLens_instructions.md
Section 9.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from windlens.loss_estimate import (
    energy_weighted_wape,
    estimate_loss,
    power_errors,
    signed_aggregate_bias_pct,
    wind_speed_errors,
)
from windlens.power_curve import apply_power_curve, fit_power_curve
from windlens.reconstruct import (
    fit_weighted_references,
    predict_with_fitted_references,
    reconstruct_wind_speed,
    reconstruct_wind_speed_ensemble,
    reconstruct_wind_speed_weighted,
    reference_within_training_domain,
    select_reference_turbine,
)
from windlens.review_gate import REVIEWABLE, classify_estimate
from windlens.dynamic_reference import select_dynamic_references
from windlens.uncertainty import (
    apply_residual_interval,
    calibrate_residual_interval,
    evaluate_interval,
)
from windlens.uncertainty_business import uncertainty_gate

# Paired pre-outage observations required of every reference used in an event before
# it counts as "aligned" -- a documented bar well above select_reference_turbine's own
# permissive floor (10), which exists only to avoid crashing on degenerate input.
MIN_ALIGNED_PAIRED_OBSERVATIONS = 500

# Minimum fraction of the event window the reconstruction must actually cover before
# the estimate is trusted. 2026-10-22 red-team review (F2): Hill of Towie 2024-08-13
# was labelled "Estimate -- reviewable" despite the selected reference reporting for
# only 31% of the window -- the wind-first scorer silently summed power over the rows
# that existed and treated the rest as zero. This gate is computed purely from how
# many reference readings exist during [block_start, block_end), which is information
# available at outage time; it never reads hidden truth.
MIN_RECONSTRUCTION_COMPLETENESS_PCT = 90.0

# Minimum pre-event calibration residuals before an uncertainty interval is trusted
# enough to support review. Matches uncertainty_business.uncertainty_gate's default.
MIN_CALIBRATION_OBSERVATIONS = 100


def reconstruction_completeness(
    reconstruction: pd.DataFrame, block_start: str, block_end: str
) -> dict[str, Any]:
    """How much of [block_start, block_end) the reconstruction actually covers.

    Computed only from the reconstruction's own row count against the window's
    expected 10-minute cadence -- never from hidden truth, so this check can run
    on a real outage. See MIN_RECONSTRUCTION_COMPLETENESS_PCT for why this exists.
    """

    expected_rows = int(
        (pd.Timestamp(block_end) - pd.Timestamp(block_start)) / pd.Timedelta(minutes=10)
    )
    if expected_rows <= 0:
        raise ValueError("block_end must be after block_start")
    covered_rows = int(len(reconstruction))
    return {
        "expected_rows": expected_rows,
        "covered_rows": covered_rows,
        "completeness_pct": float(covered_rows / expected_rows * 100.0),
    }


def input_qa_check(masked_df: pd.DataFrame, turbine_ids: set[str]) -> dict[str, Any]:
    """Real per-event input QA, available at outage time.

    2026-10-22 red-team review (F1): this gate was hard-coded to always pass,
    justified as "enforced upstream by Section 8 on the canonical dataset". That
    upstream check runs once at dataset-build time; it does not verify that the
    specific turbines and rows *this event* depends on are still clean after
    masking. This re-checks for duplicate (timestamp, turbine) rows among only
    the turbines the event actually uses.
    """

    relevant = masked_df[masked_df["turbine_id"].isin(turbine_ids)]
    duplicate_count = int(relevant.duplicated(["timestamp_utc", "turbine_id"], keep=False).sum())
    return {"duplicate_count": duplicate_count, "passed": duplicate_count == 0}


def _calibrate_and_evaluate_interval(
    masked_df: pd.DataFrame,
    target_turbine: str,
    reference_weights: dict[str, float],
    event_prediction: pd.DataFrame,
    hidden_truth: pd.DataFrame,
    block_start: str,
) -> dict[str, Any]:
    """Calibrate an empirical interval from the SAME model used for the event
    (fit once on all pre-event history), scored across that entire pre-event
    record, then score coverage on the event.

    2026-10-21: an earlier version re-fit a fresh linear model at an inner
    cutoff (the last 20% of pre-event history) to generate calibration
    predictions -- a model that differed from the one actually used for the
    event (fit on all pre-event history). That mismatch produced a calibration
    bias that flipped sign block to block (-0.17 to +0.37 m/s across the 5
    Kelmarsh blocks) and left mean observed coverage around 80% against the
    90% target. Fitting once -- matching the event model exactly -- and
    scoring residuals over the full pre-event record (not just the last 20%)
    removes that mismatch: measured residual bias collapsed to within +/-0.01
    m/s and mean coverage rose to ~90% across the same 5 blocks. See
    docs/DECISION_LOG.md for the full before/after measurement. This is a
    methodology correction justified directly by the measured residuals, not
    a widened interval chosen to hit a coverage target.
    """

    pre_target = masked_df[
        (masked_df["turbine_id"] == target_turbine)
        & (masked_df["timestamp_utc"] < block_start)
    ][["timestamp_utc", "wind_speed_ms"]].sort_values("timestamp_utc")
    if len(pre_target) < 25:
        return {"status": "unavailable", "reason": "insufficient pre-event target history"}

    try:
        fits = fit_weighted_references(masked_df, target_turbine, reference_weights, block_start)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    calibration_start = pre_target.iloc[0]["timestamp_utc"]
    try:
        calibration_prediction = predict_with_fitted_references(
            masked_df, fits, calibration_start, block_start
        )
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}
    calibration_joined = calibration_prediction.merge(
        pre_target, on="timestamp_utc", how="inner"
    )
    residuals = (
        calibration_joined["wind_speed_ms_reconstructed"]
        - calibration_joined["wind_speed_ms"]
    ).to_numpy(dtype=float)
    if len(residuals) < 20:
        return {
            "status": "unavailable",
            "reason": f"need at least 20 calibration observations; got {len(residuals)}",
        }

    calibration = calibrate_residual_interval(residuals, coverage=0.90, min_observations=20)
    event_joined = event_prediction.merge(
        hidden_truth[["timestamp_utc", "wind_speed_ms"]], on="timestamp_utc", how="inner"
    )
    lower, upper = apply_residual_interval(
        event_joined["wind_speed_ms_reconstructed"].to_numpy(dtype=float), calibration
    )
    evaluation = evaluate_interval(
        actual=event_joined["wind_speed_ms"].to_numpy(dtype=float), lower=lower, upper=upper
    )
    return {
        "status": "available",
        "calibration": calibration,
        "event_evaluation": evaluation,
    }


def run_backtest_event(
    canonical_df: pd.DataFrame,
    target_turbine: str,
    candidate_reference_turbines: list[str],
    block_start: str,
    block_end: str,
    ensemble_size: int = 3,
    metadata_df: pd.DataFrame | None = None,
    behavior_weight: float = 0.8,
    external_power_curve: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Run baseline (best single reference) and peer-ensemble reconstruction for one
    held-out block, score both against hidden truth, and classify the ensemble result.

    "Freeze model configuration before scoring" (Section 9) means the reference
    turbine(s) and the linear fit are chosen using only pre-outage data -- never the
    held-out block itself -- exactly as reconstruct_wind_speed/select_reference_turbine
    already enforce.
    """

    pre_outage = canonical_df[canonical_df["timestamp_utc"] < block_start]
    if metadata_df is None:
        selection = select_reference_turbine(pre_outage, target_turbine, candidate_reference_turbines)
        ranking_by_turbine = {entry["turbine_id"]: entry for entry in selection["ranking"]}
        baseline_reference = selection["selected"]
        ensemble_references = [entry["turbine_id"] for entry in selection["ranking"][:ensemble_size]]
        reference_weights = {reference: 1.0 for reference in ensemble_references}
        dynamic_selection = None
    else:
        dynamic_selection = select_dynamic_references(
            pre_outage,
            target_turbine,
            candidate_reference_turbines,
            metadata_df,
            lookback_days=(30, 90, 180),
            top_k=ensemble_size,
            min_paired_observations=20,
            behavior_weight=behavior_weight,
        )
        if dynamic_selection["status"] == "abstain":
            raise ValueError(f"Dynamic reference selection abstained: {dynamic_selection['reason']}")
        ranking_by_turbine = {entry["turbine_id"]: entry for entry in dynamic_selection["ranking"]}
        baseline_reference = dynamic_selection["selected"]
        ensemble_references = [entry["turbine_id"] for entry in dynamic_selection["ensemble"]]
        reference_weights = {entry["turbine_id"]: entry["weight"] for entry in dynamic_selection["ensemble"]}

    hidden_truth = canonical_df[
        (canonical_df["turbine_id"] == target_turbine)
        & (canonical_df["timestamp_utc"] >= block_start)
        & (canonical_df["timestamp_utc"] < block_end)
    ]
    if hidden_truth.empty:
        raise ValueError(f"No {target_turbine} rows in [{block_start}, {block_end})")

    masked_df = canonical_df[
        ~(
            (canonical_df["turbine_id"] == target_turbine)
            & (canonical_df["timestamp_utc"] >= block_start)
            & (canonical_df["timestamp_utc"] < block_end)
        )
    ]

    if external_power_curve is not None:
        # BayWa targets have no power time series at all to fit from -- each target
        # ships its own measured power-curve file instead. Use it as-is rather than
        # calling fit_power_curve, which would raise on the empty active_power_kw.
        power_curve = external_power_curve
    else:
        target_pre_outage = pre_outage[pre_outage["turbine_id"] == target_turbine]
        power_curve = fit_power_curve(target_pre_outage)

    def _score(reconstruction: pd.DataFrame) -> dict[str, Any]:
        # 2026-10-22 red-team review (F6): this used to integrate expected_power over
        # only the reconstruction's own timestamps (however many the reference
        # happened to report) against hidden_truth's active_power_kw over the FULL
        # window -- so a reference gap silently zeroed out that fraction of the
        # estimate while actual_lost_kwh still counted the whole window. Direct
        # power's scorer already inner-joined before integrating; wind-first did
        # not, so wind-first was penalised for gaps direct power never saw. Both
        # are now scored on the same matched (inner-joined) timestamps.
        joined = reconstruction.merge(
            hidden_truth[["timestamp_utc", "active_power_kw"]], on="timestamp_utc", how="inner"
        )
        if joined.empty:
            raise ValueError("No overlapping timestamps between reconstruction and hidden truth")
        expected_power = apply_power_curve(
            power_curve, joined["wind_speed_ms_reconstructed"].to_numpy()
        )
        truth_power = joined["active_power_kw"].to_numpy()
        loss = estimate_loss(expected_power, truth_power)
        errors = wind_speed_errors(reconstruction, hidden_truth)
        power_error_metrics = power_errors(expected_power, truth_power)
        return {"loss": loss, "wind_errors": errors, "power_errors": power_error_metrics}

    baseline_reconstruction = reconstruct_wind_speed(
        masked_df, target_turbine, baseline_reference, block_start, block_end
    )
    baseline_score = _score(baseline_reconstruction)
    baseline_score["uncertainty"] = _calibrate_and_evaluate_interval(
        masked_df,
        target_turbine,
        {baseline_reference: 1.0},
        baseline_reconstruction,
        hidden_truth,
        block_start,
    )

    ensemble_reconstruction = reconstruct_wind_speed_weighted(
        masked_df, target_turbine, reference_weights, block_start, block_end
    )
    ensemble_score = _score(ensemble_reconstruction)
    ensemble_score["uncertainty"] = _calibrate_and_evaluate_interval(
        masked_df,
        target_turbine,
        reference_weights,
        ensemble_reconstruction,
        hidden_truth,
        block_start,
    )

    domain_checks = [
        reference_within_training_domain(masked_df, reference, block_start, block_end)
        for reference in ensemble_references
    ]
    within_domain = all(check["within_domain"] for check in domain_checks)

    aligned_turbines = {baseline_reference, *ensemble_references}
    reference_target_aligned = all(
        ranking_by_turbine[turbine]["paired_observations"] >= MIN_ALIGNED_PAIRED_OBSERVATIONS
        for turbine in aligned_turbines
    )

    # Reported for back-test transparency only -- NOT fed into classify_estimate.
    # Comparing wind RMSE against hidden truth is a legitimate back-test diagnostic
    # (we have hidden truth here), but it cannot be the live decision gate the spec's
    # "back-test performance beats the agreed baseline" (WindLens_instructions.md:222)
    # actually means: a property established once across many back-test blocks, not
    # re-evaluated per event against truth that will not exist in a real outage
    # (2026-10-22 red-team review, F1).
    beats_baseline = (
        ensemble_score["wind_errors"]["rmse_ms"] <= baseline_score["wind_errors"]["rmse_ms"]
    )

    completeness = reconstruction_completeness(ensemble_reconstruction, block_start, block_end)
    input_qa = input_qa_check(masked_df, {target_turbine, *aligned_turbines})

    ensemble_uncertainty = ensemble_score["uncertainty"]
    if ensemble_uncertainty["status"] == "available":
        uncertainty_gate_result = uncertainty_gate(
            ensemble_uncertainty["calibration"], min_observations=MIN_CALIBRATION_OBSERVATIONS
        )
        uncertainty_gate_passed = uncertainty_gate_result["status"] == "reviewable"
    else:
        # No pre-event calibration could be built at all -- fail safe, don't skip the gate.
        uncertainty_gate_result = {"status": "unverified", "failed_gates": ["calibration_unavailable"]}
        uncertainty_gate_passed = False

    classification = classify_estimate(
        input_qa_passed=input_qa["passed"],
        reference_target_aligned=reference_target_aligned,
        within_validated_domain=within_domain,
        completeness_passed=completeness["completeness_pct"] >= MIN_RECONSTRUCTION_COMPLETENESS_PCT,
        abstention_triggered=False,
        uncertainty_gate_passed=uncertainty_gate_passed,
    )

    return {
        "block_start": block_start,
        "block_end": block_end,
        "baseline_reference": baseline_reference,
        "ensemble_references": ensemble_references,
        "reference_weights": reference_weights,
        "dynamic_selection": dynamic_selection,
        "baseline": baseline_score,
        "ensemble": ensemble_score,
        "domain_checks": domain_checks,
        "within_domain": within_domain,
        "reference_target_aligned": reference_target_aligned,
        "beats_baseline": beats_baseline,
        "completeness": completeness,
        "input_qa": input_qa,
        "uncertainty_gate": uncertainty_gate_result,
        "classification": classification,
    }


def aggregate_backtest(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-event metrics across the whole back-test for both models."""

    if not events:
        raise ValueError("Need at least one event to aggregate")

    def _aggregate(model_key: str) -> dict[str, float]:
        estimated = [event[model_key]["loss"]["estimated_lost_kwh"] for event in events]
        actual = [event[model_key]["loss"]["actual_lost_kwh"] for event in events]
        return {
            "energy_weighted_wape_pct": energy_weighted_wape(estimated, actual),
            "signed_aggregate_bias_pct": signed_aggregate_bias_pct(estimated, actual),
        }

    reviewable_count = sum(
        1 for event in events if event["classification"]["label"] == REVIEWABLE
    )

    return {
        "event_count": len(events),
        "baseline": _aggregate("baseline"),
        "ensemble": _aggregate("ensemble"),
        "reviewable_count": reviewable_count,
        "abstention_rate_pct": (len(events) - reviewable_count) / len(events) * 100,
    }
