"""Insurance-facing outage-loss report generator.

Turns one target turbine's entry in ``data/derived/baywa_assessment_result.json``
into a short markdown report plus a ready-to-send email draft, suitable for
attaching to a claim submitted to an insurer (the hackathon spec's bonus
"insurance report email" deliverable).

Every number in the generated report is read from the real assessment result
and the real (demo) commercial pricing profile -- nothing here is invented or
round-tripped. In particular, the "error bracket" placed around the hidden-
window kWh estimate is NOT a calibrated statistical confidence interval: no
uncertainty calibration has been run on this BayWa dataset (see
``docs/HANDOVER.md``'s 2026-10-23 entry). It is the plain observed spread of
shown-window relative energy errors across however many targets were
validated in the same assessment run (currently n=3: T1, T2, T3), reported as
such, worst-case first, so an insurer is not given false confidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from windlens.uncertainty_business import calculate_indicative_value, validate_commercial_profile

DEFAULT_ASSESSMENT_PATH = Path("data/derived/baywa_assessment_result.json")
DEFAULT_COMMERCIAL_PROFILE_PATH = Path("data/derived/commercial_profiles/demo_ppa_profile.json")


def load_assessment(path: Path = DEFAULT_ASSESSMENT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_commercial_profile(path: Path = DEFAULT_COMMERCIAL_PROFILE_PATH) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_commercial_profile(profile)
    return profile


def _find_target(assessment: dict[str, Any], target_turbine: str) -> dict[str, Any]:
    for target in assessment["targets"]:
        if target["target_turbine"] == target_turbine:
            return target
    available = ", ".join(t["target_turbine"] for t in assessment["targets"])
    raise ValueError(f"target turbine {target_turbine!r} not found in assessment (have: {available})")


def _observed_error_bracket_pct(assessment: dict[str, Any]) -> dict[str, Any]:
    """The honest n=N observed-error bracket: the spread of shown-window relative
    energy errors across every target validated in this same assessment run.
    Not a calibrated statistical interval -- see module docstring.
    """

    per_target = [
        {
            "target_turbine": t["target_turbine"],
            "relative_error_pct": t["shown_window_self_validation"][
                "energy_loss_vs_curve_derived_proxy_truth"
            ]["relative_error_pct"],
        }
        for t in assessment["targets"]
    ]
    worst = max(item["relative_error_pct"] for item in per_target)
    return {"n": len(per_target), "per_target": per_target, "worst_pct": worst}


def build_report_data(
    assessment: dict[str, Any],
    target_turbine: str,
    commercial_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble every fact the report/email needs, with no formatting."""

    target = _find_target(assessment, target_turbine)
    bracket = _observed_error_bracket_pct(assessment)
    hidden = target["hidden_window_prediction"]
    shown = target["shown_window_self_validation"]

    point_kwh = float(hidden["estimated_lost_kwh"])
    half_width_pct = bracket["worst_pct"]
    lower_kwh = max(0.0, point_kwh * (1.0 - half_width_pct / 100.0))
    upper_kwh = point_kwh * (1.0 + half_width_pct / 100.0)

    financial = None
    if commercial_profile is not None:
        financial = {
            "point": calculate_indicative_value(point_kwh, commercial_profile),
            "lower": calculate_indicative_value(lower_kwh, commercial_profile),
            "upper": calculate_indicative_value(upper_kwh, commercial_profile),
            "profile": commercial_profile,
        }

    reference_holdout_r2 = next(
        (
            ranked["holdout_r2"]
            for ranked in target["reference_ranking"]
            if ranked["turbine_id"] == target["selected_reference"]
        ),
        None,
    )
    reference_paired_observations = next(
        (
            ranked["paired_observations"]
            for ranked in target["reference_ranking"]
            if ranked["turbine_id"] == target["selected_reference"]
        ),
        None,
    )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": assessment.get("dataset"),
        "implementation_version": assessment.get("implementation_version"),
        "target_turbine": target_turbine,
        "method": target["method"],
        "selected_reference": target["selected_reference"],
        "reference_holdout_r2": reference_holdout_r2,
        "reference_paired_observations": reference_paired_observations,
        "shown_window_utc": target["shown_window_utc"],
        "hidden_window_utc": target["hidden_window_utc"],
        "hidden_rows_predicted": hidden["rows_predicted"],
        "point_kwh": point_kwh,
        "lower_kwh": lower_kwh,
        "upper_kwh": upper_kwh,
        "bracket": bracket,
        "shown_window_relative_error_pct": shown["energy_loss_vs_curve_derived_proxy_truth"][
            "relative_error_pct"
        ],
        "shown_window_compared_observations": shown["compared_observations"],
        "financial": financial,
    }


def _fmt_kwh(value: float) -> str:
    return f"{value:,.0f} kWh"


def _fmt_eur(value: float) -> str:
    return f"EUR {value:,.0f}"


