from __future__ import annotations

import unittest

from windlens.review_gate import REVIEWABLE, UNVERIFIED, classify_estimate


def _passing_kwargs(**overrides):
    base = dict(
        input_qa_passed=True,
        reference_target_aligned=True,
        within_validated_domain=True,
        completeness_passed=True,
        abstention_triggered=False,
    )
    base.update(overrides)
    return base


class ClassifyEstimateTests(unittest.TestCase):
    def test_reviewable_when_every_gate_passes(self) -> None:
        result = classify_estimate(**_passing_kwargs())
        self.assertEqual(result["label"], REVIEWABLE)
        self.assertEqual(result["failed_gates"], [])

    def test_unverified_when_input_qa_fails(self) -> None:
        result = classify_estimate(**_passing_kwargs(input_qa_passed=False))
        self.assertEqual(result["label"], UNVERIFIED)
        self.assertEqual(result["failed_gates"], ["input_qa"])

    def test_unverified_when_reference_target_not_aligned(self) -> None:
        result = classify_estimate(**_passing_kwargs(reference_target_aligned=False))
        self.assertEqual(result["failed_gates"], ["reference_target_alignment"])

    def test_unverified_when_outside_validated_domain(self) -> None:
        result = classify_estimate(**_passing_kwargs(within_validated_domain=False))
        self.assertEqual(result["failed_gates"], ["validated_domain"])

    def test_unverified_when_reconstruction_is_incomplete(self) -> None:
        # 2026-10-22 red-team review (F2): replaces the old hidden-truth-based
        # beats_baseline gate with the completeness gate.
        result = classify_estimate(**_passing_kwargs(completeness_passed=False))
        self.assertEqual(result["failed_gates"], ["completeness"])

    def test_unverified_when_abstention_is_triggered(self) -> None:
        result = classify_estimate(**_passing_kwargs(abstention_triggered=True))
        self.assertEqual(result["failed_gates"], ["abstention"])

    def test_unverified_when_uncertainty_gate_fails(self) -> None:
        result = classify_estimate(**_passing_kwargs(uncertainty_gate_passed=False))
        self.assertEqual(result["failed_gates"], ["uncertainty"])

    def test_lists_every_failed_gate_together(self) -> None:
        result = classify_estimate(
            **_passing_kwargs(input_qa_passed=False, completeness_passed=False)
        )
        self.assertEqual(result["label"], UNVERIFIED)
        self.assertEqual(result["failed_gates"], ["input_qa", "completeness"])


if __name__ == "__main__":
    unittest.main()
