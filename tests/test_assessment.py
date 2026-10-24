from __future__ import annotations

import json
import unittest

from windlens.assessment import (
    ASSESSMENT_SCHEMA_VERSION,
    build_assessment_record,
    validate_assessment_record,
)
from windlens.review_gate import REVIEWABLE


def _event() -> dict:
    return {
        "block_start": "2016-07-07T00:00:00Z",
        "block_end": "2016-07-12T00:00:00Z",
        "baseline_reference": "KWF2",
        "ensemble_references": ["KWF2", "KWF4", "KWF3"],
        "baseline": {
            "loss": {
                "estimated_lost_kwh": 110402.0,
                "actual_lost_kwh": 117373.0,
                "absolute_error_kwh": 6971.0,
                "relative_error_pct": 5.9,
            },
            "wind_errors": {
                "compared_observations": 700,
                "mae_ms": 0.5,
                "rmse_ms": 0.7,
                "signed_bias_ms": -0.1,
            },
        },
        "ensemble": {
            "loss": {"estimated_lost_kwh": 106350.0, "actual_lost_kwh": 117373.0},
            "wind_errors": {"rmse_ms": 0.8},
        },
        "domain_checks": [
            {"reference": "KWF2", "within_domain": True},
            {"reference": "KWF4", "within_domain": True},
        ],
        "within_domain": True,
        "reference_target_aligned": True,
        "beats_baseline": True,
        "classification": {"label": REVIEWABLE, "failed_gates": []},
    }


class AssessmentContractTests(unittest.TestCase):
    def test_builds_json_serializable_evidence_record(self) -> None:
        record = build_assessment_record(
            event=_event(),
            target_turbine="KWF1",
            source={
                "doi": "10.5281/zenodo.16807551",
                "licence": "CC BY 4.0",
                "dataset_checksum_md5": "15abb74500b414bff35f21e313da6827",
                "method_version": "reconstruct.v1",
            },
        )

        self.assertEqual(record["schema_version"], ASSESSMENT_SCHEMA_VERSION)
        self.assertEqual(record["incident"]["asset_id"], "KWF1")
        self.assertEqual(record["estimate"]["lost_energy_kwh"], 110402.0)
        self.assertEqual(record["reference"]["selected_asset_id"], "KWF2")
        self.assertEqual(record["review"]["label"], REVIEWABLE)
        self.assertEqual(record["validation"]["hidden_truth_kwh"], 117373.0)
        json.dumps(record)

    def test_carries_calibrated_uncertainty_from_the_model_event(self) -> None:
        event = _event()
        event["baseline"]["uncertainty"] = {
            "status": "available",
            "calibration": {"coverage_target": 0.9},
            "event_evaluation": {"coverage_pct": 88.0, "mean_width_ms": 2.1},
        }
        record = build_assessment_record(
            event=event,
            target_turbine="KWF1",
            source={
                "doi": "10.5281/zenodo.16807551",
                "licence": "CC BY 4.0",
                "dataset_checksum_md5": "15abb74500b414bff35f21e313da6827",
                "method_version": "reconstruct.v1",
            },
        )
        self.assertEqual(record["estimate"]["uncertainty"]["status"], "available")

    def test_requires_provenance_fields(self) -> None:
        with self.assertRaises(ValueError):
            build_assessment_record(event=_event(), target_turbine="KWF1", source={"doi": "x"})

    def test_validation_rejects_missing_required_section(self) -> None:
        record = build_assessment_record(
            event=_event(),
            target_turbine="KWF1",
            source={
                "doi": "10.5281/zenodo.16807551",
                "licence": "CC BY 4.0",
                "dataset_checksum_md5": "15abb74500b414bff35f21e313da6827",
                "method_version": "reconstruct.v1",
            },
        )
        del record["reference"]
        with self.assertRaises(ValueError):
            validate_assessment_record(record)


if __name__ == "__main__":
    unittest.main()
