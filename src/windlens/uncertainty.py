"""Empirical uncertainty intervals for reconstructed wind speed.

Intervals are calibrated from out-of-sample residuals collected from contiguous
validation blocks.  They are deliberately simple and auditable: the interval is
the central empirical residual quantile around each point prediction.  This is a
prediction interval for the demonstrated data domain, not a probabilistic claim
about arbitrary future farms.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def calibrate_residual_interval(
    residuals_ms: Iterable[float],
    *,
    coverage: float = 0.90,
    min_observations: int = 20,
) -> dict[str, Any]:
    """Calibrate a central empirical residual interval.

    ``residuals_ms`` should come from held-out, time-contiguous validation blocks
    (prediction minus observed wind), never from the same observations used to fit
    the reconstruction.  Quantiles are calculated with NumPy's linear interpolation
    to make the result deterministic across runs.
    """

    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be strictly between 0 and 1")
    if min_observations < 1:
        raise ValueError("min_observations must be at least 1")

    values = np.asarray(list(residuals_ms), dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("residuals must be a finite one-dimensional sequence")
    if len(values) < min_observations:
        raise ValueError(
            f"Need at least {min_observations} calibration residuals; got {len(values)}"
        )

    tail = (1.0 - coverage) / 2.0
    lower, upper = np.quantile(values, [tail, 1.0 - tail], method="linear")
    return {
        "method": "empirical_residual_quantiles",
        "coverage_target": float(coverage),
        "observations": int(len(values)),
        "lower_residual_ms": float(lower),
        "upper_residual_ms": float(upper),
        "residual_bias_ms": float(np.mean(values)),
    }


def apply_residual_interval(
    predictions_ms: Iterable[float], interval: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Return lower and upper wind-speed bounds for point predictions."""

    predictions = np.asarray(list(predictions_ms), dtype=float)
    if predictions.ndim != 1 or not np.all(np.isfinite(predictions)):
        raise ValueError("predictions must be a finite one-dimensional sequence")
    try:
        lower_residual = float(interval["lower_residual_ms"])
        upper_residual = float(interval["upper_residual_ms"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("interval lacks valid residual bounds") from exc
    if lower_residual > upper_residual:
        raise ValueError("interval lower residual cannot exceed upper residual")
    return predictions + lower_residual, predictions + upper_residual


def pooled_coverage_summary(evaluations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pooled (marginal) coverage across many scored blocks, plus a per-block
    dispersion diagnostic -- replaces "% of blocks individually >= target".

    2026-10-22 red-team review (F4): "90% of blocks individually hit 90% coverage"
    is not a meaningful target. The red-team's own simulation of a PERFECTLY
    calibrated 90% interval, scored per 5-day block under the lag-1 residual
    autocorrelation actually measured here (rho ~= 0.6-0.7), clears that bar only
    ~45-58% of the time by construction -- the metric fails even a correctly
    calibrated model. Pooled coverage (covered observations / total observations,
    across every scored point in every block) is not subject to that artefact and
    is the number that actually reflects calibration quality. The per-block
    standard deviation and range are reported alongside it as a genuine diagnostic:
    spread much wider than autocorrelation alone would produce is real evidence of
    conditional mis-calibration (e.g. short pre-event history), which the old
    pass/fail framing obscured rather than surfaced.
    """

    evaluations = list(evaluations)
    if not evaluations:
        raise ValueError("Need at least one scored block")
    total_observations = sum(int(e["observations"]) for e in evaluations)
    total_covered = sum(int(e["covered_observations"]) for e in evaluations)
    if total_observations == 0:
        raise ValueError("No observations across the given blocks")
    per_block_pct = np.array([float(e["coverage_pct"]) for e in evaluations], dtype=float)
    return {
        "n_blocks": len(evaluations),
        "total_observations": int(total_observations),
        "pooled_coverage_pct": float(total_covered / total_observations * 100.0),
        "per_block_coverage_mean_pct": float(np.mean(per_block_pct)),
        "per_block_coverage_std_pct": float(np.std(per_block_pct)),
        "per_block_coverage_min_pct": float(np.min(per_block_pct)),
        "per_block_coverage_max_pct": float(np.max(per_block_pct)),
        "per_block_coverage_p10_pct": float(np.percentile(per_block_pct, 10)),
        "per_block_coverage_p90_pct": float(np.percentile(per_block_pct, 90)),
    }


def evaluate_interval(
    *,
    actual: Iterable[float],
    lower: Iterable[float],
    upper: Iterable[float],
) -> dict[str, float | int]:
    """Score empirical interval coverage and average width on held-out data."""

    actual_values = np.asarray(list(actual), dtype=float)
    lower_values = np.asarray(list(lower), dtype=float)
    upper_values = np.asarray(list(upper), dtype=float)
    if actual_values.ndim != 1 or lower_values.ndim != 1 or upper_values.ndim != 1:
        raise ValueError("actual, lower, and upper must be one-dimensional sequences")
    if not (len(actual_values) == len(lower_values) == len(upper_values)):
        raise ValueError("actual, lower, and upper must have equal length")
    if len(actual_values) == 0:
        raise ValueError("Cannot evaluate an empty interval")
    if not all(np.all(np.isfinite(values)) for values in (actual_values, lower_values, upper_values)):
        raise ValueError("actual, lower, and upper must contain finite values")
    if np.any(lower_values > upper_values):
        raise ValueError("lower interval bound cannot exceed upper bound")

    covered = (actual_values >= lower_values) & (actual_values <= upper_values)
    return {
        "observations": int(len(actual_values)),
        "covered_observations": int(np.sum(covered)),
        "coverage_pct": float(np.mean(covered) * 100.0),
        "mean_width_ms": float(np.mean(upper_values - lower_values)),
    }
