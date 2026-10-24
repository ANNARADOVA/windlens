"""Measure-correlate-predict: reconstruct a target turbine's wind speed from a reference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    method: str = "ols"

    def predict(self, reference_wind_speed_ms: np.ndarray) -> np.ndarray:
        return self.slope * reference_wind_speed_ms + self.intercept


def _paired_series(
    df: pd.DataFrame, target_turbine: str, reference_turbine: str
) -> pd.DataFrame:
    """Simultaneous, valid wind_speed_ms observations for both turbines, by timestamp."""

    target = df[df["turbine_id"] == target_turbine].set_index("timestamp_utc")["wind_speed_ms"]
    reference = df[df["turbine_id"] == reference_turbine].set_index("timestamp_utc")[
        "wind_speed_ms"
    ]
    paired = pd.concat(
        [target.rename("target"), reference.rename("reference")], axis=1, join="inner"
    )
    return paired.dropna().sort_index()


def fit_linear(paired: pd.DataFrame, *, method: str = "ols") -> LinearFit:
    """Fit target wind speed from reference wind speed.

    ``method="ols"`` (default -- used only by ``_time_ordered_holdout_r2`` for
    reference-selection ranking): ordinary least squares, which minimizes
    in-sample squared error but shrinks predicted variance toward the mean
    (predicted/true wind standard-deviation ratio measured at 0.81-0.83 on
    Kelmarsh). Pushed through the convex part of a power curve, that variance
    shrinkage under-estimates energy by Jensen's inequality -- this is why OLS
    is kept for *ranking* candidate references (where minimizing squared error
    is the right objective) but not for the final reconstruction.

    ``method="variance_ratio"`` (used by ``reconstruct_wind_speed`` and
    ``fit_weighted_references`` for the actual wind-first reconstruction): the
    measure-correlate-predict literature's standard fix for energy estimation
    -- match the target's variance instead of minimizing in-sample squared
    error. Slope is ``std(target)/std(reference)``, signed by the
    correlation's sign. 2026-10-22 red-team review (F7): swapping only this
    dropped measured Kelmarsh wind-first WAPE from 9.89% to 5.85%.
    """

    if len(paired) < 2:
        raise ValueError("Need at least two paired observations to fit a line")
    reference = paired["reference"].to_numpy(dtype=float)
    target = paired["target"].to_numpy(dtype=float)
    if method == "ols":
        slope, intercept = np.polyfit(reference, target, 1)
    elif method == "variance_ratio":
        reference_std = float(np.std(reference))
        if reference_std == 0.0:
            raise ValueError("Reference wind speed has zero variance; cannot fit a variance-ratio slope")
        correlation = float(np.corrcoef(reference, target)[0, 1])
        sign = 1.0 if correlation >= 0 else -1.0
        slope = sign * float(np.std(target)) / reference_std
        intercept = float(np.mean(target)) - slope * float(np.mean(reference))
    else:
        raise ValueError(f"Unknown MCP fit method: {method!r}")
    return LinearFit(slope=float(slope), intercept=float(intercept), method=method)


def _time_ordered_holdout_r2(paired: pd.DataFrame, holdout_fraction: float = 0.2) -> float:
    """R^2 on a trailing time-ordered holdout slice, never a random split."""

    split = int(len(paired) * (1 - holdout_fraction))
    train, holdout = paired.iloc[:split], paired.iloc[split:]
    if len(train) < 2 or len(holdout) < 1:
        return float("-inf")

    fit = fit_linear(train)
    predicted = fit.predict(holdout["reference"].to_numpy(dtype=float))
    actual = holdout["target"].to_numpy(dtype=float)

    total_ss = float(np.sum((actual - actual.mean()) ** 2))
    if total_ss == 0:
        return float("-inf")
    residual_ss = float(np.sum((actual - predicted) ** 2))
    return 1 - residual_ss / total_ss


def select_reference_turbine(
    pre_outage_df: pd.DataFrame,
    target_turbine: str,
    candidate_turbines: list[str],
    min_paired_observations: int = 10,
    full_df: pd.DataFrame | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
) -> dict[str, Any]:
    """Rank candidate reference turbines by time-ordered holdout R^2 against the target.

    ``full_df``/``window_start``/``window_end`` (2026-10-24, correctness fix): the
    historical-fit ranking above says nothing about whether the top-ranked candidate
    actually HAS readings during the outage window itself -- a candidate can be the
    best-correlated turbine historically and still be itself down (or simply absent
    from the uploaded files) for the exact window being reconstructed, which would
    silently produce an empty/degenerate reconstruction with no coverage. When these
    three are given, the top-ranked candidate with zero valid readings in
    [window_start, window_end) is skipped in favor of the next-best-ranked candidate
    that does have coverage there, with the substitution surfaced in the result
    (never a silent fallback) via ``reference_fallback_note``.
    """

    ranking = []
    check_coverage = full_df is not None and window_start is not None and window_end is not None
    for candidate in candidate_turbines:
        paired = _paired_series(pre_outage_df, target_turbine, candidate)
        if len(paired) < min_paired_observations:
            continue
        entry = {
            "turbine_id": candidate,
            "holdout_r2": _time_ordered_holdout_r2(paired),
            "paired_observations": len(paired),
        }
        if check_coverage:
            entry["window_coverage_rows"] = int(
                full_df[
                    (full_df["turbine_id"] == candidate)
                    & (full_df["timestamp_utc"] >= window_start)
                    & (full_df["timestamp_utc"] < window_end)
                ]["wind_speed_ms"].notna().sum()
            )
        ranking.append(entry)

    if not ranking:
        raise ValueError(
            f"No candidate reference turbine had >= {min_paired_observations} "
            "paired observations with the target"
        )

    ranking.sort(key=lambda entry: entry["holdout_r2"], reverse=True)
    selected = ranking[0]["turbine_id"]
    result: dict[str, Any] = {"ranking": ranking, "selected": selected}

    if check_coverage:
        covered = [entry for entry in ranking if entry["window_coverage_rows"] > 0]
        if covered and covered[0]["turbine_id"] != selected:
            top = ranking[0]
            selected = covered[0]["turbine_id"]
            result["selected"] = selected
            result["reference_fallback_note"] = (
                f"{top['turbine_id']} was the top-ranked reference by historical fit, but has no "
                f"readings inside this outage window -- using {selected} instead, the next-best "
                "candidate that does have coverage here."
            )
        elif not covered:
            result["reference_fallback_note"] = (
                "None of the candidate reference turbines have any readings inside this outage "
                f"window -- proceeding with {selected}, the best-ranked by historical fit, but its "
                "reconstruction for this window will be empty."
            )

    return result


def reconstruct_wind_speed(
    masked_df: pd.DataFrame,
    target_turbine: str,
    reference_turbine: str,
    mask_start: str,
    mask_end: str,
) -> pd.DataFrame:
    """Predict target_turbine wind speed through [mask_start, mask_end).

    Fits the linear reference->target relationship on pre-outage data only
    (timestamp_utc < mask_start), then applies it to the reference turbine's
    own readings during the masked interval -- the data a live outage would
    still leave available.
    """

    pre_outage = masked_df[masked_df["timestamp_utc"] < mask_start]
    paired = _paired_series(pre_outage, target_turbine, reference_turbine)
    fit = fit_linear(paired, method="variance_ratio")

    reference_during = (
        masked_df[
            (masked_df["turbine_id"] == reference_turbine)
            & (masked_df["timestamp_utc"] >= mask_start)
            & (masked_df["timestamp_utc"] < mask_end)
        ]
        .set_index("timestamp_utc")["wind_speed_ms"]
        .dropna()
        .sort_index()
    )

    predicted = fit.predict(reference_during.to_numpy(dtype=float))
    return pd.DataFrame(
        {
            "timestamp_utc": reference_during.index,
            "wind_speed_ms_reconstructed": predicted,
        }
    ).reset_index(drop=True)


def reconstruct_wind_speed_ensemble(
    masked_df: pd.DataFrame,
    target_turbine: str,
    reference_turbines: list[str],
    mask_start: str,
    mask_end: str,
) -> pd.DataFrame:
    """Simple peer ensemble: average the individual single-reference linear MCP
    predictions from each reference turbine (each fit on pre-outage data only).

    Averaging independently-fit single-reference models, rather than one
    multivariate regression across all references, avoids the multicollinearity
    instability of regressing on several same-farm turbines that are themselves
    highly correlated with each other.
    """

    if not reference_turbines:
        raise ValueError("Need at least one reference turbine for the ensemble")

    predictions = [
        reconstruct_wind_speed(masked_df, target_turbine, reference, mask_start, mask_end)
        .set_index("timestamp_utc")["wind_speed_ms_reconstructed"]
        .rename(reference)
        for reference in reference_turbines
    ]
    combined = pd.concat(predictions, axis=1, join="inner")
    if combined.empty:
        raise ValueError(
            "No timestamps have a reconstructed wind speed from every reference turbine"
        )

    ensemble_mean = combined.mean(axis=1).sort_index()
    return pd.DataFrame(
        {
            "timestamp_utc": ensemble_mean.index,
            "wind_speed_ms_reconstructed": ensemble_mean.to_numpy(),
        }
    ).reset_index(drop=True)


def reconstruct_wind_speed_weighted(
    masked_df: pd.DataFrame,
    target_turbine: str,
    reference_weights: dict[str, float],
    mask_start: str,
    mask_end: str,
) -> pd.DataFrame:
    """Combine independently-fitted reference predictions using supplied weights."""

    if not reference_weights:
        raise ValueError("Need at least one weighted reference turbine")
    positive = {reference: float(weight) for reference, weight in reference_weights.items() if weight > 0}
    if not positive:
        raise ValueError("At least one reference weight must be positive")
    total = sum(positive.values())
    predictions = []
    for reference, weight in positive.items():
        prediction = reconstruct_wind_speed(
            masked_df, target_turbine, reference, mask_start, mask_end
        ).set_index("timestamp_utc")["wind_speed_ms_reconstructed"]
        predictions.append((prediction, weight / total))
    combined = pd.concat([series.rename(str(index)) for index, (series, _) in enumerate(predictions)], axis=1, join="inner")
    if combined.empty:
        raise ValueError("No timestamps have a weighted reference prediction")
    weighted = sum(combined.iloc[:, index] * weight for index, (_, weight) in enumerate(predictions))
    return pd.DataFrame(
        {"timestamp_utc": weighted.index, "wind_speed_ms_reconstructed": weighted.to_numpy()}
    ).reset_index(drop=True)


def fit_weighted_references(
    masked_df: pd.DataFrame,
    target_turbine: str,
    reference_weights: dict[str, float],
    fit_before: str,
) -> dict[str, tuple[LinearFit, float]]:
    """Fit one linear reference->target model per positive-weighted reference,
    using only data strictly before ``fit_before``, with weights normalized to
    sum to 1.

    This separates fitting from prediction so the SAME fitted model can be
    scored over a different window than the one it predicts for an event --
    needed to calibrate uncertainty intervals from the model actually used,
    rather than a model re-fit at an earlier cutoff (see
    ``_calibrate_and_evaluate_interval`` in backtest.py).
    """

    positive = {reference: float(weight) for reference, weight in reference_weights.items() if weight > 0}
    if not positive:
        raise ValueError("At least one reference weight must be positive")
    total = sum(positive.values())
    pre_outage = masked_df[masked_df["timestamp_utc"] < fit_before]
    fits: dict[str, tuple[LinearFit, float]] = {}
    for reference, weight in positive.items():
        paired = _paired_series(pre_outage, target_turbine, reference)
        fits[reference] = (fit_linear(paired, method="variance_ratio"), weight / total)
    return fits


def predict_with_fitted_references(
    masked_df: pd.DataFrame,
    fits: dict[str, tuple[LinearFit, float]],
    window_start: str,
    window_end: str,
) -> pd.DataFrame:
    """Apply already-fitted per-reference models (see ``fit_weighted_references``)
    over [window_start, window_end) without refitting."""

    if not fits:
        raise ValueError("Need at least one fitted reference")
    predictions = []
    for reference, (fit, weight) in fits.items():
        reference_during = (
            masked_df[
                (masked_df["turbine_id"] == reference)
                & (masked_df["timestamp_utc"] >= window_start)
                & (masked_df["timestamp_utc"] < window_end)
            ]
            .set_index("timestamp_utc")["wind_speed_ms"]
            .dropna()
            .sort_index()
        )
        predictions.append((fit.predict(reference_during.to_numpy(dtype=float)), reference_during.index, weight))
    combined = pd.concat(
        [pd.Series(values, index=index).rename(str(i)) for i, (values, index, _) in enumerate(predictions)],
        axis=1,
        join="inner",
    )
    if combined.empty:
        raise ValueError("No timestamps have a prediction from every fitted reference")
    weighted = sum(combined.iloc[:, i] * predictions[i][2] for i in range(len(predictions)))
    return pd.DataFrame(
        {"timestamp_utc": weighted.index, "wind_speed_ms_reconstructed": weighted.to_numpy()}
    ).reset_index(drop=True)


def reference_within_training_domain(
    masked_df: pd.DataFrame,
    reference_turbine: str,
    mask_start: str,
    mask_end: str,
) -> dict[str, Any]:
    """Whether reference_turbine's wind speed during [mask_start, mask_end) falls
    inside the range observed in its own pre-outage training data.

    A reconstruction built from reference readings outside the range the linear fit
    was trained on is an extrapolation, not an interpolation -- the "validated
    domain" check from WindLens_instructions.md Section 9.
    """

    pre_outage = masked_df[masked_df["timestamp_utc"] < mask_start]
    training_values = (
        pre_outage[pre_outage["turbine_id"] == reference_turbine]["wind_speed_ms"].dropna()
    )
    if training_values.empty:
        raise ValueError(f"No pre-outage training data for {reference_turbine}")

    during_values = masked_df[
        (masked_df["turbine_id"] == reference_turbine)
        & (masked_df["timestamp_utc"] >= mask_start)
        & (masked_df["timestamp_utc"] < mask_end)
    ]["wind_speed_ms"].dropna()

    training_min = float(training_values.min())
    training_max = float(training_values.max())
    out_of_domain = during_values[
        (during_values < training_min) | (during_values > training_max)
    ]

    return {
        "reference_turbine": reference_turbine,
        "training_min_ms": training_min,
        "training_max_ms": training_max,
        "observations_during": int(len(during_values)),
        "observations_out_of_domain": int(len(out_of_domain)),
        "within_domain": len(out_of_domain) == 0,
    }

