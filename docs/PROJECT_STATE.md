# WindLens project state — current snapshot

**Last updated:** 2026-10-24.
**This is a concise current-state snapshot, not the project history.** For
the full chronological record (including everything superseded below), see
`docs/DECISION_LOG.md`. For the current product specification, see
`docs/PRODUCT_BRIEF.md` — that file, not this one, is the detailed current
spec; this file is a quick status check.

## Current product status

WindLens reconstructs a wind turbine's lost energy production during an
outage, using the real BayWa r.e. "Energy & AI" hackathon dataset. The
graded submission is a hidden-window prediction for target turbine T3
(112,411 kWh, 2026-09-01 to 2026-09-04), reconstructed from reference
turbine O1, with a separate self-validation on a different, known window
(T3 5.19%, T1 39.36% — an investigated outlier, T2 2.73% energy error).

## Current active dataset

The real BayWa challenge dataset. Targets: T1, T2, T3. Reference candidates:
O1, O2, H1–H5. See `docs/DATA_PROVENANCE.md` for full provenance and
`docs/PRODUCT_BRIEF.md` for the product-level summary. Kelmarsh, Hill of
Towie, Penmanshiel, and EDP Portugal are historical/research datasets only —
see `docs/DATA_PROVENANCE.md`'s "Historical/research datasets" section.

## Current UI

Two pages served by `windlens.baywa_tool_server`: the analysis/result page
(upload, live result, outage-overlay chart) and the methodology page
(validation detail, editable price, report actions). Exact routes and labels
are defined in `workspace/index.html`/`workspace/app.js` — that code is
authoritative over this file if they ever diverge.

## Current verified test count

199 tests, 199 pass, as of this writing (`PYTHONPATH=src python3 -m
unittest discover -s tests -q`). This number moves as work continues — treat
the live test-run output as authoritative over this paragraph.

## Current known limitations

See `docs/PRODUCT_BRIEF.md`'s "Current limitations and non-claims" section —
not duplicated here to avoid the two going out of sync.

## Current next steps

See whatever dispatch/task is currently in flight for this session — this
file does not track a live task list. For the product's own longer-term
"future opportunities" (not current-sprint next steps), see
`docs/PRODUCT_BRIEF.md` and the README's "Future opportunities" section.

---

## Historical record (superseded — kept for context, not current)

Everything below this line describes an earlier state of the project
(Kelmarsh-first, before the real BayWa data arrived, with a different UI
route structure and test-count history). It is kept as a historical record,
not current guidance — see `docs/DECISION_LOG.md` for the full chronological
detail these paragraphs summarize.

## Product intent

WindLens is an evidence-first decision-support tool for reconstructing energy
that may have been lost during a wind-turbine telemetry outage:

1. identify an outage or missing interval;
2. select a trustworthy peer reference using geography and observed behaviour;
3. reconstruct target wind speed;
4. translate reconstructed wind into expected generation and lost kWh;
5. show uncertainty, data quality, provenance, and an explicit review decision;
6. optionally calculate an **indicative** commercial value from manually supplied
   contract assumptions.

It does not currently claim contractual settlement, Redispatch eligibility,
OEM/legal liability, or bankable accuracy.

## Design principle

The interface is an evidence-first analyst workspace: restrained institutional
visual language, calm hierarchy, evidence before decoration, one status accent,
and no chatbot, fake live activity, gradients, or oversized dashboard theatre.
The front page should explain the reconstruction story in plain language; the
current workspace remains the detailed analyst view.

## What is implemented

### Core model and QA

- Canonical Kelmarsh extraction with provenance, checksums, coverage and physical-plausibility checks.
- Simulated hidden-interval back-tests with a stored hidden truth.
- Linear MCP wind reconstruction and power-curve conversion to kWh.
- Geo-aware and behaviour-weighted dynamic reference selection.
- 30/90/180-day lookback candidates with time-ordered validation.
- Weighted reference ensemble and rolling-origin reporting utilities.
- Review gate that can mark a result `Unverified -- manual evidence required`.
- Conditional uncertainty intervals and propagation into kWh.
- Indicative commercial profile and fixed-price calculation with disclaimers.

### Workspace

`workspace/` is a dependency-free local evidence workspace driven by the
assessment JSON contract. It includes:

