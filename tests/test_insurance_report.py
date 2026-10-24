from __future__ import annotations

import unittest

from windlens.insurance_report import (
    build_report_data,
    build_report_data_for_live_target,
    generate,
    generate_for_live_target,
    load_assessment,
    load_commercial_profile,
    profile_from_price_override,
    render_email_draft,
    render_markdown_report,
)


class InsuranceReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assessment = load_assessment()
        self.profile = load_commercial_profile()

    def test_bracket_uses_worst_observed_error_across_all_targets(self) -> None:
        data = build_report_data(self.assessment, "T3", self.profile)
        errors = [item["relative_error_pct"] for item in data["bracket"]["per_target"]]
        self.assertEqual(data["bracket"]["worst_pct"], max(errors))
        self.assertEqual(data["bracket"]["n"], len(self.assessment["targets"]))

    def test_point_kwh_matches_hidden_window_prediction(self) -> None:
        data = build_report_data(self.assessment, "T2", self.profile)
        target = next(t for t in self.assessment["targets"] if t["target_turbine"] == "T2")
        self.assertEqual(data["point_kwh"], target["hidden_window_prediction"]["estimated_lost_kwh"])

    def test_financial_value_is_indicative_not_a_settlement(self) -> None:
        data = build_report_data(self.assessment, "T1", self.profile)
        self.assertIsNotNone(data["financial"])
        self.assertEqual(data["financial"]["point"]["claim_scope"], "indicative")

    def test_report_without_commercial_profile_omits_financial_section(self) -> None:
        # 2026-10-24: report rewritten as a one-page insurer-facing document
        # (Anna: "the document should be one pager... that a company like
        # BayWa would literally send to an insurance company") -- the no-price
        # case now reads as one plain line in "Estimated loss", not a
        # standalone paragraph explaining the internal data requirement.
        data = build_report_data(self.assessment, "T1", commercial_profile=None)
        report = render_markdown_report(data)
        self.assertIn("Financial impact: not calculated (no energy price supplied)", report)

    def test_report_states_uncertainty_was_not_calibrated(self) -> None:
        # 2026-10-24: reworded for the one-pager rewrite -- still asserts the
        # report is honest that this is not a calibrated statistical interval,
        # just without the old internal-audit-log section heading/phrasing.
        data = build_report_data(self.assessment, "T3", self.profile)
        report = render_markdown_report(data)
        self.assertIn("not a formal statistical confidence interval", report)

    def test_email_draft_references_the_point_estimate(self) -> None:
        data = build_report_data(self.assessment, "T3", self.profile)
        email = render_email_draft(data)
        self.assertIn("112,411 kWh", email)
        self.assertIn("Subject:", email)

    def test_unknown_target_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_report_data(self.assessment, "T99", self.profile)


