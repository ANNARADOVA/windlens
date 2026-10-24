from __future__ import annotations

import unittest

import pandas as pd

from windlens.upload_tool import (
    _targets_missing_in_window,
    describe_uploaded_files,
    detect_target_turbines,
    run_pipeline,
)


def _synthetic_wind_df(gap: bool) -> pd.DataFrame:
    """60 ten-minute rows for two turbines, TARGET and REF, with correlated but
    not identical wind speeds. If ``gap`` is True, rows 40-44 of TARGET are
    NaN (a real NaN gap, long enough for detect_target_turbines to find it);
    if False, TARGET has no NaN at all anywhere."""

    rows = []
    for i in range(60):
        # Match load_wind_data()'s own normalized format (Z suffix, not the
        # "+00:00" that bare Timestamp.isoformat() produces) -- a mismatch
        # here would make string comparisons against it silently wrong.
        ts = (pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=10 * i)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        v = 6 + (i % 7) * 0.3
        target_missing = gap and 40 <= i < 45
        rows.append((ts, "TARGET", None if target_missing else v))
        rows.append((ts, "REF", v * 0.9 + 0.2))
    return pd.DataFrame(rows, columns=["timestamp_utc", "turbine_id", "wind_speed_ms"])


class TargetsMissingInWindowTests(unittest.TestCase):
    def test_finds_turbine_with_no_reading_in_window_even_without_a_nan_run(self) -> None:
        # TARGET has no NaN anywhere -- detect_target_turbines() would find
        # nothing -- but a manual window naming a slice where TARGET has
        # readings should NOT flag it (it has data there); a window outside
        # its data range, or hand-picked to exclude it, should.
        df = _synthetic_wind_df(gap=False)
        # Window inside the data range where both turbines have readings:
        present = _targets_missing_in_window(df, "2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z")
        self.assertEqual(present, [])

        # Window entirely after the uploaded data ends: both turbines are
        # "missing" there.
        after_data = _targets_missing_in_window(df, "2026-01-02T00:00:00Z", "2026-01-02T01:00:00Z")
        self.assertEqual(after_data, ["REF", "TARGET"])

    def test_finds_turbine_with_a_real_nan_gap_too(self) -> None:
        df = _synthetic_wind_df(gap=True)
        missing = _targets_missing_in_window(df, "2026-01-01T06:40:00Z", "2026-01-01T07:30:00Z")
        self.assertEqual(missing, ["TARGET"])


class RunPipelineManualWindowRescueTests(unittest.TestCase):
    def test_manual_window_rescues_a_turbine_with_no_nan_gap(self) -> None:
        # The actual bug (2026-10-24, independent review finding #2/#6):
        # run_pipeline() used to call detect_target_turbines() unconditionally
        # and raise before ever reaching the manual_start/manual_end branch,
        # so a manual override could never identify a target turbine that has
        # no NaN gap. Confirm the NaN-gap-based path finds nothing here...
        df = _synthetic_wind_df(gap=False)
        self.assertEqual(detect_target_turbines(df), [])

        # ...but a manual window naming a slice after the uploaded data ends
        # (where TARGET genuinely has no reading) now runs successfully
        # instead of raising "No NaN wind-speed gap found... nothing to
        # reconstruct".
        result = run_pipeline(
            df,
            power_curve_df=None,
            manual_start="2026-01-02T00:00:00Z",
            manual_end="2026-01-02T01:00:00Z",
        )
        target_ids = {t["target_turbine"] for t in result["targets"]}
        self.assertIn("TARGET", target_ids)

    def test_manual_window_with_no_missing_turbine_raises_a_clear_error(self) -> None:
        df = _synthetic_wind_df(gap=False)
        with self.assertRaises(ValueError) as ctx:
            run_pipeline(
                df,
                power_curve_df=None,
                manual_start="2026-01-01T00:00:00Z",
                manual_end="2026-01-01T00:30:00Z",
            )
        self.assertIn("nothing to reconstruct", str(ctx.exception))

    def test_auto_detection_still_works_unchanged(self) -> None:
        df = _synthetic_wind_df(gap=True)
        result = run_pipeline(df, power_curve_df=None)
        target_ids = {t["target_turbine"] for t in result["targets"]}
        self.assertIn("TARGET", target_ids)
        target_entry = next(t for t in result["targets"] if t["target_turbine"] == "TARGET")
        self.assertTrue(target_entry["window_auto_detected"])