- incident window and loss estimate;
- reference selection and integrity;
- uncertainty coverage and gate state;
- back-test metrics;
- evidence register;
- methodology and limitations;
- indicative commercial value panel;
- JSON export.

### External-farm adapter

`src/windlens/excel_connector.py` now contains:

- `ExcelFarmConnector` for explicit workbook/sheet/column mappings;
- `EDPExcelConnector` for the named source boundary;
- `EDPPortugalSCADAConnector` for combining explicitly supplied EDP turbine workbooks.

The EDP mapping is:

| Canonical field | Source column |
|---|---|
| `timestamp_utc` | `Timestamp` |
| `turbine_id` | `Turbine_ID` |
| `wind_speed_ms` | `Amb_WindSpeed_Avg` |
| `wind_direction_deg` | `Amb_WindDir_Abs_Avg` |
| `active_power_kw` | `Grd_Prod_Pwr_Avg` |

The connector requires a separate `FarmRegistry` containing verified latitude,
longitude and rated power. It rejects duplicate turbine/timestamp records by
default. `duplicate_policy="keep_first"` is available only for explicit
exploratory analysis and must be reported.

### Registry import and external validation

- `src/windlens/registry_import.py` imports operator CSV metadata and emits a
  provenance-bearing report with row-level issues and a geo-selection usability gate.
- `src/windlens/run_external_validation.py` writes a standalone EDP validation
  artifact and refuses to use Kelmarsh as the external farm. It records
  `kelmarsh_training_used=false`.
- The real EDP source has been run through the preflight path. The result is
  [`data/derived/validation/edp_portugal_preflight.json`](../data/derived/validation/edp_portugal_preflight.json)
  with status `blocked_missing_registry` because the public dataset does not
  include verified turbine coordinates/rated power. No synthetic metadata was
  inserted to force a model run.
- The workspace now shows registry source, checksum, farm/turbine count,
  quality state, and an explicit abstention message when the registry is not usable.

## Reproducible demo evidence

