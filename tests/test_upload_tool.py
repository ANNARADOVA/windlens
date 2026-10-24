from __future__ import annotations

import unittest

import pandas as pd

from windlens.upload_tool import (
    _targets_missing_in_window,
    describe_uploaded_files,
    detect_outage_instances,
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


class DetectOutageInstancesTests(unittest.TestCase):
    def test_one_turbine_with_two_separate_gaps_produces_two_independently_correct_instances(self) -> None:
        # 2026-10-24: Anna asked for ALL qualifying outages per turbine to be
        # auto-detected, not just the single longest one. Build a turbine with
        # two separate NaN runs far apart (hours 20-23 and 60-63 of an 80-hour
        # series) and confirm each becomes its own instance with its own
        # correctly-scoped window AND its own correctly-scoped reference
        # selection -- not contaminated by the other gap. REF has no gaps at
        # all, so it is the only candidate reference for either instance; its
        # paired_observations count for each instance proves the pre-window
        # history used was scoped to THAT instance's own window_start (56
        # valid rows before the second gap vs. 20 before the first), not
        # mixed up between the two.
        rows = []
        for i in range(80):
            ts = (pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            v = 6.0 + (i % 5) * 0.3
            first_gap = 20 <= i < 24
            second_gap = 60 <= i < 64
            rows.append((ts, "TARGET", None if (first_gap or second_gap) else v))
            rows.append((ts, "REF", v))
        wind_df = pd.DataFrame(rows, columns=["timestamp_utc", "turbine_id", "wind_speed_ms"])

        instances = detect_outage_instances(wind_df)
        target_instances = [i for i in instances if i["target_turbine"] == "TARGET"]
        self.assertEqual(len(target_instances), 2)
        self.assertEqual(target_instances[0]["window_start"], "2026-01-01T20:00:00Z")
        self.assertEqual(target_instances[0]["window_end"], "2026-01-02T00:00:00Z")
        self.assertEqual(target_instances[1]["window_start"], "2026-01-03T12:00:00Z")
        self.assertEqual(target_instances[1]["window_end"], "2026-01-03T16:00:00Z")

        result = run_pipeline(wind_df, power_curve_df=None)
        target_results = [t for t in result["targets"] if t["target_turbine"] == "TARGET"]
        self.assertEqual(len(target_results), 2)

        by_window_start = {t["outage_window_utc"][0]: t for t in target_results}
        first = by_window_start["2026-01-01T20:00:00Z"]
        second = by_window_start["2026-01-03T12:00:00Z"]

        # Each instance reconstructs exactly its own 4-row gap, from REF (the
        # only candidate), with no errors.
        self.assertEqual(first["selected_reference"], "REF")
        self.assertEqual(second["selected_reference"], "REF")
        self.assertEqual(first["rows_predicted"], 4)
        self.assertEqual(second["rows_predicted"], 4)

        # The key correctness check: each instance's reference-selection ranking
        # was fit on ITS OWN pre-window history, not a shared/contaminated one.
        first_ranking = next(r for r in first["reference_ranking"] if r["turbine_id"] == "REF")
        second_ranking = next(r for r in second["reference_ranking"] if r["turbine_id"] == "REF")
        self.assertEqual(first_ranking["paired_observations"], 20)
        self.assertEqual(second_ranking["paired_observations"], 56)

    def test_detect_target_turbines_still_returns_one_entry_per_turbine_not_per_instance(self) -> None:
        rows = []
        for i in range(80):
            ts = (pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            v = 6.0 + (i % 5) * 0.3
            missing = (20 <= i < 24) or (60 <= i < 64)
            rows.append((ts, "TARGET", None if missing else v))
            rows.append((ts, "REF", v))
        wind_df = pd.DataFrame(rows, columns=["timestamp_utc", "turbine_id", "wind_speed_ms"])
        self.assertEqual(detect_target_turbines(wind_df), ["TARGET"])


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

    def test_result_includes_overlay_series_spanning_before_during_and_after_the_gap(self) -> None:
        # 2026-10-24 (IA rebuild): the Result chart needs the target's own actual
        # readings (with its real gap) and the reference's actual readings
        # overlaid, across a window wider than just the outage itself, so the
        # gap and the reference's continuity through it are both visible.
        df = _synthetic_wind_df(gap=True)
        result = run_pipeline(df, power_curve_df=None)
        target_entry = next(t for t in result["targets"] if t["target_turbine"] == "TARGET")

        overlay = target_entry["overlay_series"]
        self.assertGreater(len(overlay), 5)
        in_outage_points = [p for p in overlay if p["in_outage"]]
        self.assertTrue(in_outage_points)
        self.assertTrue(all(p["target_ms"] is None for p in in_outage_points))
        self.assertTrue(any(p["reference_ms"] is not None for p in in_outage_points))
        outside_points = [p for p in overlay if not p["in_outage"]]
        self.assertTrue(any(p["target_ms"] is not None for p in outside_points))


class RunPipelineMultiTargetPowerCurveTests(unittest.TestCase):
    def _two_target_wind_df(self) -> pd.DataFrame:
        rows = []
        for i in range(30):
            ts = (pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            # 20 hours of paired pre-outage history (select_reference_turbine requires
            # >=10), then a 4-hour outage, matching on both targets so O1 is the only
            # candidate reference for either (each target excludes the other, which is
            # itself a detected target, from its own candidate pool).
            v = 6.0 + (i % 5) * 0.3
            missing = 20 <= i < 24
            rows.append((ts, "T1", None if missing else v))
            rows.append((ts, "T2", None if missing else v))
            rows.append((ts, "O1", v))
        return pd.DataFrame(rows, columns=["timestamp_utc", "turbine_id", "wind_speed_ms"])

    def test_each_target_gets_its_own_matched_power_curve_not_the_first_uploaded(self) -> None:
        # 2026-10-24 correctness fix: a whole-farm-down upload (several targets,
        # each shipped with its own power curve -- exactly how BayWa names them)
        # must match each target to ITS OWN curve by filename, never silently
        # apply whichever curve happened to be uploaded first to every target.
        wind_df = self._two_target_wind_df()
        power_curve_items = [
            (b"wind_speed,power\n0,100\n50,100\n", "T1_power_curve.csv"),
            (b"wind_speed,power\n0,300\n50,300\n", "T2_power_curve.csv"),
        ]

        result = run_pipeline(wind_df, power_curve_items=power_curve_items)
        by_target = {t["target_turbine"]: t for t in result["targets"]}
        self.assertIn("T1", by_target)
        self.assertIn("T2", by_target)

        # 4 missing hourly readings: T1's own curve (100 kW flat) = 400 kWh;
        # T2's own curve (300 kW flat) = 1200 kWh. If T2 had wrongly been given
        # T1's curve (the old bug), it would also read 400 kWh.
        self.assertAlmostEqual(by_target["T1"]["estimated_lost_kwh"], 400.0, places=1)
        self.assertAlmostEqual(by_target["T2"]["estimated_lost_kwh"], 1200.0, places=1)

    def test_a_target_with_no_matching_curve_gets_a_named_unavailable_reason_not_someone_elses_curve(self) -> None:
        wind_df = self._two_target_wind_df()
        # Only T1 ships a power curve in this upload; T2 does not.
        power_curve_items = [(b"wind_speed,power\n0,100\n50,100\n", "T1_power_curve.csv")]

        result = run_pipeline(wind_df, power_curve_items=power_curve_items)
        by_target = {t["target_turbine"]: t for t in result["targets"]}

        self.assertAlmostEqual(by_target["T1"]["estimated_lost_kwh"], 400.0, places=1)
        self.assertNotIn("estimated_lost_kwh", by_target["T2"])
        self.assertIn("T2", by_target["T2"]["estimated_lost_kwh_unavailable_reason"])
        self.assertIn("No power curve uploaded", by_target["T2"]["estimated_lost_kwh_unavailable_reason"])


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
