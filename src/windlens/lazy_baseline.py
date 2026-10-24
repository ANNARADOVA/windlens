"""The simplest possible same-farm reconstruction, for comparison.

Anna's "insurer's lens" critique, 2026-10-23: the back-test harness never
reported a comparison against the simplest possible approach. This is that
approach: equal-weighted average capacity factor of every available same-farm
turbine during the event window, scaled to the target's own nameplate
(rated) capacity. No wind reconstruction, no linear fit, no reference
selection -- just "assume the target behaved like the farm average, scaled
to its own size". Any method that can't beat this has no real claim to
sophistication earning its complexity.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from windlens.loss_estimate import integrate_energy_kwh


def lazy_baseline_estimate_kwh(
    masked_df: pd.DataFrame,
    target_turbine: str,
    available_turbines: list[str],
    block_start: str,
    block_end: str,
    rated_power_kw: dict[str, float],
) -> dict[str, Any]:
    """Equal-weighted average capacity factor of ``available_turbines`` during
    [block_start, block_end), scaled to the target's own rated power.

    Averages capacity factor (active_power_kw / that turbine's own rated_power_kw),
    not raw power, so turbines of different nameplate size are combined fairly;
    "equal-weighted" means each available turbine counts once per timestamp, not
    weighted by distance, behaviour, or anything the real methods use.
    """

    if target_turbine not in rated_power_kw:
        raise ValueError(f"No rated power for target turbine {target_turbine}")
    missing_rated = [t for t in available_turbines if t not in rated_power_kw]
    if missing_rated:
        raise ValueError(f"No rated power for: {', '.join(missing_rated)}")

    window = masked_df[
        (masked_df["turbine_id"].isin(available_turbines))
        & (masked_df["timestamp_utc"] >= block_start)
        & (masked_df["timestamp_utc"] < block_end)
    ][["timestamp_utc", "turbine_id", "active_power_kw"]].copy()
    if window.empty:
        raise ValueError("No available-turbine rows in the event window")

    window["capacity_factor"] = window["active_power_kw"] / window["turbine_id"].map(rated_power_kw)
    per_timestamp_mean_cf = window.groupby("timestamp_utc")["capacity_factor"].mean().sort_index()
    predicted_power_kw = (per_timestamp_mean_cf * rated_power_kw[target_turbine]).to_numpy()

    return {
        "estimated_lost_kwh": integrate_energy_kwh(predicted_power_kw),
        "covered_timestamps": int(len(per_timestamp_mean_cf)),
        "turbines_used": sorted(set(window["turbine_id"])),
    }