- Demo farm: Kelmarsh, kept separate from external farms.
- Simulated target: KWF1, 2016-07-07 to 2016-07-12 in the assessment artifact.
- After the 2026-10-21 uncertainty-calibration fix (see `docs/DECISION_LOG.md`),
  this block now has **zero failed gates** and is classified
  "Estimate -- reviewable" (previously "Unverified -- manual evidence
  required" at ~72% observed coverage). `run_assessment.py` was re-run and
  `data/derived/assessment/kwf1_2016-07-07_assessment.json`,
  `kwf1_2016-07-07_timeseries.json`, and `workspace/assessment-data.js` were
  regenerated accordingly -- the live workspace now reflects this, not the
  older run. This paragraph describes the original 2026-10-21 five-block
  state and is kept as historical record; **current (2026-10-23)**: the
  back-test runs on 19 Kelmarsh / 28 Hill of Towie blocks and, after the
  2026-10-22 trust-gate redesign (F1/F2), Kelmarsh is 11/19 reviewable (was
  3/19) and Hill of Towie is 19/28 (was 11/28) -- see `docs/HANDOVER.md`'s
  top addendum and `docs/DECISION_LOG.md`'s 2026-10-22 (late) entries for the
  full current numbers; this file's "one block out of five" framing no
  longer reflects the current sample size or gate logic.
- The original five-block dynamic/uncertainty back-test had 0/5 reviewable
  events after the uncertainty gate; after the 2026-10-21 fix it was 1/5.
  Superseded by the 19/28-block, post-trust-gate-redesign figures above.
- Full Python suite (2026-10-23, final): **163 tests, 153 pass** (10
  pre-existing `openpyxl` failures, unchanged; see `docs/HANDOVER.md`).
- Workspace JavaScript syntax check: passes with `node --check workspace/app.js`.

## External EDP evidence

The downloaded source is documented in
[`data/raw/edp_portugal/README.md`](../data/raw/edp_portugal/README.md).

- Source: Mendeley Data `10.17632/zjxjnjp3xs.2`.
- Public archive: 2016–2017, four turbines (`T01`, `T06`, `T07`, `T11`), 10-minute data.
- Clean archive: `edp_portugal_v2_clean.zip`.
- SHA-256: `c65e2dc7d990de512f83ee4d1aacbf73aab508fe71b1533df51918b91873adb1`.
- Archive passes `unzip -t`.
- The public workbooks do not contain verified turbine geolocation or rated-power metadata.
- Repeated UTC labels occur around apparent clock-reset periods; these are a
  source-quality issue, not something to silently discard.
- EDP is one external farm. It supports adapter and separate-farm validation,
  but cannot by itself prove broad cross-farm reliability.
- `edp_portugal_v2.zip` is an interrupted malformed transfer and must not be used;
  use only `edp_portugal_v2_clean.zip`.
- A source audit confirmed that the public EDP package does not expose turbine
  coordinates. A related peer-reviewed description explicitly says the EDP
  open-data source excludes the turbine-geography dataset. See
  [`edp_registry_sources.md`](../data/raw/edp_portugal/edp_registry_sources.md).
- The EDP OpenData catalogue does name a `Wind Farm 1 Locations` dataset, but
  the IEA description marks it Restricted (NDA) and describes positions
  relative to the met mast. It is therefore a registry lead, not public
  evidence we can import. A future handoff must include the restricted file,
  the mast's absolute location, coordinate convention, and authoritative rated
  power before the geo-aware EDP run can proceed.
- A public alternative is Hill of Towie: the Zenodo release includes a
  `Hill_of_Towie_turbine_metadata.csv` with coordinates, rated power, rotor
  diameter, and hub height for 21 turbines, plus more than 10 years of 10-minute
  SCADA. It is licensed CC BY 4.0 and is suitable for a separate-farm
  validation track, subject to checking its coordinate/reference conventions
  and selecting a manageable time slice.
- Hill of Towie metadata and the partial 2026 SCADA archive are now downloaded
  and audited. The verified registry imports 21 turbines (`T01`–`T21`) with
  exact public coordinates and 2,300 kW rated power. The canonical preparation
  covers 2026-01 through 2026-04 (361,494 rows after recording 61 duplicate
  boundary rows and 27 incomplete rows). The independent validation artifact
  explicitly records `kelmarsh_training_used=false`.
- Ran the first bounded Hill of Towie back-test on target `T01` using three
  pre-declared five-day blocks. Dynamic selection used 30/90/180-day lookbacks
  and selected `T03` as the best reference in every block; the top peer set was
  `T03`, `T02`, and `T04`. The weighted ensemble improved wind RMSE in all
  three blocks, but aggregate energy WAPE was 8.15% with -8.15% signed bias,
  and only 1/3 blocks passed all review gates. This remains an honest external
  validation result, not a production accuracy claim.
- Compared wind-first reconstruction with direct power reconstruction on the
  same three blocks. Corrected direct linear power (`target_kW = intercept +
  slope * reference_kW`) achieved 2.26% aggregate energy WAPE versus 6.12%
  for wind-first; a quadratic challenger achieved 3.38%. This is exploratory
  evidence only until it is repeated across more years and target turbines.
- Extended the comparison across all 21 Hill of Towie target turbines and the
  same three 2026 blocks: 63 scored events, zero selection abstentions. Direct
  power won 10/21 targets, but aggregate WAPE was effectively tied with
  wind-first (11.33% versus 11.32%). Direct power had lower aggregate signed
  bias (+0.75% versus -2.27%). Keep both methods available until 2024/2025
  data and more target windows are evaluated.
- Completed the same comparison across the verified 2024, 2025, and partial
  2026 archives: 189 scored events with zero unscorable blocks. Direct power
  achieved 9.03% aggregate WAPE and +0.72% bias; wind-first achieved 10.10%
  WAPE and -3.39% bias. Direct power won 13/21 targets when all years were
  combined, but did not win every year or target. Both methods remain visible
  for analyst comparison.
- Therefore no EDP registry is being fabricated from a farm-centroid guess or
  an unrelated power-plant database. The geo-aware EDP run remains blocked until
  the operator/data owner supplies the registry.

## Current assumptions

1. Kelmarsh remains the reproducible showcase dataset.
2. External farms are validated separately; farms are never merged into one
   training table.
3. Reference choice combines distance and behaviour, with behaviour dominant.
4. Shorter lookback windows are preferred only when validation is stable.
5. Uncertainty is a quality gate, not decorative error bars.
6. Commercial output is indicative until an operator supplies contract, market,
   imbalance, curtailment, and negative-price terms.
7. Missing metadata causes abstention or an explicit unverified state.

## Next steps, in order

1. Add a registry import/evidence interface for operator-supplied farm metadata.
2. Run the EDP connector against the supplied registry, keeping EDP separate.
3. Uncertainty calibration was reworked 2026-10-21 (fit/score mismatch fixed;
   mean coverage ~80%→~90% on both farms) -- see `docs/DECISION_LOG.md`. The
   back-test was then expanded 2026-10-22 from 5/3 blocks to **19 Kelmarsh /
   28 Hill of Towie** blocks (more history extracted, more calendar spread).
   **Correction, 2026-10-22 (late), F4:** "90% of blocks individually pass"
   is retired as a target -- a red-team simulation showed a perfectly
   calibrated interval clears it only ~45-58% of the time by construction, so
   the Kelmarsh/Hill-of-Towie numbers below were never evidence of a problem.
   The honest headline is **pooled coverage**: Kelmarsh 91.9%, Hill of Towie
   90.2% (both on target), with per-block std of 5.4pp / 6.8pp as the real
   dispersion diagnostic. The paragraph below (block-pass-rate figures) is
   kept as historical record of the old framing; see `docs/DECISION_LOG.md`'s
   priority-item-4 entry for the corrected numbers in full.

   At the larger, statistically meaningful sample size, "90% of blocks
   individually pass" is **not met and the shortfall is now outside the 95%
   confidence interval on either farm**: Kelmarsh 9/19 (47.4%, CI
   [27.3%, 68.3%]), Hill of Towie 17/28 (60.7%, CI [42.4%, 76.4%]) -- see
   `docs/DECISION_LOG.md` 2026-10-22 entry. Kelmarsh's undercoverage traces
   to a specific, identified mechanism (blocks with <30 days of pre-event
   calibration history fail 0/4; blocks with more pass 9/15); Hill of
   Towie's does not show an equally clean single-variable pattern (checked
   month and mean wind speed) and looks more like block-to-block noise
   around a true rate below 90%. A separate, parallel audit
   (`docs/AUDIT_2026-10-22_uncertainty_calibration.md`) also flagged that the
   calibration *method* itself was chosen by best-score-on-the-original-5-
   blocks (a selection-bias risk) and that calibration residuals are drawn
   from near-training data (not a fully independent holdout) -- neither is
   resolved by more blocks alone; both need a genuinely separate
   development/holdout split, which is a methodology decision for Anna.
