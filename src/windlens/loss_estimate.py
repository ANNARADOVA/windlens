"""Integrate power into kWh and compare reconstructed vs. hidden-truth outcomes."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

INTERVAL_HOURS = 10 / 60  # the canonical research dataset's fixed 10-minute cadence

# How far a gap between consecutive timestamps may deviate from the median gap
# (as a fraction of the median) before the spacing is treated as irregular rather
# than just floating-point/parsing noise.
IRREGULAR_CADENCE_TOLERANCE = 0.05

# A single dropped/duplicate reading or clock hiccup must not nuke the whole file's
# cadence inference -- live-tested against the real BayWa sample files (2026-10-24),
# which have exactly 1 irregular gap out of 12,959 (a one-off anomaly, not a wrong
# cadence) and must still integrate energy, not raise. Genuinely wrong cadence (e.g.
# a file that's actually hourly, not 10-minute) shows up as a LARGE fraction of
# irregular gaps, not one in thousands.
IRREGULAR_CADENCE_MAX_FRACTION = 0.02


def integrate_energy_kwh(power_kw: np.ndarray, interval_hours: float = INTERVAL_HOURS) -> float:
    """Sum of power readings (kW) at a fixed cadence, converted to kWh.

    Defaults to the canonical research dataset's fixed 10-minute cadence. Callers
    working from arbitrary uploaded data must not rely on that default -- pass the
    actual cadence from ``infer_interval_hours()`` instead, since silently assuming
    10-minute spacing on, say, hourly data would produce a 6x energy error.
    """

    return float(np.sum(np.asarray(power_kw, dtype=float)) * interval_hours)


def infer_interval_hours(timestamps: pd.Series | list[str]) -> float:
    """The median spacing between consecutive timestamps, in hours, inferred from
    the data itself rather than assumed.

    Raises ValueError if fewer than two distinct timestamps are given, or if more than
    IRREGULAR_CADENCE_MAX_FRACTION of the gaps deviate from the median by more than
    IRREGULAR_CADENCE_TOLERANCE -- a genuinely irregular cadence makes a single fixed
    per-sample width unreliable for energy integration, so this refuses rather than
    silently averaging over it. A small fraction of one-off irregular gaps (a dropped
    or duplicate reading, a DST shift) does not trigger this -- the median is still a
    reliable cadence estimate in that case.
    """

    sorted_ts = pd.to_datetime(pd.Series(list(timestamps))).sort_values().reset_index(drop=True)
    gaps_hours = sorted_ts.diff().dropna().dt.total_seconds() / 3600.0
    gaps_hours = gaps_hours[gaps_hours > 0]
    if gaps_hours.empty:
        raise ValueError("Need at least two distinct timestamps to infer a sampling interval")

    median_hours = float(gaps_hours.median())
    deviation = (gaps_hours - median_hours).abs()
    irregular = deviation[deviation > IRREGULAR_CADENCE_TOLERANCE * median_hours]
    irregular_fraction = len(irregular) / len(gaps_hours)
    if irregular_fraction > IRREGULAR_CADENCE_MAX_FRACTION:
        raise ValueError(
            f"Timestamps are not evenly spaced (median gap {median_hours:.4f} hours; "
            f"{len(irregular)} of {len(gaps_hours)} gaps ({irregular_fraction:.1%}) differ from it by more than "
            f"{IRREGULAR_CADENCE_TOLERANCE:.0%}) -- cannot reliably integrate energy "
            "from an irregular cadence"
        )
    return median_hours


def wind_speed_errors(
    reconstructed: pd.DataFrame, hidden_truth: pd.DataFrame
) -> dict[str, float]:
    """MAE/RMSE/signed bias of reconstructed vs. hidden-truth wind speed, by timestamp.

    `reconstructed` must have timestamp_utc + wind_speed_ms_reconstructed;
    `hidden_truth` must have timestamp_utc + wind_speed_ms. Compared only on
    timestamps present in both.
    """

    joined = pd.merge(
        reconstructed[["timestamp_utc", "wind_speed_ms_reconstructed"]],
        hidden_truth[["timestamp_utc", "wind_speed_ms"]],
        on="timestamp_utc",
        how="inner",
    )
    if joined.empty:
        raise ValueError("No overlapping timestamps between reconstruction and hidden truth")

    error = joined["wind_speed_ms_reconstructed"].to_numpy(dtype=float) - joined[
        "wind_speed_ms"
    ].to_numpy(dtype=float)

    return {
        "compared_observations": int(len(joined)),
        "mae_ms": float(np.mean(np.abs(error))),
        "rmse_ms": float(np.sqrt(np.mean(error**2))),
        "signed_bias_ms": float(np.mean(error)),
    }


def power_errors(
    expected_power_kw: np.ndarray, truth_power_kw: np.ndarray
) -> dict[str, float]:
    """MAE/RMSE/signed bias of expected (power-curve-derived) vs. truth power, in kW.

    Mirrors ``wind_speed_errors``'s shape exactly, but takes the two power arrays
    directly (both are already aligned/joined by the caller -- see backtest.py's
    ``_score``), since callers reach this point already holding matched arrays
    rather than two separate DataFrames to join.
    """

    expected = np.asarray(expected_power_kw, dtype=float)
    truth = np.asarray(truth_power_kw, dtype=float)
    if len(expected) != len(truth):
        raise ValueError("expected_power_kw and truth_power_kw must be the same length")
    if len(expected) == 0:
        raise ValueError("No power observations to compare")

    error = expected - truth
    return {
        "compared_observations": int(len(error)),
        "mae_kw": float(np.mean(np.abs(error))),
        "rmse_kw": float(np.sqrt(np.mean(error**2))),
        "signed_bias_kw": float(np.mean(error)),
    }


def energy_weighted_wape(
    estimated_kwh_per_event: list[float], actual_kwh_per_event: list[float]
) -> float:
    """Weighted Absolute Percentage Error across events: sum(|est-actual|)/sum(actual).

    Unlike MAPE (which divides each event by its own actual and blows up near zero
    generation), WAPE divides by the *total* actual energy across all events, so a
    near-zero event can't dominate the aggregate error.
    """

    estimated = np.asarray(estimated_kwh_per_event, dtype=float)
    actual = np.asarray(actual_kwh_per_event, dtype=float)
    denominator = np.sum(np.abs(actual))
    if denominator == 0:
        raise ValueError("Cannot compute WAPE when total actual energy is zero")
    return float(np.sum(np.abs(estimated - actual)) / denominator * 100)


def signed_aggregate_bias_pct(
    estimated_kwh_per_event: list[float], actual_kwh_per_event: list[float]
) -> float:
    """Signed aggregate bias across events: sum(est-actual)/sum(actual), as a percent.

    Positive means the model systematically over-estimates lost energy; negative
    means it systematically under-estimates.
    """

    estimated = np.asarray(estimated_kwh_per_event, dtype=float)
    actual = np.asarray(actual_kwh_per_event, dtype=float)
    denominator = np.sum(actual)
    if denominator == 0:
        raise ValueError("Cannot compute signed aggregate bias when total actual energy is zero")
    return float(np.sum(estimated - actual) / denominator * 100)


def estimate_loss(
    expected_power_kw: np.ndarray, hidden_truth_power_kw: np.ndarray
) -> dict[str, Any]:
    """Compare integrated estimated-lost kWh against the actual kWh from hidden truth."""

    estimated_kwh = integrate_energy_kwh(expected_power_kw)
    actual_kwh = integrate_energy_kwh(hidden_truth_power_kw)
    absolute_error_kwh = abs(estimated_kwh - actual_kwh)
    return {
        "estimated_lost_kwh": estimated_kwh,
        "actual_lost_kwh": actual_kwh,
        "absolute_error_kwh": absolute_error_kwh,
        "relative_error_pct": (
            absolute_error_kwh / actual_kwh * 100 if actual_kwh else float("nan")
        ),
    }
