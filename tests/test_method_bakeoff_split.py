"""Tests for the method bake-off's locked dev/report split.

2026-10-23, red-team review F9/F13: the original parity split put two
overlapping Kelmarsh block pairs on opposite sides of a split documented as
"locked, disjoint" -- ~720 hidden-truth rows were scored on both sides. No
test caught this (F13: "no test that back-test blocks don't overlap or that
the dev/report split is disjoint"). These tests exercise the actual fix
(windlens.run_method_bakeoff_2026_10_23._assert_disjoint_calendar_ranges)
with assertions that can fail on a real overlap, not just list membership.
"""

from __future__ import annotations

import unittest

from windlens.run_method_bakeoff_2026_10_23 import (
    HILL_DEV,
    HILL_REPORT,
    KELMARSH_DEV,
    KELMARSH_REPORT,
    _assert_disjoint_calendar_ranges,
)


class MethodBakeoffSplitTests(unittest.TestCase):
    def test_kelmarsh_dev_and_report_share_no_calendar_days(self) -> None:
        # Would have raised at import time already if this failed; re-asserting
        # directly here makes the property a named, standalone test rather than
        # an import-time side effect nobody is explicitly testing for.
        _assert_disjoint_calendar_ranges(KELMARSH_DEV, KELMARSH_REPORT)

    def test_hill_of_towie_dev_and_report_share_no_calendar_days(self) -> None:
        _assert_disjoint_calendar_ranges(HILL_DEV, HILL_REPORT)

    def test_disjointness_check_actually_catches_a_real_overlap(self) -> None:
        # A tautological version of this check (e.g. asserting on list identity)
        # could not have caught the original F9 defect. Prove the check used
        # here can fail on a genuine overlap.
        dev = [("2016-05-17T00:00:00Z", "2016-05-22T00:00:00Z")]
        report = [("2016-05-20T00:00:00Z", "2016-05-25T00:00:00Z")]
        with self.assertRaises(AssertionError):
            _assert_disjoint_calendar_ranges(dev, report)

    def test_previously_overlapping_blocks_are_excluded_from_kelmarsh_report(self) -> None:
        formerly_overlapping = {
            ("2016-05-20T00:00:00Z", "2016-05-25T00:00:00Z"),
            ("2016-05-29T00:00:00Z", "2016-06-03T00:00:00Z"),
        }
        self.assertTrue(formerly_overlapping.isdisjoint(set(KELMARSH_REPORT)))
        self.assertEqual(len(KELMARSH_DEV), 10)
        self.assertEqual(len(KELMARSH_REPORT), 7)


if __name__ == "__main__":
    unittest.main()