def render_markdown_report(data: dict[str, Any]) -> str:
    """A one-page, insurer-facing loss assessment -- the kind of document an
    operator would actually send to a claims reviewer, not an internal audit
    log. No generation timestamps, pipeline/version strings, or dataset
    filenames; those belong in the evidence workspace, not a document going
    to an external reader."""

    target = data["target_turbine"]
    hidden_start, hidden_end = data["hidden_window_utc"]
    bracket = data["bracket"]
    financial = data["financial"]
    assessment_date = data["generated_at_utc"][:10]

    lines = [
        f"# WindLens -- Outage Loss Assessment: Turbine {target}",
        "",
        f"Assessment date: {assessment_date}",
        "",
        "## Summary",
        "",
        f"Turbine {target} was offline from {hidden_start[:10]} to {hidden_end[:10]}. "
        f"Based on wind conditions recorded by a behaviorally selected reference "
        f"turbine ({data['selected_reference']}; geographic proximity not verified) "
        f"during the same period, we estimate the "
        f"turbine would have produced {_fmt_kwh(data['point_kwh'])} had it continued "
        "operating normally.",
        "",
        "## Estimated loss",
        "",
        f"- Energy: {_fmt_kwh(data['point_kwh'])} (estimated range: "
        f"{_fmt_kwh(data['lower_kwh'])} to {_fmt_kwh(data['upper_kwh'])})",
    ]

    if financial is None:
        lines.append("- Financial impact: not calculated (no energy price supplied).")
    else:
        point_eur = financial["point"]["value"]
        lower_eur = financial["lower"]["value"]
        upper_eur = financial["upper"]["value"]
        profile = financial["profile"]
        lines.append(
            f"- Financial impact: {_fmt_eur(point_eur)} (estimated range: "
            f"{_fmt_eur(lower_eur)} to {_fmt_eur(upper_eur)}), based on an illustrative "
            f"energy price of {profile['fixed_price_eur_per_mwh']:.0f} {profile['currency']}/MWh "
            "-- to be replaced with the operator's actual contracted price."
        )

    lines += [
        "",
        "## Method",
        "",
        "We reconstruct the wind this turbine would have experienced using readings "
        f"from a behaviorally selected reference turbine ({data['selected_reference']}; "
        "geographic proximity not verified) whose historical wind closely tracked "
        "this turbine's before the outage, then convert that wind into expected "
        "power using the turbine's own power curve. The reference turbine is chosen "
        "only from data available before the outage, never from the outage window "
        "itself.",
        "",
        "## Confidence",
        "",
        "This estimate's range reflects the largest error observed when validating "
        f"this method against the other real targets in this dataset with comparable "
        f"outages ({bracket['n']} targets, up to {bracket['worst_pct']:.1f}%); it is not "
        "a formal statistical confidence interval.",
        "",
        "This is a decision-support estimate, not an independent power measurement "
        "or a settlement, contractual, regulatory, or legal determination.",
    ]
    return "\n".join(lines)


def render_email_draft(data: dict[str, Any]) -> str:
    target = data["target_turbine"]
    hidden_start, hidden_end = data["hidden_window_utc"]
    financial = data["financial"]
    subject = f"Outage loss estimate -- Turbine {target}, {hidden_start[:10]} to {hidden_end[:10]}"

    body_lines = [
        f"Subject: {subject}",
        "",
        "Hello,",
        "",
        f"Please find attached the WindLens outage loss assessment for turbine "
        f"{target}, covering the data gap from {hidden_start} to {hidden_end}.",
        "",
        f"Estimated lost production: {_fmt_kwh(data['point_kwh'])} "
        f"({_fmt_kwh(data['lower_kwh'])} to {_fmt_kwh(data['upper_kwh'])} as an "
        "observed-error range rather than a calibrated confidence interval -- see the "
        "attached report for how this range was built).",
    ]
    if financial is not None:
        body_lines.append(
            f"Illustrative financial impact: {_fmt_eur(financial['point']['value'])} "
            "at a demo energy price -- not a verified PPA figure; please substitute "
            "your own confirmed price before relying on this number."
        )
    body_lines += [
        "",
        "The attached one-page assessment sets out the method and the basis for "
        "the estimated range. Happy to walk through any part of it on a call.",
        "",
        "Best regards,",
    ]
    return "\n".join(body_lines)


def generate(
    target_turbine: str,
    *,
    assessment_path: Path = DEFAULT_ASSESSMENT_PATH,
    commercial_profile_path: Path | None = DEFAULT_COMMERCIAL_PROFILE_PATH,
) -> dict[str, str]:
    """Return {"report_markdown": ..., "email_draft": ...} for one target turbine."""

    assessment = load_assessment(assessment_path)
    commercial_profile = (
        load_commercial_profile(commercial_profile_path) if commercial_profile_path is not None else None
    )
    data = build_report_data(assessment, target_turbine, commercial_profile)
    return {
        "report_markdown": render_markdown_report(data),
        "email_draft": render_email_draft(data),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Target turbine id, e.g. T1, T2, T3")
    parser.add_argument("--assessment-path", type=Path, default=DEFAULT_ASSESSMENT_PATH)
    parser.add_argument(
        "--commercial-profile-path",
        type=str,
        default=str(DEFAULT_COMMERCIAL_PROFILE_PATH),
        help="Pass an empty string to omit the financial section",
    )
    parser.add_argument("--out-report", type=Path, default=None, help="Write the markdown report here")
    parser.add_argument("--out-email", type=Path, default=None, help="Write the email draft here")
    args = parser.parse_args()

    profile_path = None if args.commercial_profile_path == "" else Path(args.commercial_profile_path)
    result = generate(
        args.target,
        assessment_path=args.assessment_path,
        commercial_profile_path=profile_path,
    )

    if args.out_report:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(result["report_markdown"], encoding="utf-8")
        print("Wrote report to", args.out_report)
    else:
        print(result["report_markdown"])

    if args.out_email:
        args.out_email.parent.mkdir(parents=True, exist_ok=True)
        args.out_email.write_text(result["email_draft"], encoding="utf-8")
        print("Wrote email draft to", args.out_email)
    else:
        print("\n---\n")
        print(result["email_draft"])


if __name__ == "__main__":
    main()
