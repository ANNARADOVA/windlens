"""Decision-support labelling: "Estimate -- reviewable" vs. "Unverified -- manual
evidence required", per WindLens_instructions.md Section 9.
"""

from __future__ import annotations

from typing import Any

REVIEWABLE = "Estimate -- reviewable"
UNVERIFIED = "Unverified -- manual evidence required"


def classify_estimate(
    *,
    input_qa_passed: bool,
    reference_target_aligned: bool,
    within_validated_domain: bool,
    completeness_passed: bool,
    abstention_triggered: bool,
    uncertainty_gate_passed: bool = True,
) -> dict[str, Any]:
    """Label one event, naming every failed gate so an analyst knows why.

    A result is reviewable only if every gate passes. This function makes no
    judgement call of its own -- it only applies the five named gates.

    2026-10-22: the earlier fifth gate, ``beats_baseline``, compared the event's
    own wind RMSE against hidden truth -- a comparison that cannot be made in a
    real outage, where no truth exists (red-team review F1). It is replaced by
    ``completeness_passed``: whether the reconstruction covers enough of the
    event window to be trusted at all, computed purely from outage-time-available
    reference data (F2). Both inputs to this function must already be computed
    without hidden truth; this function itself never sees hidden truth.
    """

    failed_gates: list[str] = []
    if not input_qa_passed:
        failed_gates.append("input_qa")
    if not reference_target_aligned:
        failed_gates.append("reference_target_alignment")
    if not within_validated_domain:
        failed_gates.append("validated_domain")
    if not completeness_passed:
        failed_gates.append("completeness")
    if abstention_triggered:
        failed_gates.append("abstention")
    if not uncertainty_gate_passed:
        failed_gates.append("uncertainty")

    return {
        "label": UNVERIFIED if failed_gates else REVIEWABLE,
        "failed_gates": failed_gates,
    }