class RunPipelineCadenceTests(unittest.TestCase):
    def test_hourly_upload_integrates_at_hourly_cadence_not_hardcoded_ten_minutes(self) -> None:
        # 2026-10-24 independent review finding #5: run_pipeline() used to call
        # integrate_energy_kwh() with no interval_hours, which silently defaulted
        # to the research dataset's hardcoded 10-minute cadence regardless of the
        # uploaded file's real spacing -- an hourly upload would have produced a
        # 6x energy error. Build a flat (constant-power) power curve so the
        # expected kWh is exactly checkable, then confirm an hourly-cadence
        # upload's estimated_lost_kwh reflects hourly integration (6x what the
        # old hardcoded 10-minute assumption would have given).
        rows = []
        for i in range(30):
            ts = (pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=i)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            # 20 hours of paired pre-outage history (select_reference_turbine
            # requires >=10 paired observations), then a 4-hour outage. Wind
            # speed must vary (not be perfectly flat) or the fit is degenerate.
            v = 6.0 + (i % 5) * 0.3
            target_missing = 20 <= i < 24
            rows.append((ts, "TARGET", None if target_missing else v))
            rows.append((ts, "REF", v))
        wind_df = pd.DataFrame(rows, columns=["timestamp_utc", "turbine_id", "wind_speed_ms"])

        # A flat power curve: every wind speed maps to exactly 100 kW, so the
        # reconstructed wind speed's exact value doesn't matter for this check.
        power_curve_df = pd.DataFrame(
            {"bin_center_ms": [0.0, 50.0], "mean_power_kw": [100.0, 100.0]}
        )

        result = run_pipeline(wind_df, power_curve_df=power_curve_df)
        target_entry = next(t for t in result["targets"] if t["target_turbine"] == "TARGET")

        # 4 missing hourly readings at a flat 100 kW = 400 kWh at hourly cadence.
        # The old hardcoded-10-minute bug would have given 400 * (10/60) / 1 ... i.e.
        # treated each of the 4 rows as a 10-minute slice: 4 * 100 * (1/6) = 66.7 kWh.
        self.assertAlmostEqual(target_entry["estimated_lost_kwh"], 400.0, places=1)

        # 2026-10-24 independent review finding (Category 5): the inferred cadence
        # must be surfaced in the result, not silently discarded after use.
        self.assertAlmostEqual(target_entry["inferred_cadence_minutes"], 60.0, places=1)

    def test_result_includes_coverage_domain_check_and_raw_notice(self) -> None:
        # 2026-10-24 independent review finding (Category 8): the upload result must
        # carry the same evidence fields as the official record's gate -- reference
        # coverage of the outage window, a wind-speed domain check, and an explicit
        # "not validated against ground truth" notice -- not just the bare numbers.
        df = _synthetic_wind_df(gap=True)
        result = run_pipeline(df, power_curve_df=None)
        target_entry = next(t for t in result["targets"] if t["target_turbine"] == "TARGET")

        # REF has no gap at all, so it covers 100% of TARGET's 5-row outage window.
        self.assertAlmostEqual(target_entry["reference_coverage_pct"], 100.0, places=1)

        self.assertIsNotNone(target_entry["domain_check"])
        self.assertIn("within_domain", target_entry["domain_check"])
        self.assertIn("training_min_ms", target_entry["domain_check"])

        self.assertIn("not validated against ground truth", target_entry["raw_reconstruction_notice"])


class DescribeUploadedFilesTests(unittest.TestCase):
    def test_distinguishes_target_from_reference_from_power_curve(self) -> None:
        # 2026-10-24 independent review finding (Category 8, part 3): the upload
        # form's pre-run confirmation summary needs a per-file role guess so a
        # mis-assigned file (e.g. the power curve dropped in as wind data) is
        # caught before Run is clicked, not only from the result afterward.
        # A run of >=3 consecutive NaN rows (MIN_OUTAGE_RUN_LENGTH) -- matching
        # detect_target_turbines()'s own threshold, not just any single NaN, so
        # this test fixture reflects what a real outage-length gap looks like.
        target_csv = (
            b"timestamp_utc,turbine_id,wind_speed_ms\n"
            b"2026-01-01T00:00:00Z,TARGET,6.0\n"
            b"2026-01-01T00:10:00Z,TARGET,\n"
            b"2026-01-01T00:20:00Z,TARGET,\n"
            b"2026-01-01T00:30:00Z,TARGET,\n"
            b"2026-01-01T00:40:00Z,TARGET,6.1\n"
        )
        # A single isolated NaN (below MIN_OUTAGE_RUN_LENGTH) must NOT make this
        # preview as a target -- real reference-turbine files commonly have a
        # scattered dropout like this without being disqualified as a reference.
        reference_csv = (
            b"timestamp_utc,turbine_id,wind_speed_ms\n"
            b"2026-01-01T00:00:00Z,REF,6.0\n"
            b"2026-01-01T00:10:00Z,REF,\n"
            b"2026-01-01T00:20:00Z,REF,6.2\n"
        )
        power_curve_csv = b"wind_speed,power\n0,0\n10,100\n"

        described = describe_uploaded_files(
            wind_data_items=[(target_csv, "target.csv"), (reference_csv, "reference.csv")],
            power_curve_items=[(power_curve_csv, "curve.csv")],
        )

        by_filename = {d["filename"]: d for d in described}
        self.assertEqual(by_filename["target.csv"]["kind"], "wind_data")
        self.assertIn("target", by_filename["target.csv"]["role_guess"])
        self.assertEqual(by_filename["reference.csv"]["kind"], "wind_data")
        self.assertIn("reference", by_filename["reference.csv"]["role_guess"])
        self.assertEqual(by_filename["curve.csv"]["kind"], "power_curve")

    def test_reports_an_unreadable_file_without_raising(self) -> None:
        described = describe_uploaded_files(
            wind_data_items=[(b"not,a,valid,wind,file\n1,2,3,4,5\n", "garbage.csv")],
            power_curve_items=[],
        )
        self.assertEqual(len(described), 1)
        self.assertIn("error", described[0])


if __name__ == "__main__":
    unittest.main()
