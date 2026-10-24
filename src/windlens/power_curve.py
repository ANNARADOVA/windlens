"""Empirical power curve: bin wind speed, average power, interpolate to predict."""

from __future__ import annotations

import numpy as np
import pandas as pd

# 2026-10-23, "insurer's lens" quick fix #4: a row where actual power is this many
# standard deviations BELOW its own wind-speed bin's mean is flagged as likely
# curtailed/derated (not normal turbulence scatter). One-sided deliberately:
# normal scatter around a power curve is roughly symmetric, but curtailment
# produces a one-sided tail of unusually LOW power for the wind speed observed --
# a row with unusually HIGH power for its wind speed is not curtailment and is
# never flagged. 2.0 std is a conservative, documented choice (not tuned against
# any back-test result): it flags only the clear tail, not ordinary turbulence,
# consistent with how `direct_power_uncertainty.reference_operating_state_check`
# already treats near-zero power at above-cut-in wind as a distinct, flaggable
# condition rather than silently averaging it in.
CURTAILMENT_FLAG_STD_THRESHOLD = 2.0


def flag_likely_curtailed_rows(
    target_df: pd.DataFrame,
    bin_width_ms: float = 0.5,
    std_threshold: float = CURTAILMENT_FLAG_STD_THRESHOLD,
) -> pd.Series:
    """Boolean mask (aligned to target_df's index): True where a row's power looks
    like curtailment/derating rather than normal turbulence scatter for its
    wind-speed bin.

    A one-pass bin statistic, not a fitted curve residual: each row is compared
    only to the mean and std of power within its OWN wind-speed bin (bin_width_ms
    wide), among rows in the same input. Bins with fewer than 5 observations are
    never flagged (a std from 1-4 points is not a meaningful scatter estimate).
    """

    valid = target_df.dropna(subset=["wind_speed_ms", "active_power_kw"])
    flagged = pd.Series(False, index=target_df.index)
    if valid.empty:
        return flagged

    bin_index = np.floor(valid["wind_speed_ms"].to_numpy(dtype=float) / bin_width_ms).astype(int)
    stats = valid.groupby(bin_index)["active_power_kw"].agg(["mean", "std", "count"])
    bin_mean = stats["mean"].reindex(bin_index).to_numpy()
    bin_std = stats["std"].reindex(bin_index).to_numpy()
    bin_count = stats["count"].reindex(bin_index).to_numpy()

    power = valid["active_power_kw"].to_numpy(dtype=float)
    has_enough_data = bin_count >= 5
    has_scatter = np.nan_to_num(bin_std) > 0
    is_low_outlier = power < (bin_mean - std_threshold * np.nan_to_num(bin_std))
    flagged.loc[valid.index] = has_enough_data & has_scatter & is_low_outlier
    return flagged


def fit_power_curve(
    target_df: pd.DataFrame,
    bin_width_ms: float = 0.5,
    exclude_likely_curtailed: bool = False,
) -> pd.DataFrame:
    """Bin wind_speed_ms into bin_width_ms-wide bins and average active_power_kw per bin.

    Intended to be called with a single turbine's pre-outage rows. Returns a
    DataFrame with one row per populated bin: bin_center_ms, mean_power_kw,
    observation_count -- sorted by bin_center_ms.

    ``exclude_likely_curtailed`` (2026-10-23, default False) applies
    flag_likely_curtailed_rows first and fits on the surviving rows only. Default
    is False so every existing caller and every already-published back-test
    number is reproduced unchanged; this is a new, opt-in training-data filter,
    not applied retroactively to anything already in docs/DECISION_LOG.md or
    docs/METHOD_BAKEOFF_2026-10-23.md.
    """

    valid = target_df.dropna(subset=["wind_speed_ms", "active_power_kw"])
    if valid.empty:
        raise ValueError("No valid wind_speed_ms/active_power_kw observations to bin")

    if exclude_likely_curtailed:
        curtailed = flag_likely_curtailed_rows(valid, bin_width_ms=bin_width_ms)
        valid = valid.loc[~curtailed]
        if valid.empty:
            raise ValueError("No valid observations left after excluding likely-curtailed rows")

    bin_index = np.floor(valid["wind_speed_ms"].to_numpy(dtype=float) / bin_width_ms).astype(int)
    grouped = valid.groupby(bin_index)["active_power_kw"].agg(["mean", "count"])
    grouped = grouped.rename(columns={"mean": "mean_power_kw", "count": "observation_count"})
    grouped["bin_center_ms"] = (grouped.index.to_numpy(dtype=float) + 0.5) * bin_width_ms
    grouped["observation_count"] = grouped["observation_count"].astype(int)

    return (
        grouped[["bin_center_ms", "mean_power_kw", "observation_count"]]
        .sort_values("bin_center_ms")
        .reset_index(drop=True)
    )


def apply_power_curve(power_curve: pd.DataFrame, wind_speed_ms: np.ndarray) -> np.ndarray:
    """Map wind speeds to expected power by linear interpolation over the empirical curve.

    Wind speeds outside the curve's observed range are clamped to the nearest edge bin
    (numpy's default np.interp behaviour), since the empirical curve has no data to
    extrapolate from.
    """

    if power_curve.empty:
        raise ValueError("Power curve has no bins to interpolate from")

    centers = power_curve["bin_center_ms"].to_numpy(dtype=float)
    powers = power_curve["mean_power_kw"].to_numpy(dtype=float)
    return np.interp(np.asarray(wind_speed_ms, dtype=float), centers, powers)
