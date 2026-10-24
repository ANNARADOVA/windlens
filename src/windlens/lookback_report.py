"""Rolling-origin report for validating dynamic lookback selection."""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from windlens.dynamic_reference import select_dynamic_references


def evaluate_lookback_windows(
    canonical_df: pd.DataFrame,
    target_turbine: str,
    candidate_turbines: list[str],
    metadata_df: pd.DataFrame,
    origins: Iterable[str],
    *,
    lookback_days: Iterable[int] = (30, 90, 180),
    min_paired_observations: int = 20,
    top_k: int = 3,
) -> dict[str, Any]:
    """Evaluate selection at multiple historical origins without future leakage.

    Each origin sees only rows strictly before that timestamp. The returned report
    preserves each selector result so analysts can inspect why a window or
    reference was selected rather than trusting only aggregate counts.
    """

    frame = canonical_df.copy()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    rows: list[dict[str, Any]] = []
    for origin in origins:
        cutoff = pd.Timestamp(origin, tz="UTC")
        historical = frame[frame["timestamp_utc"] < cutoff]
        selection = select_dynamic_references(
            historical,
            target_turbine,
            candidate_turbines,
            metadata_df,
            lookback_days=lookback_days,
            as_of=origin,
            min_paired_observations=min_paired_observations,
            top_k=top_k,
        )
        row: dict[str, Any] = {
            "origin_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "status": selection["status"],
            "selected_reference": selection.get("selected"),
            "selected_window_days": selection.get("selected_window_days"),
            "candidate_count": len(selection.get("ranking", [])),
            "windows_evaluated": [window["lookback_days"] for window in selection.get("windows", [])],
            "selection": selection,
        }
        rows.append(row)

    selected_rows = [row for row in rows if row["status"] == "selected"]
    window_counts: dict[str, int] = {}
    reference_counts: dict[str, int] = {}
    for row in selected_rows:
        window_key = str(row["selected_window_days"])
        window_counts[window_key] = window_counts.get(window_key, 0) + 1
        reference = row["selected_reference"]
        reference_counts[reference] = reference_counts.get(reference, 0) + 1
    return {
        "event_count": len(rows),
        "selected_count": len(selected_rows),
        "abstention_rate_pct": (len(rows) - len(selected_rows)) / len(rows) * 100 if rows else 0.0,
        "selected_window_counts": window_counts,
        "selected_reference_counts": reference_counts,
        "events": rows,
    }
