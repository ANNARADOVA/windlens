"""A stable, JSON-serializable evidence contract for one WindLens assessment."""

from __future__ import annotations

from typing import Any

ASSESSMENT_SCHEMA_VERSION = "windlens.assessment.v1"
_REQUIRED_SECTIONS = (
    "schema_version",
    "assessment_type",
    "incident",
    "estimate",
    "reference",
    "validation",
    "data_quality",
    "review",
    "provenance",
    "method",
    "next_action",
    "limitations",
)
_REQUIRED_PROVENANCE = ("doi", "licence", "dataset_checksum_md5", "method_version")


def build_assessment_record(
    *,
    event: dict[str, Any],
    target_turbine: str,
    source: dict[str, Any],
    model_key: str = "baseline",
    data_quality: dict[str, Any] | None = None,
    uncertainty: dict[str, Any] | None = None,
    kwh_interval: dict[str, Any] | None = None,
    next_action: str | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Translate a back-test event into the product's evidence-facing contract.

    The estimate intentionally exposes only the model estimate. Hidden truth remains
    under validation because it is available for a simulated back-test, not a real
    outage assessment.
    """

    if model_key not in {"baseline", "ensemble"}:
        raise ValueError("model_key must be baseline or ensemble")
    model = event[model_key]
    loss = model["loss"]
    wind = model["wind_errors"]
    uncertainty_record = uncertainty if uncertainty is not None else model.get("uncertainty")
    record: dict[str, Any] = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "assessment_type": "simulated_outage_backtest",
        "model": {"key": model_key},
        "incident": {
            "asset_id": target_turbine,
            "window_start_utc": event["block_start"],
            "window_end_utc": event["block_end"],
        },
        "estimate": {
            "lost_energy_kwh": float(loss["estimated_lost_kwh"]),
            "wind_mae_ms": float(wind["mae_ms"]),
            "wind_rmse_ms": float(wind["rmse_ms"]),
            "wind_signed_bias_ms": float(wind["signed_bias_ms"]),
            "uncertainty": uncertainty_record,
            # 2026-10-22 red-team review (F5): the only interval shown anywhere in the
            # demo was wind-speed, never kWh. This is the event-level kWh band -- see
            # uncertainty_business.event_level_kwh_interval for why it replaces
            # propagate_power_interval as the hero-number uncertainty source.
            "kwh_interval": kwh_interval,
        },
        "reference": {
            "selected_asset_id": event["baseline_reference"],
            "candidate_asset_ids": list(event.get("ensemble_references", [])),
            "weights": dict(event.get("reference_weights", {})),
            "selection": event.get("dynamic_selection"),
            "target_aligned": bool(event["reference_target_aligned"]),
            "within_validated_domain": bool(event["within_domain"]),
            "domain_checks": event.get("domain_checks", []),
        },
        "validation": {
            "hidden_truth_kwh": float(loss["actual_lost_kwh"]),
            "absolute_error_kwh": float(loss["absolute_error_kwh"]),
            "relative_error_pct": float(loss["relative_error_pct"]),
            "compared_observations": int(wind["compared_observations"]),
            "beats_baseline": bool(event["beats_baseline"]),
            "baseline_reference": event["baseline_reference"],
            "completeness_pct": float(event["completeness"]["completeness_pct"]) if event.get("completeness") else None,
        },
        "data_quality": {
            # 2026-10-22 red-team review (F1): was hard-coded True. Now reflects the
            # real per-event check (backtest.input_qa_check) via the gate outcome.
            "input_qa_passed": "input_qa" not in event["classification"].get("failed_gates", []),
            **(data_quality or {}),
        },
        "review": {
            "label": event["classification"]["label"],
            "failed_gates": list(event["classification"].get("failed_gates", [])),
        },
        "provenance": dict(source),
        "method": {
            "reconstruction": (
                "time-ordered linear measure-correlate-predict"
                if model_key == "baseline"
                else "performance-weighted peer ensemble of time-ordered linear reconstructions"
            ),
            "power_curve": "empirical target pre-outage power curve",
            "energy_integration": "10-minute power samples summed to kWh",
            "configuration": (
                "single best reference selected on pre-outage holdout"
                if model_key == "baseline"
                else "top peer references selected on pre-outage holdout"
            ),
        },
        "next_action": next_action
        or (
            "Proceed to analyst review"
            if not event["classification"].get("failed_gates")
            else "Review failed quality gates and reference suitability"
        ),
        "limitations": limitations
        or [
            "Kelmarsh reference assets are same-farm peer proxies, not a separate neighbouring farm.",
            "This record is a simulated outage back-test; a data gap alone does not prove an outage.",
            "The kWh interval is an event-level band from this method's own back-test error "
            "history, not a per-point statistical guarantee; with ~19-28 back-test events per "
            "farm its own width is itself uncertain (see kwh_interval.half_width_sampling_ci_pct).",
            "WindLens estimates the counterfactual production during an outage; it does not "
            "determine or classify the cause (mechanical failure vs. grid curtailment vs. "
            "other) -- that must come from an external source.",
        ],
    }
    validate_assessment_record(record)
    return record


def validate_assessment_record(record: dict[str, Any]) -> None:
    """Raise ValueError when a record cannot be safely rendered as evidence."""

    missing = [section for section in _REQUIRED_SECTIONS if section not in record]
    if missing:
        raise ValueError(f"Assessment record missing required sections: {', '.join(missing)}")
    if record["schema_version"] != ASSESSMENT_SCHEMA_VERSION:
        raise ValueError("Unsupported assessment schema version")
    for field in _REQUIRED_PROVENANCE:
        if not record["provenance"].get(field):
            raise ValueError(f"Assessment provenance missing required field: {field}")
    incident = record["incident"]
    for field in ("asset_id", "window_start_utc", "window_end_utc"):
        if not incident.get(field):
            raise ValueError(f"Assessment incident missing required field: {field}")
    if record["estimate"].get("lost_energy_kwh") is None:
        raise ValueError("Assessment estimate must include lost_energy_kwh")
    uncertainty = record["estimate"].get("uncertainty")
    if uncertainty is not None and uncertainty.get("status") not in {"available", "unavailable"}:
        raise ValueError("Assessment uncertainty must declare available or unavailable status")
    if not isinstance(record["limitations"], list) or not record["limitations"]:
        raise ValueError("Assessment limitations must be a non-empty list")