4. Decide whether to promote direct-power regression over wind-first.
   2026-10-22: direct power now has its own calibrated uncertainty interval
   (the gap this item used to name), measured across the same 19/28-block
   sets: WAPE still favours it clearly (Kelmarsh 6.3% vs wind-first's
   10.0%; Hill of Towie 7.0% vs 13.9%), but coverage does **not** favour it
   -- Kelmarsh 8/19 blocks (42.1%) vs wind-first's 9/19 (47.4%); Hill of
   Towie 17/28 (60.7%) both methods. So coverage is not a new reason to
   prefer wind-first, but it's not a reason to prefer direct power either.
   Promoting it still changes the workspace's "reconstructed wind"
   narrative -- a deliberate product decision for Anna, not made this
   session. See `docs/DECISION_LOG.md` 2026-10-21 and 2026-10-22 entries.
5. Add the user-facing front page explaining outage → reference → wind → kWh →
   review decision, while preserving this detailed workspace.
6. Add contract/grid evidence interfaces and keep all commercial outputs clearly
   labelled indicative.
7. Obtain a second independent farm with compatible metadata before making a
   broad cross-farm reliability claim.

## Documentation rule

Every future implementation change must update this file and
`docs/DECISION_LOG.md` with:

- what changed;
- why it changed;
- assumptions introduced or retired;
- evidence and verification results;
- remaining limitations;
- the next concrete handoff step.

## 2026-10-20 — UI — Three evidence-first demo views added

- Added route-based views in `workspace/index.html`, `workspace/app.js`, and
  `workspace/styles.css`: **Assessment** (`#overview`), **Evidence**
  (`#evidence`), and **Methodology** (`#method`). The existing detailed
  evidence workspace remains available; the new routes only change what is
  visible and do not change the underlying assessment data or model outputs.
