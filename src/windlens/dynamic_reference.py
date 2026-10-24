"""Leakage-safe geo + behaviour reference selection for WindLens.

The selector uses turbine metadata as a geographic prior, then lets contiguous
pre-event validation performance choose the usable lookback window and reference
weights. It never reads target observations from the held-out outage window.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

REQUIRED_METADATA = {"turbine_id", "latitude", "longitude"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 latitude/longitude points."""

    earth_km = 6371.0088
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return float(2 * earth_km * np.arcsin(np.sqrt(a)))


def _paired(df: pd.DataFrame, target: str, reference: str) -> pd.DataFrame:
    target_values = df[df["turbine_id"] == target].set_index("timestamp_utc")["wind_speed_ms"]
    ref_values = df[df["turbine_id"] == reference].set_index("timestamp_utc")["wind_speed_ms"]
    return pd.concat(
        [target_values.rename("target"), ref_values.rename("reference")], axis=1, join="inner"
    ).dropna().sort_index()


def _validate_candidate(paired: pd.DataFrame, holdout_fraction: float) -> dict[str, float]:
    split = int(len(paired) * (1 - holdout_fraction))
    if split < 2 or len(paired) - split < 1:
        raise ValueError("not enough paired observations for a time-ordered holdout")
    train, holdout = paired.iloc[:split], paired.iloc[split:]
    slope, intercept = np.polyfit(train["reference"], train["target"], 1)
    predicted = slope * holdout["reference"].to_numpy(float) + intercept
    actual = holdout["target"].to_numpy(float)
    residual = predicted - actual
    total_ss = np.sum((actual - actual.mean()) ** 2)
    return {
        "holdout_observations": int(len(holdout)),
        "rmse_ms": float(np.sqrt(np.mean(residual**2))),
        "mae_ms": float(np.mean(np.abs(residual))),
        "signed_bias_ms": float(np.mean(residual)),
        "holdout_r2": float(1 - np.sum(residual**2) / total_ss) if total_ss else float("-inf"),
    }


