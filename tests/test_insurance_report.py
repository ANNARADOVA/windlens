from __future__ import annotations

import unittest

from windlens.insurance_report import (
    build_report_data,
    load_assessment,
    load_commercial_profile,
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


if __name__ == "__main__":
    unittest.main()
