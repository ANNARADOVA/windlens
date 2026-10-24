"""Uncertainty-interval calibration for the direct power-to-power regression method.

The project's existing uncertainty interval (windlens.uncertainty /
windlens.backtest._calibrate_and_evaluate_interval) is wind-speed-domain only: it
calibrates and scores on wind_speed_ms residuals, because the production pipeline
reconstructs wind speed first and converts to power via a power curve. Direct-power
regression (reference active_power_kw -> target active_power_kw directly, no wind-speed
step) has no uncertainty interval of its own yet -- this was flagged as the next step in
docs/DECISION_LOG.md (2026-10-21 entry) and is what this module adds.

Same calibration methodology as the wind-speed fix (2026-10-21): fit the regression once
on all pre-event history (matching the model actually used for the event), then score
calibration residuals over that same full pre-event history, then apply the resulting
empirical quantile interval to the event. This is deliberately NOT a new interval design
-- it is the existing, already-validated calibration pattern applied to a different
residual domain (power in kW, instead of wind speed in m/s), reusing
windlens.uncertainty's generic (domain-agnostic) calibration functions unchanged.

Known limitation, carried over unchanged from the wind-speed version: the parallel audit
in docs/AUDIT_2026-10-22_uncertainty_calibration.md notes that scoring calibration
residuals on (near-)the same data used to fit the model is not a fully independent
holdout. That critique applies equally here; it is not re-solved by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from windlens.uncertainty import apply_residual_interval, calibrate_residual_interval, evaluate_interval


@dataclass(frozen=True)
class PowerLinearFit:
    slope: float
    intercept: float
    rated_power_kw: float

    def predict(self, reference_power_kw: np.ndarray) -> np.ndarray:
        return np.clip(self.slope * reference_power_kw + self.intercept, 0.0, self.rated_power_kw)


def _paired_power_series(df: pd.DataFrame, target_turbine: str, reference_turbine: str) -> pd.DataFrame:
    """Simultaneous, valid active_power_kw observations for both turbines, by timestamp."""

    target = df[df["turbine_id"] == target_turbine].set_index("timestamp_utc")["active_power_kw"]
    reference = df[df["turbine_id"] == reference_turbine].set_index("timestamp_utc")["active_power_kw"]
    paired = pd.concat([target.rename("target"), reference.rename("reference")], axis=1, join="inner")
    return paired.dropna().sort_index()


def fit_direct_power(
    df: pd.DataFrame, target_turbine: str, reference_turbine: str, fit_before: str, rated_power_kw: float
) -> PowerLinearFit:
    """Fit target~reference active_power_kw linear regression using only data strictly
    before `fit_before` -- exactly mirroring reconstruct.fit_weighted_references's
    fit-before-the-event contract, applied to the power domain."""

    pre = df[df["timestamp_utc"] < fit_before]
    paired = _paired_power_series(pre, target_turbine, reference_turbine)
    if len(paired) < 2:
        raise ValueError("Need at least two paired power observations to fit a line")
    slope, intercept = np.polyfit(
        paired["reference"].to_numpy(dtype=float), paired["target"].to_numpy(dtype=float), 1
    )
    return PowerLinearFit(slope=float(slope), intercept=float(intercept), rated_power_kw=float(rated_power_kw))


def predict_direct_power(
    df: pd.DataFrame, fit: PowerLinearFit, reference_turbine: str, window_start: str, window_end: str
) -> pd.DataFrame:
    """Apply an already-fitted direct-power model over [window_start, window_end)
    without refitting -- mirrors reconstruct.predict_with_fitted_references."""

    reference = (
        df[
            (df["turbine_id"] == reference_turbine)
            & (df["timestamp_utc"] >= window_start)
            & (df["timestamp_utc"] < window_end)
        ]
        .set_index("timestamp_utc")["active_power_kw"]
        .dropna()
        .sort_index()
    )
    if reference.empty:
        raise ValueError("No reference power observations in the requested window")
    predicted = fit.predict(reference.to_numpy(dtype=float))
    return pd.DataFrame({"timestamp_utc": reference.index, "predicted_power_kw": predicted}).reset_index(drop=True)


# Typical small-turbine cut-in speed. Below this, near-zero reference power is
# expected and not evidence of a stop -- see reference_operating_state_check.
DEFAULT_MIN_WIND_SPEED_MS = 4.0
# Reference power at/below this fraction of rated output, while wind is above cut-in,
# counts as "looks stopped" for one reading.
DEFAULT_MAX_IDLE_POWER_FRACTION = 0.01
# If more than this fraction of the event window looks stopped, abstain.
DEFAULT_MAX_STOPPED_FRACTION = 0.2


def reference_operating_state_check(
    df: pd.DataFrame,
    reference_turbine: str,
    window_start: str,
    window_end: str,
    rated_power_kw: float,
    *,
    min_wind_speed_ms: float = DEFAULT_MIN_WIND_SPEED_MS,
    max_idle_power_fraction: float = DEFAULT_MAX_IDLE_POWER_FRACTION,
    max_stopped_fraction: float = DEFAULT_MAX_STOPPED_FRACTION,
) -> dict[str, Any]:
    """Detect a reference turbine that looks stopped-but-reporting during the event
    window: wind well above typical cut-in but power near zero.

    2026-10-22 red-team review (F8): nothing in this module caught this. On one
    Hill of Towie block the selected reference (T04) was stopped while the target
    was not; direct power predicted ~0 kW throughout (447 kWh vs. 30,243 kWh
    actual, -98.5% error). This reads only the reference's own wind and power
    readings during the window -- never the target or hidden truth -- so it is
    available at outage time.
    """

    window = df[
        (df["turbine_id"] == reference_turbine)
        & (df["timestamp_utc"] >= window_start)
        & (df["timestamp_utc"] < window_end)
    ][["wind_speed_ms", "active_power_kw"]].dropna()
    if window.empty:
        return {"passed": False, "observations": 0, "stopped_fraction": 1.0, "reason": "no reference readings in window"}

    idle_threshold_kw = max_idle_power_fraction * rated_power_kw
    looks_stopped = (window["wind_speed_ms"] >= min_wind_speed_ms) & (
        window["active_power_kw"] <= idle_threshold_kw
    )
    stopped_fraction = float(looks_stopped.mean())
    return {
        "passed": stopped_fraction <= max_stopped_fraction,
        "observations": int(len(window)),
        "stopped_fraction": stopped_fraction,
        "max_stopped_fraction": max_stopped_fraction,
    }


def calibrate_and_evaluate_direct_power_interval(
    masked_df: pd.DataFrame,
    target_turbine: str,
    reference_turbine: str,
    block_start: str,
    block_end: str,
    rated_power_kw: float,
    hidden_truth: pd.DataFrame,
) -> dict[str, Any]:
    """Direct-power analogue of backtest._calibrate_and_evaluate_interval: fit once
    (matching the model used for the event), score calibration residuals over the full
    pre-event history, apply the resulting interval to the event, and evaluate coverage.
    """

    pre_target = masked_df[
        (masked_df["turbine_id"] == target_turbine) & (masked_df["timestamp_utc"] < block_start)
    ][["timestamp_utc", "active_power_kw"]].dropna().sort_values("timestamp_utc")
    if len(pre_target) < 25:
        return {"status": "unavailable", "reason": "insufficient pre-event target history"}

    operating_state = reference_operating_state_check(
        masked_df, reference_turbine, block_start, block_end, rated_power_kw
    )
    if not operating_state["passed"]:
        return {
            "status": "unavailable",
            "reason": (
                f"reference {reference_turbine} looks stopped for "
                f"{operating_state['stopped_fraction']:.0%} of the event window "
                "(wind above cut-in, power near zero)"
            ),
            "operating_state": operating_state,
        }

    try:
        fit = fit_direct_power(masked_df, target_turbine, reference_turbine, block_start, rated_power_kw)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    calibration_start = pre_target.iloc[0]["timestamp_utc"]
    try:
        calibration_prediction = predict_direct_power(masked_df, fit, reference_turbine, calibration_start, block_start)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    calibration_joined = calibration_prediction.merge(
        pre_target.rename(columns={"active_power_kw": "actual_power_kw"}), on="timestamp_utc", how="inner"
    )
    residuals = (calibration_joined["predicted_power_kw"] - calibration_joined["actual_power_kw"]).to_numpy(dtype=float)
    if len(residuals) < 20:
        return {
            "status": "unavailable",
            "reason": f"need at least 20 calibration observations; got {len(residuals)}",
        }

    calibration = calibrate_residual_interval(residuals, coverage=0.90, min_observations=20)

    try:
        event_prediction = predict_direct_power(masked_df, fit, reference_turbine, block_start, block_end)
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    event_joined = event_prediction.merge(
        hidden_truth[["timestamp_utc", "active_power_kw"]], on="timestamp_utc", how="inner"
    )
    if event_joined.empty:
        return {"status": "unavailable", "reason": "no overlapping event timestamps"}

    lower, upper = apply_residual_interval(event_joined["predicted_power_kw"].to_numpy(dtype=float), calibration)
    evaluation = evaluate_interval(
        actual=event_joined["active_power_kw"].to_numpy(dtype=float), lower=lower, upper=upper
    )
    return {"status": "available", "calibration": calibration, "event_evaluation": evaluation, "fit": {"slope": fit.slope, "intercept": fit.intercept}}
