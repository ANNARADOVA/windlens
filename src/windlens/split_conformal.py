"""Split-conformal prediction intervals with a finite-sample coverage guarantee.

Fixes Problem 1 from docs/AUDIT_2026-10-22_uncertainty_calibration.md: the shipped
calibration (windlens.uncertainty.calibrate_residual_interval, as used in
backtest.py/direct_power_uncertainty.py) scores residuals on (near-)the same
observations used to fit the model. This module instead requires the caller to
supply residuals from a calibration window that is time-contiguous with, but
strictly disjoint from, the fitting window -- then applies the textbook
split-conformal correction (Angelopoulos & Bates, arXiv 2107.07511, Theorem 1):
for n calibration residuals and target coverage (1-alpha), the interval
half-width is the ceil((n+1)(1-alpha))-th smallest absolute residual. This gives
P(Y_test in C(X_test)) >= 1-alpha under exchangeability of calibration and test
points -- a finite-sample guarantee, not an asymptotic one.

This produces a SYMMETRIC interval (point prediction +/- half-width), unlike
uncertainty.calibrate_residual_interval's asymmetric two-sided quantile. That is
a deliberate departure, not an oversight: the published finite-sample guarantee
is stated for the symmetric/absolute-residual construction, and reporting that
guarantee honestly requires implementing exactly that construction rather than
the shipped method's shape.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


def calibrate_split_conformal_interval(
    residuals: Iterable[float],
    *,
    coverage: float = 0.90,
    min_observations: int = 20,
) -> dict[str, Any]:
    """Calibrate a symmetric split-conformal half-width from DISJOINT calibration
    residuals (caller's responsibility: these must come from a window the fitted
    model was never scored or trained on before this call).
    """

    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be strictly between 0 and 1")
    if min_observations < 1:
        raise ValueError("min_observations must be at least 1")

    values = np.asarray(list(residuals), dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("residuals must be a finite one-dimensional sequence")
    n = len(values)
    if n < min_observations:
        raise ValueError(f"Need at least {min_observations} calibration residuals; got {n}")

    alpha = 1.0 - coverage
    abs_sorted = np.sort(np.abs(values))
    rank = math.ceil((n + 1) * (1.0 - alpha))  # 1-indexed per Angelopoulos & Bates
    if rank > n:
        # Not enough calibration points to guarantee this coverage at all; the
        # textbook convention is to widen to the full observed range (infinite
        # half-width), signalled here rather than silently returning a narrower,
        # unguaranteed interval.
        half_width = float("inf")
        guaranteed = False
    else:
        half_width = float(abs_sorted[rank - 1])
        guaranteed = True

    return {
        "method": "split_conformal_symmetric",
        "coverage_target": float(coverage),
        "observations": int(n),
        "half_width": half_width,
        "coverage_guaranteed_at_this_n": guaranteed,
        "residual_bias_diagnostic": float(np.mean(values)),
    }


def apply_split_conformal_interval(
    predictions: Iterable[float], interval: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Return symmetric lower/upper bounds: prediction +/- half_width."""

    values = np.asarray(list(predictions), dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("predictions must be a finite one-dimensional sequence")
    try:
        half_width = float(interval["half_width"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("interval lacks a valid half_width") from exc
    if half_width < 0:
        raise ValueError("half_width cannot be negative")
    return values - half_width, values + half_width
