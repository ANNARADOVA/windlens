from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class WorkspaceRegistryEvidenceTests(unittest.TestCase):
    def test_workspace_no_longer_has_a_standalone_registry_evidence_panel(self) -> None:
        # 2026-10-24: Anna asked for the standalone "Farm metadata evidence"
        # panel to be removed -- its one fact (no farm-location registry exists
        # for this dataset, so reference selection is purely behavioral) was
        # already stated in the T1/T2/T3 intro paragraph right above it in the
        # same disclosure, making the panel pure duplication. Removed the panel,
        # its render function (renderRegistryEvidence), and its call site;
        # the underlying registry_evidence data block itself is untouched (see
        # test_generated_workspace_bundle_contains_registry_provenance below).
        html = (ROOT / "workspace/index.html").read_text(encoding="utf-8")
        app = (ROOT / "workspace/app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="registry-evidence"', html)
        self.assertNotIn('renderRegistryEvidence', app)
        self.assertIn(
            "no farm-location registry for this dataset",
            html,
            "the one fact the removed panel conveyed must still be stated somewhere on the page",
        )

    def test_generated_workspace_bundle_contains_registry_provenance(self) -> None:
        # 2026-10-23: the Overview record is now the real BayWa r.e. submission
        # (T3), which ships no lat/lon or farm registry at all -- unlike the
        # retired Kelmarsh<->Penmanshiel record this test used to check,
        # usable_for_geo_selection is honestly false here, with a status_note
        # explaining why (no registry exists, not an abstention).
        bundle = (ROOT / "workspace/assessment-data.js").read_text(encoding="utf-8")
        self.assertIn('"registry_evidence"', bundle)
        self.assertIn('"usable_for_geo_selection":false', bundle)
        self.assertIn('"status_note":', bundle)


if __name__ == "__main__":
    unittest.main()
