"""Coverage and contiguous-gap reporting for the canonical SCADA dataset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

CADENCE_MINUTES = 10


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _format_ts(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def expected_slot_count(start: str, end: str, cadence_minutes: int = CADENCE_MINUTES) -> int:
    """Number of start-inclusive, end-exclusive cadence-minute slots in [start, end)."""

    start_utc = _parse_ts(start)
    end_utc = _parse_ts(end)
    if start_utc >= end_utc:
        raise ValueError("start must be before end")
    total_minutes = (end_utc - start_utc).total_seconds() / 60
    return int(total_minutes // cadence_minutes)


def _contiguous_gaps(
    sorted_timestamps: list[datetime],
    window_start: datetime,
    window_end: datetime,
    cadence: timedelta,
) -> list[dict[str, Any]]:
    """Missing-slot runs within [window_start, window_end), including leading/trailing gaps."""

    gaps: list[dict[str, Any]] = []
    cursor = window_start

    for timestamp in sorted_timestamps:
        if timestamp > cursor:
            missing_slots = int((timestamp - cursor) / cadence)
            gaps.append(
                {
                    "gap_start_utc": _format_ts(cursor),
                    "gap_end_utc": _format_ts(timestamp),
                    "missing_slots": missing_slots,
                }
            )
        cursor = timestamp + cadence

    last_expected_slot_start = window_end - cadence
    if cursor <= last_expected_slot_start:
        missing_slots = int((window_end - cursor) / cadence)
        gaps.append(
            {
                "gap_start_utc": _format_ts(cursor),
                "gap_end_utc": _format_ts(window_end),
                "missing_slots": missing_slots,
            }
        )

    return gaps


def turbine_coverage(
    df: pd.DataFrame,
    turbine_id: str,
    start: str,
    end: str,
    cadence_minutes: int = CADENCE_MINUTES,
) -> dict[str, Any]:
    """Expected vs. actual 10-minute slots and contiguous gaps for one turbine."""

    cadence = timedelta(minutes=cadence_minutes)
    window_start = _parse_ts(start)
    window_end = _parse_ts(end)
    expected = expected_slot_count(start, end, cadence_minutes)

    rows = df[
        (df["turbine_id"] == turbine_id)
        & (df["timestamp_utc"] >= start)
        & (df["timestamp_utc"] < end)
    ]
    timestamps = sorted({_parse_ts(value) for value in rows["timestamp_utc"]})

    gaps = _contiguous_gaps(timestamps, window_start, window_end, cadence)

    return {
        "turbine_id": turbine_id,
        "expected_slots": expected,
        "actual_valid_slots": len(timestamps),
        "coverage_pct": (len(timestamps) / expected * 100) if expected else 0.0,
        "contiguous_gaps": gaps,
    }


def simultaneous_overlap(
    df: pd.DataFrame,
    target_turbine: str,
    reference_turbine: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    """Count of timestamps in [start, end) where both target and reference are valid."""

    window = (df["timestamp_utc"] >= start) & (df["timestamp_utc"] < end)
    target_ts = set(df[window & (df["turbine_id"] == target_turbine)]["timestamp_utc"])
    reference_ts = set(df[window & (df["turbine_id"] == reference_turbine)]["timestamp_utc"])

    return {
        "target_turbine": target_turbine,
        "reference_turbine": reference_turbine,
        "target_valid_slots": len(target_ts),
        "reference_valid_slots": len(reference_ts),
        "simultaneous_valid_slots": len(target_ts & reference_ts),
    }