- The Assessment view keeps the existing headline estimate, gates, chart,
  registry evidence, and clearly labelled indicative commercial value. It does
  not introduce Hill of Towie results into the Kelmarsh assessment.
- The Evidence view isolates the traceable evidence table. The Methodology view
  adds a four-step factual story rail: detect the gap, select a like-for-like
  peer, estimate wind/power, and gate the result. The wording deliberately
  describes the implemented checks and preserves the failed-gate state.
- Verified with the local loopback server at `http://127.0.0.1:8000/`:
  browser navigation to all three routes produced the expected headings and
  route-specific content. `node --check workspace/app.js` passes and the full
  Python suite remains 102/102 green.
- No new data claims, model claims, or commercial/legal claims were added.

### Next handoff

Use the Assessment route for the live demo narrative, the Evidence route for
the audit trail, and the Methodology route for the explanation. Before adding
any new headline metric, attach a source artifact and update this file plus
`docs/DECISION_LOG.md`.

The concise cross-session handover is also maintained in
[`docs/HANDOVER.md`](HANDOVER.md).

## Metric policy

The reconstruction is scored as a continuous prediction problem. Required
metrics are wind MAE, RMSE, signed bias, holdout R², energy error/WAPE, signed
aggregate bias, interval coverage versus target, interval width, paired
observations, domain/alignment checks, and abstention rate. A generic
“accuracy” percentage is not used because it would hide the size and direction
of numerical error. Precision/recall/F1 are reserved for a future outage
detector with verified event labels; the current simulated missing-data
back-tests do not provide those labels.

## Public outage-label research — 2026-10-21

An outage-detection extension is feasible, but labels must be typed rather than
treated as interchangeable. The public EDP Portugal release contains
timestamped event/alarm logs and 28 manual confirmed component-failure records;
the event log is not a resolved outage register. The public WindML project
documents labelled major-fault stops for Kelmarsh and Penmanshiel, while the
CARE benchmark contains labelled anomaly frames and normal sequences across 36
turbines and three farms. These are candidate detection-validation inputs and
must remain separate from the Kelmarsh reconstruction training table.

The proposed architecture is detection first, reconstruction second. A future
detection scorecard should use event-level precision, recall, F1, false alarms
per turbine-month, missed-event rate, and time-to-detect, with a declared event
matching tolerance. A telemetry gap alone remains an unverified data-quality
condition, not a confirmed outage label.

## 2026-10-20 — UI — Operator-facing assessment interaction pass

- Reframed the Assessment view around an operator decision: estimated lost
  energy, explicit unverified state, selected peer, assessment window, and
  next action. The status now sits beside the headline number so the number
  cannot be read as an approved result by itself.
- Added a plain-language subtitle explaining the product task: estimate missing
  turbine production from verified peer behaviour, then gate the result.
- Corrected the chart SVG styling so reconstructed wind is a solid orange line,
  hidden truth is a dashed navy line, and the interval is a translucent band.
  The previous unstyled SVG paths rendered as confusing black filled shapes.
- Renamed unavailable horizon options to “not calculated in this record” and
  changed the trust panel to identify the actual failed **Uncertainty gate**
  (72% observed coverage versus a 90% target).
- Added an interactive chart layer with a hover crosshair/tooltip and a
  validation-overlay toggle. Hidden truth is off by default and explicitly
  labelled validation-only. The control is correctly labelled **reference
  lookback**: 90 days is selected in the saved record, while 30 and 180 days
  are not calculated in this record. The outage assessment window itself is
  five days.
- Reworded the commercial panel as an indicative exposure scenario. The saved
  fixed-price profile remains editable, but the UI now says scenario and
  clearly excludes settlement, liability, and legal interpretation.
- Converted the methodology rail into four clickable presentation steps. Each
  step now states what the step proves and what it does not prove, with the
  detailed methodology/limitations content retained below it.
- No assessment data, model coefficients, or validation results changed.

Verification: browser accessibility checks confirmed the new status, horizon
control, validation toggle, and four methodology buttons. `node --check
workspace/app.js` passes and the full Python suite remains 102/102 green.