class LiveUploadReportTests(unittest.TestCase):
    """2026-10-24 correctness fix: previously there was NO code path for
    building a report from a live /run upload result at all -- generate()
    only ever read the fixed official assessment file, so a report requested
    after an upload silently showed the official T3 record (or errored for
    any turbine id outside T1/T2/T3). These tests build directly from a
    target-entry dict shaped exactly like run_pipeline()'s own output."""

    def setUp(self) -> None:
        self.profile = load_commercial_profile()
        self.live_target = {
            "target_turbine": "T9",
            "selected_reference": "REFX",
            "reference_ranking": [{"turbine_id": "REFX", "holdout_r2": 0.512, "paired_observations": 144}],
            "outage_window_utc": ["2026-05-01T00:00:00Z", "2026-05-02T00:00:00Z"],
            "rows_predicted": 24,
            "estimated_lost_kwh": 4321.5,
        }

    def test_report_names_the_actual_uploaded_target_not_the_official_demo(self) -> None:
        data = build_report_data_for_live_target(self.live_target, self.profile)
        report = render_markdown_report(data)
        email = render_email_draft(data)
        self.assertIn("T9", report)
        self.assertIn("4,322 kWh", report)  # _fmt_kwh rounds 4321.5 -> 4,322
        self.assertIn("T9", email)
        # Must never silently show the official demo's turbine or figure.
        self.assertNotIn("T3", report)
        self.assertNotIn("112,411", report)
        self.assertNotIn("T3", email)

    def test_live_target_report_has_no_invented_calibrated_bracket(self) -> None:
        data = build_report_data_for_live_target(self.live_target, self.profile)
        report = render_markdown_report(data)
        # The official-record-only phrase must not appear -- a live run has no
        # shown-window self-validation to build a bracket from.
        self.assertNotIn("not a formal statistical confidence interval", report)
        self.assertIn("single, live reconstruction run", report)

    def test_live_target_without_power_curve_reports_energy_not_calculated(self) -> None:
        target = dict(self.live_target)
        del target["estimated_lost_kwh"]
        target["estimated_lost_kwh_unavailable_reason"] = "No power curve uploaded for T9 -- showing wind-speed reconstruction only."

        data = build_report_data_for_live_target(target, self.profile)
        report = render_markdown_report(data)
        email = render_email_draft(data)
        self.assertIn("Energy: not calculated", report)
        self.assertIn("No power curve uploaded for T9", report)
        self.assertIn("No power curve uploaded for T9", email)
        # No financial figure can be derived with no kWh number.
        self.assertIsNone(data["financial"])

    def test_live_target_report_works_with_no_commercial_profile(self) -> None:
        data = build_report_data_for_live_target(self.live_target, commercial_profile=None)
        report = render_markdown_report(data)
        self.assertIn("Financial impact: not calculated (no energy price supplied)", report)


class PriceOverrideTests(unittest.TestCase):
    """2026-10-24 correctness fix: the generated report used to always price at
    the fixed illustrative 85 EUR/MWh demo profile, even when the Analysis page
    itself was showing a real, sourced price (e.g. reBAP) for the exact same
    outage -- two different financial-impact figures on screen for one result.
    generate()/generate_for_live_target() must use an injected override price
    instead of silently re-loading the demo profile from disk."""

    def test_official_report_dollar_figure_matches_an_injected_override_price_not_the_demo_default(self) -> None:
        override = {"price_eur_per_mwh": 150.88, "source_label": "netztransparenz.de reBAP (test)", "is_real_price": True}
        result = generate("T3", price_override=override)
        # T3's real hidden-window kWh (112,411.16) at 150.88 EUR/MWh = EUR 16,961 -- and
        # NOT the demo default's EUR 9,555 (85 EUR/MWh).
        self.assertIn("EUR 16,961", result["report_markdown"])
        self.assertNotIn("EUR 9,555", result["report_markdown"])
        self.assertIn("151 EUR/MWh", result["report_markdown"])  # 150.88 rounded
        # The "illustrative... to be replaced" caveat must not appear for a real price.
        self.assertNotIn("illustrative", result["report_markdown"])
        self.assertIn("real netztransparenz.de reBAP (test) price", result["report_markdown"])

    def test_live_target_report_dollar_figure_matches_an_injected_override_price(self) -> None:
        target_entry = {
            "target_turbine": "T9",
            "selected_reference": "REFX",
            "reference_ranking": [{"turbine_id": "REFX", "holdout_r2": 0.5, "paired_observations": 100}],
            "outage_window_utc": ["2026-05-01T00:00:00Z", "2026-05-02T00:00:00Z"],
            "rows_predicted": 24,
            "estimated_lost_kwh": 10000.0,
        }
        override = {"price_eur_per_mwh": 200.0, "source_label": "Test source", "is_real_price": True}
        result = generate_for_live_target(target_entry, price_override=override)
        # 10,000 kWh / 1000 * 200 EUR/MWh = EUR 2,000.
        self.assertIn("EUR 2,000", result["report_markdown"])
        self.assertIn("real Test source price", result["report_markdown"])

    def test_profile_from_price_override_builds_a_valid_fixed_profile(self) -> None:
        profile = profile_from_price_override(123.45, "Some source", True)
        self.assertEqual(profile["fixed_price_eur_per_mwh"], 123.45)
        self.assertEqual(profile["price_basis"], "fixed")
        self.assertTrue(profile["is_real_price"])


if __name__ == "__main__":
    unittest.main()