def select_dynamic_references(
    pre_outage_df: pd.DataFrame,
    target_turbine: str,
    candidate_turbines: list[str],
    metadata_df: pd.DataFrame,
    *,
    lookback_days: Iterable[int] = (30, 90, 180),
    as_of: str | None = None,
    min_paired_observations: int = 20,
    holdout_fraction: float = 0.2,
    top_k: int = 3,
    max_distance_km: float | None = None,
    behavior_weight: float = 0.8,
) -> dict[str, Any]:
    """Choose a leakage-safe lookback window and reference ranking.

    The selected window minimises the best candidate's contiguous holdout RMSE,
    preferring the shortest window within a numerical tie. Candidate ranking uses
    ``behavior_weight`` behavioural validation and ``1 - behavior_weight``
    geographic proximity (default 0.8/0.2, the shipped weighting -- see
    `docs/DECISION_LOG.md`'s 2026-10-23 reference-selection weighting ablation
    entry for why this default was kept rather than one of the tested
    alternatives). No candidate means ``status='abstain'`` instead of an
    invented reference.
    """

    missing = REQUIRED_METADATA - set(metadata_df.columns)
    if missing:
        raise ValueError(f"metadata missing required columns: {', '.join(sorted(missing))}")
    if top_k < 1 or not 0 < holdout_fraction < 1:
        raise ValueError("top_k must be positive and holdout_fraction must be between 0 and 1")
    if not 0.0 <= behavior_weight <= 1.0:
        raise ValueError("behavior_weight must be between 0 and 1")

    df = pre_outage_df.copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    cutoff = pd.Timestamp(as_of, tz="UTC") if as_of else df["timestamp_utc"].max()
    if pd.isna(cutoff):
        raise ValueError("pre_outage_df has no timestamps")
    meta = metadata_df.drop_duplicates("turbine_id").set_index("turbine_id")
    if target_turbine not in meta.index:
        raise ValueError(f"metadata has no target turbine {target_turbine}")

    target_lat, target_lon = float(meta.loc[target_turbine, "latitude"]), float(
        meta.loc[target_turbine, "longitude"]
    )
    if not np.isfinite([target_lat, target_lon]).all():
        raise ValueError(f"metadata has non-finite coordinates for {target_turbine}")
    windows: list[dict[str, Any]] = []
    for days in sorted(set(int(day) for day in lookback_days)):
        if days <= 0:
            raise ValueError("lookback windows must be positive days")
        start = cutoff - pd.Timedelta(days=days)
        window_df = df[(df["timestamp_utc"] >= start) & (df["timestamp_utc"] < cutoff)]
        # Build the timestamp×turbine matrix once per lookback. The previous
        # row-filter implementation repeated full-frame scans for every
        # candidate, which became impractical on multi-year public archives.
        wind_matrix = window_df.pivot_table(
            index="timestamp_utc", columns="turbine_id", values="wind_speed_ms", aggfunc="mean"
        )
        candidates: list[dict[str, Any]] = []
        for turbine in candidate_turbines:
            if turbine == target_turbine or turbine not in meta.index:
                continue
            candidate_lat, candidate_lon = float(meta.loc[turbine, "latitude"]), float(
                meta.loc[turbine, "longitude"]
            )
            if not np.isfinite([candidate_lat, candidate_lon]).all():
                continue
            distance = haversine_km(
                target_lat,
                target_lon,
                candidate_lat,
                candidate_lon,
            )
            if max_distance_km is not None and distance > max_distance_km:
                continue
            if target_turbine not in wind_matrix.columns or turbine not in wind_matrix.columns:
                continue
            paired = wind_matrix[[target_turbine, turbine]].dropna().rename(
                columns={target_turbine: "target", turbine: "reference"}
            )
            if len(paired) < min_paired_observations:
                continue
            try:
                metrics = _validate_candidate(paired, holdout_fraction)
            except ValueError:
                continue
            candidates.append(
                {
                    "turbine_id": turbine,
                    "distance_km": distance,
                    "paired_observations": int(len(paired)),
                    **metrics,
                }
            )
        if candidates:
            windows.append(
                {
                    "lookback_days": days,
                    "window_start_utc": start.isoformat().replace("+00:00", "Z"),
                    "window_end_utc": cutoff.isoformat().replace("+00:00", "Z"),
                    "candidates": candidates,
                    "best_rmse_ms": min(item["rmse_ms"] for item in candidates),
                }
            )

    if not windows:
        return {
            "status": "abstain",
            "reason": "no reference met the minimum paired-observation and distance gates",
            "selected": None,
            "windows": [],
        }

    # Stable model choice: shortest window wins any near-tie (within 1% RMSE).
    best_rmse = min(window["best_rmse_ms"] for window in windows)
    eligible = [window for window in windows if window["best_rmse_ms"] <= best_rmse * 1.01]
    chosen_window = min(eligible, key=lambda window: window["lookback_days"])
    candidates = chosen_window["candidates"]
    min_distance, max_distance = min(c["distance_km"] for c in candidates), max(
        c["distance_km"] for c in candidates
    )
    min_rmse, max_rmse = min(c["rmse_ms"] for c in candidates), max(c["rmse_ms"] for c in candidates)
    for candidate in candidates:
        behavior = 1.0 if max_rmse == min_rmse else (max_rmse - candidate["rmse_ms"]) / (max_rmse - min_rmse)
        geography = 1.0 if max_distance == min_distance else (max_distance - candidate["distance_km"]) / (max_distance - min_distance)
        candidate["selection_score"] = behavior_weight * behavior + (1.0 - behavior_weight) * geography
    candidates.sort(key=lambda item: item["selection_score"], reverse=True)
    selected = candidates[0]
    ensemble = candidates[: min(top_k, len(candidates))]
    inverse_errors = np.array([1.0 / max(item["rmse_ms"], 1e-6) for item in ensemble])
    weights = inverse_errors / inverse_errors.sum()
    for item, weight in zip(ensemble, weights):
        item["ensemble_weight"] = float(weight)

    return {
        "status": "selected",
        "selected": selected["turbine_id"],
        "selected_window_days": chosen_window["lookback_days"],
        "ensemble": [{"turbine_id": item["turbine_id"], "weight": item["ensemble_weight"]} for item in ensemble],
        "ranking": candidates,
        "windows": windows,
    }
