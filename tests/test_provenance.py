from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from windlens.provenance import build_manifest, render_manifest_markdown, write_manifest


def _sample_manifest(**overrides):
    base = dict(
        source_doi="https://doi.org/10.5281/zenodo.16807551",
        licence="CC BY 4.0",
        archive_path=Path("Kelmarsh_SCADA_2016_3082.zip"),
        expected_archive_md5="ca8efbb6dbcfae3516583937eb5b5402",
        observed_archive_md5="ca8efbb6dbcfae3516583937eb5b5402",
        window_start="2016-05-01T00:00:00Z",
        window_end="2016-07-30T00:00:00Z",
        implementation_version="prepare_dataset.v2-section8",
        output_path=Path("kelmarsh_2016_90d_canonical.csv"),
        output_md5="15abb74500b414bff35f21e313da6827",
        extraction_report={
            "kept_rows": 64406,
            "dropped_invalid_rows": 1,
            "dropped_implausible_rows": 2,
            "dropped_out_of_window_rows": 3,
            "dropped_out_of_cadence_rows": 4,
            "dropped_duplicate_rows": 0,
        },
        coverage_by_turbine=[
            {
                "turbine_id": "KWF1",
                "expected_slots": 12960,
                "actual_valid_slots": 10829,
                "coverage_pct": 83.5,
                "contiguous_gaps": [{"gap_start_utc": "x", "gap_end_utc": "y", "missing_slots": 3}],
            }
        ],
    )
    base.update(overrides)
    return base


class BuildManifestTests(unittest.TestCase):
    def test_flags_checksum_match(self) -> None:
        manifest = build_manifest(**_sample_manifest())
        self.assertTrue(manifest["archive_checksum_verified"])

    def test_flags_checksum_mismatch(self) -> None:
        manifest = build_manifest(**_sample_manifest(observed_archive_md5="deadbeef"))
        self.assertFalse(manifest["archive_checksum_verified"])


class RenderManifestMarkdownTests(unittest.TestCase):
    def test_includes_required_section_8_fields(self) -> None:
        manifest = build_manifest(**_sample_manifest())
        rendered = render_manifest_markdown(manifest)

        for required in [
            manifest["source_doi"],
            manifest["licence"],
            manifest["expected_archive_md5"],
            manifest["observed_archive_md5"],
            manifest["window_start_utc"],
            manifest["window_end_utc"],
            manifest["implementation_version"],
            manifest["output_md5"],
            "64,406",  # kept_rows, thousands-separated
            "KWF1",
        ]:
            self.assertIn(required, rendered)

    def test_flags_a_checksum_mismatch_visibly(self) -> None:
        manifest = build_manifest(**_sample_manifest(observed_archive_md5="deadbeef"))
        rendered = render_manifest_markdown(manifest)
        self.assertIn("MISMATCH", rendered)


class WriteManifestTests(unittest.TestCase):
    def test_writes_the_rendered_markdown_to_disk(self) -> None:
        manifest = build_manifest(**_sample_manifest())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "out.manifest.md"
            write_manifest(path, manifest)
            self.assertTrue(path.exists())
            self.assertIn(manifest["output_md5"], path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
