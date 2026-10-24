"""Uncertainty and indicative commercial valuation helpers.

These helpers deliberately keep the claims narrow: intervals are empirical model
diagnostics and commercial outputs are indicative values, never legal or settlement
decisions.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from windlens.loss_estimate import INTERVAL_HOURS, integrate_energy_kwh
from windlens.power_curve import apply_power_curve


def _array(values: Iterable[float], name: str) -> np.ndarray:
    result = np.asarray(list(values), dtype=float)
    if result.ndim != 1 or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite one-dimensional sequence")
    return result


def calibrate_conditional_intervals(
    residuals_ms: Iterable[float],
    wind_speeds_ms: Iterable[float],
    directions_deg: Iterable[float] | None = None,
    *,
    coverage: float = 0.90,
    min_observations: int = 30,
    wind_edges: tuple[float, ...] = (0.0, 4.0, 8.0, 12.0, float("inf")),
    direction_sector_count: int = 8,
) -> dict[str, Any]:
    """Calibrate empirical residual bands by wind-speed and direction regime.

    Sparse cells fall back to the global band. Inputs must be out-of-sample
    residuals collected from multiple contiguous validation blocks.
    """

    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be strictly between 0 and 1")
    if min_observations < 1 or len(wind_edges) < 2 or direction_sector_count < 1:
        raise ValueError("invalid conditioning configuration")
    residuals = _array(residuals_ms, "residuals_ms")
    wind = _array(wind_speeds_ms, "wind_speeds_ms")
    if len(residuals) != len(wind):
        raise ValueError("residuals_ms and wind_speeds_ms must have equal length")
    direction = np.zeros(len(wind)) if directions_deg is None else _array(directions_deg, "directions_deg")
    if len(direction) != len(wind):
        raise ValueError("directions_deg must have the same length as residuals_ms")
    direction = np.mod(direction, 360.0)
    tail = (1.0 - coverage) / 2.0

    def band(values: np.ndarray) -> dict[str, float | int]:
        lower, upper = np.quantile(values, [tail, 1.0 - tail], method="linear")
        return {
            "observations": int(len(values)),
            "lower_residual_ms": float(lower),
            "upper_residual_ms": float(upper),
            "residual_bias_ms": float(np.mean(values)),
        }

    global_band = band(residuals)
    cells: dict[str, dict[str, float | int]] = {}
    wind_bucket = np.digitize(wind, wind_edges[1:-1], right=False)
    direction_bucket = np.floor(direction / (360.0 / direction_sector_count)).astype(int)
    for wi in range(len(wind_edges) - 1):
        for di in range(direction_sector_count):
            mask = (wind_bucket == wi) & (direction_bucket == di)
            if int(np.sum(mask)) >= min_observations:
                cells[f"{wi}:{di}"] = band(residuals[mask])
    return {
        "method": "conditional_empirical_residual_quantiles",
        "coverage_target": float(coverage),
        "observations": int(len(residuals)),
        "wind_edges_ms": list(wind_edges),
        "direction_sector_count": int(direction_sector_count),
        "min_cell_observations": int(min_observations),
        "global": global_band,
        "cells": cells,
    }


def apply_conditional_intervals(
    predictions_ms: Iterable[float],
    wind_speeds_ms: Iterable[float],
    directions_deg: Iterable[float],
    calibration: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """Apply conditional residual bands, using the global fallback for sparse cells."""

    predictions = _array(predictions_ms, "predictions_ms")
    wind = _array(wind_speeds_ms, "wind_speeds_ms")
    direction = np.mod(_array(directions_deg, "directions_deg"), 360.0)
    if not (len(predictions) == len(wind) == len(direction)):
        raise ValueError("predictions, wind_speeds, and directions must have equal length")
    edges = np.asarray(calibration["wind_edges_ms"], dtype=float)
    sectors = int(calibration["direction_sector_count"])
    bucket = np.digitize(wind, edges[1:-1], right=False)
    sector = np.floor(direction / (360.0 / sectors)).astype(int)
    lower = np.empty(len(predictions), dtype=float)
    upper = np.empty(len(predictions), dtype=float)
    for i in range(len(predictions)):
        cell = calibration.get("cells", {}).get(f"{bucket[i]}:{sector[i]}", calibration["global"])
        lower[i] = predictions[i] + float(cell["lower_residual_ms"])
        upper[i] = predictions[i] + float(cell["upper_residual_ms"])
    return lower, upper


def propagate_power_interval(
    power_curve: pd.DataFrame,
    predicted_wind_ms: Iterable[float],
    lower_wind_ms: Iterable[float],
    upper_wind_ms: Iterable[float],
    *,
    interval_hours: float = INTERVAL_HOURS,
) -> dict[str, float]:
    """Propagate wind bounds through the empirical power curve into kWh bounds."""

    predicted = _array(predicted_wind_ms, "predicted_wind_ms")
    lower = _array(lower_wind_ms, "lower_wind_ms")
    upper = _array(upper_wind_ms, "upper_wind_ms")
    if not (len(predicted) == len(lower) == len(upper)):
        raise ValueError("wind arrays must have equal length")
    if np.any(lower > upper):
        raise ValueError("lower_wind_ms cannot exceed upper_wind_ms")
    point_kwh = integrate_energy_kwh(apply_power_curve(power_curve, predicted))
    lower_kwh = integrate_energy_kwh(apply_power_curve(power_curve, lower))
    upper_kwh = integrate_energy_kwh(apply_power_curve(power_curve, upper))
    return {
        "point_kwh": float(point_kwh),
        "lower_kwh": float(min(lower_kwh, upper_kwh)),
        "upper_kwh": float(max(lower_kwh, upper_kwh)),
        "interval_width_kwh": float(abs(upper_kwh - lower_kwh)),
    }


def event_level_kwh_interval(
    relative_errors_pct: Iterable[float],
    point_estimate_kwh: float,
    *,
    quantile_pct: float = 90.0,
    bootstrap_resamples: int = 2000,
    random_seed: int = 0,
) -> dict[str, Any]:
    """An event-level kWh uncertainty band, built the way the 2026-10-22 red-team
    review recommended (F5) instead of ``propagate_power_interval``.

    ``propagate_power_interval`` shifts every 10-minute point to the same wind
    residual quantile at once, which implicitly assumes errors are perfectly
    correlated across the whole event. Measured 6-hour-lag error autocorrelation
    is only ~0.05-0.14, so that assumption produces an interval that is almost
    uninformative (median width ~98% of the point estimate on Kelmarsh, ~76% on
    Hill of Towie -- roughly "estimate plus or minus half of itself"). It is kept
    in this module as a general-purpose helper but is NOT what feeds the demo's
    hero number.

    This function instead takes the empirical distribution of |relative kWh
    error| the reconstruction method actually produced across back-test events
    (``relative_errors_pct``, e.g. one farm's wind-first ensemble WAPE-style
    per-event errors) and uses its upper quantile as a symmetric half-width
    around today's point estimate. With n in the 19-28 range (one farm's
    back-test), the quantile itself is noisy, so this also reports a
    nonparametric bootstrap CI of the quantile -- the honest caveat the
    red-team review asked for rather than presenting a single number as exact.
    """

    if not 0.0 < quantile_pct < 100.0:
        raise ValueError("quantile_pct must be strictly between 0 and 100")
    errors = np.abs(_array(relative_errors_pct, "relative_errors_pct"))
    n = len(errors)
    if n < 5:
        raise ValueError("Need at least 5 back-test events to estimate an event-level interval")

    half_width_pct = float(np.percentile(errors, quantile_pct))
    half_width_kwh = point_estimate_kwh * half_width_pct / 100.0

    rng = np.random.default_rng(random_seed)
    bootstrap_quantiles = np.array(
        [
            np.percentile(rng.choice(errors, size=n, replace=True), quantile_pct)
            for _ in range(bootstrap_resamples)
        ]
    )
    ci_lower_pct, ci_upper_pct = np.percentile(bootstrap_quantiles, [2.5, 97.5])

    lower_kwh = max(0.0, point_estimate_kwh - half_width_kwh)
    upper_kwh = point_estimate_kwh + half_width_kwh
    return {
        "method": "event_level_empirical_relative_error_quantile",
        "quantile_pct": float(quantile_pct),
        "n_events": int(n),
        "half_width_pct": half_width_pct,
        "point_kwh": float(point_estimate_kwh),
        "lower_kwh": float(lower_kwh),
        "upper_kwh": float(upper_kwh),
        "half_width_sampling_ci_pct": [float(ci_lower_pct), float(ci_upper_pct)],
    }


def uncertainty_gate(
    calibration: dict[str, float | int],
    *,
    min_observations: int = 100,
    max_width_ms: float | None = None,
) -> dict[str, Any]:
    """Classify whether a PRE-EVENT calibration is suitable to support review.

    2026-10-22 red-team review (F1): this used to take the event's own
    ``event_evaluation`` (coverage scored against hidden truth) and checked
    ``observations`` there -- but that dict's ``observations`` is the event's
    row count, not the calibration's, so "insufficient_calibration_observations"
    was silently checking the wrong count and could never fail for a reasonably
    long event. Both defects are fixed by taking the *calibration* dict (built
    from pre-event history, see ``backtest._calibrate_and_evaluate_interval``)
    instead: it is available at outage time and its ``observations`` really is
    the calibration residual count. The old ``coverage``/``target_coverage``
    check is removed entirely -- that required hidden truth and cannot run in
    a real outage; see docs/REDTEAM_2026-10-23_adversarial_review.md.
    """

    failed: list[str] = []
    observations = int(calibration.get("observations", 0))
    width = float(calibration.get("upper_residual_ms", 0.0)) - float(
        calibration.get("lower_residual_ms", 0.0)
    )
    if observations < min_observations:
        failed.append("insufficient_calibration_observations")
    if max_width_ms is not None and width > max_width_ms:
        failed.append("interval_width")
    return {
        "status": "reviewable" if not failed else "unverified",
        "failed_gates": failed,
        "calibration_observations": observations,
    }


def validate_commercial_profile(profile: dict[str, Any]) -> None:
    """Validate a saved, user-entered pricing profile; no legal interpretation."""

    for field in ("profile_id", "currency", "settlement_interval_minutes", "price_basis", "source"):
        if not profile.get(field):
            raise ValueError(f"commercial profile missing required field: {field}")
    if profile["price_basis"] == "fixed":
        price = profile.get("fixed_price_eur_per_mwh")
        if price is None or float(price) < 0:
            raise ValueError("fixed commercial profile needs a non-negative price")
    elif profile["price_basis"] == "time_series":
        if not profile.get("price_series"):
            raise ValueError("time_series profile needs price_series")
    else:
        raise ValueError("price_basis must be fixed or time_series")


def calculate_indicative_value(lost_kwh: float, profile: dict[str, Any]) -> dict[str, Any]:
    """Calculate an indicative value from a saved fixed-price profile."""

    validate_commercial_profile(profile)
    if lost_kwh < 0:
        raise ValueError("lost_kwh cannot be negative")
    if profile["price_basis"] != "fixed":
        raise ValueError("time_series valuation requires timestamped allocation")
    value = float(lost_kwh) / 1000.0 * float(profile["fixed_price_eur_per_mwh"])
    return {
        "value": value,
        "unit": profile["currency"],
        "lost_kwh": float(lost_kwh),
        "price_per_mwh": float(profile["fixed_price_eur_per_mwh"]),
        "claim_scope": "indicative",
        "disclaimer": "Not a settlement, contractual, regulatory, or legal determination.",
    }
