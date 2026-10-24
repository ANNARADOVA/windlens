# WindLens — Decision & Story Log

Purpose: a short, running record of what we did, where the data came from, and why we made each call — so the final presentation can be built from this file instead of memory, and so any decision can be explained and defended on demand.

## How to use this file

- Add an entry whenever we make a real decision, get a result, or change direction — not for every file edit or commit.
- Keep each entry to a handful of lines. Link out to the manifest/spec/code for detail instead of repeating it here.
- Entries are chronological, oldest first — read top to bottom and it's the story.
- Tag each entry with a type: **DATA** (sourcing/provenance), **SCOPE** (what's in/out), **DECISION** (a choice made between alternatives), **RESULT** (a number/metric we got), **RISK** (something flagged but not fully resolved).
- Update "At a glance" whenever the current stage changes — that section alone should be enough to brief someone cold.

---

## At a glance

- **Challenge (BayWa r.e.):** when a wind farm loses power it stops recording wind data too; use a neighboring reference farm's wind data to reconstruct the missing wind and estimate the resulting energy yield loss (kWh).
- **What this is:** counterfactual reconstruction during/after a known outage — not failure prediction, not root-cause analysis.
- **Dataset:** Kelmarsh Wind Farm SCADA v4 (Zenodo, CC BY 4.0, DOI 10.5281/zenodo.16807551) — 6 Senvion MM92 turbines, 10-minute UK SCADA. `KWF1` = simulated affected asset, `KWF2`–`KWF6` = peer-reference proxies.
- **Current working slice:** `data/derived/kelmarsh_2016_90d_canonical.csv` — window 2016-05-01 to 2016-07-30, 64,406 valid records.
- **Stage reached:** spike done, Section 8 QA hardening done, *and* the Section 9 multi-block back-test done (single-reference baseline vs. simple peer ensemble, 5 held-out blocks, reviewable/unverified gating). 56/56 tests pass. Honest finding: the naive peer ensemble underperforms the single best-correlated reference overall -- see the RISK entry below before using the ensemble as the headline model.
- **Not yet done:** evidence workspace UI, price/PPA connector, and (per the back-test's own finding) a better peer-ensemble method than equal-weight averaging.

---

## Log

### 2026-10-20 — DATA — Chose Kelmarsh v4 as the demo dataset
**What:** Picked the public Kelmarsh SCADA v4 archive over building or sourcing a true two-farm dataset.
**Why:** Real SCADA data, CC BY 4.0 (attribution required, reusable), small enough for a hackathon, six turbines so we can split roles: one "affected" asset, several reference turbines.
**Honesty caveat:** these turbines are in the *same* farm, not a separate neighboring farm. We call them "peer-reference proxies" everywhere rather than claiming a true cross-farm setup, so the demo doesn't overclaim. The design still has to accept a real external-farm connector later without a rebuild.
**Evidence:** [`DATASET_DISCOVERY.md`](../DATASET_DISCOVERY.md).

### 2026-10-20 — SCOPE — Reconstruction, not prediction; decision-support, not automation
**What:** WindLens reconstructs wind/generation *during* a known outage window from reference data. It does not predict future failures, infer root cause, or produce legal/financial determinations (settlement value, Redispatch eligibility, OEM liability, "bankable" certification).
**Why:** Matches the literal challenge wording, keeps the product in "evidence for a human analyst" territory, and avoids the overclaiming that would make judges (or a real analyst) distrust the number.
**Evidence:** [`WindLens_instructions.md`](../WindLens_instructions.md) §1–§3.

### 2026-10-20 — RESULT — First canonical working slice extracted
**What:** Built `src/windlens/prepare_dataset.py` to pull a 90-day, 10-minute canonical slice (UTC timestamp, turbine ID, wind speed, wind direction, active power) out of the raw archive, with checksums recorded end to end.
**Result:** 64,406 valid records kept; 13,354 invalid source readings and 236,736 out-of-window records dropped; 0 duplicates. Per-turbine breakdown in the manifest.
**Evidence:** [`data/derived/kelmarsh_2016_90d_canonical.csv`](../data/derived/kelmarsh_2016_90d_canonical.csv), [`.manifest.md`](../data/derived/kelmarsh_2016_90d_canonical.manifest.md), [`tests/test_prepare_dataset.py`](../tests/test_prepare_dataset.py).

### 2026-10-20 — DECISION — Harden ingestion/QA before touching modeling
**What:** Agreed to strengthen the ingestion/QA layer (automated provenance manifest, gap/coverage reporting, explicit header validation, physical-plausibility bounds, atomic writes, a fuller test matrix) before building outage masking or the reconstruction model.
**Why:** An independent review judged the first slice too thin to trust for a number that will be presented as "estimated kWh lost" — a wrong number here is the most damaging possible failure for this product's credibility.
**Risk flagged:** doing this exhaustively, item by item, risks spending most of the remaining hackathon time on QA scaffolding before a demoable reconstruction + loss estimate exists. Open question for Anna: do the full hardening pass as written, or do the highest-value subset now (header validation, plausibility bounds, atomic write, coverage report) and defer the rest, to protect time for the model and the evidence screen.
**Evidence:** [`WindLens_instructions.md`](../WindLens_instructions.md) §8.

### 2026-10-20 — DECISION — Resolved: spike first, then harden Section 8 fully
**What:** Context changed the call above — this is pre-hackathon prep (event starts Saturday, challenge assignment not yet confirmed), not hours ticking during the event itself, so the time pressure that motivated "do the lean subset only" is lower than first assumed.
**Decision:** do one rough end-to-end pass first — mask a known-healthy interval, run the simplest linear reconstruction, convert to kWh, sanity-check the number — before investing in the full Section 8 hardening and test matrix. Once the core idea is shown to produce a plausible number on this data, go back and do Section 8 properly in full, since its coverage/gap/plausibility output is literal content for the evidence/methodology screen (§11), not incidental infra.
**Why this order:** the spike targets the biggest real unknown (does reconstruction→kWh even work on this dataset) before spending days on comparatively low-risk engineering; a stalled core idea is cheaper to discover now than after a week of ingestion polish.
**Evidence:** this conversation; supersedes the open question in the entry above.

### 2026-10-20 — RESULT — End-to-end spike runs green, numbers are plausible and good

**What:** Built the four spike modules end to end: `src/windlens/mask_outage.py` (mask/hidden-truth split with recorded interval + checksums), `src/windlens/reconstruct.py` (linear measure-correlate-predict, reference turbine chosen by time-ordered holdout R², fit only on pre-outage data), `src/windlens/power_curve.py` (empirical binned power curve from KWF1's own pre-outage data), `src/windlens/loss_estimate.py` (kWh integration + comparison + wind error metrics), wired together in `src/windlens/run_spike.py`. 16 new focused unit tests added across `tests/test_mask_outage.py`, `tests/test_reconstruct.py`, `tests/test_power_curve.py`, `tests/test_loss_estimate.py`; full suite (17 tests incl. the pre-existing ingestion test) passes under `PYTHONPATH=src .../python3 -m unittest discover -s tests -v`. pandas/numpy were sufficient — no scikit-learn or pytest needed (linear fit via `numpy.polyfit`, test runner is stdlib `unittest`).

**Masked interval chosen:** `KWF1`, 2016-07-05T00:00:00Z to 2016-07-10T00:00:00Z (5 days, end-exclusive), picked by inspecting daily record counts — both KWF1 and KWF2 have near-full coverage (143–144 of 144 possible 10-min readings/day) across that whole span, with 63 days of pre-outage history available to fit on. 719 KWF1 rows removed into the hidden-truth file.

**Result (real run against the canonical dataset):**
- Reference turbine auto-selected: **KWF2** (time-ordered holdout R² ≈ 0.867 on pre-outage data; KWF4 ≈ 0.758, KWF5 ≈ 0.546, KWF3 ≈ 0.498, KWF6 ≈ 0.443 — KWF2 was the clear best by a wide margin).
- Wind reconstruction vs. hidden truth over 719 shared timestamps: **MAE 0.538 m/s, RMSE 0.745 m/s, signed bias −0.132 m/s** (slight underestimate).
- **Estimated lost kWh: 86,289.7** vs. **actual lost kWh (hidden truth): 89,521.0** → **absolute error 3,231.2 kWh (3.6% relative)**.
- Minor data wrinkle, not a bug: the masked interval has 720 KWF2 readings but only 719 KWF1 readings (KWF1 is missing exactly one 10-minute reading at 2016-07-06T07:30:00Z even within this "near-full" window) — the reconstruction therefore has one more point than the hidden truth, and `wind_speed_errors` correctly compares only the 719 overlapping timestamps. Immaterial to the result but worth remembering for Section 8's coverage reporting.

**Honest read:** this is a *good* result for a first-pass linear MCP spike, not an implausible one — 3.6% relative kWh error and sub-1-m/s wind RMSE are well within the range this kind of simple linear model is expected to produce, and the model picked a sensibly strong reference turbine automatically. We are not polishing this number; it's reported as-is.

**Evidence:** [`src/windlens/mask_outage.py`](../src/windlens/mask_outage.py), [`src/windlens/reconstruct.py`](../src/windlens/reconstruct.py), [`src/windlens/power_curve.py`](../src/windlens/power_curve.py), [`src/windlens/loss_estimate.py`](../src/windlens/loss_estimate.py), [`src/windlens/run_spike.py`](../src/windlens/run_spike.py), [`tests/test_mask_outage.py`](../tests/test_mask_outage.py), [`tests/test_reconstruct.py`](../tests/test_reconstruct.py), [`tests/test_power_curve.py`](../tests/test_power_curve.py), [`tests/test_loss_estimate.py`](../tests/test_loss_estimate.py), [`data/derived/spike/`](../data/derived/spike/).

### 2026-10-20 — RISK — Same-farm reference turbines likely flatter the correlation

**What:** The strong KWF2 holdout R² (≈0.87) that drove this spike's good numbers is measured between two turbines on the *same* Kelmarsh farm, a few hundred metres apart — not a true geographically-separate neighbouring farm, which is the real BayWa r.e. use case. A genuine cross-farm reference is very likely to correlate less tightly (different micro-siting, terrain, wake effects), so this spike's 3.6% kWh error should be read as a best-case validation of the *method*, not as the accuracy WindLens would achieve on a real two-farm deployment.
**Why flagged now, not fixed:** already logged as an honesty caveat when the dataset was chosen (see the DATA entry above); repeating it here because the spike's result makes the caveat concrete and consequential for how the number should be presented to judges.
**Evidence:** this run's result above; original caveat in the DATA entry above.

### 2026-10-20 — RESULT — Section 8 ingestion QA hardening complete, canonical dataset unchanged

**What:** Implemented the full §8 checklist on top of the validated spike: `src/windlens/checksums.py` (shared MD5 helper, also used to de-duplicate `mask_outage.py`'s own checksum code), `src/windlens/coverage.py` (expected-vs-actual 10-minute slot counts, contiguous-gap detection including leading/trailing/whole-turbine-missing gaps, target↔reference simultaneous overlap), `src/windlens/provenance.py` (builds + renders a provenance manifest from an actual extraction run instead of hand-writing one), and a hardened `src/windlens/prepare_dataset.py` (explicit required-column validation with a clear error naming the missing column; archive-checksum verification against the documented MD5 before any extraction; configurable physical-plausibility bounds -- wind speed, `[0,360)` direction normalization treating exact 360° as 0°, and a rated-power + documented overspeed-tolerance bound -- tracked in a new `dropped_implausible_rows` counter separate from pure parse failures; a hard failure if zero valid records are produced; and an atomic write via temp-file + rename so a failed run never touches a pre-existing valid output). New glue script `src/windlens/build_canonical_dataset.py` regenerates the dataset + manifest end to end, replacing the hand-written manifest with a generated one.

**Verification that hardening didn't silently change the data:** reran extraction against the real archive through the new pipeline. Output MD5 is still `15abb74500b414bff35f21e313da6827`, kept rows still 64,406, per-turbine valid-record counts identical to the original hand-written manifest, and the old undifferentiated "13,354 invalid readings excluded" splits exactly into the new `3,326 invalid + 10,028 implausible` buckets. The plausibility bounds (wind speed ≤50 m/s, power ≤2,255 kW = rated 2,050 kW × 1.10 tolerance) were sized from the real data's observed ranges (max wind speed 13.9 m/s, max power 2,017.8 kW, no exact-360° readings) specifically so hardening adds validation without rejecting any currently-valid row. Reran `run_spike.py` afterward -- identical masked/hidden-truth checksums and identical kWh/wind-error numbers to the pre-hardening run, confirming no downstream regression.

**Test matrix:** 19 new tests added (`tests/test_coverage.py` ×7, `tests/test_provenance.py` ×5, plus 7 new cases folded into the expanded `tests/test_prepare_dataset.py`: missing required column, zero-valid-output failure, duplicate dropping, 360°-normalization + out-of-range direction rejection, implausible wind-speed/power rejection, configurable overspeed tolerance, archive-checksum mismatch, and preservation of a prior valid output when a later run fails). Full suite: **37/37 tests pass**.

**Honest read:** no surprises -- the real dataset was already physically plausible (confirmed by inspection before picking bounds), so this pass added rigor and auditability without changing a single extracted value. The one genuinely new finding: per-turbine coverage is lower than the "near-full" 5-day masked window suggested -- full 90-day coverage is only 79-84% per turbine (hundreds of contiguous gap intervals each, mostly short), which is worth keeping in mind before trusting any *other* interval without checking its coverage first.

**Evidence:** [`src/windlens/checksums.py`](../src/windlens/checksums.py), [`src/windlens/coverage.py`](../src/windlens/coverage.py), [`src/windlens/provenance.py`](../src/windlens/provenance.py), [`src/windlens/prepare_dataset.py`](../src/windlens/prepare_dataset.py), [`src/windlens/build_canonical_dataset.py`](../src/windlens/build_canonical_dataset.py), [`tests/test_coverage.py`](../tests/test_coverage.py), [`tests/test_provenance.py`](../tests/test_provenance.py), [`tests/test_prepare_dataset.py`](../tests/test_prepare_dataset.py), regenerated [`data/derived/kelmarsh_2016_90d_canonical.manifest.md`](../data/derived/kelmarsh_2016_90d_canonical.manifest.md).

### 2026-10-20 — RESULT — Section 9 multi-block back-test run: only 1/5 blocks reviewable, ensemble underperforms baseline

**What:** Implemented the Section 9 back-test: `src/windlens/reconstruct.py` gained `reconstruct_wind_speed_ensemble` (a "simple peer ensemble" -- the mean of independently-fit single-reference linear MCP predictions, chosen over one multivariate regression across all references to avoid multicollinearity instability between highly-correlated same-farm turbines) and `reference_within_training_domain` (flags reconstruction-time reference readings that fall outside the range the linear fit was trained on -- the "validated domain" check). `src/windlens/loss_estimate.py` gained `energy_weighted_wape` and `signed_aggregate_bias_pct` (aggregate, not per-event, denominators -- robust to near-zero-generation events, unlike MAPE). New `src/windlens/review_gate.py` implements the exact "Estimate -- reviewable" / "Unverified -- manual evidence required" gate list from §9. New `src/windlens/backtest.py` runs one held-out block end to end (baseline + ensemble, both scored, domain-checked, and classified) and aggregates across blocks; `src/windlens/run_backtest.py` is the glue script against the real dataset.

**Blocks used:** 5 held-out 5-day intervals picked from the real per-turbine daily coverage table built during Section 8 (near-full coverage, spread across May/June/July 2016, none overlapping the spike's already-used 2016-07-05–10 week): 05-17–22, 05-29–06-03, 06-26–07-01, 07-07–12, 07-13–18. Honesty note: this 90-day, single-season, single-UK-farm dataset cannot give true weather-regime diversity -- month-of-year is the only proxy for "different conditions" available here.

**Result (real run against the canonical dataset):**

| Block | Baseline ref | Ensemble refs | Baseline est/actual kWh | Ensemble est/actual kWh | Ensemble beats baseline? | In domain? | Classification |
|---|---|---|---:|---:|---|---|---|
| 05-17–22 | KWF2 | KWF2,3,4 | 65,387 / 76,884 | 55,388 / 76,884 | No | No | Unverified |
| 05-29–06-03 | KWF2 | KWF2,3,6 | 120,337 / 135,329 | 126,463 / 135,329 | Yes | No | Unverified |
| 06-26–07-01 | KWF2 | KWF2,4,5 | 60,812 / 66,393 | 54,010 / 66,393 | No | Yes | Unverified |
| 07-07–12 | KWF2 | KWF2,4,3 | 110,402 / 117,373 | 106,350 / 117,373 | Yes | Yes | **Reviewable** |
| 07-13–18 | KWF2 | KWF2,4,5 | 63,234 / 66,887 | 54,807 / 66,887 | No | Yes | Unverified |

**Aggregate across all 5 blocks:** baseline energy-weighted WAPE **9.2%**, signed aggregate bias **-9.2%** (consistent under-estimate). Ensemble energy-weighted WAPE **14.2%**, signed aggregate bias **-14.2%** -- worse on every count. Only 1 of 5 blocks (07-07–12) is "Estimate -- reviewable"; the other 4 are "Unverified -- manual evidence required," either on the validated-domain gate (2 blocks) or the beats-baseline gate (3 blocks; one block fails both).

**Evidence:** [`src/windlens/reconstruct.py`](../src/windlens/reconstruct.py), [`src/windlens/loss_estimate.py`](../src/windlens/loss_estimate.py), [`src/windlens/review_gate.py`](../src/windlens/review_gate.py), [`src/windlens/backtest.py`](../src/windlens/backtest.py), [`src/windlens/run_backtest.py`](../src/windlens/run_backtest.py), [`tests/test_reconstruct.py`](../tests/test_reconstruct.py), [`tests/test_loss_estimate.py`](../tests/test_loss_estimate.py), [`tests/test_review_gate.py`](../tests/test_review_gate.py), [`tests/test_backtest.py`](../tests/test_backtest.py).

### 2026-10-20 — RISK — Naive equal-weight peer ensemble is worse than the single best reference, not better

**What:** Averaging the top-3 individually-selected reference turbines' predictions (the "simple peer ensemble" from §9) underperformed the single best-correlated reference (KWF2) on every block and in aggregate (14.2% vs. 9.2% WAPE). This is the opposite of what ensembling is supposed to buy you.
**Why it happens:** equal-weight averaging only helps when the ensembled predictors have comparable individual skill and largely independent errors. Here KWF2 correlates with KWF1 much more strongly than KWF3/4/5/6 do (see the spike's holdout R² ranking: KWF2 ≈0.87 vs. KWF3-6 in the 0.44-0.76 range) -- averaging a strong predictor in with 2 much weaker ones dilutes it rather than cancelling noise.
**Not fixed now, by design:** the hackathon spirit here is to report the honest number, not tune the model until it looks better. A weighted ensemble (weight by holdout R², or only ensemble turbines above some minimum R² threshold) is the obvious next experiment, but that's new modeling work, not part of this back-test pass.
**Secondary finding:** the validated-domain gate fails more often on the two earliest blocks (May), because "train only on pre-outage data" means those blocks have a much shorter training history (2-4 weeks vs. 9-11 weeks for the July blocks) and therefore a narrower observed wind-speed range -- an expected, not surprising, consequence of the no-leakage training rule, but worth remembering when picking which historical interval to demo.
**Evidence:** this run's result table above; [`WindLens_instructions.md`](../WindLens_instructions.md) §9.

<!-- Add new entries below this line, in order. -->

### 2026-10-20 — RESULT — Assessment contract and empirical uncertainty layer added
**What:** Added `src/windlens/assessment.py`, a versioned JSON contract for one evidence record, plus `src/windlens/run_assessment.py` to generate the canonical reviewable demo artifact at `data/derived/assessment/kwf1_2016-07-07_assessment.json`. The record carries the incident window, model estimate, reference integrity, QA status, validation metrics, review gates, provenance, method, next action, and explicit limitations. Hidden truth is stored under validation because it exists only for the simulated back-test.

Added `src/windlens/uncertainty.py` with an empirical central residual interval calibrated from a trailing, time-ordered pre-event block and evaluated on the held-out event. The back-test now records calibration observations, target coverage, and mean interval width for both baseline and ensemble outputs. This is deliberately a transparent prediction interval for the demonstrated domain, not a probabilistic guarantee for a different farm.

**Result:** The generated reviewable ensemble assessment for 2016-07-07 to 2016-07-12 estimates 106,349.5 kWh lost versus 117,372.9 kWh hidden truth (9.4% relative error). Its 90% target wind interval covered 68.1% of the held-out observations with mean width 2.0 m/s, so the UI must show the interval as under-covering on this block and keep the review status visible. Full suite: 65/65 tests pass.

**Evidence:** [`src/windlens/assessment.py`](../src/windlens/assessment.py), [`src/windlens/uncertainty.py`](../src/windlens/uncertainty.py), [`src/windlens/run_assessment.py`](../src/windlens/run_assessment.py), [`data/derived/assessment/kwf1_2016-07-07_assessment.json`](../data/derived/assessment/kwf1_2016-07-07_assessment.json).

### 2026-10-20 — DECISION — Built the evidence-first analyst workspace
**What:** Added a dependency-free local workspace in `workspace/`, driven by the assessment JSON contract and its generated time-series evidence. The page is organized around the analyst question “how much energy was likely lost, and how trustworthy is that number?” It includes the incident header, loss estimate, review gates, reconstructed-versus-hidden-truth series, reference integrity, uncertainty coverage, back-test metrics, evidence register, methodology, limitations, and JSON export.

**Design constraint:** kept the institutional terminal direction from the MVP instructions: restrained palette, one status accent, dense but calm information hierarchy, evidence before decoration, and no chatbot, fake live activity, gradients, or oversized dashboard theatre.

**Evidence:** [`workspace/index.html`](../workspace/index.html), [`workspace/styles.css`](../workspace/styles.css), [`workspace/app.js`](../workspace/app.js), [`workspace/README.md`](../workspace/README.md), [`data/derived/assessment/kwf1_2016-07-07_timeseries.json`](../data/derived/assessment/kwf1_2016-07-07_timeseries.json).

### 2026-10-20 — DECISION — Reference selection and uncertainty are now explicit model gates
**What:** Added leakage-safe geo-plus-behaviour reference selection in `src/windlens/dynamic_reference.py`, using haversine distance, time-ordered holdout RMSE/MAE/bias/R², minimum overlap, 30/90/180-day lookbacks, and inverse-error ensemble weights. The real back-test path now reads Kelmarsh turbine coordinates, selects the shortest stable lookback within 1% of the best validation RMSE, and uses weighted reconstruction.

Added conditional wind-speed/direction intervals, wind-to-kWh interval propagation, uncertainty quality gates, and saved indicative commercial profiles in `src/windlens/uncertainty_business.py`. The uncertainty gate is now part of the review classification. On the current single-farm sample, it correctly changes the result from “reviewable” to “Unverified” because the empirical interval under-covers the 90% target. That is a stricter and more honest gate, not a regression.

**External-data decision:** Kelmarsh remains the reproducible demo dataset, but cross-farm validation should use a second dataset. The strongest practical candidates found are Hill of Towie (large, long-term 10-minute SCADA with turbine metadata; https://zenodo.org/records/22662930) and the smaller EDP Portugal SCADA set (four turbines, 2016–2017, SCADA plus met mast/events; https://data.mendeley.com/datasets/zjxjnjp3xs/1). Do not merge farms blindly: validate each farm separately through the same connector and report cross-farm performance.

**Result:** Full suite: 75/75 tests pass. The current five-block run has 0/5 reviewable events after the uncertainty gate, exposing the next technical priority: calibrate intervals across many rolling blocks and widen/abstain until coverage is reliable.

### 2026-10-20 — RESULT — EDP Portugal source adapter verified against the public archive
**What:** Downloaded the public Mendeley Data version-2 EDP Portugal archive, verified the ZIP integrity and recorded its SHA-256, extracted the published workbooks for inspection, and added `EDPPortugalSCADAConnector`. The adapter requires explicit workbook paths and a separately verified turbine registry, maps the published SCADA columns into the canonical WindLens schema, normalizes UTC timestamps, and rejects duplicate turbine/timestamp records.

**Evidence:** [`data/raw/edp_portugal/README.md`](../data/raw/edp_portugal/README.md), [`src/windlens/excel_connector.py`](../src/windlens/excel_connector.py), [`tests/test_excel_connector.py`](../tests/test_excel_connector.py). The clean archive passes `unzip -t`; the full suite is 92/92 tests green.

**Boundary:** the public EDP workbooks do not include verified turbine latitude/longitude or rated-power metadata. The adapter intentionally does not invent them, so a geo-aware cross-farm run must wait for an operator-supplied registry with provenance. EDP is one independent farm and therefore supports external-farm adapter validation, but it does not alone prove broad cross-farm reliability.

**Data-quality finding:** the EDP workbooks contain repeated UTC labels around clock-reset periods. WindLens rejects these by default; keeping one record is an explicit exploratory policy, not a hidden cleanup.

### 2026-10-20 — RESULT — Registry import and EDP validation boundary added
**What:** Added the CSV registry importer, versioned registry evidence contract, operator template, standalone EDP validation runner, and workspace metadata-evidence panel. The importer validates coordinates, rated power, provenance, quality status, and duplicate keys without fabricating missing metadata. The EDP runner rejects Kelmarsh as an external farm and writes `kelmarsh_training_used=false` in its artifact.

**Real EDP run:** ran the four extracted 2016 EDP turbine workbooks through the separate validation preflight. It produced [`data/derived/validation/edp_portugal_preflight.json`](../data/derived/validation/edp_portugal_preflight.json) with status `blocked_missing_registry`. This is the correct evidence-first result: the public EDP files lack verified geolocation/rated-power metadata, so WindLens abstains instead of inventing it.

**Verification:** full suite is 102/102 tests green; `node --check workspace/app.js` passes. The regenerated workspace bundle contains the verified Kelmarsh registry evidence used by the reproducible demo.

**Next handoff:** attach a real, provenance-bearing EDP registry, rerun `run_edp_validation`, then evaluate EDP separately. Do not merge it into Kelmarsh training.

### 2026-10-20 — RESULT — EDP registry source audit remains blocked on geolocation
**What:** Audited the official EDP/Mendeley record and related peer-reviewed dataset documentation for a turbine registry. The official record confirms the four published turbine IDs and SCADA coverage. The peer-reviewed description explicitly notes that the EDP open-data source excludes the dataset containing turbine geographical location; published material gives only a broad 2-MW class description, not exact per-turbine registry metadata.

**Decision:** do not create coordinates from a farm centroid, reverse geocode an unrelated EDP plant, or treat a broad 2-MW class statement as an exact asset registry. Keep the external validation artifact at `blocked_missing_registry` until the data owner or operator supplies coordinates and rated power with provenance.

**Evidence:** [`data/raw/edp_portugal/edp_registry_sources.md`](../data/raw/edp_portugal/edp_registry_sources.md), official [Mendeley dataset record](https://data.mendeley.com/datasets/zjxjnjp3xs/2), and the related [peer-reviewed dataset description](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2022.904622/full).

### 2026-10-20 — RESULT — EDP registry lead found, but access is NDA-restricted
**What:** Researched the EDP OpenData catalogue for the missing turbine registry. The IEA Wind package description names a `Wind Farm 1 Locations` dataset containing turbine positions relative to the met mast and marks it **Restricted (NDA)**. This is stronger evidence than simply failing to find a file: the location asset appears to exist, but the public SCADA release intentionally omits it.

**Decision:** keep `edp_portugal_preflight.json` blocked. Do not reconstruct WGS84 coordinates from a farm centroid, an unrelated EDP power-plant record, or the broad 2-MW class description. Request the restricted location asset, mast absolute coordinates, coordinate convention, and rated-power metadata from EDP/data owners; alternatively choose an external farm with a public registry.

**Evidence:** [IEA Wind EDP OpenData Details](https://iea-wind.org/wp-content/uploads/2024/07/EDP-OpenData-Details.pdf), [public EDP Mendeley record](https://data.mendeley.com/datasets/zjxjnjp3xs/2), and the updated [`edp_registry_sources.md`](../data/raw/edp_portugal/edp_registry_sources.md).

### 2026-10-20 — DECISION — Use public farm metadata rather than guessed EDP coordinates
**What:** Checked the public Hill of Towie alternative. Its Zenodo release includes `Hill_of_Towie_turbine_metadata.csv` with coordinates, rated power, rotor diameter, and hub height for 21 turbines, alongside more than 10 years of 10-minute SCADA. The release is open under CC BY 4.0.

**Decision:** do not use map guesses or fictional coordinates for EDP. If the goal is a genuinely public cross-farm validation, use Hill of Towie as a separate validation farm, keep it out of Kelmarsh training, and first audit its coordinate reference, identifiers, coverage, and a bounded time slice before downloading the large SCADA archive.

**Evidence:** [Hill of Towie Zenodo record](https://zenodo.org/records/22662930).

### 2026-10-20 — RESULT — Hill of Towie public registry and separate validation input prepared
**What:** Downloaded the public metadata CSV and partial 2026 SCADA archive from Zenodo. Audited the registry and found 21 exact turbine IDs (`T01`–`T21`), latitude/longitude, Station IDs, and 2,300 kW rated power. Joined the monthly turbine and grid tables into the canonical WindLens schema using the documented `TimeStamp`/`StationId` key.

**Result:** the source archive MD5 is `42a2264187912ca63214bacfbc8d4905`. The preparation wrote 361,494 canonical rows for 2026-01-01 through 2026-05-01, excluding 61 duplicate month-boundary rows and 27 incomplete rows. No StationIds were unknown. The normalized registry imported with 21 accepted rows, zero issues, and `usable_for_geo_selection=true`.

The separate input-validation artifact is [`hill_of_towie_2026_validation.json`](../data/derived/validation/hill_of_towie_2026_validation.json). It records `kelmarsh_training_used=false` and `model_training_mixed_with_kelmarsh=false`.

**Assumptions:** timestamps are UTC and represent 10-minute period ends, as documented by the publisher. Coordinates are taken directly from the public metadata CSV. Directional modelling must respect the documented turbine-north calibration caveat.

**Next handoff:** select a bounded target outage/back-test window within Hill of Towie, run dynamic geo-plus-behaviour reference selection and uncertainty gates, and report the farm separately from Kelmarsh.

### 2026-10-20 — RESULT — First Hill of Towie dynamic reference back-test completed
**What:** Ran three pre-declared five-day simulated outage blocks for target `T01` using only the public January–April 2026 slice. For each block, the selector evaluated 30-, 90-, and 180-day pre-event lookbacks, ranked candidate turbines using 80% behavioural holdout error and 20% geographic proximity, and assigned inverse-RMSE ensemble weights. Hidden target data was used only for scoring after the model configuration was frozen.

**Result:** `T03` was selected as the best single reference in all three blocks. The peer ensemble improved wind RMSE in every block (1.060→0.658, 0.923→0.692, and 1.173→0.809 m/s). However, ensemble aggregate energy WAPE was 8.15% with signed bias -8.15%; only 1/3 blocks were labelled `Estimate -- reviewable`. The two other blocks remain `Unverified -- manual evidence required` because uncertainty coverage and/or domain gates failed.

**Why this is credible:** the blocks were declared before scoring, all candidate turbines were eligible by the same rule, the hidden target interval was never used for selection or fitting, and all blocks—including failures—are saved in [`hill_of_towie_2026_backtest.json`](../data/derived/validation/hill_of_towie_2026_backtest.json).

**Next handoff:** repeat across additional target turbines and years once the 2024/2025 archives finish downloading; report aggregate performance, coverage, bias, and abstention rate rather than a single favourable example.

### 2026-10-20 — RESULT — Direct-power challenger beats wind-first on the first Hill slice
**What:** Compared three methods on the same three held-out blocks: wind-first reconstruction plus an empirical target power curve; direct linear power regression; and a quadratic direct-power challenger. The direct linear formula is `target_kW = intercept + slope * reference_kW` and was fit only on pre-block paired data.

**Result:** aggregate energy WAPE was 2.26% for direct linear power, 3.38% for direct quadratic power, and 6.12% for wind-first. Direct linear power is therefore the current challenger to carry into multi-year validation, not an immediate replacement.

**Correction recorded:** an initial scratch calculation reversed the `(slope, intercept)` order returned by `numpy.polyfit`, producing an invalid large-error result. The scratch output was discarded. The saved artifact was regenerated by [`compare_reconstruction_methods.py`](../src/windlens/compare_reconstruction_methods.py) with the correct coefficient order.

**Limitation:** this remains one farm, one partial year, one target, and three blocks. The result could still be farm-specific. Gradient boosting was not run because scikit-learn is unavailable in the bundled runtime; it is not needed before testing the simpler direct-power challenger across the completed 2024–2026 data.

### 2026-10-20 — RESULT — All-target 2026 method sweep is mixed, not a replacement decision
**What:** Ran direct-power and wind-first methods over all 21 Hill of Towie target turbines and the same three pre-declared five-day blocks: 63 scored events with no reference-selection abstentions.

**Result:** direct power had lower aggregate signed bias (+0.75% versus -2.27%) and won 10 of 21 target turbines, but aggregate energy WAPE was effectively tied with wind-first (11.33% versus 11.32%). This is materially less favourable than the single-target result and is exactly why the sweep is needed.

**Decision:** retain both methods as challengers. Do not switch the production default based on the first three blocks. Re-run across 2024/2025 and additional windows once those archives are complete; select a method by aggregate WAPE, bias, uncertainty coverage, and abstention rate.

**Evidence:** [`hill_of_towie_2026_method_sweep.json`](../data/derived/validation/hill_of_towie_2026_method_sweep.json).

### 2026-10-20 — RESULT — Multi-year Hill of Towie comparison completed
**What:** Verified and moved the public 2024, 2025, and partial 2026 archives into `data/raw/hill_of_towie/`. Prepared each year independently, then ran the same direct-power versus wind-first comparison across 21 turbines and three pre-declared March/April blocks per year.

**Result:** 189 events were scored with zero unscorable blocks or reference-selection abstentions. Direct power achieved 9.03% aggregate energy WAPE with +0.72% signed bias; wind-first achieved 10.10% WAPE with -3.39% signed bias. Direct power won 15/21 targets in 2024, 12/21 in 2025, and 10/21 in 2026 (13/21 across all years).

**Decision:** direct power is the leading transparent challenger, but the UI and evidence contract should keep wind-first available for comparison. The result is credible because each year was scored separately, held-out blocks were fixed in advance, and the yearly outputs were combined only after scoring.

**Quality correction:** the initial multi-year attempt revealed that empty target/reference overlaps were producing NumPy warnings. The run was stopped; the sweep now marks fewer-than-20-row overlaps as `unscorable`. The final run had none.

**Evidence:** [`hill_of_towie_2024_2026_method_sweep.json`](../data/derived/validation/hill_of_towie_2024_2026_method_sweep.json), year-specific preparation audits, and source archive checksums in [`data/raw/hill_of_towie/README.windlens.md`](../data/raw/hill_of_towie/README.windlens.md).

### 2026-10-20 — PROCESS — Persistent project handoff documentation required
**Decision:** every future implementation or modeling change must update both [`docs/PROJECT_STATE.md`](PROJECT_STATE.md) and this decision log with the change, rationale, assumptions, evidence/verification, limitations, and next handoff step.

**Reason:** the project is being developed across Codex and Claude sessions. A future agent must be able to continue from the documented state without relying on conversation history.

### 2026-10-20 — UI — Evidence-first assessment, evidence, and methodology routes

**What:** Added a lightweight route switch to the local workspace. `#overview`
shows the Assessment view, `#evidence` shows the traceability table, and
`#method` shows the Methodology view with a four-step reconstruction story.

**Design decision:** the Assessment route is the demo surface, but it reuses
only the existing Kelmarsh assessment record. The Evidence route exposes the
source, checksum, reference overlap, uncertainty coverage, and review gate.
The Methodology rail states the actual sequence implemented in code and keeps
the uncertainty failure visible. This follows the project principle of evidence
before decoration and avoids presenting unverified external-farm results as
part of the showcase assessment.

**Verification:** served the workspace on loopback and navigated to all three
hash routes. The browser showed the expected route heading and content for each:
Outage reconstruction, Evidence register, and Methodology. `node --check
workspace/app.js` passes; the Python suite is 102/102 green.

**Boundary:** this is a presentation-layer change. It does not make the
Kelmarsh simulated outage operational evidence, does not improve the 72%
observed versus 90% target interval coverage, and does not claim settlement or
legal value. Those remain visible limitations.

**Next handoff:** use the Assessment route for the demo walkthrough; attach any
future headline number to a saved validation artifact before displaying it.

### 2026-10-20 — UI — Assessment made decision-oriented and inspectable

**What changed:** Reworked the assessment surface to put the review state next
to the energy estimate, renamed the commercial output to an indicative
exposure scenario, added chart hover inspection and a validation-only hidden
truth toggle, and added a guarded assessment-horizon selector. The methodology
rail is now a clickable four-step presentation with explicit evidence
boundaries.

The top-level subtitle now explains the product in plain language: estimate
missing turbine production from verified peer behaviour, then gate the result.

**Why:** an operator needs to know what happened, how large the impact is, how
much to trust it, and what to do next before reading technical detail. A graph
without hover values or a visible validation boundary invites over-interpretation.

**Evidence boundary:** only the existing five-day Kelmarsh assessment is
available in this bundle. The 30/90/180-day controls are intentionally marked
“requires recalculation”; they do not generate unsupported results. Hidden truth
is shown only when the user explicitly enables the simulated back-test overlay.

Follow-up correction: the control is now labelled **Reference lookback**, not
assessment horizon. The saved assessment is five days long; 90 days is the
selected pre-event lookback, while 30 and 180 days are not calculated in this
record. The chart now uses explicit line strokes and a translucent interval
band; the previous default SVG fill made both series look like black area
shapes. The trust panel now names the failed gate as **Uncertainty gate**,
rather than implying a generic back-test failure.

### 2026-10-21 — METRIC POLICY — Regression quality versus classification quality

**Decision:** evaluate reconstruction with MAE, RMSE, signed bias, holdout R²,
energy error/WAPE, interval coverage and width, domain/alignment checks, and
abstention rate. Do not report a generic accuracy percentage: it is not a useful
single measure for a continuous kWh/wind estimate.

Precision, recall, and F1 are not currently tracked because the public sample
does not contain verified operational-outage labels. They belong to a future
outage detector scorecard, where suspected-outage alerts can be compared with
confirmed events. Adding them to the current reconstruction score would imply
ground truth that we do not have.

### 2026-10-21 — DATA — Public labels can support a separate outage detector

**Finding:** public labelled material exists, but it represents different
events. The EDP Portugal release contains timestamped alarms/events plus 28
manual confirmed component-failure records. The WindML project documents
major-fault stop episodes for Kelmarsh and Penmanshiel. The CARE benchmark
contains labelled anomaly frames leading to faults and normal sequences from 36
turbines across three farms. Sources: [EDP/Mendeley dataset](https://data.mendeley.com/datasets/zjxjnjp3xs/1), [WindML overview](https://ml.beehivewebstudio.com/windml/), [WindML failure labels](https://ml.beehivewebstudio.com/windml/labels/), and [CARE to Compare](https://arxiv.org/abs/2404.10320).

**Decision:** treat this as a future two-stage extension: first detect and
classify a suspected event, then reconstruct counterfactual generation. Keep
event/alarm/failure labels distinct and do not mix external-farm labels into
Kelmarsh reconstruction training. Evaluate detection with event-level
precision, recall, F1, false alarms per turbine-month, missed events, and
time-to-detect. A data gap without an independent event label remains
unverified.

**Verification:** browser checks confirmed the Assessment and Methodology views
render the new controls and labels; the four methodology steps are accessible
buttons. `node --check workspace/app.js` passes and all 102 Python tests pass.

**Next handoff:** implement recalculated horizons only after adding the matching
saved assessment artifacts and rolling validation evidence. Do not enable the
disabled horizon options by changing the label alone.

### 2026-10-21 — PROCESS — Interpreting the "push toward 90%, ideally 95%" instruction

**Context:** Anna asked (loosely, before going to sleep) to "figure out the
analysis and approximations above 90%, goal 95%" and left this session running
unattended overnight. Writing down the interpretation now, as instructed, so
she can correct it in the morning. Procedural note, for honesty: this entry
was drafted after the uncertainty-coverage diagnosis below had already started
(reading the coverage code and running the existing 5-block Kelmarsh back-test
to see current numbers), not strictly before any investigation. No code was
changed before this entry was written -- only read-only diagnostics were run.
The instruction said to write this before changing code, and that bar is met;
it did not say before reading/running existing code to establish a baseline,
but flagging the actual order here rather than implying otherwise.

**Interpretation adopted:**
- (a) Uncertainty-interval coverage: target is that **>=90% of back-test
  blocks individually meet their own 90% coverage target** (not a mean
  coverage number averaged across blocks), stretch >=95% of blocks. This reads
  "coverage across back-test blocks" as a pass/fail rate over blocks, matching
  how the existing uncertainty gate already works (a block either clears 90%
  coverage or it doesn't).
- (b) Aggregate energy WAPE: target <=10% (read as the "90% accuracy"
  complement Anna mentioned), stretch <=5% (the "95%" complement. This is
  evaluated as the existing `energy_weighted_wape_pct` aggregate metric
  already used across all blocks in a given back-test (Kelmarsh 5-block,
  Hill of Towie 3-block), for whichever reconstruction method is being scored.

**Order of work, per the brief:** (1) look at whether the uncertainty interval
method is too narrow and try an empirical/conformal-style fix calibrated from
residuals, re-run both farms, report before/after honestly; (2) check whether
direct-power regression beats wind-first on Kelmarsh too (same-farm caveat
applies), and try a behaviour-weighted ensemble only if quick; (3) update
DECISION_LOG/PROJECT_STATE/HANDOVER as work proceeds. Guardrails observed: no
new dependency without flagging and stopping for confirmation (none was
needed); no fabricated precision or brute-force padding to cross a target; the
EDP abstention and the outage-detection extension are untouched; no git
commands were run (this is explicitly not a git repository).

If this interpretation is wrong -- for example if "coverage across blocks"
was meant as a single pooled/mean coverage number rather than a pass-rate over
blocks -- the raw before/after numbers below are reported either way, so the
correct interpretation can be re-applied without re-running anything.

### 2026-10-21 — RESULT — Uncertainty interval calibration: root cause found and fixed, coverage improved but not at target

**What was wrong:** `backtest.py`'s `_calibrate_and_evaluate_interval` already
used an empirical/conformal-style interval (central residual quantiles from
`windlens/uncertainty.py`), not a fixed/parametric width -- that part of the
brief's hypothesis did not hold. The actual bug: calibration residuals were
generated by **re-fitting a fresh linear model** at an inner cutoff (the last
20% of available pre-event history) and scoring it only over that short
trailing window. That re-fit model differed from the model actually used for
the event (fit on *all* pre-event history up to `block_start`), and its bias
drifted in sign block to block: measured residual bias on the Kelmarsh
ensemble ranged from +0.37 m/s (block 2) to -0.34 m/s (block 4). A directional
miss-count diagnostic confirmed this was not a symmetric spread problem: block
2's misses were almost all actual-wind-below-lower-bound (126 of 148 misses),
while blocks 4 and 5 were almost all actual-wind-above-upper-bound (198/200
and 184/203) -- opposite directions, which a wider symmetric interval cannot
fix without being arbitrarily padded.

**What was tried and did not help (logged so it is not re-tried):**
- Shortening the calibration window to a fixed recent trailing window (3, 5,
  7, 10 days before the event, re-fitting at that cutoff): mean ensemble
  coverage 85.4% / 81.6% / 81.1% / 83.3% respectively across the 5 Kelmarsh
  blocks -- better than the original 79.6% mean in the best case (3-day
  window) but still only 2/5 blocks >=90%, and no window size was reliable
  (minimum coverage stayed in the 70s-80s). Rejected: it does not reliably
  fix the sign-flipping bias, it is noisier with smaller calibration samples,
  and picking "whichever window looks best in hindsight" would itself be an
  unjustified form of tuning to the test data.
- Conditioning the interval on wind-speed bucket and direction sector, using
  the existing (already-tested, previously unused in the back-test)
  `calibrate_conditional_intervals`/`apply_conditional_intervals` in
  `uncertainty_business.py`: this made coverage *worse* (mean 67.9%, down from
  79.6%), because narrower per-cell bands overfit to a calibration-period
  bias that does not hold during the event. Rejected.

**What fixed it:** fit the weighted-reference model **once**, on the same
pre-event cutoff used for the actual event (`fit_weighted_references`, new
function in `reconstruct.py`), then score that *same* fitted model's residuals
across the *entire* available pre-event history for the target turbine
(`predict_with_fitted_references`, also new), instead of re-fitting at an
inner 20% cutoff. This is a methodology correction directly justified by the
residuals -- removing the fit/score mismatch collapsed the measured bias to
within +/-0.01 m/s on every Kelmarsh block (down from -0.34..+0.37 m/s), and
that bias collapse is what raised coverage, not a wider interval chosen to
hit a number. `_calibrate_and_evaluate_interval` in `backtest.py` was
rewritten to use this; both the baseline (single reference) and ensemble
paths now share the same calibration logic (previously duplicated via two
separate `prediction_fn` lambdas). 3 new tests added to
`tests/test_reconstruct.py` for the two new functions (equivalence to
`reconstruct_wind_speed_weighted` over the same window; scoring a fitted model
over a different window without refitting; weight-validation). Full suite:
**105/105 tests pass** (102 previous + 3 new).

**Before/after, Kelmarsh 5-block back-test (ensemble, the one surfaced in the
UI's uncertainty gate):**

| Block | Coverage before | Coverage after |
|---|---|---|
| 2016-05-17 | 85.4% | 85.2% |
| 2016-05-29 | 79.4% | 84.5% |
| 2016-06-26 | 89.8% | 95.8% |
| 2016-07-07 | 72.0% | 95.9% |
| 2016-07-13 | 71.2% | 88.1% |
| **Mean** | **79.6%** | **89.9%** |
| **Blocks >=90%** | **0/5** | **2/5** |

Baseline (single reference) improved from mean 84.4% (1/5 >=90%) to mean 89.2%
(3/5 >=90%). Reviewable events rose from **0/5 to 1/5** (block 2016-07-07 now
passes every gate: "Estimate -- reviewable"). Aggregate WAPE is unchanged
(11.6% baseline / 14.0% ensemble) -- expected and a useful sanity check, since
this change only touches the uncertainty calibration path, not the point
reconstruction.

**Hill of Towie 3-block external back-test**, same fix applied (it reuses the
same `run_backtest_event`/`_calibrate_and_evaluate_interval` code path):

| Block | Coverage before | Coverage after |
|---|---|---|
| 2026-03-01 | 93.6% | 91.5% |
| 2026-04-01 | 89.0% | 91.5% |
| 2026-04-15 | 80.1% | 84.7% |
| **Mean** | **87.6%** | **89.2%** |
| **Blocks >=90%** | **1/3** | **2/3** |

Reviewable count stayed at 1/3: block 2026-04-01's uncertainty gate now
passes, but that block still fails the separate `validated_domain` gate, so
its overall classification is unchanged. Aggregate WAPE unchanged (6.12%
baseline / 8.15% ensemble), confirming the same isolation.

**Honest read against the adopted target:** mean coverage is now close to 90%
on both farms, and the fix is methodologically justified (it fixes a real
fit/score mismatch, evidenced by the bias collapse), not padding. But by the
adopted pass/fail-per-block reading of the target ("90% of blocks meet their
coverage target"), the result is **2/5 Kelmarsh blocks and 2/3 Hill of Towie
blocks**, well short of the 90% of blocks bar and nowhere near the 95%
stretch. The remaining gap is a genuine small-sample, single-season (3 months
on one UK farm; 3 blocks across 2 months on Hill of Towie) limitation: 2-5
blocks per farm is not enough to assess a 90%-of-blocks rate with any
precision, and the per-block coverage still has real variance (block 2's
85.2%/84.5%, block 5's 88.1%/80.1%) that recency-window and regime-conditioning
experiments above failed to fully explain or close. This is reported as the
honest current state, not tuned further to cross 90%.

**Evidence:** [`src/windlens/reconstruct.py`](../src/windlens/reconstruct.py)
(`fit_weighted_references`, `predict_with_fitted_references`),
[`src/windlens/backtest.py`](../src/windlens/backtest.py)
(`_calibrate_and_evaluate_interval`),
[`tests/test_reconstruct.py`](../tests/test_reconstruct.py).

**Next step:** if more calibration blocks become available (more seasons, more
farms), re-test whether a recency-weighted or regime-conditioned interval
starts to help once there is enough data per condition -- both were rejected
here specifically because the available samples were too small/non-stationary
for them to work, not because the ideas are wrong in general.

### 2026-10-21 — RESULT — Direct-power regression beats wind-first on Kelmarsh too; ensembling still does not help

**What was checked:** whether the Hill of Towie finding (direct linear
power regression from a single reference's power to the target's power beats
wind-first reconstruction: 9.03% vs 10.10% aggregate WAPE, 189 events) also
holds on the Kelmarsh same-farm back-test. New script
[`src/windlens/run_kelmarsh_method_comparison.py`](../src/windlens/run_kelmarsh_method_comparison.py)
runs both methods on the same 5 Kelmarsh blocks and single best reference
(by `select_dynamic_references`) already used by `run_backtest.py`.

**Result:** direct linear power again beat wind-first: aggregate WAPE **9.30%**
(direct) vs **11.06%** (wind-first), both single-reference. Direct power won
4 of 5 blocks; the one loss (2016-05-29: 11.9% vs 11.1%) was narrow. Same-farm
caveat applies in full here -- Kelmarsh references are other turbines on the
*same* farm as the target, so this is not independent external-farm evidence;
it is a second same-farm data point consistent with the external-farm result,
which is the most this comparison can honestly claim.

**Ensembling direct power does not help either (quick check, as the brief
allowed):** weighting multiple references' direct-power fits by the same
inverse-holdout-RMSE behaviour weights the production ensemble already uses
made the aggregate WAPE *worse* (10.04% vs 9.30% single-reference), consistent
with the existing finding that ensembling (naive or behaviour-weighted)
underperforms a single well-chosen reference on this same-farm dataset. Noting
explicitly: the production ensemble in `backtest.py` (via
`select_dynamic_references`) is **already** inverse-error/behaviour-weighted,
not naive equal-weight -- it was never the naive case, and it still
underperforms the single-reference baseline (14.0% vs 11.6% WAPE, wind-first;
10.04% vs 9.30%, direct power). This is the same conclusion already on record
for the naive ensemble, now confirmed for the properly-weighted case too, so
no further ensemble work is planned.

**Decision:** direct power is the stronger method on both available farms now,
and single-reference direct power alone would cross the adopted 10% WAPE
target on Kelmarsh (9.30% < 10%), which wind-first does not (11.06%). It is
**not** being swapped in as the production/demo default tonight. Reason:
`workspace/` and the assessment JSON contract are built entirely around the
"reconstructed wind -> power curve -> kWh" narrative (the chart, the
methodology steps, the evidence register all show *wind*); switching the
scored method to direct power-to-power regression is a real product/demo
decision -- it changes what the UI shows and claims -- not a parameter tweak,
and per the project's own guardrails that kind of change should not happen
unilaterally overnight. It is recorded here as the clearest concrete next
step for WAPE, consistent with how the first Hill of Towie direct-power result
was handled ("retain both methods as challengers, do not switch the production
default based on the first result") -- except this is now the *second*
farm confirming the same direction, which is a stronger basis for a deliberate
decision than the first result was.

**Evidence:**
[`src/windlens/run_kelmarsh_method_comparison.py`](../src/windlens/run_kelmarsh_method_comparison.py),
[`data/derived/validation/kelmarsh_method_comparison.json`](../data/derived/validation/kelmarsh_method_comparison.json).

**Next step:** if/when Anna wants to pursue this, promoting direct power to
production means: (1) deciding how the workspace narrative and evidence
register describe the method (no more "reconstructed wind speed" chart, or a
reframed one), (2) building an uncertainty-interval calibration for direct
power predictions (none exists yet -- `uncertainty.py`/`backtest.py` only
calibrate wind-speed residuals), (3) re-running both farms' full gate
pipeline (domain checks, alignment, uncertainty) against the new method before
any claim changes in `docs/HANDOVER.md`.

### 2026-10-22 -- SCOPE -- Demo visual-quality reference (for later, not now)

**What:** Anna shared two real photos of real energy-market analyst platforms
(eq Energy's Battery Index dashboard and APG's grid-transparency portal) as a
calibration for the visual bar the WindLens demo should hit, saying plainly
that the current workspace "does really look like a very bad platform, AI
generated." The photo content is unrelated to WindLens (different market,
different data) -- only the visual register matters.

**What those references actually look like:** plain white/light-grey
background, no gradients or glassmorphism; dense but legible data (numeric
values printed directly on a choropleth map, not hidden behind hover-only
tooltips); a muted, desaturated palette (dusty purple/blue/orange, not
vibrant); small-caps sans-serif section labels; a flat text-list sidebar nav,
no icon-heavy card nav; a plain tab row for time granularity; simple
line/area time-series charts with inline legend callouts. The overall
impression is authentic, slightly utilitarian enterprise software built for
working traders/analysts -- not a polished startup landing page, not
"AI-generated-looking" (oversized rounded cards, heavy shadows, big
gradients, a giant hero number floating with no surrounding context,
excessive whitespace).

**Why this isn't new direction:** it concretizes, rather than changes,
`WindLens_instructions.md` section 11's existing design principle (Modo
Energy as the visual benchmark, "no gradients, glassmorphism, rainbow charts
... oversized dashboard theatre"). It's recorded here so it isn't lost before
the demo visual pass actually happens.

**Status:** explicitly deferred. Anna's own words: "the importance right now
is not to touch the demo, but it's to really see and validate the confidence
range." No workspace/UI changes made tonight because of this entry --
overnight effort stays on uncertainty-interval validation.

### 2026-10-22 -- RESULT -- Demo visual-quality pass implemented in `workspace/`

**What changed (presentation layer only -- no data, model numbers, or claims
touched):** this entry executes the visual direction scoped above. Read the
live assessment contract first
([`data/derived/assessment/kwf1_2016-07-07_assessment.json`](../data/derived/assessment/kwf1_2016-07-07_assessment.json),
regenerated 2026-10-21 01:23 by the overnight session) to confirm every number
still on screen is current: 107,495 kWh lost energy, "Estimate -- reviewable"
(zero failed gates), 95.9% observed coverage vs. 90% target, 8.4% relative
kWh error, KWF2 reference. Nothing in `workspace/assessment-data.js` or the
two `data/derived/assessment/*.json` files was edited.

**Visual changes, all in [`workspace/styles.css`](../../workspace/styles.css)
and [`workspace/index.html`](../../workspace/index.html):**
- Removed the soft drop-shadow (`--shadow`, used on every `.panel` and the
  chart tooltip) and the glow ring on the sidebar status dot. Flat 1px
  borders only now, matching the eq Energy / APG reference screenshots
  (no card "theatre").
- Replaced the warm cream background (`#f3f1eb`) and off-white panel fill
  (`#faf9f5`) with a plain light-grey page (`#f1f2f4`) and white cards
  (`#ffffff`), closer to the "plain white/light-grey background" Anna
  pointed to, and less "polished SaaS landing page."
- Normalized the extreme negative letter-spacing used on every large numeral
  and heading (hero kWh number was `-.085em`, three-column stat numbers
  `-.07em`, topbar h1 `-.055em`, commercial result `-.05em`, etc.) down to a
  consistent `-.02em`, and reduced the headline kWh number from 66px to 52px.
  That aggressive negative tracking on big digits is a recognizable
  trendy-SaaS/AI-template tell; normalizing it reads as plainer enterprise
  software instead.
- Left the small-caps eyebrow labels, DM Mono data typeface, navy sidebar,
  and muted orange/sage status accents alone -- those already matched the
  reference direction from section 11 and weren't the problem.

**Structural changes, matching Anna's own page-1/page-2 description verbatim
(logged above in this file, 2026-10-21 -- SCOPE entry's parent task):**
- `#overview` (page 1) now reads, top to bottom: headline lost-kWh number ->
  reconstructed-wind chart -> the three-panel dashboard (reference
  integrity / uncertainty / back-test) -> indicative commercial exposure.
  This was already close to the target order; the one change was moving the
  farm-metadata registry panel (`#registry-evidence`, `data-route` was
  `"assessment evidence"`) to evidence-only (`data-route="evidence"`), since
  it's provenance/registry detail, not part of the headline-number-then-chart
  story Anna described, and it duplicated nothing removed from `#evidence`.
- `#method` (page 2) already had the four-slide "what this proves / what it
  does not prove" summary followed by the detailed reconstruction/energy/
  limitations grid, but the two blocks ran together under one faint 1px
  line. Added an explicit labelled divider (`.method-divider`, a small-caps
  "Full methodology and limitations" label with an expanding rule) between
  them, so the slide summary and the detailed content read as two distinct
  sections, per Anna's "slide-like summary, then a visual divider, then the
  in-depth content" description.
- `#evidence` got the same shadow/background/letter-spacing pass; its
  structure (table + now the registry panel) was not otherwise changed.

**Copy:** the workspace copy had already been through an Oliver Wyman-style
wording pass the previous night (see the 2026-10-21 overnight entry above),
and a fresh check against `oliver-wyman-marsh-writing-style` found no
violations (serial commas, sentence-case headings, em-dash spacing, no
filler words were already correct). Made one small tightening edit: the
chart's hidden-truth caption ("Hidden truth is off by default because it
exists only for this simulated back-test.") became "Hidden truth stays off
by default -- it exists only for this simulated back-test." No other copy
was rewritten, to conserve tonight's budget rather than churn text that
already passed the style check.

**Guardrails followed:** no new dependency (still only the existing Google
Fonts `@import` for DM Mono/Manrope, already present before tonight); no
`.py` file touched; no data/evidence file touched; not a git repository, so
no git commands were run.

**Verification:**
- `node --check workspace/app.js` passes (app.js itself was not edited this
  session -- only `index.html` and `styles.css` changed).
- Served `workspace/` on loopback (`python -m http.server`) and checked all
  three hash routes (`#overview`, `#evidence`, `#method`) in a browser: the
  headline number, gates, chart, three-panel dashboard, commercial exposure,
  evidence table, and registry panel all render with live data matching the
  JSON above; the method-page divider renders as intended; nav active-state
  is correct per route (confirmed via DOM query, not just screenshot).

**Known pre-existing issue, not caused by and not fixed in this pass:** at
mobile width (375px) the page content overflows horizontally -- panel
headings and some flex rows do not wrap within the viewport even though the
`@media (max-width:900px)` rule correctly collapses the grid to one column.
None of tonight's edits touched grid/flex/width rules (only color tokens,
letter-spacing, font-size, shadow removal, and two `data-route`/divider
markup changes), so this is an existing responsive gap, not a regression.
Flagging it for whoever picks up `workspace/` next rather than spending
tonight's remaining budget on it, since Anna's visual reference (eq Energy,
APG) was desktop analyst software and the brief's "golden path" check here
was the desktop loopback view.

**Evidence:** [`workspace/styles.css`](../../workspace/styles.css),
[`workspace/index.html`](../../workspace/index.html).

**Next step:** if someone wants to take the visual pass further, the mobile
overflow above is the clearest next item, followed by a full line-by-line
copy rewrite (not needed tonight -- the existing copy already passed a style
check) if a harder tightening pass is wanted later.

### 2026-10-22 -- PROCESS -- Interpreting the "expand sample size, then
calibrate direct-power uncertainty" instruction

A second cross-session brief asked, in order: (1) pull many more
non-overlapping held-out blocks for both Kelmarsh and Hill of Towie before
trusting any coverage percentage -- 5 and 3 blocks respectively were too
small a sample -- including extending Kelmarsh's canonical extraction window
beyond its 90-day slice if the raw archive supports it, and checking whether
undercoverage concentrates in specific conditions (a seasonality/regime
question Anna asked earlier); then (2) calibrate an uncertainty interval for
the direct-power method using the larger block set, without promoting it to
production or touching `workspace/`. Same guardrails as before: no git, no
new dependency without flagging first, log everything including mixed
results, never adjust a number to cross a target. This entry is written
after the data scan and extraction had already started (read-only
investigation), per the same honest-sequencing note as the 2026-10-21
PROCESS entry. While working this, found
[`docs/AUDIT_2026-10-22_uncertainty_calibration.md`](AUDIT_2026-10-22_uncertainty_calibration.md)
-- an independent session's audit of last night's calibration fix, run in
parallel. Its most load-bearing finding for this work: small-sample
"N/5"/"N/3" pass rates carry roughly +/-40-point 95% confidence intervals
and should never be quoted bare. The result below applies that standard to
its own, larger numbers (see "statistical confidence" below) rather than
repeating the same gap at bigger n.

### 2026-10-22 -- RESULT -- Kelmarsh and Hill of Towie back-tests expanded to
19 and 28 blocks; coverage rate drops once the sample is larger, and is now
precise enough to say the 90% target is genuinely not met

**What changed:** built a second Kelmarsh canonical extraction,
[`kelmarsh_2016_full_year_canonical.csv`](../data/derived/kelmarsh_2016_full_year_canonical.csv)
(`src/windlens/build_kelmarsh_extended_dataset.py`), spanning the raw
archive's full declared range (2016-01-03 to 2017-01-01) instead of the
demo's 90-day window (2016-05-01 to 2016-07-30). This is a **separate file**
from `kelmarsh_2016_90d_canonical.csv`, which `run_assessment.py` and the
live `workspace/` demo still read unchanged -- extending the window does not
touch the demo. Extraction found the archive's turbines actually only log
valid readings from **2016-05-03 to 2016-12-31**, identical across all 6
turbines; the "2017-01-01" in the raw filenames is the nominal end of the
logging request, not real sensor coverage, so "full year" here means "full
available range," not calendar-year Jan-Dec. There is genuinely no Kelmarsh
data for January-April 2016 to test seasonality against -- confirmed as a
property of the source archive, not a filtering artefact on our part.

Scanned the extended dataset for every 5-day window with >=95% coverage for
KWF1 and all 5 reference turbines (scratch script), and greedily picked
non-overlapping ones spread May-December, explicitly excluding the one
candidate overlapping the live demo's already-showcased 2016-07-05/07-10
week (preserving the original back-test's documented reason for avoiding
it). Re-ran the original 5 blocks plus 16 new candidates through the same
calibrated pipeline
(`src/windlens/run_kelmarsh_extended_backtest.py`, using
`windlens.backtest.run_backtest_event` unchanged, including the 2026-10-21
fit/predict calibration fix); 2 of the 16 new candidates turned out to be
exact duplicates of 2 original blocks, leaving **19 unique blocks**, all
scored successfully (0 skipped).

For Hill of Towie, the existing yearly canonicals (2024, 2025, partial 2026)
already covered far more than the 3 blocks `run_hill_backtest.py` used (all
three in 2026-03/04). Scanned each year for >=95%-coverage 5-day windows for
T01 (scratch script) and picked roughly one per calendar month per year
(2024: 11, 2025: 11, 2026: the original 3 plus 3 more in Feb/Mar/Apr) =
**28 blocks total**, run via `src/windlens/run_hill_uncertainty_multiyear.py`
(same `run_backtest_event` call per block, each year's pre-event history and
reference selection confined to that year's own canonical file -- no
cross-year leakage). All 28 scored successfully.

**Results, with sample size and statistical confidence stated every time
(the audit above flags bare percentages as an existing gap in this project's
reporting; applying its standard here):**

| Farm | Blocks (old -> new) | Blocks meeting 90% coverage | Mean coverage |
|---|---|---|---|
| Kelmarsh | 5 -> 19 | 2/5 (40.0%) -> **9/19 (47.4%)** | 89.9% -> 90.8% |
| Hill of Towie | 3 -> 28 | 2/3 (66.7%) -> **17/28 (60.7%)** | 89.2% -> 89.8% |

95% confidence intervals (Wilson score, not Clopper-Pearson -- computed in
pure Python to avoid adding `scipy` as a new dependency; qualitatively the
same conclusion either way) on the pass rate:
- Kelmarsh: 2/5 was [11.8%, 76.9%] -- wide enough that "40%" and "77%" were
  statistically indistinguishable. 9/19 narrows this to **[27.3%, 68.3%]**.
- Hill of Towie: 2/3 was [20.8%, 93.9%] -- consistent with almost any true
  rate. 17/28 narrows this to **[42.4%, 76.4%]**.

This is the real payoff of the larger sample: at the old sample sizes, the
data could not rule out the true pass rate being close to 90% on either
farm. At the new sample sizes, the upper confidence bound sits at 68.3%
(Kelmarsh) and 76.4% (Hill of Towie) -- both comfortably below 90%. **The
working "90% of blocks individually meet 90% coverage" target is now not
just numerically unmet but statistically distinguishable from met, on both
farms.** That is a materially stronger and more honest claim than either the
5-block or 3-block samples could support.

Energy-weighted WAPE across the larger Kelmarsh sample: baseline 10.0%,
ensemble 11.7% (vs. the previously reported 11.6%/14.0% over just 5 blocks --
a different, larger sample, not a correction of the README's existing
numbers, which describe that original 5-block run specifically). Hill of
Towie's 28-block run: baseline 13.9%, ensemble 13.0%, using `ensemble_size=3`
weighted ensembling per block -- a different method from the single-
reference dynamic selection the method-sweep scripts use, so **not directly
comparable** to the 9.03%/10.10% Hill of Towie figures already in the
README; this run answers a different question (ensemble vs. baseline
coverage/WAPE at scale across many blocks), not "which method wins."

**Seasonality/regime question, answered differently per farm:**
- **Kelmarsh:** undercoverage concentrates clearly in blocks with short
  pre-event calibration history, not in any particular month or wind regime.
  All 4 blocks with less than 30 days of pre-event history (the earliest
  blocks in the dataset's life, 13-25 days) failed the 90% target (0/4, mean
  coverage ~85%); blocks with 30+ days of history passed 9/15 (60%). Mean
  wind speed showed no comparable pattern. This matches and sharpens last
  night's finding that Kelmarsh block 1 (14 days of history) was the
  earliest and weakest block -- it is not an isolated case, it is a
  systematic effect of too little calibration data early in the record.
- **Hill of Towie:** no comparably clean single-variable explanation was
  found. Pass rate by month ranges from 0/2 (June, both years failed) to
  2/2 (July, August, and October all passed both/all available years), but
  every month has only 2-5 blocks, too few to treat a month effect as
  confirmed rather than noise. Mean wind speed per block showed no
  correlation with pass/fail (both pass and fail blocks span roughly 3-9
  m/s). Pre-event history length does not explain it either -- unlike
  Kelmarsh, every Hill of Towie block already has 30+ days of history by
  construction (past the regime where Kelmarsh's effect showed up), and
  blocks with *less* within-year history actually passed *more* often (3/4)
  than blocks with more (14/24, 58%). Honest conclusion: Hill of Towie's
  undercoverage looks more like block-to-block noise around a true rate
  somewhat below 90% than a specific, fixable regime failure -- unlike
  Kelmarsh, where the mechanism (insufficient calibration history) is
  identified and specific.

**Reconciling with the parallel audit:** the audit's §1 finding (calibration
residuals are drawn from near-training data, not a truly independent
holdout) and §3 finding (the calibration *method* itself was picked by
best-score-on-these-same-5-blocks, a selection-bias risk) both concern the
*method*, not the event-level coverage statistic itself -- which the audit's
§4 independently confirms is computed correctly, per block, with no leakage
of the masked interval. The 16 new Kelmarsh blocks and 25 new Hill of Towie
blocks in this entry were never part of the four-way calibration-method
comparison the audit flagged, so the larger numbers above are to that extent
a genuine out-of-sample check on the method choice, not a repeat of the same
selection-biased evaluation on more data from the same contaminated process
-- though the audit's §1 concern (residuals scored on near-fitting data)
still applies equally to every block run here, old and new, since no change
was made to `_calibrate_and_evaluate_interval` itself this session.

**Guardrails followed:** no new dependency (Wilson interval computed in
plain Python, not `scipy`); no git command; EDP abstention, outage-detection
extension, and `workspace/` untouched; no number was widened or tuned to
cross 90% -- every figure above is a direct measurement from re-running the
existing calibrated pipeline on more blocks.

**Evidence:**
[`kelmarsh_2016_full_year_canonical.manifest.md`](../data/derived/kelmarsh_2016_full_year_canonical.manifest.md),
[`data/derived/validation/kelmarsh_extended_uncertainty_backtest.json`](../data/derived/validation/kelmarsh_extended_uncertainty_backtest.json),
[`data/derived/validation/hill_of_towie_multiyear_uncertainty_backtest.json`](../data/derived/validation/hill_of_towie_multiyear_uncertainty_backtest.json).

**Next step:** calibrate an uncertainty interval for the direct-power method
using this larger block set (the next entry in this log covers that), as
asked. Beyond tonight: Kelmarsh's undercoverage mechanism is identified
(insufficient calibration history) but not applied as a guardrail anywhere
-- e.g. a minimum pre-event-history gate before a block is even eligible to
be called "reviewable" -- and the audit's §1/§3 methodology concerns
(near-training-data residuals; calibration-method selection bias) are not
addressed by more blocks alone and would need a genuinely separate
development/holdout split to resolve properly. Both are product/methodology
decisions for Anna, not made unilaterally here.

### 2026-10-22 -- RESULT -- Direct-power regression now has its own
uncertainty interval; still beats wind-first on WAPE, still short of 90%
coverage, same early-history weakness

**What changed:** direct power-to-power regression (reference
`active_power_kw` -> target `active_power_kw`, no wind-speed step) had no
uncertainty interval of its own -- flagged as the explicit next step in the
2026-10-21 entry. Added
[`src/windlens/direct_power_uncertainty.py`](../src/windlens/direct_power_uncertainty.py)
(`fit_direct_power`/`predict_direct_power`/
`calibrate_and_evaluate_direct_power_interval`), applying the **exact same
fit-once/score-over-full-pre-event-history calibration pattern** used for
the wind-speed interval (2026-10-21) to power-domain residuals instead --
reusing `windlens.uncertainty`'s calibration functions unchanged, since they
are domain-agnostic. 5 new tests in
[`tests/test_direct_power_uncertainty.py`](../tests/test_direct_power_uncertainty.py).

Ran this across the same 19 Kelmarsh + 28 Hill of Towie blocks from the
entry above
(`src/windlens/run_direct_power_uncertainty_backtest.py`), using the **same
baseline reference turbine per block** the existing wind-speed pipeline
already selects (behaviour+geo dynamic selection), so direct-power and
wind-first are compared like-for-like, not against different references.

**Results (honest, with sample size and confidence interval stated):**

| Farm | Method | WAPE | Coverage (blocks meeting 90%) | Mean coverage |
|---|---|---|---|---|
| Kelmarsh (19 blocks) | Direct power | **6.3%**, bias -4.7% | 8/19 (42.1%, CI [23.1%, 63.7%]) | 85.8% |
| Kelmarsh (19 blocks) | Wind-first baseline | 10.0% | 9/19 (47.4%, CI [27.3%, 68.3%]) | 90.8% |
| Hill of Towie (28 blocks) | Direct power | **7.0%**, bias -0.8% | 17/28 (60.7%, CI [42.4%, 76.4%]) | 88.5% |
| Hill of Towie (28 blocks) | Wind-first baseline | 13.9% | 17/28 (60.7%, CI [42.4%, 76.4%]) | 89.8% |

Direct power clears the 10% WAPE target comfortably on both farms, now on a
much larger and more statistically defensible sample than the 5/3-block
figures from 2026-10-21 (9.30%/9.03%) -- a stronger version of the same
conclusion, not a different one. Its uncertainty coverage, now measurable
for the first time, is **not better than wind-first's**: Kelmarsh is
actually somewhat worse (42.1% vs 47.4% of blocks), Hill of Towie is
identical by coincidence of counts (17/28 both, though not necessarily the
same individual blocks -- not checked). Neither method clears the 90%
working coverage target on either farm. The same early-dataset-history
weakness found for wind-speed Kelmarsh calibration reproduces here too: the
four blocks with under 30 days of pre-event history (May 2016) are again
the weakest (56.5-89.0% coverage), consistent with this being a general
property of the calibration method and the dataset, not specific to the
wind-speed domain.

**What this means for the production-promotion decision (still not made
here):** direct power now has what it was missing -- an honest uncertainty
number, not just a WAPE advantage. It is a materially better WAPE method on
both farms at this sample size, and its coverage shortfall is no worse than
(and on Kelmarsh, mildly worse than) the wind-first method's existing
shortfall -- so coverage is not a new reason to prefer wind-first over
direct power; WAPE still favours direct power. Promoting it still requires
reworking the workspace's "reconstructed wind" narrative (direct power
skips the wind-speed step the chart currently shows) and is still a
product decision for Anna, not made unilaterally tonight, per explicit
instruction not to touch `workspace/` or promote it this session.

**Test suite:** 110 tests total (105 + 5 new). 100 pass; the same 10
Excel-connector tests the parallel audit already flagged fail with
`ModuleNotFoundError: No module named 'openpyxl'` -- a pre-existing
undeclared-dependency gap (no `requirements.txt`/`pyproject.toml` exists),
confirmed independently by that audit, not a regression introduced tonight.
`openpyxl` was not installed, per the no-new-dependency guardrail.

**Guardrails followed:** no new dependency (not even `openpyxl`, despite the
pre-existing test gap -- flagging it here rather than installing it); no
git command; `workspace/` untouched; direct power not promoted to
production; no number widened or tuned to cross a target.

**Evidence:**
[`data/derived/validation/direct_power_uncertainty_backtest.json`](../data/derived/validation/direct_power_uncertainty_backtest.json).

**Next step:** this closes out the two items in tonight's brief. Open for
Anna: (a) the production-promotion decision for direct power, now backed by
both a WAPE and a coverage number; (b) whether to apply a minimum-
pre-event-history gate (both methods' Kelmarsh weakness traces to the same
cause); (c) the parallel audit's methodology concerns (near-training-data
calibration residuals, calibration-method selection bias) remain
unaddressed and apply to both the wind-speed and the new direct-power
interval equally.

## 2026-10-22 — RESEARCH: literature and market scan (done now, not before build)

No literature or competitor review was done before building — the Codex plan
specified MCP wind reconstruction + power-curve loss estimation directly.
Anna asked for this scan after the fact, to see if it changes anything.
Honest finding: it validates the chosen approach rather than replacing it,
but surfaces one concrete lead for the open calibration problem.

**Algorithms/methodology (web search, not a full literature review):**
MCP for gap-filling and power-curve-based loss accounting (PCYA — benchmark
against a turbine's own historical power curve) are the standard approach in
both patents (e.g. a Windlogics farm-loss patent splitting losses into
availability/sub-curve/curtailment) and applied studies — consistent with
what this project already does. No peer-reviewed standard procedure exists
for combining MCP with a counterfactual power curve end-to-end; uncertainty
treatment varies by source (bootstrapping, round-robin holdout). One
concrete lead: **split-conformal prediction** has a known finite-sample
coverage guarantee (1-α to 1-α+1/(n+1)) and is model-agnostic — unlike our
current calibration, it requires a genuinely separate calibration set by
construction, which would directly address both open audit findings
(near-training-data residuals, calibration-method selection bias) rather
than patching around them. Not yet tried here. Not independently verified
beyond the paper abstracts (see search below).

**Market positioning (web search):** vendors in this space (Delfos, Clir
Renewables, DNV WindGEMINI, 3E SynaptiQ, WPO, OxMaint) sell SCADA-based loss
attribution and AI anomaly detection, usually marketed with a vendor-claimed
AEP-uplift percentage (e.g. "up to 10%", "up to 5%") and no visible
confidence interval or calibration disclosure on the number itself. None of
the sources found show an honest, stated uncertainty/coverage figure next
to their headline claim — WindLens's trust-first, "estimate vs. unverified"
framing (and admitting when coverage misses target, as logged above) is not
something this scan found a competitor doing publicly. That is a plausible
differentiator for the presentation, not just a technical choice.

**Caveat:** this was web search only (not full-text paper review, not a
systematic literature search) — treat as directional, not exhaustive.

**Next step:** Anna to decide whether split-conformal is worth prototyping
against the existing 19/28-block back-test before the presentation, given
the token budget.

## 2026-10-22 — RESEARCH (redone properly): full-text literature review + direct vendor-page due diligence

The above entry was explicitly web-search-only; Anna asked for a real pass. A
separate session read 5 papers in full text (not abstracts) and fetched 6
vendors' actual product/case-study pages directly (not search snippets).
Full detail: `docs/RESEARCH_2026-10-22_due_diligence.md`.

**Headline findings:** (1) split-conformal prediction (Angelopoulos & Bates,
arXiv 2107.07511) is a well-evidenced fix for the audit's Problem 1
(near-training-data residuals) if given a genuinely held-out, time-disjoint
calibration slice — recommended as the next prototyping step. A second,
more specialized paper (Liang/Zhu/Barber, arXiv 2408.07066) directly fixes
Problem 2 (calibration-method selection bias) without new data-splitting,
but is a heavier lift with thin real-data validation; a cheap interim fix
(pick the calibration method on a separate development slice of blocks) gets
most of the benefit for less budget. (2) Neither fixes the coverage
shortfall by itself: a published 2026 wind-turbine CQR paper (arXiv
2502.07344), using the textbook-correct method on real turbine data,
reported 86% coverage against an implied 90% target — direct evidence that
valid calibration does not guarantee clearing 90%. (3) The "we show honest
uncertainty, nobody else visibly does" claim holds up under direct
inspection of vendor pages (Delfos, Clir, DNV WindGEMINI/GreenPowerMonitor,
3E SynaptiQ, WindESCo/PulseSense all disclose zero uncertainty/validation
data publicly), with the caveat that this is about public marketing pages
only, not vendors' private technical documentation. Two previously-named
"vendors" were ruled out: OxMaint is general CMMS, not a wind-loss tool;
"WPO" could not be identified as a real company.

**Next step:** unchanged from the entry above — Anna to decide whether to
prototype split-conformal given the token budget; this pass adds evidence
that it is the better-justified of the two calibration fixes but should be
budgeted as a validity fix, not a guaranteed path to 90%+ coverage.

### 2026-10-23 — RESULT — Overnight method bake-off, dev/report split locked before any comparison

**What:** Full write-up: `docs/METHOD_BAKEOFF_2026-10-23.md`. Basics check passed
(110 tests/100 pass as documented, checksums verified, time-ordered splitting
confirmed enforced everywhere). Locked a dev/report split across all 47
back-test blocks (chronological, index-parity rule, decided before any block
was scored) specifically to avoid repeating the 2026-10-22 audit's
selection-bias trap. On the dev subset: direct-power regression re-verified
as the best point estimate (~2x lower WAPE than either wind-first variant,
both farms) — confirmed again on the untouched report subset (Kelmarsh 7.60%
vs. 9.73%/9.21%; Hill of Towie 6.82% vs. 11.85%/9.16%). Implemented
split-conformal calibration with a genuinely time-disjoint calibration slice
(`src/windlens/split_conformal.py`, 6 new tests) — the audit's recommended
Problem-1 fix. **Honest result: split-conformal is statistically
indistinguishable from the current (known-flawed) calibration at this sample
size** (pooled dev pass rate tied exactly at 11/24 for all three candidates
tested); its value is methodological validity, not a bigger number. On the
report subset, the 90%-of-blocks coverage target is still not met with
statistical confidence on either farm, by either method (Kelmarsh 95% CI
upper bounds 73.3%/81.1%; Hill of Towie identical 71.4% pass rate, CI
[45.4%, 88.3%], for both methods).

**Why no production change:** direct power remains not promoted to
production (unchanged guardrail from 2026-10-21/22 — still Anna's call);
`workspace/` untouched. `docs/HANDOVER.md`'s top summary is therefore not
updated this pass, per the brief's own instruction to only update it if the
recommended method actually changes from what's currently shipped.

## 2026-10-22 (late) — FIX — Priority item 1: trust-gate redesign to outage-time-only information (F1, F2)

**What changed, and why.** The red-team review (`docs/REDTEAM_2026-10-23_adversarial_review.md`,
F1/F2) found the "Estimate — reviewable" label was computed from two gates
that read the event's own hidden truth (`beats_baseline`, `uncertainty_gate_passed`),
which does not exist in a real outage, and that no gate checked whether the
reconstruction actually covered the event window — which let a Hill of Towie
block with only 31% reference coverage and a −70% kWh error get labelled
"reviewable". Changes, all in `src/windlens/`:

- **`review_gate.classify_estimate`**: the `beats_baseline` parameter (hidden-truth
  wind-RMSE comparison) is replaced by `completeness_passed`.
- **`backtest.py`**: added `reconstruction_completeness()` (fraction of the event
  window the reconstruction actually covers, from reference-reporting rows only —
  no hidden truth) and `input_qa_check()` (real duplicate-row check on the
  turbines the event uses, replacing the hard-coded `True`). Added
  `MIN_RECONSTRUCTION_COMPLETENESS_PCT = 90.0`. `beats_baseline` is still computed
  and returned in the event dict for back-test transparency (it is a legitimate
  back-test diagnostic since hidden truth exists there) but no longer feeds the
  gate.
- **`uncertainty_business.uncertainty_gate`**: now takes the pre-event
  *calibration* dict instead of the event's hidden-truth-scored `event_evaluation`.
  This also fixes the `"insufficient_calibration_observations"` bug (it was
  silently checking the event's own row count, not the calibration's).
- **`assessment.py`**: `input_qa_passed` now reads the real gate outcome instead
  of a hard-coded `True`.
- Added 8 new tests (`tests/test_backtest.py`, `tests/test_uncertainty_business.py`,
  `tests/test_review_gate.py`) including one that directly reproduces F2's failure
  mode (a sparse-reference block that must now fail the completeness gate).

**Re-ran the full back-test to check for mislabeled blocks.** Hill of Towie
2024-08-13 (the exact F2 case) now scores completeness 30.7% and is correctly
`Unverified — manual evidence required`, failed gate `['completeness']`. Checked
every Kelmarsh (19) and Hill of Towie (28) block by hand: no block with
estimate-vs-truth error >25% is labelled reviewable, **except one**: Hill of
Towie 2025-10-13 (54.3% error) still passes every gate. This is **not** an F1/F2
defect — completeness is 100% and calibration is well-populated; the cause is
F15 (separate, not in this session's scope): the *target* turbine itself was
likely curtailed/derated during the masked "healthy" window, which these gates
cannot detect since they check data availability, not operating state. Flagging
this honestly rather than hiding it: **the gate redesign does not close F15.**

**Side effect caught and fixed:** `run_assessment.py` picked its demo block with
`min(events, key=len(failed_gates))`. Under the new gates, 3 of the 5 original
blocks tie at zero failed gates, and `min` silently started returning a
*different* block (2016-06-26) than the one every filename and doc references
(`kwf1_2016-07-07_*`). Fixed by selecting the named block explicitly
(`run_assessment.py`). Regenerated `data/derived/assessment/kwf1_2016-07-07_*.json`
and `workspace/assessment-data.js`: the demo block is unchanged in substance
(107,494.95 kWh estimated vs. 117,372.94 kWh truth, reproduced exactly), still
labelled reviewable, and `input_qa_passed` now reflects a real check.

**Reviewable counts changed materially** because the new gates no longer
require clearing a hidden-truth-based bar: Kelmarsh 11/19 reviewable (was 3/19),
Hill of Towie 19/28 (was 11/28). This is the correct, intended effect of removing
a gate that cannot run in production — it is not evidence the method got better.
`docs/HANDOVER.md`'s top summary needs updating to state this; see that file.

**Known gaps, not addressed by this item (by design, out of scope for item 1):**
- F15 (target curtailment confound, above) — needs an operating-state filter on
  the masked target's own "healthy" window, not just the reference.
- F11's UI-copy mismatch: `workspace/app.js`'s "Uncertainty gate" trust-panel row
  still displays `coverage_pct` vs. `coverage_target` as if that were the gate's
  basis — it isn't, anymore. The gate now checks calibration sample size. This is
  bucketed under priority item 6 (hygiene) and not fixed here.
- The demo's `app.js:55` "Coverage met the calibration target on this block"
  text and the `app.js:59` "Uncertainty gate" label text are otherwise unchanged
  — still F11, still deferred to item 6.

**Test suite:** 124 tests (was 116; +8 new), 114 pass, 10 pre-existing
`openpyxl`-missing errors (unchanged, unrelated to this change). No regressions.

**Next:** priority item 2 (F5 — event-level kWh uncertainty interval on the hero
number).

## 2026-10-22 (late) — FIX — Priority item 2: event-level kWh uncertainty interval on the hero number (F5)

**What changed, and why.** The red-team review (F5) found the demo's hero kWh
number and EUR exposure were point values with no range at all; the only
"90% interval" anywhere was wind-speed, and the one kWh-propagation function
that existed (`uncertainty_business.propagate_power_interval`) was dead code
that, when actually run, produced an almost-uninformative interval (median
width ~98% of the point estimate on Kelmarsh) because it assumes errors are
perfectly correlated across the whole event — a false assumption given
measured 6-hour-lag autocorrelation of only ~0.05-0.14.

- **`uncertainty_business.event_level_kwh_interval`** (new): takes the
  empirical distribution of `|relative kWh error|` this method actually
  produced across back-test events and uses its upper quantile (default 90th
  percentile) as a symmetric half-width around today's point estimate — the
  red-team's own recommended replacement. Also reports a nonparametric
  bootstrap 95% CI of that quantile itself, since n is only 19-28 events per
  farm (the red-team's explicit ask: "report it with its own sampling
  uncertainty"). `propagate_power_interval` is left in place (still a valid
  generic helper) with a docstring note that it is not the production source.
- **`assessment.build_assessment_record`**: new optional `kwh_interval` param,
  stored at `estimate.kwh_interval`; added a `limitations` bullet explaining
  the interval's basis and its own sampling uncertainty.
- **`run_assessment.py`**: computes the interval from the Kelmarsh 19-block
  extended back-test's wind-first-ensemble per-event errors (not the original
  5-block set — too few events for a stable quantile), applied to the demo
  block's point estimate. Result: half-width 16.6% (90th pct), band
  89,625–125,365 kWh around the 107,495 kWh point estimate, n=19, bootstrap CI
  of the half-width itself [15.0%, 27.8%] — consistent with the red-team's own
  "~17% Kelmarsh wind-first" figure.
- **`workspace/index.html` + `app.js`**: added `#hero-kwh-range` under the hero
  kWh number and `#commercial-range` under the EUR exposure, both now rendered
  from `kwh_interval`. Verified in the browser pane (screenshot taken): renders
  correctly, no layout regression. `node --check workspace/app.js` passes.

**What this does not fix (deferred, F11):** `app.js:55`'s "Coverage met the
calibration target on this block" text and the "Uncertainty gate" trust-panel
row still describe *wind-speed* pointwise coverage, not this new kWh band —
that UI-copy cleanup is bucketed under priority item 6.

**Test suite:** 127 tests (was 124; +3 new), 117 pass, same 10 pre-existing
`openpyxl` errors. No regressions.

**Next:** priority item 3 (F6+F7+F8 — point-estimate method comparison:
WAPE-alignment bug, variance-ratio MCP, reference-operating-state filter).

## 2026-10-22 (late) — FIX — Priority item 3: point-estimate method comparison, three fixes (F6, F7, F8)

**What changed, and why.** The red-team review found the bake-off's "direct power
wins decisively, roughly 2x lower WAPE on both farms" verdict rested on three
defects. All three are now fixed:

- **F6 (WAPE scoring bug), `backtest.py`'s `_score` closure:** wind-first used to
  integrate estimated power over only the reconstruction's own timestamps but
  actual power over the *entire* window, so a reference gap silently deflated
  the estimate relative to a truth that counted the whole window — direct
  power's inner-join never had this problem. Both are now inner-joined on
  timestamp before integrating, so `estimated_lost_kwh`/`actual_lost_kwh` are
  always computed on identical rows.
- **F7 (biased MCP variant), `reconstruct.py`:** `fit_linear` gained a `method`
  parameter (`"ols"` default, `"variance_ratio"` new). OLS shrinks predicted
  wind variance toward the mean under noise (measured ratio 0.81–0.83 on
  Kelmarsh pre-fix), which under-estimates energy through the power curve's
  convex region (Jensen's inequality). `reconstruct_wind_speed` and
  `fit_weighted_references` — the actual wind-first reconstruction path — now
  use `variance_ratio`; `_time_ordered_holdout_r2` (reference-selection
  ranking only) is unchanged, still OLS, since minimizing squared error is the
  right objective for *ranking* candidates, not for the final energy estimate.
- **F8 (no reference-operating-state filter), `direct_power_uncertainty.py`:**
  added `reference_operating_state_check()` — flags a reference reporting
  wind well above cut-in (≥4 m/s) but power near zero (≤1% of rated) for more
  than 20% of the event window. Wired into
  `calibrate_and_evaluate_direct_power_interval` and the bake-off's
  `_direct_power_block`; both now abstain instead of silently scoring a ~0 kW
  prediction. The exact Hill of Towie 2024-08-13 case (reference T04 stopped,
  −98.5% error) now abstains with reason "reference T04 looks stopped for 99%
  of the event window".
- 13 new tests across `tests/test_backtest.py`, `tests/test_reconstruct.py`,
  `tests/test_direct_power_uncertainty.py`.

**Re-ran the full comparison with all three fixes in place.** Extended
back-tests: Kelmarsh WAPE dropped from 10.0%/11.7% (baseline/ensemble) to
**5.9%/6.8%**; Hill of Towie from 13.9%/13.0% to **10.4%/9.4%**. Re-ran the
locked dev/report point-estimate comparison
(`run_method_bakeoff_2026_10_23.run_point_estimate_comparison`):

| Farm | Subset | Wind-first baseline | Wind-first ensemble | Direct power | Winner |
|---|---|---|---|---|---|
| Kelmarsh | dev (n=10) | 6.14% | 9.11% | 5.16% | direct power, narrowly |
| Kelmarsh | report (n=9) | 5.54% | **4.41%** | 7.60% | **wind-first ensemble** |
| Hill of Towie | dev (n=13, 1 abstained) | 9.24% | 9.68% | 4.01% | direct power |
| Hill of Towie | report (n=14) | 11.86% | 9.09% | 6.82% | direct power |

**Honest re-statement, replacing "direct power, 2x better, both farms, both
subsets":** there is no single winner anymore. Direct power still wins clearly
on Hill of Towie (both subsets, ~1.3-1.7x). On Kelmarsh, the methods are close
on dev and **wind-first ensemble actually wins on the report subset** — the
opposite of the original claim on that farm/subset. Updated
`docs/METHOD_BAKEOFF_2026-10-23.md` with a correction note at the top (the
original Sections 3/5/6 are left as the historical record of what was measured
*before* this correction, not deleted) and `README.md`'s WAPE table with a
pointer note (the table itself is still on the old 5/3-block numbers — full
refresh is item 6/F14).

**Side effect, expected and re-verified:** `run_assessment.py`'s demo block
(2016-07-07) now reconstructs with variance-ratio MCP too. Re-ran it:
estimate 114,770 kWh vs. 117,169 kWh truth (2.0% error, down from the old
OLS-based 8.4%), still labelled reviewable, event-level kWh interval
half-width now 13.4% (down from 16.6%, consistent with the lower measured
WAPE). `node --check` passes on both `app.js` and the regenerated
`assessment-data.js`.

**What this does not fix / known residual gaps:**
- Dev-vs-report instability (e.g. Kelmarsh wind-first ensemble: 9.11% dev vs.
  4.41% report; baseline beats ensemble on dev for both farms but not on
  report) is itself evidence of how noisy these comparisons are at n=9-14 per
  subset — flagged honestly, not smoothed over. No further investigation
  attempted; out of scope for this item.
- The uncertainty-calibration comparison (Section 4 of the bake-off doc,
  split-conformal vs. current) was not re-run — item 3's brief scoped only the
  point-estimate comparison (F6/F7/F8), not calibration method selection.
- `README.md`'s full WAPE/coverage tables, `PROJECT_STATE.md`, and
  `HANDOVER.md`'s test-count drift remain stale — bucketed under item 6 (F14).

**Test suite:** 134 tests (was 127; +7 new), 124 pass, same 10 pre-existing
`openpyxl` errors. No regressions.

**Next:** priority item 4 (F4 — replace the "% of blocks ≥90%" coverage target
with pooled coverage plus a dispersion diagnostic).

## 2026-10-22 (late) — FIX — Priority item 4: replace the "% of blocks ≥90%" coverage target with pooled coverage (F4)

**What changed, and why.** The red-team review (F4) showed "90% or more of
blocks individually hit 90% coverage" is unattainable by construction: a
simulated *perfectly calibrated* 90% interval, scored per 5-day block under
this project's own measured residual autocorrelation (median rho ≈ 0.6-0.7),
clears that bar only ~45-58% of the time. Every doc reporting "9/19 blocks
(47.4%)" etc. as a failure was reporting an artefact of the metric, not a
real defect — and was simultaneously failing to report the real issue: how
much individual blocks vary (genuine evidence of conditional mis-calibration,
e.g. short pre-event history).

- **`uncertainty.pooled_coverage_summary`** (new): pooled coverage (covered
  observations ÷ total observations, across every scored point in every
  block) plus per-block mean/std/min/max/p10/p90 as the dispersion
  diagnostic. 2 new tests.
- **`run_kelmarsh_extended_backtest.py` + `run_hill_uncertainty_multiyear.py`**:
  both now compute and print pooled coverage as the headline; the old
  block-pass-rate figures are kept (renamed with a `_NOT_A_MEANINGFUL_TARGET`
  suffix in the JSON artifact) as secondary, clearly-labelled context, not
  deleted.
- **Re-ran both scripts.** Pooled coverage: **Kelmarsh 91.9%** (std 5.4pp,
  range 80.1-99.4%), **Hill of Towie 90.2%** (std 6.8pp, range 72.5-99.7%) —
  both at or above the 90% target. (These numbers also reflect item 3's
  variance-ratio MCP change, run earlier tonight — not re-isolated from it.)
- **Doc corrections across every place stating the old framing:**
  `README.md` (two sections — "Uncertainty-interval coverage" and "What this
  means against the 90%/95% goal" — correction notes added, historical tables
  kept below them), `docs/PROJECT_STATE.md` ("Next steps" point 3),
  `docs/HANDOVER.md` (top summary — this also fixed a note from item 1's
  checkpoint that items 3/4 had since made stale), `docs/METHOD_BAKEOFF_2026-10-23.md`
  (Section 6 "Honest verdict"). All as correction notes above the original
  text, not silent rewrites — the historical record of what was measured
  before each correction stays visible and labelled.

**What this does not fix:** `README.md`'s numeric tables (5/3-block figures)
are still stale in absolute terms — only annotated, not replaced with current
19/28-block numbers. A full numeric refresh is item 6 (F14).

**Test suite:** 136 tests (was 134; +2 new), 126 pass, same 10 pre-existing
`openpyxl` errors. No regressions.

**Next:** priority item 5 (F3 — re-scope the pitch: validated for
single-turbine same-farm outages; the challenge's neighbouring-farm scenario
is untested).

## 2026-10-22 (late) — FIX — Priority item 5: re-scope the pitch honestly (F3)

**What changed, and why.** The red-team review (F3) found the project's
pitch overclaims external validity. The BayWa challenge brief
(`WindLens_instructions.md:9-11`) describes a *whole-farm* outage
reconstructed from a *neighbouring farm's* reference data. Every validated
number in this project is single-turbine, same-farm proxy reconstruction
instead: Kelmarsh's references are 0.27-0.75 km away on the same farm, same
turbine model; Hill of Towie's are 0.34-0.52 km away, also same farm, also
same turbine model. Hill of Towie being a *different farm from Kelmarsh* is
real and useful evidence (rules out Kelmarsh-specific overfitting) but was
being mis-described as testing the challenge's actual scenario, which it
does not — its own `honesty_note` field said "a genuinely external farm (not
same-farm, unlike Kelmarsh)", true about the farm but silent on the fact
that its *references* are same-farm, which is what the challenge scenario
actually depends on.

- **`README.md`**: added a "Validated scope" section right after the opening
  pitch paragraph, stating plainly (with exact distances/turbine models) that
  validation is single-turbine same-farm proxy reconstruction and that the
  challenge's neighbouring-farm scenario is untested; corrected the
  "Hill of Towie is the only genuinely external-farm result" line (same
  defect as the `honesty_note` above) to say what Hill of Towie's
  same-farm-ness of its *references* actually means; corrected the "What it
  does" list's gate description, stale since item 1.
- **`run_hill_uncertainty_multiyear.py`**'s `honesty_note` field: corrected
  and expanded, same substance as the README fix. Regenerated
  `data/derived/validation/hill_of_towie_multiyear_uncertainty_backtest.json`.
- **`workspace/`**: no change needed. The demo's `limitations` list
  (`assessment.py`) already states "Kelmarsh reference assets are same-farm
  peer proxies, not a separate neighbouring farm" and is rendered on screen —
  checked and confirmed this predates and already satisfies this finding for
  the Kelmarsh demo record specifically.
- **`docs/PROJECT_STATE.md`/`docs/HANDOVER.md`**: checked for the same
  "external farm" language; existing mentions there are about the EDP
  connector's data-source separation guardrail, not performance claims — no
  change needed.

**What this does not fix:** no code or method changed — this item is
documentation-only, correcting claims to match what was actually validated.
The underlying gap (no neighbouring-farm back-test exists) remains open; the
red-team review's own "what I could not check" section flags searching for a
public neighbouring-farm dataset pair as "the most valuable follow-up," not
attempted here or by this session.

**Test suite:** 136 tests, 126 pass, same 10 pre-existing `openpyxl` errors
(no code changed except the `honesty_note` string). No regressions.

**Next:** priority item 6 (hygiene — F9-F11, F13, F14 — only if budget
remains).

## 2026-10-22 (late) — SESSION CLOSE — Items 1-5 complete; item 6 deliberately skipped

**Stopping point, and why.** All five substantive priority items from the
red-team review's "Suggested priority order for Anna" are complete, tested,
and checkpointed above (F1/F2, F5, F6/F7/F8, F4, F3). Per the session's own
guardrail ("getting the top 2-3 items solidly right beats rushing all 6 and
leaving something broken"), and acting on Anna's explicit caution about
session usage limits (a sibling session hit a hard usage-limit error earlier
tonight), this session stops here rather than starting item 6's hygiene
cleanup (F9-F11, F13, F14) now. The project is left in a consistent,
fully-tested state — nothing is mid-edit.

**Item 6 is a real, legitimate remaining item, not resolved by this
session.** What it would cover, left for the next session or Anna's own
pass:
- **F9:** two overlapping block pairs in the bake-off's "non-overlapping"
  Kelmarsh split, plus the bake-off doc's own factual errors (the split-
  conformal CI number, the overstated exchangeability guarantee) — the "2x"
  overclaim part of F9 is already fixed by this session's item 3.
- **F10:** the demo's showcase block is chosen by outcome
  (`min(events, key=len(failed_gates))` in `run_assessment.py`, now
  explicitly pinned to the named 2016-07-07 block by this session's item 1
  side-fix, but the underlying "best-of-N" selection logic for *future*
  arbitrary block choices is untouched) -- not in Anna's priority list,
  flagged by the red-team as "defensible with a fix", not required.
- **F11:** UI copy that still contradicts actual behaviour --
  `workspace/app.js:55`'s "Coverage met the calibration target on this
  block" and the "Uncertainty gate" trust-panel row still describe
  wind-speed coverage as the gate's basis, which item 1 changed (now
  calibration sample size); the false "not calculated" labels for 30/180-day
  reference windows (they ARE calculated and rejected); the chart plotting
  the unweighted ensemble mean rather than the scored inverse-RMSE-weighted
  model; method slide 03's "compare transparent wind-first and direct-power
  challengers" when the demo record has no direct-power result.
- **F13:** replace tautological test assertions (`test_backtest.py:117`'s
  `assertIn(label, (REVIEWABLE, UNVERIFIED))`,
  `test_direct_power_uncertainty.py`'s `0 <= coverage <= 100`) with ones that
  can actually fail; add tests for gates-avoid-hidden-truth, dev/report
  disjointness, and statistical validity on synthetic residuals.
- **F14:** reconcile test-count and block-count drift across
  `README.md`/`PROJECT_STATE.md`/`HANDOVER.md`/`DECISION_LOG.md` so they all
  state the current 136-test, 19/28-block reality consistently (this
  session's own edits added more drift sources by necessity -- e.g.
  README's WAPE table is now doubly stale, annotated but not replaced).

**Final verification before stopping:** full test suite re-run one more
time (136 tests, 126 pass, same 10 pre-existing `openpyxl`-missing errors,
unchanged all session -- `openpyxl` was never installed, per the
no-new-dependency guardrail). The demo workspace was re-checked live in the
browser pane after all five items' changes (screenshot taken): hero kWh
(114,770, was 107,495 before item 3's MCP fix), its new event-level range,
the EUR range, and all four trust gates render correctly with no layout
regression. No `git` command was run at any point (not a git repository). No
new dependency was installed.

## 2026-10-23 — Item 1: whole-site masking stress test (Kelmarsh)

**Framing, verbatim (also in `src/windlens/evidence_tiers.py` and the JSON):**
whole-site masking stress test, ~300-400m reference separation — a best-case
ceiling bound, NOT a neighbouring-farm validation.

**What was built.** `src/windlens/run_kelmarsh_whole_site_masking_backtest.py`
(+ `src/windlens/evidence_tiers.py` for the shared tier labels, +
`tests/test_whole_site_masking.py`, 4 tests). Output:
`data/derived/validation/kelmarsh_whole_site_masking_backtest.json`.

**Why it is not a rewrite.** `run_backtest_event` already takes an explicit
`candidate_reference_turbines` list and draws references *only* from it
(ranking, dynamic selection, fits, domain checks, alignment gate). Restricting
that list to the surviving half *is* the whole-site mask on the reference side;
no gate / calibration / WAPE logic is duplicated. Rather than trust that by
reading, `assert_no_masked_peer` re-checks every event's output (baseline +
ensemble references) and the test suite includes a fixture where the masked-half
peer is a *perfect copy* of the target (so it would be chosen if allowed) and
asserts it never is.

**Setup.** South = {KWF1, KWF4, KWF6}, north = {KWF2, KWF3, KWF5} (latitude
split agreed 2026-10-23). Each half is masked as a whole; each masked turbine is
reconstructed from the three surviving-half turbines only. Blocks: the existing
19 Kelmarsh extended blocks (all scored with >=95% coverage of every Kelmarsh
turbine when they were selected for the same-farm test, so no re-selection and
no outcome-based choice here). 3 targets x 19 blocks x 2 scenarios = 114 events.
A **paired comparison** was run on the same targets and blocks with all five
other turbines available (today's same-farm method) so the cost of whole-site
masking is measured against the exact same events.

**Results (ensemble, event-level WAPE / signed aggregate bias / reviewable / pooled 90% coverage):**

| scenario | whole-site mask | same-farm paired (same targets+blocks) |
|---|---|---|
| south masked <- north refs | WAPE 9.5%, bias -3.4%, 39/57 reviewable, cov 88.2% | WAPE 8.7%, bias -3.5%, 33/57, cov 88.7% |
| north masked <- south refs | WAPE 8.0%, bias -4.7%, 33/57, cov 88.1% | WAPE 7.2%, bias -3.8%, 33/57, cov 88.1% |

So taking the whole site away costs roughly **+0.8 pp WAPE** (both halves) on
this geometry; accuracy and coverage are essentially unchanged. Mean
reference distance actually used: 534 m (whole-site) vs. 431-471 m (paired).

**Discrepancy to be aware of (self-critique).** The agreed label says "~300-400m
reference separation". That is the north-south band gap. The *measured* half-to-half
turbine-pair distances are **271 m to 935 m, mean 534 m**. The verbatim label is
kept (agreed) but the measured range is stored in the JSON
(`half_to_half_distance_m`) and must accompany the label in any UI.

**What this does and doesn't prove.**
- It DOES show the pipeline does not silently depend on having same-farm
  fallback turbines: with zero fallback, it still works and its gates/intervals
  behave as before. That was untested until now.
- It does NOT validate a neighbouring-farm scenario: all references are within
  ~1 km, same ridge, same inflow. Best-case ceiling only.
- The 114 events are NOT independent (same 19 blocks reused across 6 targets;
  turbines sharing weather). Treat effective sample size as ~19 blocks x 2.
- "Reviewable" count rising from 33 to 39 (south) under the harder condition is
  a gate artefact (different reference sets pass/fail the alignment and domain
  checks differently), not evidence the harder setup is *better*. Do not read
  reviewable counts as accuracy.
- Pooled coverage 88% is slightly under the 90% nominal, as in the same-farm test.

## 2026-10-23 — Item 2 (setup checkpoint, written BEFORE any cross-farm result was computed)

**Data.** Penmanshiel SCADA 2016 (Zenodo 10.5281/zenodo.16807304, Plumley & Takeuchi,
Cubico, published 2025-08-13). Downloaded only the files needed into
`data/raw/penmanshiel/`: `Penmanshiel_SCADA_2016_WT01-10_3107.zip` (129 MB),
`Penmanshiel_SCADA_2016_WT11-15_3107.zip` (56 MB), `Penmanshiel_WT_static.csv`
(2 KB), plus the Zenodo record JSON. MD5s of all three match the values Zenodo
publishes (3819e1b2..., 92c30453..., c4cd4191...). **Licence: CC BY 4.0, same
publisher/authors/licence as Kelmarsh** (confirmed in the record's `license.id`);
attribution is recorded in `data/derived/penmanshiel_2016_canonical.manifest.json`
and the module docstring of `build_penmanshiel_dataset.py`. Downloaded with `curl`
(no new dependency). A stray `data/raw/penmanshiel/.claude-flow/` tooling folder was
auto-created by a hook when a shell sat in that directory; it is not data (the
safety hook blocked my delete, so it remains and can be removed by hand).

**Format check (not assumed).** Same Greenbyte export as Kelmarsh: `# Date and time`
header row, UTC, 10-minute, identical column names (`Wind speed (m/s)`, `Wind
direction (°)`, `Power (kW)`), files `Turbine_Data_Penmanshiel_NN_...csv`. Static CSV
has 14 turbines (T01-T15, no T03) with latitude/longitude from the publisher
(52.40N,-0.94E Kelmarsh vs. 55.90N,-2.29E Penmanshiel), but carries blank padding
rows and an unnamed trailing column -> `FarmRegistry.from_csv` now drops wholly
empty rows/columns (never fills values) and reads `utf-8-sig`. Extraction reuses
`prepare_dataset.extract_canonical_slice` unchanged for Kelmarsh via two new
parameters (`turbine_file_pattern`, `turbine_id_format`; defaults reproduce the old
behaviour) so both farms get identical QA/plausibility rules. Output:
`data/derived/penmanshiel_2016_canonical.csv` (253,617 rows, md5 6ddc7f93...).

**Things a reviewer will ask about.**
- Penmanshiel's 2016 data start at commissioning (2016-06-02 to 07-27 per turbine);
  declared commercial operations date is **2016-09-01**. Back-test blocks start 2016-09-01.
- Hardware/terrain differ: Kelmarsh Senvion MM92 (78.5 m hub, 92 m rotor, ~145-157 m
  elevation); Penmanshiel MM82 (59 m hub, 82 m rotor, ~180-228 m elevation, hillier).
- The shared plausibility rule drops negative standby power (physically normal at
  standstill) as "implausible": 21,847 Kelmarsh rows, 71,197 Penmanshiel rows (mostly negative power; a minority are out-of-range wind speeds). That
  punches holes in calm windows, so Penmanshiel coverage since 2016-09 is only
  70-85% per turbine, and blocks passing a coverage bar skew toward windy, fully
  operating periods (already true of the same-farm blocks). Not changed here
  (would alter all earlier evidence); flagged as an open data-prep question.

**Pre-registered design** (also in the docstring of
`run_kelmarsh_penmanshiel_crossfarm_backtest.py`): whole-farm outage on the target
side (candidates = other farm only, asserted per event); 5-day non-overlapping grid
from 2016-09-01 to 2017-01-01; eligibility = target >=90% of slots and >=5 reference-
farm turbines >=90%; targets = all 6 Kelmarsh (ref Penmanshiel) and all 14
Penmanshiel (ref Kelmarsh); method/gates/thresholds untouched (`run_backtest_event`
as-is); paired same-farm run on identical targets+blocks. **The 90% coverage bar
was chosen over 95% purely on block counts taken before any back-test ran:** 95%
gave 5 / 3 blocks (22 / 32 events), 90% gives 8 / 9 blocks (47 / 96 events); 85%
(11 / 13) was counted, not used. No other threshold or block set was tried.

## 2026-10-23 — Item 2 RESULT: Kelmarsh <-> Penmanshiel real cross-farm backtest

Framing, verbatim: real cross-farm backtest at ~399 km separation (Kelmarsh,
Northamptonshire vs. Penmanshiel, Scottish Borders) — a realistic-distance floor,
NOT a neighbouring-farm validation: the challenge's actual neighbouring farm is
expected to land between this and the whole-site ceiling (Item 1).
Artifact: `data/derived/validation/kelmarsh_penmanshiel_crossfarm_backtest.json`.
Run exactly as pre-registered above; nothing (method, gates, thresholds, blocks)
changed after seeing results.

| direction | cross-farm (events) | WAPE | bias | reviewable | pooled 90% cov | median abs event err |
|---|---|---|---|---|---|---|
| Kelmarsh masked <- Penmanshiel refs | 47 | **13.1%** | -5.8% | 19/47 | 87.6% | 10.6% |
| Penmanshiel masked <- Kelmarsh refs | 96 | **14.2%** | -0.8% | 70/96 | 88.6% | 12.2% |
| same-farm, same-farm refs (Kelmarsh targets) | 84 | 9.0% | -6.3% | 59/84 | 88.0% | 8.5% |
| same-farm, same-farm refs (Penmanshiel targets) | 108 | 6.2% | -5.1% | 57/108 | 88.3% | 5.2% |

Concurrent 10-minute wind-speed correlation, Sep-Dec 2016 (descriptive, not used by
the method): cross-farm mean r = **0.44** (0.32-0.53) vs. within Kelmarsh 0.86 and
within Penmanshiel 0.97.

**Reading it honestly.**
- It is not "unworkable": energy error roughly doubles (6-9% -> 13-14% WAPE) at ~400 km
  and the 90% interval still covers ~88%. It is not good either: ~13-14% of 5-day energy.
- Why WAPE stays this moderate despite r=0.44: events are 5-day energy totals, so errors
  at 10-minute scale largely average out, and the fit is variance-matched with the
  target's own power curve. Do not read 13-14% as "10-minute accuracy".
- **A finding against our own gates:** with a 0.44 raw correlation, the gates still pass
  70/96 Penmanshiel-target events as "reviewable". They check alignment sample size,
  domain, completeness and calibration size, not how strong the cross-farm relationship
  is. For distant references the gate is not discriminating; do not use it as a
  distance guard (open item).
- **The "paired same-farm" comparison is NOT event-for-event** (my earlier description
  was wrong): eligibility is evaluated separately for it (84/108 events vs. 47/96), so
  the event sets overlap but differ. It is same targets and calendar grid only. Per-event
  paired data were not saved, so an intersection comparison needs a re-run (not done).
- Skipped: 97/144 Kelmarsh-target and 240/336 Penmanshiel-target target-block slots
  failed the >=90% input-availability rule (the 70-85% Penmanshiel coverage issue
  logged above). Surviving blocks skew windy/fully-operating.
- Events within a direction share blocks and weather: not independent; effective sample
  is roughly the 8-9 blocks per direction.
- Terrain/hardware differ (MM92 78.5 m vs MM82 59 m hub); this mixes distance with
  hardware and climate effects, so it is a floor for "far, different farm", not a clean
  distance-response curve.
- Tier ordering supported by data: whole-site ceiling (Item 1) ~8-9.5% WAPE <
  cross-farm floor ~13-14%. The neighbouring-farm case remains untested.

**Not done (scope reduced by the coordinating session at Anna's request to conserve
usage):** Item 3 (workspace three-tier integration and full-slide methodology
redesign) was stopped part-way. State left: `workspace/index.html`, `styles.css`,
`app.js` contain an UNVERIFIED first draft (deck markup/CSS/JS, tiers panel) and
`src/windlens/build_evidence_tiers_data.py` is written but NOT run, so
`workspace/evidence-tiers-data.js` does not exist (the page shows a "not generated"
message in the tiers panel). Nothing from item 3 has been checked in the browser.
README "Validated scope" and HANDOVER were not extended beyond the note below.
Tests: 145 total, 135 pass, same 10 pre-existing `openpyxl` errors.

## 2026-10-23 — Item 3 completed (resumed at Anna's request after the earlier stop)

Supersedes the "Not done" paragraph above. Built and browser-checked (pane at 1280x800
emulation, then reset):
- **Three-tier panel** ("Validated scope", Assessment + Evidence views) driven by
  `workspace/evidence-tiers-data.js`, generated from the three validation JSONs by
  `python -m windlens.build_evidence_tiers_data` (no hand-typed numbers; each tier carries its
  source path). Tier 1 6.8% / Tier 2 8.8% / Tier 3 13.9% WAPE, each with its verbatim framing,
  a "does not prove" line, and a log-scale distance bar marking the untested neighbouring-farm gap.
  Tier headline numbers are different statistics (Tier 1 energy-weighted, Tier 2/3
  event-count-weighted means of two sub-results) -- labelled in each card, not interchangeable.
- **Methodology deck** replaces the click-and-swap text: six full-stage slides with a signal-colour
  curtain wiping the whole stage while content swaps underneath (direction-aware), staggered reveal,
  tab rail, prev/next, <-/-> keys, Present (fullscreen), reduced-motion fallback. Verified: navigation
  01->02->03->02, a mid-transition frame showing the full-stage curtain, slide 05 (Evidence) fitting
  its stage with framing text on all three tiers. Slide copy also fixed two stale claims (slide 03
  no longer says "compare wind-first and direct-power challengers" as if both appear in the record).
- Not verified: mobile layout beyond a quick narrow-pane glance, real fullscreen "Present" mode,
  keyboard navigation (code path only), other browsers. CSS/JS are cache-busted via `?v=` in index.html.
- Evidence-slide cards are compacted (3 stats, framing only); full detail incl. "does not prove"
  is in the Validated-scope panel.

## 2026-10-23 — Independent re-verification (coordinating session, after the sub-session hit its usage limit)

The sub-session that built items 1-3 ended its final turn mid-report with a hard
usage-limit error; its last relayed message said item 3 was "stopped, unverified" --
that was stale (composed before the limit hit, during an earlier stop/resume cycle).
The actual state on disk, and the "Item 3 completed" entry directly above, show it
finished and verified the work before running out of budget. Independently
re-checked here, fresh, not reusing the sub-session's claims:
- Started a local server, loaded `#overview`, `#method`, `#evidence`. Zero console
  errors on all three routes.
- Confirmed the three-tier panel's numbers match `docs/DECISION_LOG.md`'s own Item 1
  and Item 2 RESULT entries exactly (6.8% / 8.8% / 13.9% WAPE), with the "does not
  prove" captions present and correctly worded.
- Clicked through the full 6-slide methodology deck one slide at a time (not
  batched -- a batched multi-click test gave a false "stuck" reading because the
  element ref went stale between clicks; sequential clicks worked correctly every
  time). All 6 slides render with real content, the tab rail and counter track
  correctly, slide 6 ends on the honest "what we cannot claim yet" framing.
- Checked mobile width (375px): confirmed a 158px horizontal overflow, but traced
  it to the page shell/sidebar (same pre-existing issue flagged in this file's
  2026-10-21 entries, not new tonight) -- not the tier panel or slide deck, which
  were not the source.
- Full test suite: 145 tests, 135 pass, same 10 pre-existing `openpyxl` errors.
  Matches the sub-session's own last-reported count exactly.

**Conclusion: items 1, 2, and 3 are all genuinely complete, tested, and now
independently browser-verified.** Nothing further needed from this handoff.
Still open, unchanged from the sub-session's own honest list: real fullscreen
"Present" mode, keyboard navigation, other browsers, and a fuller mobile pass
(pre-existing, not new).

## 2026-10-23 — Reference-selection weighting ablation (Anna's request)

**Anna's brief, verbatim:** "I think we should test different behaviors when
choosing the method for the most alike turbines. then we can check that we
thought about different things, and I think this makes sense."
`src/windlens/dynamic_reference.py::select_dynamic_references` ranks
candidate reference turbines by `selection_score = 0.8*behavior + 0.2*
geography` (behavior = holdout R²/RMSE from a time-ordered fit; geography =
inverse distance). This weighting was chosen and shipped without ever being
tested against an alternative. Tested honestly tonight, using the exact same
dev/report discipline the method bake-off already established (not a new
split): reused `data/derived/validation/method_bakeoff_2026_10_23.json`'s
`locked_split` key verbatim (Kelmarsh 10 dev / 9 report, Hill of Towie 14 dev
/ 14 report).

**Code change (both backward-compatible, no behaviour change for any
existing caller):** `select_dynamic_references` gained a `behavior_weight:
float = 0.8` parameter (geography gets `1 - behavior_weight`), replacing the
hard-coded `0.8`/`0.2` literals. `run_backtest_event` gained a passthrough
`behavior_weight: float = 0.8`. Every existing call site (`backtest.py` and
nine other scripts/tests) passes neither argument, so every existing
back-test number in this project is reproduced unchanged -- verified: full
suite still 145 tests, 135 pass, same 10 pre-existing `openpyxl` errors, and
the Kelmarsh report-subset wind-first-ensemble WAPE recomputed with the new
parameter at its default reproduces the bake-off's own number exactly
(4.41%, see below).

**Candidates tested (Anna's list, all four, including the one expected to
lose):** current shipped blend (0.8/0.2), 100% behavior / 0% geography,
50/50, and 0% behavior / 100% geography (floor/sanity check). New script:
`src/windlens/run_reference_weighting_ablation.py`. Reference selection
feeds the whole downstream pipeline (which turbine is "the" reference, which
three form the ensemble, their weights), so each candidate re-runs the full
wind-first back-test (`run_backtest_event`), not just the selector in
isolation.

**Dev-subset results (method selection happens here only):**

| Farm | Candidate | Ensemble WAPE | Bias | Pooled coverage |
|---|---|---|---|---|
| Kelmarsh (n=10) | current 80/20 | 9.11% | -9.02% | 91.6% |
| Kelmarsh (n=10) | 100% behavior | 10.39% | -9.85% | 91.6% |
| Kelmarsh (n=10) | 50/50 | 8.15% | -8.07% | 92.5% |
| Kelmarsh (n=10) | 0% behavior (geography-only) | 8.24% | -8.16% | 92.2% |
| Hill of Towie (n=14) | current 80/20 | 9.68% | -6.86% | 88.0% |
| Hill of Towie (n=14) | 100% behavior | 9.95% | -7.62% | 88.4% |
| Hill of Towie (n=14) | 50/50 | 9.06% | -6.17% | 88.0% |
| Hill of Towie (n=14) | 0% behavior (geography-only) | 9.43% | -6.38% | 87.0% |

The spread across all four candidates is small (Kelmarsh 8.15-10.39%, Hill of
Towie 9.06-9.95%) and, notably, the floor candidate (geography-only) is NOT
clearly the worst on either farm at this sample size -- it actually beats
"current" and "100% behavior" on Kelmarsh dev. That alone is a sign the
differences are noise, not signal, so a block-level bootstrap (5,000
resamples, resampling whole blocks with replacement, matching the pre-mortem
discipline already used for the calibration comparison) was run before
reading anything into the ranking:

| Farm | Candidate | Point WAPE | 95% bootstrap CI |
|---|---|---|---|
| Kelmarsh (n=10) | current 80/20 | 9.11% | [6.34%, 11.74%] |
| Kelmarsh (n=10) | 100% behavior | 10.39% | [6.86%, 13.46%] |
| Kelmarsh (n=10) | 50/50 | 8.15% | [5.49%, 10.54%] |
| Kelmarsh (n=10) | geography-only | 8.24% | [5.42%, 10.93%] |
| Hill of Towie (n=14) | current 80/20 | 9.68% | [5.19%, 14.91%] |
| Hill of Towie (n=14) | 100% behavior | 9.95% | [5.54%, 14.96%] |
| Hill of Towie (n=14) | 50/50 | 9.06% | [4.10%, 14.63%] |
| Hill of Towie (n=14) | geography-only | 9.43% | [4.82%, 14.01%] |

**Every candidate's 95% CI overlaps every other candidate's 95% CI, on both
farms.** This is exactly the same "noise, not signal" pattern the
calibration-method comparison (`docs/METHOD_BAKEOFF_2026-10-23.md` §4) found
when comparing `current` vs. `split_conformal_30pct` vs. `split_conformal_
50pct` -- and the same honest response applies: picking whichever candidate
scored marginally best here would be exactly the Problem-2 selection-bias
trap this whole dev/report discipline exists to avoid, even on the dev side
of the lock.

**Decision rule, stated independently of which number looks best (same
discipline as the calibration choice): keep the current 80/20 blend.**
Reasoning, not the numbers above:
1. Geography is a physical plausibility prior (nearby turbines share more
   microclimate/wake exposure), not a directly-validated predictive signal.
   A candidate that drops geography to 0% has no regularizer against
   holdout-estimation noise in the behavioural RMSE itself (computed from a
   20% holdout of a 30-180 day window) -- it could pick a turbine that
   scored well on a noisy small holdout while being less physically
   plausible, with nothing to catch that. Ruling out 100% behavior.
2. The 0% behavior (geography-only) candidate is the floor/sanity check by
   design -- it ignores the one signal with any direct evidence of
   predictive quality. That it isn't measurably worse than the others at
   n=10-14 blocks is a comment on this sample size's resolving power, not a
   reason to make a pure-geography heuristic the production default.
   Ruling out 0% behavior.
3. Between 0.8 and 0.5: the directly-validated signal (behavior) should
   dominate, with geography acting as a tie-breaker/regularizer rather than
   a co-equal partner -- the same principle that motivated the weighting
   when it was first chosen, independent of today's numbers.
4. Switching to a numerically indistinguishable alternative would silently
   change every other already-published number in this project that depends
   on `select_dynamic_references` (every Kelmarsh/Hill of Towie back-test,
   the whole-site masking stress test, the cross-farm backtest) for no
   honest statistical gain -- the same reasoning the calibration choice used
   to reject chasing a noise-level win.

**Report-subset result, computed exactly once, for the chosen (current)
weighting, after the decision above was locked in -- also serves as a
reproducibility check of the new `behavior_weight` parameter:**

| Farm | Metric | Value |
|---|---|---|
| Kelmarsh (n=9) | ensemble WAPE | **4.41%** (bias -3.10%) |
| Kelmarsh (n=9) | pooled coverage | 92.2% |
| Hill of Towie (n=14) | ensemble WAPE | **9.09%** (bias -4.33%) |
| Hill of Towie (n=14) | pooled coverage | 92.3% |

Kelmarsh's 4.41% reproduces `docs/METHOD_BAKEOFF_2026-10-23.md`'s own
report-subset wind-first-ensemble number **exactly** (its correction note:
"wind-first ensemble actually wins on the report subset (4.41%...)"),
confirming the new parameter changes nothing for the default weighting.
Hill of Towie's 9.09% is close to, not identical to, the bake-off's own
9.16% -- both computed from the same locked report blocks and the same
pipeline; the small residual difference is not investigated further here
(bounded, does not change any conclusion).

**Artifacts:** `data/derived/validation/reference_weighting_ablation_2026_
10_23.json` (dev subset, all four candidates, per-block kWh pairs for
reproducibility) and `..._report.json` (report subset, chosen weighting
only). **Verdict: the shipped 0.8/0.2 weighting is retained, now because it
was honestly tested and found no worse than three alternatives (including
the floor case) at this sample size, not because it was never questioned.**
No change to any other project number. Full test suite: 145 tests, 135 pass,
same 10 pre-existing `openpyxl` errors.

**Next:** red-team hygiene items F9/F11/F13/F14, and the four "insurer's
lens" quick fixes.

## 2026-10-23 — Hygiene: F9, F11, F13, F14 (red-team priority item 6, finalized)

Deliberately skipped by a prior session to conserve budget after items 1-5
("Session stopped after item 5 (F3), deliberately"); finalized now per
Anna's request to finish the remaining red-team items.

**F9 (Kelmarsh bake-off split overlap + doc factual errors):**
- Two Kelmarsh block pairs (2016-05-17..05-22 / 2016-05-20..05-25, and
  2016-05-27..06-01 / 2016-05-29..06-03) overlapped by 2-3 days each and
  landed on opposite sides of the bake-off's "locked, disjoint" dev/report
  split. Fixed in `run_method_bakeoff_2026_10_23.py`: the two overlapping
  report-side blocks are now excluded from `KELMARSH_REPORT` (9 -> 7 blocks;
  dev stays at 10), and a new `_assert_disjoint_calendar_ranges` runs a real
  date-range check at import time (not just a count assert). Historical
  report-subset numbers computed under the old 9-block split are left as
  published (F9's own verdict: bounded effect, no conclusion changes) --
  not recomputed.
- Fixed the doc's own factual errors: the split-conformal CI-upper-bound
  claim ("modestly exceeds 90%" when the actual value, 81.1%, is below 90%)
  and the overstated "actual finite-sample guarantee" claim (split-
  conformal's guarantee requires exchangeable residuals, which this
  project's autocorrelated 10-minute data does not have -- the pre-mortem
  already said so; the verdict had dropped that caveat). The "2x" WAPE
  overclaim was already fixed by a prior session (item 3).
- Fixed two stale docstrings/comments: `run_kelmarsh_extended_backtest.py`
  said "21 non-overlapping... 16 new" (true: 19 blocks / 14 new, two pairs
  overlapping); `run_backtest.py` claimed none of the original 5 blocks
  overlap the spike week, when the demo block (07-07 to 07-12) overlaps it
  by 3 days.
- New test: `tests/test_method_bakeoff_split.py` (4 tests) -- asserts real
  calendar disjointness for both farms, proves the check can catch a genuine
  overlap (not tautological), and pins the corrected Kelmarsh split counts.

**F11 (UI copy contradicting actual behaviour):**
- `workspace/app.js`: "Empirical residual interval calibrated on a prior
  contiguous block" (false since 2026-10-21) -> "calibrated on the full
  pre-event history (in-sample, not a held-out block)".
- `workspace/index.html`: "30/180 days · not calculated in this record"
  (false -- both were calculated and rejected) -> "evaluated, not selected
  (worse holdout fit)".
- `run_assessment.py`: the chart line called `reconstruct_wind_speed_
  ensemble` (unweighted equal-mean) while the printed coverage/interval are
  for the scored `reconstruct_wind_speed_weighted` model (inverse-RMSE
  weights) -- the two differed by up to 0.41 m/s and the drawn band's
  empirical coverage (95.1%) didn't match the printed number (95.9%). Now
  both come from the same weighted model. Regenerated
  `workspace/assessment-data.js` and verified live in the browser (local
  server on a session-private port, since another session's demo server
  was already running on 8000): drawn-band coverage is now 95.6% against a
  printed 96.4% (small residual gap is display subsampling -- 90 plotted
  points out of hundreds -- not a model mismatch). Headline kWh number
  (114,770) is unchanged, since the backtest's own scoring already used the
  weighted model; only the separate chart-only reconstruction call was
  wrong. The already-fixed items from F11's list (Input QA unconditional
  tick = F1; method-slide-03 direct-power-challenger claim = prior
  session's item 3) were re-verified, not re-fixed.

**F13 (tautological tests + missing coverage):**
- `test_backtest.py`: `assertIn(label, (REVIEWABLE, UNVERIFIED))` ->
  `assertEqual(label, REVIEWABLE)` + `assertEqual(failed_gates, [])`
  (verified the fixture deterministically produces REVIEWABLE first).
- `test_direct_power_uncertainty.py`: `0 <= coverage <= 100` (true by
  construction) -> pinned exact deterministic values from the fixed-seed
  fixture (observations=34, covered=24, coverage=70.588235%,
  width=134.392230 kW).
- New test class `RunBacktestEventDynamicSelectionTests` in
  `test_backtest.py`: exercises `run_backtest_event(..., metadata_df=...)`
  end to end (the dynamic-selection path every published number actually
  uses -- previously only the `metadata_df=None` branch was tested).
- New test `test_silently_integrates_mismatched_length_arrays_
  independently` in `test_loss_estimate.py`: documents `estimate_loss`'s
  lack of timestamp awareness directly (mismatched-length arrays integrate
  independently with no error) -- the exact hazard that caused F6, with a
  comment pointing to the real fix (the caller's inner join in
  `backtest.py::_score`) and its own regression test.

**F14 (test/block-count drift across docs):**
- Current authoritative count (re-run after all F9/F13 test additions):
  **154 tests, 144 pass**, same 10 pre-existing `openpyxl` failures.
  `README.md` ("105 of 105"), `docs/PROJECT_STATE.md` ("105 tests pass"),
  and `docs/HANDOVER.md` ("110 tests, 100 pass") all updated to this number.
- `docs/PROJECT_STATE.md`'s "one block out of five passing" / "3 of 19
  Kelmarsh blocks reviewable" framing (dated 2026-10-21, pre-dating both the
  19/28-block expansion and the 2026-10-22 trust-gate redesign) is left as
  historical record with an inline note pointing to the current 11/19
  figure in `docs/HANDOVER.md`'s top addendum, rather than rewritten --
  consistent with how this file treats its own dated history elsewhere.
  README's WAPE/coverage tables (5/3-block era) already carry correction
  notes pointing to the current 19/28-block numbers from a prior session;
  not further rewritten here (same bounded-scope reasoning: the numbers
  readers would act on are already correct via the notes, only the
  underlying historical table is stale by design).

**Test suite after all of F9/F11/F13/F14:** 154 tests, 144 pass, same 10
pre-existing `openpyxl` errors (verified below, combined with Part B.2's
fixes). No `git` command run. No new dependency installed.

**Next:** the four "insurer's lens" quick fixes.

## 2026-10-23 — Four "insurer's lens" quick fixes, finalized

1. **Scope note (cause classification).** Added, verbatim as specified, to
   `README.md` (right under the opening pitch paragraph) and to the
   workspace's own limitations list (`src/windlens/assessment.py`'s default
   `limitations`, which feeds `workspace/app.js`'s on-screen limitations
   panel): "WindLens estimates the counterfactual production during an
   outage; it does not determine or classify the cause (mechanical failure
   vs. grid curtailment vs. other) -- that must come from an external
   source." Documentation only, no modeling change, as specified.

2. **EUR exposure label.** The existing disclaimer ("Scenario only; not
   settlement, liability, or legal value.") was already present but in
   small, separate fine print below the range line, several DOM elements
   away from the number itself. Added a second, visually distinct
   "INDICATIVE DEMO PRICE" badge directly beside the `EUR 9,755.47` figure
   itself (`workspace/index.html`'s `.commercial-result`, new
   `.value-with-badge`/`.indicative-badge` CSS in `workspace/styles.css`),
   with a full-sentence tooltip. Verified live in the browser (session-
   private server on port 8011, since another session's demo server
   occupies 8000): the badge renders directly next to the number, not
   buried in fine print. Both the existing disclaimer and the new badge are
   kept -- belt and braces, not a replacement.

3. **Lazy baseline.** New `src/windlens/lazy_baseline.py`
   (`lazy_baseline_estimate_kwh`): equal-weighted average capacity factor
   (active_power_kw / that turbine's own rated_power_kw) of every available
   same-farm turbine during the event window, scaled to the target's own
   rated power -- no wind reconstruction, no fit, no reference selection.
   New `src/windlens/run_lazy_baseline_comparison.py` runs it over the
   exact same Kelmarsh 19-block and Hill of Towie 28-block sets already
   used by the existing extended back-tests, for direct comparability.
   **Result, and it is a genuinely surprising one, reported as measured,
   not softened:**

   | Farm | Lazy baseline WAPE | Wind-first baseline WAPE | Wind-first ensemble WAPE | Direct power WAPE |
   |---|---|---|---|---|
   | Kelmarsh (19 blocks) | **5.67%** (bias -3.16%) | 10.04% | 11.71% | 6.34% |
   | Hill of Towie (28 blocks) | **5.86%** (bias -3.89%) | 13.88% | 12.99% | 6.98% |

   The simplest possible method -- the farm average, scaled to nameplate --
   **beats every wind-first variant on both farms and is competitive with
   (even nominally better than) direct-power regression**, the method this
   project's own bake-off called "the genuinely best-performing method."
   This is not a bug: averaging five-to-twenty correlated same-farm
   turbines' capacity factors cancels idiosyncratic single-reference noise
   that a single best-reference wind-first (or direct-power) fit cannot,
   and Kelmarsh/Hill of Towie turbines are highly correlated same-model
   peers a few hundred metres to a few km apart -- exactly the regime where
   a naive farm average is expected to do well. It is also exactly what
   F3's "defensible differentiator" paragraph in the red-team review already
   named as the industry-standard baseline this project's complexity would
   need to earn its place against, and today it has not clearly done so on
   WAPE alone (direct power's narrower tails under F8 and wind-first's
   physical chain for a genuine neighbouring-farm scenario, untested here,
   remain the stated reasons for the extra machinery -- not WAPE on this
   same-farm problem). **This is a material finding for the project's own
   honesty standard and is flagged here explicitly, not buried**: the
   current pitch and demo do not claim WindLens beats a naive average, and
   should not, without re-stating this comparison. Artifact:
   `data/derived/validation/lazy_baseline_comparison_2026_10_23.json`.
   New tests: `tests/test_lazy_baseline.py` (4 tests).

4. **Curtailment/derating training-row filter.** New
   `windlens.power_curve.flag_likely_curtailed_rows` + `fit_power_curve`'s
   new opt-in `exclude_likely_curtailed` parameter (default `False` --
   **not applied retroactively to any already-published back-test number**,
   exactly as instructed). Rule: within each wind-speed bin, a row is
   flagged only if its power is more than `CURTAILMENT_FLAG_STD_THRESHOLD`
   (2.0, a documented, not-tuned-against-results choice) standard
   deviations BELOW that bin's own mean, and the bin has at least 5
   observations (fewer is not a meaningful scatter estimate). Deliberately
   one-sided: normal turbulence scatter is roughly symmetric around the
   curve, but curtailment/derating produces unusually LOW power for the
   wind speed observed, never unusually high -- a high outlier is never
   flagged, by design (tested directly: `tests/test_power_curve.py`'s
   `test_never_flags_a_high_outlier_even_though_it_is_also_a_statistical_
   outlier`). This directly targets F15's plausible mechanism (curtailed/
   derated "healthy" truth confounding method ranking) at the training-data
   level, not the truth-window level -- F15 itself (whether back-test
   target windows are genuinely curtailment-free) remains open, unresolved
   by this fix, and is not attempted here (out of scope for a quick fix;
   needs status/alarm logs this project doesn't have, per F15's own "what I
   could not check"). New tests: `tests/test_power_curve.py` (5 new tests;
   9 total in that file).

**Verification:** `node --check workspace/app.js` passes (app.js itself
unchanged this section; styles.css/index.html changes are non-executable).
Browser-verified live (badge placement, no console errors). Full test
suite: 163 tests, 153 pass, same 10 pre-existing `openpyxl` errors (see
below for the final combined run). No `git` command run. No new dependency
installed.

**What was NOT done, explicitly:** the lazy-baseline result (item 3) is a
finding, not a fix -- no pitch, README claim, or workspace copy was
rewritten to react to it; that is a product-framing decision for Anna, not
made here, flagged clearly above instead. The curtailment filter (item 4)
is not applied to the shipped reconstruction pipeline's actual power-curve
fit (`backtest.py` still calls `fit_power_curve` with its default,
unchanged behaviour) -- enabling it there is also a methodology decision
for Anna, since it would change every back-test number currently published,
not something to flip silently in a hygiene pass.

## 2026-10-23 — SESSION CLOSE: ablation + all six priority-list items complete

Both pieces of Anna's request are done: the reference-selection weighting
ablation (Part A) and all of red-team priority item 6 (hygiene F9/F11/F13/
F14) plus the four insurer's-lens quick fixes (Part B). Nothing stopped
early; no usage-limit issue hit this session.

**Final state:**
- `select_dynamic_references`'s 0.8/0.2 behavior/geography weighting is
  retained, now backed by an honest ablation against three alternatives
  (all statistically indistinguishable at n=10-14 dev blocks) rather than
  never having been tested.
- F9 (split overlap + doc errors), F11 (UI-copy mismatches), F13
  (tautological tests + missing coverage), F14 (doc/test-count drift) are
  all fixed and verified.
- Scope note, EUR-exposure badge, lazy-baseline comparison, and curtailment
  filter are all shipped. **The lazy-baseline finding (farm average beats
  every wind-first variant, competitive with direct power) is the most
  important new fact from this session and is not yet reflected in any
  pitch, README headline, or workspace copy -- flagged as the clearest next
  product-framing decision for Anna.**
- Full test suite: **163 tests, 153 pass**, same 10 pre-existing `openpyxl`
  errors (unchanged all session; no new dependency installed; no `git`
  command run at any point).
- `docs/HANDOVER.md`'s top addendum and `README.md`/`docs/PROJECT_STATE.md`'s
  test counts updated to match.

**Next work, in order of what a reader would most want to act on:**
1. Decide how (or whether) to message the lazy-baseline finding in the
   pitch -- it's the single most consequential fact from tonight.
2. F10 (demo block chosen by outcome) and F15 (curtailment confound on back-
   test target windows) remain open, as previously documented; F15 is
   partially addressed at the training-row level by tonight's curtailment
   filter but the filter is not yet enabled on the shipped pipeline.
3. The real neighbouring-farm validation gap (this project's single
   biggest unresolved claim, per F3) remains untested, as stated everywhere
   else in this project's own documentation.

## 2026-10-23 — RESULT: cross-farm lazy baseline test (Anna's request)

**Anna's brief, verbatim:** "test whether the lazy baseline still wins at
cross-farm distance (i think after this we have a good tests, models, and
methology to argue for)."

**Why the same-farm lazy baseline isn't directly portable to cross-farm:**
the same-farm lazy baseline (`src/windlens/lazy_baseline.py`) averages
*surviving same-farm* turbines. In the actual challenge's farm-wide-outage
scenario there are no surviving same-farm turbines to average -- that's
precisely why a neighbouring-farm method is needed at all. The fair,
analogous cross-farm lazy baseline instead averages the *reference farm's*
available turbines (Penmanshiel's, when reconstructing Kelmarsh; Kelmarsh's,
when reconstructing Penmanshiel) during the event window, scaled to the
target's own nameplate power -- same mechanism, same capacity-factor logic,
just drawn from the other farm.

**Implementation:** `src/windlens/run_crossfarm_lazy_baseline_comparison.py`
(new orchestration script; `lazy_baseline_estimate_kwh` itself needed no
change -- it already accepts any `available_turbines` list, so passing the
reference farm's turbine IDs instead of same-farm peers was sufficient;
no capacity-factor logic was duplicated). Runs over the **exact locked
(target, block_start) event set already scored** by the real wind-first
cross-farm backtest -- read back directly from
`data/derived/validation/kelmarsh_penmanshiel_crossfarm_backtest.json`'s own
`per_event` lists for both directions, not re-derived or re-selected. Same
47 Kelmarsh-masked / 96 Penmanshiel-masked events, same target/reference
farm assignments, same 90%-coverage eligibility rule that produced them.
All 47/47 and 96/96 locked events scored (nothing newly skipped).

**Result:**

| Direction | Lazy cross-farm WAPE | Wind-first cross-farm WAPE |
|---|---|---|
| Kelmarsh masked, Penmanshiel reference (n=47) | **22.30%** (bias +18.02%) | 13.09% |
| Penmanshiel masked, Kelmarsh reference (n=96) | **19.09%** (bias -14.64%) | 14.25% |

Artifact: `data/derived/validation/crossfarm_lazy_baseline_comparison_
2026_10_23.json` (per-direction WAPE/bias, per-event kWh pairs, the exact
wind-first numbers it's compared against, for reproducibility).

**Honest read, reported as measured, hoped-for outcome did not shape the
build:** the naive cross-farm average **loses clearly** at ~399 km
separation -- roughly 1.4-1.7x worse than wind-first (22.3% vs 13.1% on one
direction, 19.1% vs 14.2% on the other), a full reversal from the same-farm
result where the lazy baseline *beat* wind-first (5.67%/5.86% vs
10-14%). This is the second, useful outcome the brief described, not the
first: the naive average does not win regardless of distance -- it degrades
badly specifically because it ignores farm-specific scaling, hub height
(78.5 m Kelmarsh vs 59 m Penmanshiel), power-curve, and climate/terrain
differences between two genuinely independent, ~400 km-apart sites, which
matter far more across farms than between same-farm peers a few hundred
metres to a few km apart. A fitted wind-first reconstruction can partially
correct for exactly these differences (dynamic reference selection,
regression fit, calibrated interval) and so holds up comparatively better,
even though its own cross-farm WAPE (13-14%) is itself worse than its
same-farm WAPE (5.9-6.8%) -- distance costs the sophisticated method too,
just less than it costs the naive one.

**What this settles, stated plainly:** the same-farm lazy-baseline finding
(F-insurer's-lens item 3) does NOT generalize to "the simple method wins
regardless of distance" -- it does not. At genuine neighbouring-farm
distance, the complexity earns its place on WAPE alone, not only on
auditability or tail behaviour. The project's defensible story is now: same
farm, keep it simple (the naive average is competitive or better, and that
should be said plainly, not hidden); genuinely different farm, the
reconstruction machinery is doing real, measurable work. Both facts should
be stated together, not just the flattering one.

**Guardrails followed:** no `git` command run. No new dependency added. No
change to `workspace/`, the pitch, or any README claim -- this is a
measurement, reported here only. Full test suite re-run after the code
addition: 163 tests, 153 pass, same 10 pre-existing `openpyxl` errors --
unchanged, no regression.

**Not done:** no product-framing or pitch change in reaction to this result
-- same stance as the same-farm finding, this is Anna's call, flagged here
plainly instead.

## 2026-10-23 — Tier 1 of "running the entire matrix" (Anna's request)

**Anna's brief, verbatim:** "i think we should do 'Running the entire
matrix'." The full brief asked for the complete method x scenario matrix,
checkpointed after each tier; tier 1 (cross-farm single-reference wind-first
+ direct power) is the highest-priority piece and the one this entry covers.

**What was missing before today:** at real cross-farm distance
(Kelmarsh<->Penmanshiel, ~399 km), only wind-first ensemble and the lazy
average had ever been run. Single-reference wind-first and direct power had
never been tested at this distance -- both were cross-farm gaps.

**Event set: not re-derived.** Both methods below run over the exact locked
(target, block_start) pairs already scored by the real wind-first ensemble
cross-farm backtest, read back from
`kelmarsh_penmanshiel_crossfarm_backtest.json`'s own `directions.*.per_event`
lists -- same 47 Kelmarsh-masked / 96 Penmanshiel-masked events, same
target/reference-farm assignments, nothing newly selected.

**Surprising discovery: the single-reference number already existed.**
`run_backtest_event` (the function the cross-farm ensemble backtest already
calls) computes the single-best-reference baseline alongside the ensemble on
*every* call -- `backtest.py`'s `aggregate_backtest` already aggregates both
as `"baseline"` and `"ensemble"`. Those baseline numbers were already sitting,
unread, inside `kelmarsh_penmanshiel_crossfarm_backtest.json`'s own
`directions.*.cross_farm.aggregate.baseline` -- computed in the 2026-10-23
1:40am cross-farm run, never surfaced in `docs/HANDOVER.md` or this log,
which only ever cited the ensemble's 13.1%/14.2%. New script
`src/windlens/run_crossfarm_full_matrix_tier1.py` reads them back directly
(byte-identical, not recomputed) and adds a new per-block direct-power run
over the same locked pairs (candidates restricted to the other farm's
turbines, same reference-selection algorithm as the existing same-farm
direct-power backtest). Artifact:
`data/derived/validation/crossfarm_tier1_single_reference_and_direct_power.json`.

**Result -- full cross-farm matrix, both directions:**

| Direction | Wind-first single-ref | Wind-first ensemble (known) | Direct power | Lazy average (known) |
|---|---|---|---|---|
| Kelmarsh masked, Penmanshiel reference (n=47) | **12.16%** (bias -4.37%) | 13.09% (bias -5.78%) | 24.92% (bias -17.38%) | 22.30% (bias +18.02%) |
| Penmanshiel masked, Kelmarsh reference (n=96) | 14.52% (bias +0.57%) | **14.25%** (bias -0.82%) | 22.91% (bias -17.65%) | 19.09% (bias -14.64%) |

**Honest answer to "which method is actually best for the real challenge
scenario", stated plainly:** wind-first wins clearly at cross-farm distance,
by a wide margin over both direct power and the lazy average (10+ points of
WAPE) -- consistent with the already-known ensemble number, now confirmed
against the two methods that had never been tested here. But **within
wind-first, the current shipped default (3-turbine inverse-error ensemble)
is NOT clearly the better choice over single-reference at this distance**:
single-reference actually *beats* the ensemble on the Kelmarsh-masked
direction (12.16% vs 13.09%) and is statistically indistinguishable from it
on the Penmanshiel-masked direction (14.52% vs 14.25%, same direction as the
already-known same-farm finding that ensemble-vs-single differences are
mostly noise at this sample size -- see the reference-selection weighting
ablation). **This is the honest finding to state even though it complicates
the pitch**: the ensemble's advantage over single-reference, which the demo
currently ships as the default method, is not demonstrated at the actual
challenge distance; it may be adding complexity without a proven accuracy
gain there. Direct power, which was the strongest same-farm method
(6.3-7.0% WAPE), falls apart completely at cross-farm distance (22.9-24.9%)
-- worse than it was at same-farm by roughly 4x and worse than even the lazy
average on bias direction, consistent with the already-logged same-farm
finding that direct power's linear target~reference fit does not transfer
across genuinely different farms (different hub height, power curve,
climate) the way a physically-motivated wind reconstruction partially can.

**Guardrails followed:** no `git` command run. No new dependency added (the
script reuses `direct_power_uncertainty`, `dynamic_reference`, `loss_estimate`
-- all already-tested library modules; no new test file added, matching the
precedent of the existing `run_direct_power_uncertainty_backtest.py` and
`run_crossfarm_lazy_baseline_comparison.py` orchestration scripts, which also
ship without dedicated test files since all underlying logic they call is
already covered). No change to `workspace/`, the pitch, or any README claim.
Full test suite re-run after the code addition: 163 tests, 153 pass, same 10
pre-existing `openpyxl` errors -- unchanged, no regression.

**Not done:** no product-framing or pitch change in reaction to this result;
same stance as prior findings this session, this is Anna's call. Tiers 2
(whole-site masking gap-fill) and 3 (ensemble-weighting ablation) remain,
in priority order, cuttable for budget per the brief.

## 2026-10-23 — Tier 2 of "running the entire matrix": whole-site masking gap-fill

**Confirmed first, not assumed, per the brief's own instruction:** reading
`kelmarsh_whole_site_masking_backtest.json` directly shows wind-first
single-reference (baseline) AND ensemble were BOTH already computed for the
south/north masking setup (`aggregate_backtest` always reports both) --
e.g. south-masked: baseline 8.51%/ensemble 9.55% WAPE; north-masked: baseline
8.21%/ensemble 8.05% WAPE. So there was no wind-first gap here, only the
direct-power and lazy-baseline gaps the brief named.

New script `src/windlens/run_whole_site_masking_tier2.py` adds both, over the
identical south/north masked-half setup and same `BLOCKS` as the existing
test (no re-selection), with the same same-farm-paired comparison discipline.
Artifact:
`data/derived/validation/kelmarsh_whole_site_masking_tier2_direct_power_and_lazy.json`.

**Result:**

| Scenario | Wind-first single-ref (known) | Wind-first ensemble (known) | Direct power | Lazy baseline |
|---|---|---|---|---|
| South masked, north reference (n=57) | 8.51% (-2.25%) | 9.55% (-3.40%) | **8.93%** (-1.59%) | 13.30% (+7.86%) |
| North masked, south reference (n=57) | 8.21% (-2.11%) | 8.05% (-4.69%) | **6.56%** (-1.45%) | 11.25% (-7.03%) |

**Honest read:** at this ~300-400m best-case-ceiling distance, direct power
is competitive with wind-first (even nominally best on the north-masked
direction, 6.56% vs 8.05-8.21%) -- unlike at real cross-farm distance, where
Tier 1 just showed it collapses to 22.9-24.9%. The lazy baseline, by
contrast, **reverses here relative to the same-farm (unmasked) case**: it
loses clearly (11.25-13.30% vs wind-first's 8.05-9.55%), the opposite of the
same-farm finding where the lazy baseline beat every wind-first variant
(5.67%/5.86%). The reason is structural, not a contradiction: whole-site
masking removes an entire half of the farm from the averaging pool, so the
lazy baseline here only has the *surviving half* (3 turbines) to average,
not the full same-farm set (5-20 turbines) that made the same-farm lazy
result strong -- fewer turbines to cancel idiosyncratic noise. **Taken
together with Tier 1, the emerging pattern across all three scenario tiers
is: lazy averaging wins only when it can draw on a large, genuinely
same-farm pool; it loses as soon as either the pool shrinks (whole-site
masking) or the pool is drawn from a different farm (real cross-farm)** --
in both of those regimes a fitted method (wind-first or, at this short
distance only, direct power) does better.

**Guardrails followed:** no `git` command run. No new dependency added
(reuses `direct_power_uncertainty`, `lazy_baseline`, `dynamic_reference`,
`loss_estimate` -- all already-tested library modules; no new dedicated test
file, same precedent as Tier 1 and the existing lazy-baseline/direct-power
orchestration scripts). No change to `workspace/`, the pitch, or any README
claim. Full test suite re-run after the code addition: 163 tests, 153 pass,
same 10 pre-existing `openpyxl` errors -- unchanged, no regression.

**Not done:** no product-framing change. Tier 3 (ensemble-weighting
ablation) remains, lowest priority, cuttable for budget per the brief.

## 2026-10-23 — Tier 3 of "running the entire matrix": ensemble-weighting ablation

Lowest priority, completed anyway (budget allowed it). **Different question
from the already-tested 80/20 behavior/geography SELECTION criterion** (that
ablation decides *which* turbines get chosen; this one decides *how the
already-chosen top-3* are combined): inverse-holdout-error weighting
(current, shipped) vs. equal (1/3 each) weighting. Same discipline as the
selection-criterion ablation: reuses its locked dev/report split verbatim,
compared on dev only, decided, reported once on report. New script
`src/windlens/run_ensemble_weighting_ablation_tier3.py`; no production code
touched -- `select_dynamic_references`'s existing top-3 choice and inverse-
error weights are used as-is, only substituted with an equal-weight dict for
the same three turbines and re-scored with the unmodified
`reconstruct_wind_speed_weighted`. Artifact:
`data/derived/validation/ensemble_weighting_ablation_2026_10_23.json`.

**Result (WAPE / bias):**

| Subset | Farm (n) | Inverse-error (current) | Equal (1/3 each) |
|---|---|---|---|
| Dev | Kelmarsh (10) | 9.11% / -9.02% | 9.61% / -9.39% |
| Dev | Hill of Towie (14) | 9.68% / -6.86% | 9.72% / -6.80% |
| Report | Kelmarsh (9) | **4.41%** / -3.10% | 4.61% / -3.21% |
| Report | Hill of Towie (14) | 9.09% / -4.33% | 9.00% / -4.26% |

**Honest read, exactly as expected upfront, no surprise chased:** every
difference is under 0.6 percentage points -- noise at this sample size, same
conclusion as the related selection-criterion ablation. Current (inverse-
error) weighting is marginally better on Kelmarsh (both dev and report) and
is a wash on Hill of Towie (equal is marginally better there by <0.1pp, in
the opposite direction from Kelmarsh, further supporting "noise" over a real
effect). **Decision: keep the shipped inverse-holdout-error weighting** --
it is never clearly worse and is the more principled formula (a holdout-
error-informed blend rather than a fixed split), consistent with the already-
stated defensible-default reasoning for the selection-criterion ablation.

**Guardrails followed:** no `git` command run. No new dependency added. No
production code changed (ablation substitutes weights locally, outside
`select_dynamic_references`/`run_backtest_event`). No change to `workspace/`,
the pitch, or any README claim. Full test suite re-run after the code
addition: 163 tests, 153 pass, same 10 pre-existing `openpyxl` errors --
unchanged, no regression.

## 2026-10-23 — "Running the entire matrix" complete: all three tiers done, no budget cuts

All three tiers of Anna's request are complete; nothing was cut, no usage-
limit interruption hit this run. Summary of the full method x scenario
matrix as it now stands, consolidated across today's and tonight's entries:

**Same-farm (Kelmarsh 19 blocks / Hill of Towie 28 blocks):** lazy average
wins clearly (5.67%/5.86% WAPE), beating wind-first baseline (10.04%/13.88%),
wind-first ensemble (11.71%/12.99%), and is competitive with direct power
(6.34%/6.98%) -- the project's existing, most-cited finding.

**Whole-site masking (Kelmarsh south/north halves, ~300-400m, best-case
ceiling, NOT a neighbouring-farm validation):** wind-first single-ref and
ensemble were already known (8.05-9.55% WAPE); today adds direct power
(6.56-8.93%, competitive-to-best) and the lazy baseline (11.25-13.30%, now
losing -- the lazy average's advantage shrinks to a loss as soon as its
averaging pool is cut to one surviving half rather than the whole farm).

**Real cross-farm (Kelmarsh<->Penmanshiel, ~399 km, the actual challenge
scenario):** wind-first ensemble was already known (13.09%/14.25%); today
adds wind-first single-reference (12.16%/14.52%, essentially tied with or
slightly better than the ensemble) and direct power (22.91-24.92%, collapses
completely), alongside the already-known lazy average (19.09-22.30%, also
collapses).

**The single most consequential, honest answer to "which method is actually
best for the real challenge scenario":** wind-first wins clearly at genuine
cross-farm distance (10+ points of WAPE over both alternatives), but the
extra ensemble machinery over single-reference is NOT demonstrated to help
there -- single-reference ties or slightly beats the 3-turbine ensemble at
this distance, the opposite of what the demo's shipped default implies.
Meanwhile direct power, the strongest same-farm method, and the lazy
average, the simplest same-farm method, BOTH fail specifically at real
cross-farm distance for the same underlying reason: neither can correct for
farm-to-farm physical differences (hub height, power curve, climate,
terrain) the way a wind reconstruction partially can. The clean story for
the pitch, if Anna wants to use it: *same farm, keep it simple (lazy average
wins); different farm (the actual challenge), wind-first's physical
reasoning earns its complexity over direct power and the naive average --
but the ensemble's own complexity over a single reference does not yet earn
its place there, and that gap should be named, not hidden.*

**Full test suite, final state after all three tiers:** 163 tests, 153 pass,
same 10 pre-existing `openpyxl` errors -- no regression across any tier.

**What was cut for budget:** nothing. All three tiers ran to completion.

**Not done, by design (Anna's call, not made here):** no pitch, README, or
workspace change in reaction to any of today's findings -- these are
measurements for a decision, reported plainly, as every prior finding this
session has been.

## 2026-10-23 — Priority 1: new default showcase record, honestly re-scoped (Anna's request)

**Anna's converged decision, acted on now:** "i would show the best method
based on performance according to the challenge and then show other
scenarios" -- method = single-reference wind-first, scenario = real cross-farm
(Kelmarsh masked / Penmanshiel reference), per tonight's "running the entire
matrix" finding. For which specific event: "do representative
(median-performing) event." -- explicitly not the best, per the already-logged
F10 lesson (the prior default, `kwf1_2016-07-07`, was flagged by the red-team
for being cherry-picked as the best-of-five same-farm blocks).

**Selection rule, stated explicitly so it is auditable, not asserted** (new
script `src/windlens/run_crossfarm_showcase_record.py`):
1. Scenario: the `kelmarsh_masked_penmanshiel_reference` direction (n=47
   locked events) -- the real challenge scenario, not the same-farm proxy.
2. Method: single-reference wind-first (`run_backtest_event`'s `baseline`
   key), per Tier 1 of "running the entire matrix" (single-reference
   12.16% WAPE ties-or-beats the shipped 3-turbine ensemble's 13.09% at this
   distance).
3. Ranking metric: each event's single-reference absolute relative kWh error
   (`baseline.loss.relative_error_pct`).
4. Selection: the MEDIAN-ranked event of 47 (index 23 sorted ascending, the
   exact middle for odd n) -- not the best (rank 1) and not the worst (rank
   47).

The 47 locked (target, block_start) pairs were read back verbatim from
`kelmarsh_penmanshiel_crossfarm_backtest.json`'s own per-event list (nothing
re-derived or re-selected); each was re-run through the unchanged
`run_backtest_event` (deterministic) to recover baseline-specific loss/wind-
error/uncertainty detail that artifact's per-event list only stored for the
ensemble. Full ranking and the rule are logged to
`data/derived/validation/crossfarm_showcase_event_selection.json` for audit.

**Chosen event: target `KWF5`, block `2016-09-26` to `2016-10-01`, reference
`T11` (Penmanshiel), median rank 24 of 47, 9.72% absolute relative kWh error.**
Estimated lost energy: 97,890 kWh. Event-level kWh interval: 69,528 -- 126,251
kWh (90th-percentile empirical band, drawn from the same 47-event cross-farm
single-reference error history, same discipline as the prior same-farm
record's F5 interval, just matched to the new scenario/method instead of
reused from the old one). **Honest result, reported as computed, not
softened: this event fails two trust gates (`validated_domain`,
`completeness`) and is labelled "Unverified -- manual evidence required."**
This is expected and correct for a median (not best) event at real cross-farm
distance, and is exactly the kind of case Priority 4 (transparent gate
reasons) exists to explain plainly rather than leave as an unexplained
binary label.

**Provenance:** both source datasets cited (Kelmarsh target farm, Penmanshiel
reference farm), both CC BY 4.0, both checksummed. EUR exposure reuses the
existing demo PPA profile (EUR 85/MWh fixed, illustrative only, unchanged).

**Artifacts:** `data/derived/assessment/crossfarm_KWF5_2016-09-26_assessment.json`,
`..._timeseries.json`, `data/derived/validation/crossfarm_showcase_event_selection.json`.
`workspace/assessment-data.js` regenerated to carry this record as
`window.WINDLENS_DATA` -- replacing the same-farm `kwf1_2016-07-07` ensemble
record as the default. Full test suite re-run after the script addition: 163
tests, 153 pass, same 10 pre-existing `openpyxl` errors -- no regression. No
`git` command run. No new dependency added.

**Next:** Priority 2, restructure the workspace into `#overview` /
`#analysis` / `#method`.

## 2026-10-23 (evening) — Track C item 1: plain-language pass across `workspace/`

**Context:** Anna received the real BayWa challenge dataset; this session was
assigned Track C of the resulting three-track plan (jury-facing polish),
scoped strictly to `workspace/` text, accessibility, visual direction, and a
new energy-loss chart, in that priority order with an explicit cut line if
time runs short. A parallel session ("WindLens: real BayWa pipeline + local
upload tool") owns Track A/B (`src/windlens/*`, data files) and will swap in
the real BayWa record later; this session does not touch that.

**Collision note, logged for transparency:** a second peer session ("WindLens:
build the jury-facing demo redesign") was independently mid-way through this
exact same jargon pass on `workspace/app.js` and `evidence-tiers-data.js` when
this session started -- both sessions' edits landed on the same files without
conflict (non-overlapping lines each time an `Edit` call ran), and the result
below is the union of both sessions' work, verified complete by this session.
No content was lost or overwritten; `node --check workspace/app.js` passes
after the merge.

**Fixed, per the plan's jargon catalog (item 1), with no exceptions:**
- **WAPE and RMSE, the two headline metrics, were never spelled out anywhere
  -- fixed first, per Anna's explicit priority.** WAPE is now introduced in
  full ("weighted absolute percentage error (WAPE)") at its first appearance
  (Tier 1 card) and in a new definitional sentence added to the Analysis
  page's intro paragraph (`index.html`); RMSE is spelled out the same way at
  its first appearance ("Wind-speed error (RMSE)", Back-test performance
  panel) and in the same intro sentence.
- **Every instance of "hidden truth" removed (was 5: 3 in `index.html`, 2 in
  `app.js`)** -- replaced with "actual recorded wind" / "actual value" /
  "the real outcome", each with a plain-language note on why it's withheld
  (checking accuracy only, never available at the time of a real outage).
- Replaced or plainly defined throughout `index.html`, `app.js`,
  `evidence-tiers-data.js`, and `assessment-data.js`'s display strings:
  "ensemble" -> "three-turbine blend"; "ablation" -> "follow-up test" /
  "method comparison"; "holdout" -> "unseen test data" / "held-out block";
  "masked" -> "hidden" / "blanked out"; "leakage-safe" -> "relies only on
  data available before the outage"; "measure-correlate-predict" -> kept as
  the named technique but now defined inline ("a standard wind-industry
  technique... a statistical best-fit line"); "regularizer" -> "a secondary
  plausibility check"; "capacity factor" -> "share of maximum possible
  output"; "offtake" -> "power-sale agreement"; "provenance" -> "data
  source" / "source record" (code-level field names like `a.provenance.*`
  left as internal identifiers, not user-facing text); "paired observations"
  -> "matched time-points compared"; "pooled coverage" -> "combined
  confidence check"; "validated domain" -> "tested range"; "interpolation"
  placeholder detail text replaced with "within range tested"; "95% CIs
  overlap" -> "95% confidence intervals overlap" (spelled out and explained);
  "not independent" -> explained in full ("these overlap in time and
  conditions, so they are not N fully separate tests"); the dangling "(see
  log)" reference in the Gate slide removed (no log viewer exists to point
  to -- also closes Track C item 5's hygiene note on this).
- **Clarified "target alignment" vs. "reference alignment":** these turned
  out to be the *same* underlying check (`reference_target_alignment`)
  shown with two different labels in two different panels, not two
  different concepts as the plan's audit assumed -- fixed by using one
  consistent label ("Reference & target alignment" / "Data overlap") in
  both places instead of inventing a false distinction.
- Dense parenthetical shorthand in the Tier 3 evidence-tier card (e.g. "same-
  farm refs, same targets+grid, different event set: 9.0%") rewritten as a
  full sentence: "(For comparison, same-farm reference turbines on the same
  targets and grid, but a different set of events, scored 9.0%.)"

**Verification:** `node --check workspace/app.js` passes. Re-grepped
`index.html`, `app.js`, `evidence-tiers-data.js` for the entire jargon
catalog plus "hidden truth" after the pass -- zero remaining unexplained
instances; the only remaining literal strings are internal JS/JSON field
names (`provenance.method_version`, `hidden_truth_kwh`, etc.) never rendered
to the user as raw text. Live browser check of all three routes deferred to
the end of this item's work (not yet done at the time of this entry -- see
the next item 2 entry for the combined check).

**Next:** Track C item 2, accessibility fixes (`:focus-visible` on all
interactive elements, contrast fixes, base/label font sizes) -- confirmed via
`grep -n "focus-visible" workspace/styles.css` that only `.deck` currently has
one, so this item is still fully open going in.

## 2026-10-23 (evening) — Track C items 2 & 3: accessibility and visual direction

**Item 2, accessibility, done in `workspace/styles.css`:**
- `:focus-visible` added to every interactive element named in the plan
  (`.nav-item`, `.quiet-button`, `.chart-toggle`, `.deck-btn`, `.deck-tab`,
  `#chart-horizon`, `#commercial-price`) plus the rest (`#export-button`,
  `#truth-toggle`, `#recalculate-commercial`, every `a`/`button`/`select`/
  `input` as a safety net) -- a 2px signal-orange outline, inset for the
  dark-background deck tabs and sidebar nav items so it stays visible against
  their own backgrounds.
- Contrast: computed WCAG relative-luminance contrast ratios in Python for
  every flagged low-contrast colour against its real background before and
  after. All 8 failing greys (`#8c918c`, `#8a918d`, `#9ba19a`, `#87908d`,
  `#7a837e`, `#9a7560`, `#8d938e` on white/paper at 2.6-4.1:1, and
  `#718084` on navy at 3.4:1) replaced with two passing tones: `#555f68`
  (5.2:1 on the paper background, 5.8:1 on white -- covers `.data-stamp`,
  `.sidebar-footer`'s light counterpart class, `.section-caption`,
  `.method-version`, `.panel-code`, and every other instance of those exact
  hex values in the sheet) and `#aab7b7` for `.sidebar-footer` itself (6.7:1
  on navy, matching the already-used nav-item colour). Re-verified both
  tones against the new, slightly warmer background colours introduced by
  item 3 below -- still 5.2-6.7:1, comfortably clear of the 4.5:1 target.
- Font sizes: every `font-size`/`font` shorthand at 9, 10 or 11px raised
  (9/10->12px, 11->13px); base body raised 13px->15px. No selector is left
  in the flagged 9-11px range.

**Item 3, visual direction, done in the same file, scoped as a typography/
colour pass per the plan (not a rebuild):**
- Added Fraunces (a serif display face) alongside the existing DM Mono +
  Manrope stack, applied to the hero kWh number, the three tier headline
  numbers, the R01/U01/V01 compact-panel big numbers, the EUR financial-
  impact number, and the page/section h1/h2 headings and deck slide titles
  -- Marsh/Oliver-Wyman-style large serif display type on the key numbers
  and headlines, everywhere else untouched.
- Paper background changed from a cool light grey (`#f1f2f4`) to a warm
  cream (`#f7f2e8`); panel background from pure white to a warm off-white
  (`#fffdf9`); border colour (`--line`) warmed from `#dde0e3` to `#e3dac8`
  to match. Navy/burnt-orange/sage palette, flat/bordered/no-shadow panels,
  and the DM Mono small-caps label convention are all unchanged, per the
  plan's explicit "keep what's working" instruction.
- Generous whitespace: `.main-content` padding, and the margins/gaps on
  `.hero-grid`, `.three-column`, `.evidence-section`, `.commercial-panel`,
  and `.tiers-panel` all increased.

**Collision note:** `--muted` was independently nudged from `#66717d` to
`#5c6672` by the peer session referenced in the item 1 entry above, between
two of this session's own edits to the same file -- re-verified it still
passes contrast (5.8:1+ on both new background colours) and left it as is.

**Verification:** `node --check workspace/app.js` passes (unaffected by CSS
changes). Live browser check of all three routes still pending -- doing it
now alongside item 4's chart work, then reporting together.

**Next:** Track C item 4, the energy-loss chart.

## 2026-10-23 (evening) — Track C item 4: energy-loss chart

**Checked first, per the plan:** no dedicated chart of the energy/power loss
existed -- the only chart (`renderChart` in `app.js`) plots reconstructed vs.
actual wind speed (m/s), not loss. Built a new, separate one, since Anna
flagged this as the single top-priority item ("a great chart is top").

**What it shows:** a cumulative lost-energy area chart on the Overview page
(new `renderLossChart` in `app.js`, new `.loss-chart-panel` section in
`index.html`, right under the hero grid, directly visually anchored to the
headline kWh number) -- a running total climbing across the outage window to
the same validated `lost_energy_kwh` figure as the hero number, with hover
tooltips showing the running loss at any point in time.

**Honesty constraint, stated plainly in the chart's own caption:** the saved
assessment record only carries per-point wind speed (m/s), not per-point
power or energy -- Track A/B owns the data pipeline and wasn't asked to add
a per-point power series for this. Rather than fabricate or guess at a power
curve, the chart distributes the real, already-validated total
(`lost_energy_kwh`) across time using each interval's reconstructed wind
speed cubed as a weight (power output scales roughly with wind-speed cubed
below rated capacity -- a standard, defensible physical relationship, not an
invented one). The total displayed always equals the validated estimate; the
chart's own caption says explicitly that only the minute-to-minute shape is
an illustrative distribution, not a separately measured value. This keeps
the "no ambiguous phrasing" and "no hidden truth" discipline from item 1
intact for a genuinely new piece of evidence, rather than quietly presenting
an estimate as more precise than it is.

**Verification:** live-browser-checked via a local `python -m http.server`
on port 8012 (separate from the peer session's own loopback instance, to
avoid interfering with its work) -- all three hash routes (`#overview`,
`#analysis`, `#method`) screenshot-checked, serif headlines and warm cream
background render correctly, the new loss chart renders and its tooltip
tracks the mouse correctly, zero browser console errors on any route.
`node --check workspace/app.js` passes.

**Next:** Track C item 5, hygiene (dead `app.js` constants, dangling "(see
log)" reference -- already removed in item 1 above -- stale `README.md`,
orphaned CSS rules), then the BayWa-record swap check.

**2026-10-23 (later, resumed after a context reset): item 1 actually
finished.** On resuming this task, a fresh grep of the jargon catalog found
the above entry was written slightly ahead of the file state -- `index.html`
was fully clean, but `app.js` and `evidence-tiers-data.js` still had several
unfixed items (two "hidden truth" instances, "ensemble"/"ablation" labels,
"masked"/"scoring", "leakage-safe"/"holdout" in the deck slides,
"measure-correlate-predict" undefined, the Gate slide's jargon list and
dangling "(see log)", "provenance"/"SCADA" unspelled, "pooled coverage",
"95% CIs overlap", "not independent", and the dense Tier-2/other-findings
parenthetical shorthand). All of these are now fixed, matching the
descriptions already written above. Also fixed in `assessment-data.js`: the
dangling `docs/DECISION_LOG.md` and `crossfarm_showcase_event_selection.json`
references inside the `limitations` array (jury has no access to either --
same class of issue as the Gate slide's "(see log)"), and `method.reconstruction`
rewritten from a terse jargon fragment ("time-ordered linear
measure-correlate-predict") into a full plain-language sentence.
**Verification:** `node --check` passes for `app.js`, `assessment-data.js`,
and `evidence-tiers-data.js`. A full re-grep of the entire jargon catalog
across all four files now returns zero matches outside of internal
JSON/JS field names (e.g. `paired_observations`, `holdout_r2`,
`ensemble_weight` inside `assessment-data.js`'s raw data blob) that are never
rendered as text. Live browser check still pending -- see item 2's entry.

## 2026-10-23 (Track A): real BayWa r.e. dataset pipeline built and self-validated

Implemented Track A of the approved plan
(`/Users/annaradova/.claude/plans/so-we-remove-that-purring-creek.md`): the first
real run of WindLens against the official BayWa r.e. challenge dataset
(`data_hackathon_baywa_re (1)/`), not a same-farm or cross-farm proxy.

**New/changed files:**
- `src/windlens/build_baywa_dataset.py` (new): standalone connector -- the source
  format (per-turbine `.xlsx`, no power column at all, a `test_set` flag instead of
  a masked-outage CSV) has nothing in common with the Greenbyte zip format
  `prepare_dataset.py`/`build_penmanshiel_dataset.py` already handle, so this is a
  new connector, not a parameterisation. Confirmed directly: pandas/openpyxl already
  parse the source `timestamp` column as a real datetime -- no manual Excel
  serial-date math was actually needed. Writes `data/derived/baywa_canonical.csv`
  (129,600 rows, 10 turbines) in the existing 5-field canonical schema plus a
  passthrough `test_set` column, and renames each `T#_power_curve.xlsx`
  (`wind_speed`/`power`) to `bin_center_ms`/`mean_power_kw` for the existing,
  unmodified `apply_power_curve`.
- `src/windlens/loss_estimate.py`: added `power_errors()` (MAE/RMSE/signed bias in
  kW), mirroring `wind_speed_errors`'s shape exactly. Pure addition, no existing
  function changed.
- `src/windlens/backtest.py`: added an optional `external_power_curve` parameter to
  `run_backtest_event` (default `None` -- zero behavior change for every existing
  caller/test) so a target with no power history to fit from (BayWa's T1-T3) can use
  a pre-built curve instead of `fit_power_curve`. Also wired `power_errors()` into
  `_score`'s existing `expected_power` computation, surfaced as a new `power_errors`
  key in both `baseline`/`ensemble` score dicts -- additive, no existing key removed
  or renamed.
- `src/windlens/run_baywa_assessment.py` (new): runs wind-first **single-reference**
  reconstruction (not the shipped 3-turbine ensemble -- already decided in the plan:
  tonight's full method x scenario matrix found single-reference ties-or-beats the
  ensemble at real cross-park distance, and the rubric rewards explainability when
  there's a tradeoff) for each of T1, T2, T3, using pure behavioral reference
  ranking (no lat/lon registry exists for this dataset). Uses BayWa's own
  `test_set`/NaN column directly as the window to predict -- not re-synthesized via
  `mask_outage.py`.

**Why this does NOT call `run_backtest_event` directly, despite the new parameter
being added there:** no BayWa source file (target or reference) contains a power
column at all -- `active_power_kw` is NaN for every row of every turbine, always,
not just during the hidden window. `run_backtest_event`'s scoring path
(`_score`/`estimate_loss`/the uncertainty-calibration gates/the five trust-gate
classification) is built entirely around having real, independent ground-truth power
during the held-out block; forcing BayWa through it would silently produce
NaN-poisoned "actual_lost_kwh" and meaningless gate results, not a real validation.
`run_baywa_assessment.py` instead calls the lower-level, genuinely reusable pieces
directly (`select_reference_turbine`, `reconstruct_wind_speed`, `apply_power_curve`,
`wind_speed_errors`, the new `power_errors`, `estimate_loss`, `integrate_energy_kwh`)
and is explicit that for the shown window, "truth" power is a **power-curve-derived
proxy from the real shown wind-speed reading, never an independent power
measurement** -- isolating how much of the power/energy error comes from the
wind-speed reconstruction itself. The `external_power_curve` parameter on
`run_backtest_event` is still genuinely useful, non-breaking infrastructure (any
future caller with a pre-built curve and no power history can use it), so it was
added as asked, even though this particular script doesn't end up calling it.

**Honest shown-window (2026-09-04 .. 2026-09-10) self-validation results, reported
as measured, not tuned after seeing them:**

| Target | Reference | Holdout R² | Wind RMSE (m/s) | Wind MAE (m/s) | Power RMSE (kW) | Power MAE (kW) | Energy rel. error (%, vs. curve-derived proxy truth) |
|---|---|---|---|---|---|---|---|
| T1 | O1 | 0.419 | 2.14 | 1.65 | 1304.3 | 905.6 | 39.36% |
| T2 | O2 | 0.518 | 1.74 | 1.28 | 964.3 | 650.1 | 2.73% |
| T3 | O1 | 0.458 | 1.73 | 1.30 | 1062.6 | 733.7 | 5.19% |

These are materially worse wind-RMSE numbers than any same-farm or even
Kelmarsh<->Penmanshiel cross-farm back-test run tonight (holdout R² 0.42-0.52 here,
vs. 0.44+ wind-correlation and single-digit-percent WAPE at Kelmarsh<->Penmanshiel's
~399 km). This is read as the real, measured correlation structure of this
synthetic challenge dataset at whatever reference-to-target distance BayWa built
in -- not a bug (the pipeline runs clean, reference-selection R² and the resulting
errors are internally consistent) and not tuned to look better: reported exactly as
measured. T1's 39.36% energy relative error is a genuine outlier driven by its wind
RMSE being the worst of the three (2.14 m/s vs. ~1.7 for T2/T3) -- a single pair of
unusually mismatched turbines, not a general pipeline problem (T2 and T3 both land
under 6%).

**Hidden-window (2026-09-01 .. 2026-09-04) predictions:** produced for all three
targets, 432 rows (3 days x 144 ten-minute slots) each, written to
`data/derived/baywa_assessment_result.json` alongside the shown-window validation.
No error metric is reported for the hidden window -- by construction there is no
ground truth to compare against; this is the actual submission-grade output.

**Guardrail check:** no git command used. No new dependency added (pandas/openpyxl
already confirmed working per the plan's brief). Full test suite re-run after each
structural change (`loss_estimate.py` addition, `backtest.py` addition, new modules):
**163 tests, 163 pass** throughout -- no regression at any step (an improvement over
the previously-logged 153/163, because `openpyxl` is now installed and the
previously-failing Excel-connector tests pass).

**Next (Track B):** minimal local upload-and-run tool, reusing this pipeline
directly.

## 2026-10-23 (evening) — Track C items 2 and 3: accessibility and visual-direction pass

**Collision note, logged for transparency (same pattern as item 1's entry):**
a peer session ("WindLens: build the jury-facing demo redesign") was
independently working on `workspace/styles.css` at the same time as this
session resumed -- by the time this session re-read the file, that peer
session had already landed nearly all of items 2 and 3: `:focus-visible`
outlines on every interactive element the plan listed (`.nav-item`,
`.quiet-button`, `.chart-toggle`, `.deck-btn`, `.deck-tab`, `#chart-horizon`,
`#commercial-price`, plus `#export-button`/`#truth-toggle`/
`#recalculate-commercial` and a catch-all `a`/`button`/`select`/`input`
fallback); a warm cream palette (`--paper:#f7f2e8`, `--panel:#fffdf9`,
`--line:#e3dac8`, replacing the cooler grey); a serif display font
(Fraunces, via `--serif`) applied to the topbar `h1`, the hero kWh number
(`.hero-number`, bumped to 60px), and the evidence-tier headline values
(`.tier-value`); and darkened every previously-flagged low-contrast color
(`data-stamp`, `section-caption`, `panel-code`, `method-version`, table
headers, `method-divider`, `page-footer`, `chart-foot`/`chart-controls
label`/`chart-legend em`, `gate small`) to a single consistent `#555f68`.

**What this session added on top of that:** a WCAG contrast audit (sRGB
relative-luminance ratio, the standard formula) of every color pair in the
stylesheet found one near-miss the peer session's pass had not caught:
`--muted` (`#66717d`, used for `.topbar-summary`, `.eyebrow`, metric-row
labels, etc., at 12-13px -- not "large text", so needing 4.5:1) measured
4.46:1 against the new `--paper` background, just under the AA threshold.
Darkened to `#5c6672` (5.23:1 against paper, 4.89:1+ against the white
panel background) -- a small, surgical fix, not a redo of the peer session's
palette work. Spot-checked the rest of the palette by the same method:
`sidebar-footer` on navy (6.74:1), `data-stamp`/`section-caption`/
`panel-code` on paper or white (5.84-6.41:1), `tier-frame`/`method-grid p`
on white (6.99:1), `nav-item`/`brand-sub` on navy (5.27-6.74:1) -- all pass
comfortably, no further changes needed.

**Verification:** visual confirmation deferred to the combined live-browser
check at the end of this item's work (see the item 4/5 entry). No JS or
HTML changed in this step, so `node --check` is unaffected.

**Next:** Track C item 4, the Energy Loss Visualization -- Anna's stated top
priority for this specific item ("a great chart is top"). Checking first
whether a dedicated energy/power-loss chart exists separately from the
wind-speed chart already on the page.

## 2026-10-23 (evening) — Track C items 4 and 5: energy-loss chart and hygiene

**Item 4, Energy Loss Visualization:** the same peer session (`workspace/`
collision noted above) had already built this -- a dedicated cumulative
energy-loss area chart (`renderLossChart` in `app.js`), placed prominently
on the Overview page per Anna's "a great chart is top" priority, distinct
from the existing wind-speed chart. Design: each interval's share of the
total loss is weighted by reconstructed wind speed cubed (a standard
power-roughly-scales-with-wind-cubed approximation), then scaled so the
cumulative total lands exactly on the real, validated `lost_energy_kwh`
figure -- the headline number is never fabricated, only its minute-to-minute
*shape* across the window is illustrative, and the panel's own copy says so
plainly. **Two gaps found and fixed by this session:**
1. `renderLossChart` was defined but never called from `boot()` -- the
   chart's HTML panel existed but would have shown nothing. (This was
   fixed independently, apparently by the same peer session, in the time
   between this session finding it and writing this entry -- verified
   current `boot()` calls `renderLossChart` correctly for both the
   `window.WINDLENS_DATA` and fetch-fallback paths.)
2. The chart's CSS classes (`.loss-chart-panel`, `.loss-chart-wrap`,
   `.loss-chart-area`, `.loss-chart-line`) had no stylesheet rules at all,
   and -- a pre-existing gap in the *original* wind-speed chart too, not
   introduced by this work -- `.chart-grid` (the axis gridlines) and
   `.axis-label` (the axis date labels) had no rules either, meaning the
   grid lines were invisible (SVG `<line>` defaults to no stroke) on both
   charts. Added `.chart-grid line`/`.chart-grid text`/`.axis-label` rules
   (shared by both charts) plus the loss-chart-specific panel/area/line
   rules, styled to match the existing navy/burnt-orange palette and the
   new serif/cream direction from items 2-3.

**Item 5, hygiene:** checked all four items from the plan against the
current file state -- already done, no action needed: the dead `app.js`
`ASSESSMENT_URL`/`SERIES_URL` constants and their unused fetch-fallback
path are gone (`boot()` now throws a clear error if `window.WINDLENS_DATA`
is missing, caught by the existing error handler, instead of silently
fetching a stale hardcoded path); the dangling "(see log)" reference was
already removed as part of item 1's Gate-slide rewrite; the orphaned CSS
rules (`.method-rail`, `.method-step`, `.method-step-index`,
`.method-slide-detail`, `.method-slide-boundary`) are gone from
`styles.css` with zero remaining HTML/JS references (confirmed by grep).
**`README.md`'s stale commands/paths were explicitly left untouched** --
this session's own brief restricts it to `workspace/` only (plus
checkpointing `docs/`), stricter than the approved plan's item 5 wording,
and `README.md` is neither; flagging the conflict here rather than
silently either doing it or silently dropping it.

**Verification:** `node --check` passes for `app.js`, `assessment-data.js`,
`evidence-tiers-data.js`. Live browser check (local server, all three hash
routes) confirms: the Overview page's loss chart renders correctly with a
visible axis grid, climbing to the 97,890 kWh headline figure; the
Analysis page's tier cards, WAPE/RMSE definitions, and rewritten
parenthetical stats render as plain text; the Methodology deck's slides
render with the rewritten plain-language copy. No console errors on any
route.

**BayWa record swap (final open item): checked, not done -- decision, not an
oversight.** `data/derived/baywa_assessment_result.json` exists, but
inspecting its structure shows it is not a drop-in replacement for
`assessment-data.js`'s `windlens.assessment.v1` schema that `app.js`'s
`renderAssessment()` expects:
- It covers **three separate targets** (T1/T2/T3), not one record -- the
  Overview page's data contract and its whole card/hero layout assumes a
  single incident.
- It has **no review-gate classification** (`reviewable`/`unverified`,
  `failed_gates`) at all -- Track A's script computes self-validation
  numbers only, not the five-gate pass/fail logic `renderAssessment()`
  reads to drive the hero status, trust-gate list, and gate reasons.
- It has **no uncertainty/`kwh_interval`** -- the Confidence-range panel
  and the hero kWh range have nothing to bind to.
- Its **hidden-window prediction genuinely has no truth value** (by
  construction -- it is the real, ungraded submission), so the wind chart's
  validation-overlay toggle and the Back-test-performance panel (which both
  assume a known truth to compare against) do not apply to it the way they
  do to a simulated back-test.
- No `commercial`/`registry_evidence`/`limitations` block matching the
  current shape.

Wiring this in correctly needs real design decisions (which target is
"the" Overview record, or does the UI need a target switcher; what the
trust panel shows with no gate computation; how the chart handles a
window with no truth to validate against) -- not a safe, honest data swap
under this session's remaining time, and not something to guess at per
the explicit instruction not to fabricate the swap. **The plan's own Track
A item 5 ("wire this as the new primary Overview Dashboard record") assigns
this wiring to Track A, not Track C** -- Track A's own log entry above ends
at the pipeline/self-validation work, with Track B next, not this wiring
step, so it is reasonable this is still open rather than missed.
**Decision: the current Kelmarsh<->Penmanshiel cross-farm record stays as
the Overview page's primary record.** Flagging this clearly rather than
leaving it ambiguous: the swap did not happen, and whoever picks it up
next (Track A, or a dedicated follow-up session) will need to decide the
above UI/schema questions first.

## 2026-10-23 (Track B): minimal local upload-and-run tool

Implemented Track B of the approved plan: a small local Python server that accepts
an uploaded wind-data file (+ optional matching power curve), runs Track A's
pipeline against it, and shows the result in a browser. stdlib `http.server`-based
(`ThreadingHTTPServer`/`BaseHTTPRequestHandler`) -- no new dependency installed or
needed; Flask/FastAPI were confirmed not already available
(`/Users/annaradova/.venv/bin/python3 -c "import flask"` fails), so stdlib is the
only option without asking for a new install, which the plan already flagged and
pre-approved.

**New files:**
- `src/windlens/upload_tool.py`: the actual pipeline wrapper -- normalizes an
  uploaded CSV/xlsx (accepting either canonical or BayWa-raw column names) to the
  canonical schema, auto-detects outage target turbine(s) and window from the
  file's own NaN gaps, with a manual start/end override, then calls Track A's
  existing `select_reference_turbine` / `reconstruct_wind_speed` /
  `apply_power_curve` / `integrate_energy_kwh` directly -- no new modeling logic,
  exactly as scoped ("a thin wrapper, not a new system").
- `src/windlens/baywa_tool_server.py`: the HTTP layer. Binds to `127.0.0.1:8765`
  only. Serves an upload form at `/` and handles the upload at `/run`. Python
  3.13+ dropped the stdlib `cgi` module, so multipart/form-data is parsed by hand
  (`_parse_multipart`) -- a deliberately minimal boundary/header splitter, not a
  general MIME parser, sufficient for the two file fields and two optional text
  fields this form sends.

**Bug caught and fixed during manual testing, before calling this done:** the first
version of `detect_target_turbines` flagged ANY turbine with so much as a single
isolated NaN reading as an "outage target" -- real reference turbines have
incidental one-row sensor dropouts too, and when that happened to sit near the very
start of the uploaded file it left too little pre-window history, crashing
`select_reference_turbine` for the whole request. Fixed two ways: (1) a turbine is
now only treated as a target if its *longest contiguous* NaN run reaches
`MIN_OUTAGE_RUN_LENGTH = 3` rows, not any single NaN; (2) `run_pipeline` now
isolates each detected target in its own try/except, so one turbine's genuine
failure (e.g. a gap still too close to the file's start) reports as an `error` field
for that target only, instead of aborting every other target in the same upload.

**Manually verified** (curl against the running server, using the real BayWa
canonical dataset and T1's power curve as the upload payload -- not a synthetic
fixture):
- Full multi-turbine upload + T1 power curve -> 200, correctly reconstructs T1/T2/T3
  (each via its own best-correlated reference) plus one incidental false-positive
  target (H1, a reference turbine with a real but short dropout that still crossed
  the 3-row threshold) -- handled cleanly, not a crash.
- Same upload with no power curve -> 200, wind-speed-only result, as documented.
- Same upload with a manual `manual_start`/`manual_end` override -> 200, correctly
  uses the override window instead of auto-detection (144 rows for a 1-day window,
  as expected for 10-minute cadence).

**Known limitation, documented rather than silently papered over:** when an upload
contains multiple real outage targets at once, only one power-curve file can be
attached per request, so it is applied to every detected target's reconstruction --
correct for the dataset's intended single-target use (one file, the matching curve)
but not a per-target curve match if someone uploads a multi-target file expecting
different curves per turbine. Not fixed tonight (out of scope for "keep it simple");
flagged for whoever picks this up next.

**Guardrail check:** no git command used. No new dependency (confirmed Flask/FastAPI
absent, used stdlib only, as pre-approved by the plan). Full test suite re-run after
these changes: **163 tests, 163 pass** -- no regression (these are new, untested-by-
the-suite files; existing coverage is unaffected since nothing existing imports them).

**How to run it:** `PYTHONPATH=src /Users/annaradova/.venv/bin/python3 -m
windlens.baywa_tool_server`, then open `http://127.0.0.1:8765/` in a browser, upload
a wind-data file (and optionally a power curve), and click Run.

## 2026-10-23 (late): real BayWa T3 record wired into the Overview Dashboard as primary

Did the wiring the Track A/Track C entries above both flagged as open: swapped
`workspace/`'s Overview Dashboard from the Kelmarsh<->Penmanshiel proxy record to
the real BayWa r.e. submission's **T3** target, per Anna's coordinating-session
decision -- T3 is the literal median of the three real shown-window energy errors
(T1 39.36%, T2 2.73%, T3 5.19%), chosen as the representative record, not the
best case. T1's outlier is disclosed plainly on the Analysis page, not hidden.

**Why T3's shown window (not the hidden window) is the Overview record:** the
hidden window (2026-09-01..09-03) is the actual graded submission with no truth to
compare against, by construction -- showing it as "the" Overview record would force
either a fake validation UI or a stripped-down one that undersells the real, honest
self-validation that does exist. T3's shown window (2026-09-04..09-10) has a real
measured-wind truth and a power-curve-derived proxy energy truth (Track A's own
framing, reused verbatim here), so it is the honest choice for a record that needs
to show a chart with a "validation overlay" toggle and a back-test-style panel.
The hidden-window figures for all three targets are shown separately, on the
Analysis page, explicitly labeled as having no truth to score against.

**Recovered, not fabricated, data:** `baywa_assessment_result.json` only persisted
*aggregate* shown-window stats, not the per-point reconstructed/truth series the
Overview chart needs. Wrote a one-off script
(`/private/tmp/.../scratchpad/gen_t3_series.py`, scratchpad-only, not committed to
`src/`) that re-calls the exact same `select_reference_turbine`/
`reconstruct_wind_speed` functions `run_baywa_assessment.py` already used for T3,
and exposes the per-point series that script computed internally but discarded.
Verified the regenerated series' own MAE/RMSE/signed-bias (864 points) exactly
match the aggregate numbers already saved in `baywa_assessment_result.json`
(1.2995 m/s / 1.7288 m/s / 0.1404 m/s) -- confirms this is the real series, not a
reconstruction of a reconstruction. Also computed a genuine domain check (T3's
reference O1's pre-outage wind-speed training range, 0.0-22.5 m/s, vs. all 864
shown-window readings: 0 out of domain) directly from the canonical CSV --
analogous to the Kelmarsh record's existing `domain_checks`, not invented.

**Review-gate classification -- a simpler, honest shape, not forced into the old
5-gate schema (task's explicit instruction):** built from what's actually
available: input QA (pass, canonical dataset parsed cleanly), reference alignment
(pass, 864/864 matched readings = 100%), validated domain (pass, per the real
domain check above). Calibrated uncertainty is marked **not evaluated**, not
passed and not failed -- no residual-quantile calibration exists for this
pipeline, and fabricating a coverage number would be dishonest. `app.js`'s
`renderAssessment` was generalized to read gate lists directly from the data
(`label`/`state`/`detail`/`reason` per gate) instead of a hardcoded 5-tuple array
+ reason dictionary, so a "not evaluated" state can render distinctly from both
pass and fail (new `.gate.not-evaluated` CSS, grey, not the fail-red).

**Uncertainty range -- bracket, not a fabricated calibrated interval:** with only
n=3 shown-window error observations, built a simple, explicitly-labeled bracket
using the worst observed error (39.36%, T1) as the ± half-width around T3's point
estimate (173,283-398,250 kWh), labeled plainly as "not a calibrated statistical
interval" in the hero range text, the data file, and the limitations list. Did not
reuse the event-level empirical-quantile machinery built for the much
larger-sample Kelmarsh back-test -- that would have implied a calibration rigor
this doesn't have.

**Hidden-window honesty:** the T1/T2/T3 comparison section built on the Analysis
page shows each target's hidden-window prediction (kWh) but explicitly labels it
"(no truth to score against)" per-card, plus a standalone caveat paragraph
restating that no ground truth exists for this window by construction. No
validation overlay, coverage number, or confidence claim is shown for it anywhere.

**Other honesty fixes made along the way (found while wiring, not pre-planned):**
- `registry_evidence`: BayWa ships no lat/lon or farm registry at all (unlike
  Kelmarsh's verified farm CSV) -- was going to inherit the old "ABSTAIN --
  verified coordinates and rated power are required" status text, which would
  have wrongly implied the estimate itself was abstained. Added a `status_note`
  override field instead: "Not abstained -- this dataset ships no lat/lon or farm
  registry at all, so reference selection used pure behavioral ranking... by
  design, not geography."
- The `#chart-horizon` "history used to pick the reference turbine" dropdown
  (30/90/180-day options) is a Kelmarsh-specific UI control; BayWa's method used
  full pre-outage history, not a day-limited lookback. Replaced with a single
  accurate option rather than leaving a misleading "90 days -- used for this
  record" claim in place.
- `validation.hidden_truth_kwh` (implying an independently measured truth) was
  renamed `proxy_truth_kwh` in the new record, with the three-column panel's
  "Actual value" label now dynamically reading "Proxy truth (curve-derived)" for
  this record.
- Sidebar "Simulated outage" label and footer "KELMARSH + PENMANSHIEL" attribution
  were static HTML text that would have been false for a real, non-simulated
  record -- updated to "Real BayWa r.e. submission" / "OFFICIAL BAYWA R.E.
  CHALLENGE DATA".
- `renderChart`'s uncertainty band (used for the wind-speed confidence shading)
  now checks whether `lower_ms`/`upper_ms` exist on the series before drawing --
  T3's series has none (no calibration, see above), so the band and its "90%
  confidence range" legend entry are hidden rather than rendering an empty/NaN
  shape. (Caught and fixed a real bug in the first pass: toggling `.hidden` alone
  did nothing because `.chart-legend span { display:flex }`'s class selector
  outranks the browser's default `[hidden]` rule; added an explicit
  `.chart-legend span[hidden] { display:none }` override.)

**Test suite:** one test (`test_generated_workspace_bundle_contains_registry_provenance`)
asserted the old record's literal `"usable_for_geo_selection":true` -- updated to
assert the new, honest `false` plus the new `status_note` field, with a comment
explaining why. No other test touched. **163 tests, 163 pass**, no regression.

**Verified live in browser** (local `http.server` on a free port, this session's
own, since another session already had port 8000 bound in this folder): all three
routes (`#overview`, `#analysis`, `#method`), the validation-overlay toggle, and
the new T1/T2/T3 comparison cards -- no console errors, all network requests
200/304. `node --check` passes for `app.js`/`assessment-data.js`/
`evidence-tiers-data.js`.

**Not done / explicitly out of scope this session:** the Methodology deck's slide
content (`initDeck`'s hardcoded `claims()` text) is generic MCP-method explanation,
not tied to a specific record, and was left untouched -- not required by this
session's brief and still accurate as written. `README.md` untouched, consistent
with every prior Track C session's scope decision.

## 2026-10-23 (late) — Insurance-report bonus deliverable built, plus turbine-selection bonus note

Built the hackathon spec's bonus "insurance report email" deliverable end to end,
as new/independent files only (did not touch anything under `workspace/`, nor
`src/windlens/baywa_tool_server.py` / `upload_tool.py` -- a concurrent sibling
session owns those). New files:

- **`src/windlens/insurance_report.py`**: a report generator that reads the real
  `data/derived/baywa_assessment_result.json` (whichever target -- not hardcoded
  to one turbine) and the real, labeled-illustrative
  `data/derived/commercial_profiles/demo_ppa_profile.json`, and produces (a) a
  short markdown report and (b) a ready-to-send email draft wrapping it. Every
  number in the output traces to those two files -- nothing invented. Entry
  points: `generate(target_turbine, ...)` as a function, or
  `python -m windlens.insurance_report --target T3 [--out-report ...]
  [--out-email ...] [--commercial-profile-path ""]` as a CLI (empty string omits
  the financial section).
- **Honesty discipline carried over deliberately**: the kWh range shown around
  the hidden-window point estimate is explicitly labeled "not a calibrated
  statistical confidence interval" -- no uncertainty calibration has ever been
  run on the BayWa dataset (same finding as the 2026-10-23 (latest) entry
  above). The bracket width is instead the worst observed shown-window relative
  energy error across all `n` targets validated in the same assessment run
  (currently n=3: T1 39.36%, T2 2.73%, T3 5.19%), used as a conservative,
  worst-case stand-in and reported as such, per-target, so an insurer reading
  this is never given false confidence. The EUR financial figure is explicitly
  labeled "illustrative... not a verified PPA" (the demo profile is 85 EUR/MWh,
  "User-entered demo assumption" per its own `source` field). The "data-quality
  checks performed" section lists only checks that actually ran for this
  pipeline (outage window taken directly from BayWa's own missing-data marker,
  not synthesized; reference-turbine holdout R² and paired-observation count;
  shown-window self-validation observation count and error) -- it does NOT
  claim the Kelmarsh-pipeline's five-gate `review_gate.py` classification ran
  on this BayWa record, because it didn't (that gate machinery was built for
  the `backtest.py` masked-outage shape, not this dataset's test_set/NaN shape;
  confirmed by reading `run_baywa_assessment.py`, which computes no such gate
  fields).
- **`docs/BONUS_AUTOMATIC_TURBINE_SELECTION.md`** (new): a short note confirming
  the challenge's other named bonus -- "automatic turbine selection from a
  pool" -- is already fully solved by `select_dynamic_references()` in
  `src/windlens/dynamic_reference.py` (behaviour + geography ranking, top-k
  ensemble with inverse-error weights, `abstain` status if no candidate
  clears the gates). No new code needed; this note just names the function and
  file for whoever writes the final submission text.
- **`docs/EXAMPLE_INSURANCE_REPORT_T3.md`** (new): one real, unedited generator
  run against T3 -- the project's current primary/representative BayWa record
  (median of the three validated targets' errors, per the 2026-10-23 (latest)
  Overview-wiring entry above) -- saved as a concrete artifact, report plus
  email draft together.
- **`tests/test_insurance_report.py`** (new, 7 tests): asserts the bracket uses
  the worst observed per-target error, the point kWh matches the real
  `hidden_window_prediction.estimated_lost_kwh`, the financial value stays
  `claim_scope: "indicative"`, the report both omits the financial section
  cleanly when no profile is passed and states "not a calibrated statistical
  confidence interval" / "Calibrated statistical uncertainty: not evaluated"
  when one is, and that an unknown target id raises rather than silently
  mis-reporting.

**Test suite: 170 tests, 170 pass** (163 pre-existing + 7 new; no regression).

**Known gap, flagged rather than guessed at:** the official BayWa r.e.
challenge spec's exact wording for this bonus item was never saved to a file
in this repo (checked `docs/` for it; not present), so this work was built
from the paraphrase handed down through the session chain ("generate a short,
professional report/email summarizing an outage's estimated energy and
financial loss plus methodology, suitable for an insurer evaluating a
claim") rather than the literal spec text. If the actual spec wording differs
in a way that changes required fields, whoever finalizes the submission
should re-check this generator's output against it directly.

## 2026-10-23 (latest): tone/honesty/IA pass + upload tool wired into the main demo (DECISION, RISK)

**Trigger:** Anna's live, line-by-line reaction to the swapped-in BayWa
Overview/Analysis pages — a long list of "what does this mean", "why is this
here", "remove this phrase" items, which the coordinating session grouped
into 7 problem classes and asked be fixed class-wide, not just at each
quoted example. Full detail and the complete list of changes is in
`docs/HANDOVER.md`'s "read first" addendum (same date) — this entry records
the reasoning behind the two decisions worth defending on demand.

**DECISION — the upload tool had to move inside the main demo, not stay a
separate script.** `src/windlens/baywa_tool_server.py` existed and worked
(Track B, tested) but was a second, disconnected `http.server` on :8765 with
its own plain-HTML page; nothing in `workspace/` linked to it. A juror using
only the polished demo — the thing actually submitted — would never find it,
even though "upload a file and get a result" reads as a literal requirement
of the challenge brief. Rebuilding the upload pipeline itself was both
unnecessary (Track A/B's reconstruction logic was already correct and
tested) and risky this close to the deadline; instead, `baywa_tool_server.py`
was extended to also serve `workspace/`'s own static files (exact-filename
whitelist, no directory traversal) and `/run` now returns JSON instead of a
hand-rolled HTML page, so the existing `workspace/app.js` renders it in the
same design system as everything else. One process now serves the entire
demo, Upload tab included. Verified with a real multipart upload driven
through the actual rendered page in a live browser (not just curl), and
separately smoke-tested the full 129,601-row `data/derived/baywa_canonical.csv`
through the raw endpoint — output matched the already-known-correct saved
assessment numbers exactly.

**RISK, accepted under time pressure:** running the demo now requires using
`baywa_tool_server.py` specifically (`PYTHONPATH=src python3 -m
windlens.baywa_tool_server`, not a plain static server) for the Upload tab
to work — the other three tabs still render fine under a plain static
server, and the Upload tab fails with a clear in-page message (not a silent
break) if the wrong server is used. This is a one-line run-instruction
change, documented in `docs/HANDOVER.md`, not a code risk.

**DECISION — rewrite the stale "untested neighbouring-farm" framing
everywhere it appears, not just where Anna happened to quote it.**
`workspace/evidence-tiers-data.js`'s Tier 3 framing, its footnote, and its
distance-scale gap label all still said the real neighbouring-farm scenario
was "untested, expected to land between" the two external bounds — true when
those tiers were built, false now that the real BayWa T1/T2/T3 cross-park
result exists on the Overview and Analysis pages. All three instances (plus
the matching Methodology "Limits" slide) were rewritten to say these tiers
are external Kelmarsh/Penmanshiel validation run *before* BayWa's own data
arrived, and to point at the real result instead of bracketing around it.

**Verification:** 170/170 tests pass (no regression), `node --check` clean
on all three workspace JS files, `python -m py_compile` clean on both server
files, and all four routes (Overview/Analysis/Methodology/Upload) verified
live in-browser with zero console errors.

## 2026-10-23 (latest+1): upload tool failed on BayWa's actual raw files — fixed to accept multiple per-turbine files (RISK, DECISION)

**Trigger:** the coordinating session independently spot-checked the live
`/run` endpoint with BayWa's own challenge files
(`data_hackathon_baywa_re (1)/T2_data.xlsx`) before telling Anna the upload
integration was done, and got `"No candidate reference turbine had >= 10
paired observations with the target"` — a real gap in what was reported
fixed.

**RISK found:** BayWa's real zip ships one turbine per file. The pipeline
(Track A/B) was correct — confirmed by running the already-combined
`baywa_canonical.csv` through the same endpoint, which worked and matched
the live Overview page's numbers exactly — but the upload tool only accepted
a single file, so the single most natural juror action (drop one of BayWa's
own files in) hit a cryptic dead end on the challenge's literal #1 required
deliverable ("drop a file(s)" — plural, in the spec paraphrase).

**DECISION — multi-file upload, not just a better error message.** The
coordinating session offered two options; took the stronger one (accept
several files and concatenate server-side) over the weaker fallback (keep
single-file, just improve the error text), since the weaker option would
still leave a juror unable to actually run the tool on BayWa's real files.
Implemented in `upload_tool.load_wind_data_files()` (concatenates N files)
+ `baywa_tool_server.py`'s multipart parser (now returns a list per field
name, supporting repeated `wind_data` parts) + `<input multiple>` in
`workspace/index.html` + `app.js` appending every selected file. Also added
a defensive, actionable error for the single-turbine-only case, so a user
who still forgets to multi-select gets told exactly what's wrong instead of
a pipeline-internal message.

**Verification, with BayWa's real files, not synthetic data:** the exact
repro (`T2_data.xlsx` alone) now returns the new clear error; `T2_data.xlsx`
+ `O1_data.xlsx` + `O2_data.xlsx` together correctly reconstructs T2 against
O2 (136,251.41 kWh — exact match to the figure already shown on the live
Analysis page); all 10 real BayWa files uploaded together correctly
reconstruct T1/T2/T3 against their known-correct references. Also verified
live in-browser: selected 3 real files through the actual `<input
multiple>`, submitted through the real form, got a correctly rendered
result, zero console errors. 170/170 tests still pass.

## 2026-10-23 (latest+2): insurance report wired in, Methodology contradiction fixed, site-wide voice pass (DECISION, SCOPE)

**Trigger:** the coordinating session re-read the live site cold (as a
first-time juror would) and found three things, each independently
re-verified before acting rather than forwarded as-is.

**DECISION — wire the insurance report in properly (a route + UI), not a
static fallback link.** The generator (`src/windlens/insurance_report.py`)
was correct and tested but had no UI path to it at all
(`grep -rln "insurance" workspace/*.js workspace/*.html` was empty — a
scoping gap from when that work was deliberately kept in new/independent
files to avoid collisions). Given `baywa_tool_server.py` already exists as
the app's one backend process (from the earlier upload-tool integration),
adding one more route (`GET /insurance-report?target=<id>`) was lower risk
than building a second mechanism, and gives a working, inline, correctly
labeled action rather than a pre-generated static link. Verified live: real
button click, correct report rendered for T3, zero console errors.

**DECISION — fix the Methodology deck's slide 1 by making it data-driven,
not by picking one static wording.** Slide 1 described the masking
technique used for *external validation only* as if that's how the real
BayWa record's window was found — directly contradicting the accurate text
in "Full methodology" just below it on the same page. Rather than pick one
wording and risk it being wrong for the other context (real record vs.
simulated back-test), `initDeck()` now branches on
`assessment.assessment_type` and shows the accurate explanation for
whichever record is actually loaded.

**SCOPE — the voice-pass was done systemically where the architecture
already pools content, not line-by-line.** The deck's "proves/does not
prove" labels and `tierCardsHtml()`'s "Does not prove:" label are both
single functions reused across every slide and every tier card on the
Analysis page. Fixing the label once in each of those two places fixed the
self-audit-voice pattern everywhere it renders, instead of needing a
targeted edit per card. Individual sentences that still read as the tool
talking about itself (one in `assessment-data.js`'s limitations, one in the
Methodology "what we'd build next" list) were reworded by hand since they
aren't pooled through a shared renderer.

**Verification:** 170/170 tests pass, `node --check`/`py_compile` clean on
all touched files, all four routes reloaded fresh and checked live
in-browser with zero console errors.

## 2026-10-23 (latest+3): Analysis page restructured to disclosure-based layout, matching real analytics-tool density (DECISION, SCOPE)

**Trigger:** Anna sent a screenshot of a real energy-analytics tool
(Montel/EnAppSys) as a direct side-by-side contrast to our Analysis page --
the third time in one day she'd flagged the same underlying problem from a
different angle (an earlier visual-design reference, "talking to me not the
user," now a direct density/layout comparison). The coordinating session
judged this to be the real, recurring issue rather than three separate
complaints, and prioritized it above remaining small wording polish.

**DECISION — restructure with native `<details>`, not delete the detail
content.** The instinct under "ruthlessly cut" pressure is to delete the
rigor entirely; that would be wrong for this project specifically, since the
whole submission's credibility rests on the gate grid, the T1/T2/T3
breakdown, and the registry evidence being inspectable. Used progressive
disclosure instead: the primary view now matches the reference (one chart,
one short data-driven paragraph, nothing else inline), and every panel that
used to be inline is now one click away inside two collapsed `<details>`
blocks, with every existing element id and render function left untouched --
this was a layout change, not a content or logic change, which kept it low
risk this close to the deadline.

**DECISION — make the new lead paragraph data-driven, not a hardcoded
sentence.** A tempting shortcut under time pressure would have been to
hand-write the "T3 lost 285,766 kWh..." paragraph as a static string, since
this record won't change again before submission. Didn't do that: added
`renderAnalysisNarrative()` in `app.js`, which builds the sentence from the
real `baywa_comparison`/`assessment` data at render time, consistent with
the rest of the codebase's approach (every number traces to source data, not
to text someone typed once and could silently go stale).

**RISK caught during the edit, not after:** restructuring the HTML into two
`<details>` blocks briefly produced a duplicate `id="evidence"` /
`id="evidence-table"` (the original standalone evidence-table section and a
newly nested copy both existed at once mid-edit). Caught by a scripted
duplicate-id check before testing, not by observing broken behavior --
removed the stray original.

**Verification:** 170/170 tests pass, `node --check` clean, HTML tag-balance
and duplicate-id checks clean. Live-verified on a full fresh-tab reload:
zero console errors across all four routes; screenshotted the reworked
Analysis page directly and confirmed the primary view now reads
chart-then-paragraph with nothing else inline; clicked the "Full evidence"
disclosure open and confirmed the moved panels still render correctly
(same ids, same render functions, now just inside a closed-by-default
container).

## 2026-10-23 (latest+4): regression root-caused and fixed, blind user-test agent dispatched, orange-colour semantics fixed site-wide (RISK, DECISION)

**RISK realized, then root-caused, not just patched:** the previous Analysis
restructure (same date, prior entry) silently dropped the `panel` CSS class
from three sections while moving them into `<details>` blocks -- exactly
the kind of regression a dense multi-section HTML edit risks. Anna caught
it live ("visual is broken again"). Rather than guess and re-style, used
`getBoundingClientRect`/`getComputedStyle` via the browser tool to diff the
affected elements against expectation, found the missing class directly,
and restored it -- a two-line fix once correctly diagnosed, confirmed with a
screenshot afterward.

**DECISION — dispatch a genuinely context-free agent, not a fork.** Anna
asked for "someone who tests this without knowing what it should do." A
fork would inherit this whole session's context, defeating the purpose. Used
a fresh `general-purpose` agent instead, with no project background at all
in its prompt -- only a URL and an instruction to explore and report
confusion. Its findings (a real rendering bug on the Methodology deck, the
same orange-colour-misuse pattern Anna flagged independently, several more
instances of jargon/self-referential text, and the Upload tab being a
genuine dead end for a visitor with no files) were corroborating, not
duplicate work -- it found the slide-overlap bug neither Anna nor this
session had yet noticed.

**DECISION — "not evaluated" is a third state, not a flavour of "caution."**
The evidence table and the Overview's "next action" box used one boolean
(verified vs. caution) to represent what are really three distinct states:
passed, genuinely failed, and not-yet-evaluated. Collapsing "not evaluated"
into "caution" (orange) was the root cause of Anna's and the test agent's
shared complaint that the page "feels like something's wrong" when nothing
is. Added a real third state (`pending`, neutral grey) rather than just
recolouring the existing caution state, so failed vs. not-evaluated stay
visually distinguishable going forward, not just differently worded.

**Verification:** 170/170 tests pass, `node --check`/`py_compile` clean,
HTML balance/duplicate-id checks clean. Live-verified: the Methodology
slide-5 overlap is visually gone (screenshot, before/after); evidence-table
rows for not-evaluated gates render with the `pending` class, not `caution`
(confirmed via direct DOM query); the new `/sample/*` download route serves
BayWa's real challenge files with correct headers (confirmed via curl);
zero console errors across all four routes on a full fresh-tab reload.

## 2026-10-24 (latest+5): independent-review fix batch -- Overview swapped to hidden-window prediction, methodology/upload bugs fixed, cadence hardcoding removed (DECISION, RISK, RESULT)

**Context:** an independent review ("ChatGPT Codex", run by Anna against the
live site) surfaced seven findings, three personally re-verified in code by
the coordinating session before dispatch: a methodology-text/code mismatch,
a manual-override upload bug that could never actually fire, and a direct,
visible contradiction between the Overview's primary number and the
insurance report's number for the same turbine (T3).

**DECISION -- Overview's primary record swapped from the shown-window
self-validation to the hidden-window prediction (112,411 kWh, 01-04 Sept),
not the reverse.** The two pages disagreed because the Overview showed
T3's shown-window self-test (285,766 kWh, 04-10 Sept, real recorded wind to
check against) as the headline, while "Generate insurance report" produced
the hidden-window prediction (112,411 kWh, 01-04 Sept, no ground truth by
construction -- the actual graded deliverable) for the same turbine. Aligning
Overview to the hidden-window number (rather than the reverse) matches what
the BayWa challenge actually grades and required less rework. The
shown-window self-validation was not deleted -- it moved to a clearly
labelled "How we validated this method" / supporting-evidence role on the
Analysis page, honestly distinguished from the ungraded prediction (chart,
narrative, and `review.label`/`next_action` text all state plainly that no
ground truth exists for the 01-04 Sept window, by construction).

**Methodology text fixed to match the code, not the reverse.** The formula
caption claimed "least-squares regression" unqualified; production code
(`reconstruct_wind_speed`/`fit_weighted_references`) actually uses
variance-ratio fitting (`fit_linear(..., method="variance_ratio")`), a
deliberate, documented choice (2026-10-22 red-team finding F7: OLS
under-predicts energy through a power curve via Jensen's inequality; OLS is
only used for holdout-R² reference-selection ranking, never for the
reconstruction itself). Rewrote the HTML caption to describe variance-ratio
fitting instead of changing the code to match stale copy.

**Manual outage-window override bug fixed at the root cause, not patched
around.** `run_pipeline()` called `detect_target_turbines()`
unconditionally and raised before ever reaching the
`manual_start`/`manual_end` branch, so a manual override could never rescue
a target turbine with no NaN-run gap -- contradicting the function's own
docstring. Restructured to branch on manual-window presence *before*
computing targets, added `_targets_missing_in_window()` (every turbine with
zero valid readings in the given window, NaN-run-length rule aside) and five
new tests in `tests/test_upload_tool.py` covering the rescue path, the
clear-error path, and an explicit auto-detection-unchanged regression test.

**RISK found and fixed, not previously flagged: hardcoded 10-minute
integration cadence.** `loss_estimate.py`'s `INTERVAL_HOURS = 10/60` was
used unconditionally by `integrate_energy_kwh()`, including from
`upload_tool.py`'s live reconstruction path -- an uploaded file at any other
cadence (e.g. hourly) would have silently produced a wrong energy total (a
naive hourly-vs-10-minute mismatch is 6x). Fixed by giving
`integrate_energy_kwh()` an `interval_hours` parameter (default
`INTERVAL_HOURS`, so every internal research script -- `run_*.py`,
`compare_reconstruction_methods.py`, `lazy_baseline.py`,
`uncertainty_business.py`, all of which only ever run against the canonical
fixed-cadence research datasets -- is unaffected), and adding
`infer_interval_hours()`, which computes the median gap between consecutive
timestamps and raises if any gap deviates from that median by more than 5%
(an irregular cadence, not a genuine regular one at a different rate).
`upload_tool.py`'s `run_pipeline()` now infers the cadence from the selected
reference turbine's own full timestamp series (continuous through the gap,
so more reliable than the short reconstructed window itself) before calling
`integrate_energy_kwh()`. New test confirms an hourly-cadence synthetic
upload integrates at ~400 kWh (4 missing hourly readings x 100 kW), not the
~66.7 kWh the old hardcoded-10-minute assumption would have silently given.

**Honesty-wording fixes:** replaced "nearby"/"neighbouring reference
turbine" with "behaviorally selected reference turbine; geographic
proximity not verified" everywhere it represented a real BayWa-specific
claim (Overview/Analysis upload-results card in `app.js`, and both the
Summary and Method sections of `insurance_report.py` -- regenerated
`docs/EXAMPLE_INSURANCE_REPORT_T3.md` to match); there is no
farm-location registry for this dataset, so claiming geographic proximity
was never supportable. Left the two legitimate uses of "nearby" alone
(verified external Kelmarsh/Penmanshiel geographic framing, and general
future-concept language). Review-status label changed from the
contradictory "Reviewed -- all applicable checks passed" (next to a visible
"1 not evaluated") to "Evidence checks passed; uncertainty not calibrated."
Rounded the Overview's indicative financial-impact figure from
`fmt(value, 2)` (false-precision cents, "EUR 9,554.95") to `fmt(value, 0)`
("EUR 9,555"), matching the already-integer-rounded range beside it and
`insurance_report.py`'s own `_fmt_eur`. Updated README's stale "163 tests,
153 pass" line (two locations) to the current, re-verified "182 tests, 182
pass" -- the prior entry's 10 `openpyxl`-related failures no longer apply;
`openpyxl` is now installed.

**RESULT -- also fixed in this round (unrelated contrast sub-task, run
immediately before the above):** two new stdlib-only verification scripts
(`scripts/check_contrast.py`, `scripts/check_dead_controls.py`) found two
real WCAG AA failures (`--signal` on `--paper` for large text, 2.90:1 vs
3.0:1 needed; `--signal` on `--navy`, 4.31:1 vs 4.5:1 needed). Fixed by
darkening `--signal` (`#d57641` -> `#c2642f`) and adding a new
`--signal-light` (`#f0bb92`) token as the dark-background counterpart to
the existing `--signal-dark`, applied to the two actual text/icon uses on
navy backgrounds (`.hero-status`, `.chart-tooltip strong`). All 9 checked
colour pairs now pass. (A true headless click-through would need
Playwright -- a real new dependency, not yet installed or approved; flagged
to Anna via the coordinating session rather than added unilaterally.)

**Verification:** 182/182 tests pass (up from 170; 17 new:
`tests/test_upload_tool.py` x2 fixtures/5 tests, `tests/test_loss_estimate.py`
x7 tests for `infer_interval_hours`/`integrate_energy_kwh`'s new parameter).
`node --check workspace/assessment-data.js` clean.
`scripts/check_demo_copy.py`, `scripts/check_contrast.py`,
`scripts/check_dead_controls.py` all clean (one incidental
`check_demo_copy.py` finding -- an unused, never-rendered `schema_version`
JSON field in `assessment-data.js`, present before this round -- fixed by
deleting the dead field rather than widening the check's ignore-list).
Live-verified on a fresh server restart + fresh-tab reload across all four
routes (Overview, Analysis, Methodology, Upload): zero console errors;
Overview's headline now reads 112,411 kWh / 01-04 Sept / "Evidence checks
passed; uncertainty not calibrated" / "No ground truth exists to check this
prediction against"; Analysis page's T1/T2/T3 cards correctly separate each
target's hidden-window prediction from its shown-window self-validation
percentage with no contradictory claim; Methodology's formula caption and
limitations list both now describe variance-ratio fitting and the
hidden-window prediction accurately; chart's truth-toggle/legend correctly
absent (no ground truth exists for this series); EUR figure confirmed
rendering as "EUR 9,555" post-fix. Upload-tool's live file-picker flow was
not driven through the browser (file-input `.value` cannot be set via
JS/CDP in this tool), so the manual-override and cadence-inference fixes
are verified by the new unit tests and a direct `run_pipeline()` call
(both confirmed passing/correct), not by an in-browser upload.

## 2026-10-24 (latest+6): second independent-review (Codex) round -- presentation/copy fixes, window-separation redesign, and a live-verification-caught cadence regression

**Context:** a second independent review confirmed the P0 contradiction fix from
the previous round (112,411 kWh / 01-04 Sept agrees everywhere; 182/182 tests
passing; arithmetic independently confirmed correct) and found six categories of
follow-up findings, all presentation/copy, not calculation bugs. Coordinator's
instruction: fix stale copy first (factual regression), then calibration-implying
labels, then BayWa-scenario overclaim wording, then the hidden/shown-window
visual-separation redesign (flagged as the single highest-leverage fix), then
surface an already-computed-but-discarded data field, then a broken README
command. All six done; see below.

**Category 1 (stale copy, factual regression) -- DONE.** `app.js`'s per-target
`framing` string for the Overview record still described the OLD Overview
(shown-window median driving the headline) after the previous round swapped the
headline to the hidden-window prediction. Fixed to:
"T3 is the primary graded target for this submission. It was selected for
presentation because its shown-window self-validation error (X%) is the median
of the three targets' errors -- a reasonable match to expect for the ungraded
hidden window too." A SECOND, independent occurrence of the identical stale
"literal median... representative result, not the best case" text was found
during this round's own live verification in `assessment-data.js`'s
`baywa_comparison.intro` field (not caught by the coordinator's grep audit,
since it's a different data field from the one named) -- fixed to match.

**Category 2 (calibration-implying wording) -- DONE.** "Confidence range" card
label -> "Uncertainty status" (the card shows raw observed coverage, not a
calibrated interval). "...the total matches the validated estimate" (loss-chart
caption) -> "...matches the calculated prediction" (one occurrence found, not
two as the coordinator's message estimated -- the Overview hero text uses
different wording, handled under Category 4 below). "...supports confidence in
this method" -> "...provides an accuracy check for this method", fixed in BOTH
places it appears: `app.js`'s chart-note string AND the data-driven
`assessment-data.js` `next_action` field (the latter is what actually renders on
the Overview page -- the `app.js` occurrence is dead code for the current
record type, fixed anyway for consistency/future-proofing).

**Category 3 (BayWa-scenario overclaim wording) -- DONE.** "Real BayWa r.e.
submission" (3 occurrences: `app.js` route-title map, two `index.html` eyebrow
labels) -> "BayWa challenge-data prediction". "Real cross-park test" / "real
BayWa cross-park test" / "real BayWa cross-park case" (3 occurrences in
`evidence-tiers-data.js`, a generated-but-hand-edited data file that had
diverged from its generator script `build_evidence_tiers_data.py` -- noted as a
pre-existing staleness, not fixed beyond the requested text swap, to stay in
scope) -> "cross-asset test" / "cross-asset case". Methodology's "Naive
averaging of nearby turbines" -> "Naive averaging of other turbines in the
uploaded dataset". Analysis page heading "What happened during the outage" ->
"What the model estimates during the gap".

**Category 4 (hidden/shown-window visual separation) -- DONE, the highest-
leverage fix.** Root cause confirmed by inspecting the data: the "Reference
integrity" card on the Analysis page mixed `validation.compared_observations`
(864 -- a SHOWN-window metric, the self-validation holdout count) with
`domain-status`/`alignment-status` (computed from the HIDDEN window's 432
readings against the reference's trained range) in one unlabeled card, exactly
the mixing the reviewer flagged. Restructured into two explicitly headed
`.window-group` sections (new CSS, navy-underline divider + eyebrow tag):
"Hidden-window prediction -- the graded record" (reference & domain check,
renamed "Uncertainty status" card) and "Separate self-validation -- shown
window, 04-10 Sept -- used only to gauge method accuracy" (now also holding the
864-count `paired-count` field, moved out of the hidden-window card where it
didn't belong). Pure HTML/CSS move for `paired-count` -- `app.js` sets it by id
regardless of which card holds that id, so no JS change was needed for the
move itself. Added one new explanatory line directly under the Overview's hero
kWh number (`#hero-window-caveat`, new element + CSS, populated in
`renderAssessment()`), stating the hidden/shown-window distinction with live
data (lost kWh, T3's shown-window error%, worst observed error% across the 3
targets) rather than the coordinator's example's hardcoded numbers. Gate panel:
the "not evaluated" gate already had a distinct icon (`?` vs `✓`/`!`) and color,
but the color (`#8a8f78` muted gray) was too close in weight to the pass color
to read as clearly distinct at a glance -- changed to a highlighted amber box
(`background:#f7eacb`, mark `background:#8a6a1a`) with contrast-checked text
(5.92:1 on the row, 5.05:1 for the white glyph on its mark -- both pass WCAG AA;
computed by hand since `check_contrast.py` only checks the fixed CSS-variable
pairs it's told about, not ad hoc colours).

**Category 5 (surface the already-computed cadence) -- DONE.**
`upload_tool.py`'s `run_pipeline()` already called `infer_interval_hours()` for
the energy-integration fix from the previous round, but discarded the result
after use. Added `entry["inferred_cadence_minutes"] = interval_hours * 60` to
the result dict; `app.js`'s `renderUploadResult()` now shows a "Sampling
interval used" row. New test assertion
(`test_hourly_upload_integrates_at_hourly_cadence_not_hardcoded_ten_minutes`)
confirms the field is present and correct (60.0 minutes for the synthetic
hourly fixture).

**Category 6 (broken README command) -- DONE, and extended.** Confirmed by
direct test: plain `python3` on this machine has no numpy (`homebrew`
`python3`, not the project's venv), so `workspace/README.md`'s
`PYTHONPATH=src python3 -m windlens.baywa_tool_server` command fails with
`ModuleNotFoundError: No module named 'numpy'` for anyone following it
literally, while two lines above it the README already uses the full venv path
for a different command. Fixed to use the same
`/Users/annaradova/.venv/bin/python3` path, with a short note on what the
`ModuleNotFoundError` means if a reader substitutes their own interpreter. Also
fixed the root `README.md`'s "Running it locally" and "Current verified state"
code blocks for the identical root cause (same `ModuleNotFoundError` reproduced
by direct test) -- not explicitly named by the coordinator, but the same
category of fix and left broken would mean a reviewer following the README's
own top-level instructions hits the same wall; noted here rather than treated
as silent scope creep.

**Live-verification-caught regression (not in the coordinator's list -- found
during this round's own "read the whole site as a reviewer" pass):**
`infer_interval_hours()` (added in the previous round) rejected ANY timestamp
gap deviating from the median by more than 5%, with no tolerance for how MANY
such gaps existed. Tested end-to-end against the real BayWa sample files
(`workspace/sample/T2_data.xlsx` + `O1_data.xlsx` + `T2_power_curve.xlsx`,
downloaded via the running server's own `/sample/*` routes and POSTed to
`/run`) and got `ValueError: Timestamps are not evenly spaced (median gap
0.1667 hours; 1 of 12959 gaps differ from it by more than 5%)` -- the Upload
tool's own documented demo path, using the exact sample files linked on the
page, was completely broken. One irregular gap out of 12,959 (0.0077%) is
self-evidently a one-off data hiccup, not a wrong cadence, but the previous
round's fix treated any single bad gap as disqualifying. Root-caused and fixed:
added `IRREGULAR_CADENCE_MAX_FRACTION = 0.02` -- the existing per-gap 5%
deviation test still identifies which gaps are irregular, but the function now
only raises if MORE THAN 2% of all gaps are irregular, not on any single one.
Verified both directions: `test_rejects_irregular_spacing` (1 of 4 gaps bad =
25%, still raises) and a new `test_tolerates_a_single_one_off_gap_among_many`
(1 of ~300 gaps bad = ~0.3%, no longer raises) both pass; re-ran the exact
real-sample-file curl request after restarting the local server with the fix
and got a correct result (`estimated_lost_kwh: 133507.17`,
`inferred_cadence_minutes: 10.0`, `rows_predicted: 432`) instead of the error.
This is the kind of bug that only a real end-to-end run against real data
catches -- the previous round's synthetic unit-test fixtures were all
perfectly regular, so the too-strict rejection never showed up until this
round's live verification against the actual linked sample files.

**Verification:** 183/183 tests pass (up from 182; 1 new:
`test_tolerates_a_single_one_off_gap_among_many`, plus the
`inferred_cadence_minutes` assertion added to the existing cadence test).
`node --check` clean on `app.js`, `assessment-data.js`, `evidence-tiers-data.js`.
`scripts/check_demo_copy.py`, `scripts/check_contrast.py`,
`scripts/check_dead_controls.py` all clean, run again after every substantive
change in this round. Live-verified on a fresh server restart (the previous
dev server process, PID 96407, was killed and restarted so it would pick up
the code fix -- it was not a process this session started, but it is a stateless
local dev server local to this machine, safe to restart) + fresh-tab reload
across all four routes: zero console errors on Overview, Analysis (both detail
panels expanded), Methodology, and Upload. The real-sample-file upload path
was end-to-end verified via direct `curl -F` POSTs to the running server's
`/run` endpoint (not through the browser file-picker, which still cannot be
driven via this session's tools -- same documented limitation as the previous
round), which is a stronger check than the previous round's unit-tests-only
verification for this path, since it caught the regression above that no unit
test had surfaced.

## 2026-10-24 (latest+7): P2 round -- nav relabeling, upload-tool evidence parity, analyst checklist, ambiguous-label fixes, commercial-figure demotion

**Context:** coordinator said there was more time than assumed and asked for five more categories (7-11) after categories 1-6 above, same "we have more time, same discipline" instruction: checkpoint docs, re-run the full suite (held at 186/186 -- none of this touches calculation logic except Category 8's new, purely additive evidence fields), report back with before/after detail.

**Category 7 (nav labels communicate sequence) -- DONE.** Sidebar nav relabeled
from "Overview / Analysis / Methodology / Analyse your own outage" to "Result /
Why to trust it / How it works / Run your own data" (hashes/routes unchanged:
`#overview`/`#analysis`/`#method`/`#upload`). Per-page topbar `<h1>` titles left
as their own, more descriptive text (a different, intentional pattern from the
short nav label, not an oversight). Every in-copy reference to a tab by its old
name updated to match: "Real BayWa r.e. submission" eyebrow and "Overview and
Analysis pages" (`index.html`, `app.js`) and, in the two hand-assembled data
files, all 7 occurrences found by searching for the pattern (`assessment-data.js`:
the uncertainty-reason string, a review-gate reason, `next_action`, a
`limitations[]` entry, and the `baywa_comparison.intro` field; `evidence-tiers-data.js`:
both "Overview and Analysis pages" references) -- confirmed zero remaining
matches by re-grepping after the edits.

**Category 8 (upload-tool evidence parity + task-first ordering +
pre-run confirmation) -- DONE, all three parts.**
1. `upload_tool.py::run_pipeline()` now computes and returns, per target:
   `reference_coverage_pct` (reconstructed rows / the target's own expected row
   count in the outage window, from the file's own sampling grid -- a reference
   with gaps of its own now shows up as <100% instead of silently producing
   fewer rows with no explanation), `domain_check` (reusing
   `reconstruct.py::reference_within_training_domain()`, the SAME function the
   official BayWa record's review gate uses -- not a reimplementation),
   `inferred_cadence_minutes` (now computed unconditionally, not only when a
   power curve is uploaded), and a static `raw_reconstruction_notice` stating
   this is unvalidated against ground truth for this event, same standard as
   the official record. All three new per-target computations are wrapped in
   their own try/except so one target's bad reference data can't abort the
   whole multi-target upload (extending the existing per-target error-isolation
   pattern). `app.js::renderUploadResult()` renders all of these as new rows on
   each upload-result card.
2. The upload page's copy reordered task-first: the first thing visible is now
   "Select your target turbine's file..., a reference turbine's file, and
   (optional) a power curve", with the four-column-schema-variant detail moved
   into a collapsed `<details>` "File format details" section below the task
   instruction and the sample-file download line (kept visible, since it's
   actionable, not schema detail).
3. New lightweight `/preview` server endpoint (`baywa_tool_server.py`, shares
   its multipart-parsing and file-classification code with `/run` rather than
   duplicating it) backed by a new pure function
   `upload_tool.py::describe_uploaded_files()` -- per-file role guess (target /
   reference candidate / power curve) with NO reference selection or model
   fit, wired to the `#upload-files` input's `change` event in `app.js` so a
   confirmation summary ("T2_data.xlsx -> target (has a data gap)", etc.)
   appears before the user clicks Run, letting a mis-assigned file be caught
   early.

**A real bug caught by this round's own live verification (not in the
coordinator's list):** `describe_uploaded_files()`'s first version flagged ANY
NaN reading in a file as "target (has a data gap)" -- tested against the real
sample files via `curl -X POST /preview` and got BOTH `T2_data.xlsx` AND
`O1_data.xlsx` labeled "target", when the real `/run` pipeline correctly
selects O1 as T2's reference (confirmed: `detect_target_turbines()` requires a
NaN run of at least `MIN_OUTAGE_RUN_LENGTH` (3) consecutive rows, not just any
single NaN -- O1 has scattered, isolated single-row NaN readings elsewhere in
its real history that don't reach that threshold). A preview that contradicts
what the real run then does would defeat the entire point of Category 8's
ask. Fixed by reusing the exact same `_longest_nan_run`/`MIN_OUTAGE_RUN_LENGTH`
logic `detect_target_turbines()` itself uses, instead of a naive `.isna().any()`
check. Re-verified against the real sample files after the fix: O1 now
previews correctly as "reference candidate (no gap in this file)", matching
`/run`'s own selection.

**Category 9 (analyst operational checklist) -- DONE.** Added a short, scannable
4-item ordered list directly inside the Overview's existing "Next action" panel
(not a new section, to avoid adding visual weight to the hero area): confirm
the outage cause independently, confirm turbine identities match the reader's
own records, review the T1/T2/T3 self-validation spread on the Why-to-trust-it
page, and treat the figure as provisional, not a settlement number.

**Category 10 (remaining ambiguous labels) -- DONE.** The Analysis page's
"Reference & domain check" card (hidden-window group, from the previous
round's window-separation redesign) now also shows "Prediction window points:
432" next to "Selected reference", so the hidden-window count is visible in
that card too, not only in the chart's caption above it -- symmetric with the
shown-window card's "Training-history points compared: 864" (also relabeled
this round, from the previous round's generic "Matched time-points compared").
"Tested wind-speed range" gained a qualifying note: "This checks wind-speed
range only -- not power-curve behavior, seasonality, or cross-farm transfer."

**Category 11 (commercial-figure prominence) -- DONE.** `.commercial-result
strong` (the EUR figure) changed from 28px `--signal-dark` (the same
attention-drawing accent color used for warnings/cautions elsewhere, which was
inadvertently giving a merely-indicative demo-price figure outsized visual
weight) to 21px `--ink` (plain body-text color, same family/weight pattern as
other card numbers, matching its actual evidentiary weight). Not removed, not
hidden -- same information, demoted visual salience.

**Verification:** 186/186 tests pass (up from 183; 3 new: cadence-plus-coverage
assertion extended, `test_result_includes_coverage_domain_check_and_raw_notice`,
`DescribeUploadedFilesTests` x2). `node --check` clean on `app.js`. Dev server
restarted twice during this round so curl-based verification reflected the
latest code each time. `scripts/check_demo_copy.py`, `scripts/check_contrast.py`
(the new EUR color change re-verified: `--ink` on `--panel` is an existing
checked, passing pair), `scripts/check_dead_controls.py` all clean. Live-verified
all four routes (now titled Result/Why to trust it/How it works/Run your own
data in the sidebar) via fresh-tab reload: zero console errors; Overview shows
the new checklist and amber not-evaluated gate; Analysis's detail panel shows
both new point-count labels and the domain-check qualifier; Upload page shows
the reordered task-first copy with collapsed format details. The real
end-to-end `/preview` + `/run` round-trip against the actual linked sample
files (`T2_data.xlsx`/`O1_data.xlsx`/`T2_power_curve.xlsx`) was re-run after
the bug above was fixed and confirmed correct: `reference_coverage_pct: 100.0`,
`domain_check.within_domain: true`, `inferred_cadence_minutes: 10.0`, and the
`/preview` role guesses now agree with what `/run` actually selects. The
browser file-picker itself still cannot be driven by this session's tools (the
same documented limitation as both previous rounds), so the pre-run
confirmation summary's client-side rendering logic (`renderUploadSelectionSummary`
in `app.js`) was verified by code review plus the server-side `/preview`
response it consumes being independently confirmed correct, not by a live
file-select-and-watch-it-render pass.

---

**2026-10-24 (latest+8): IA rebuild -- two pages instead of four, from Anna's
hand-sketched wireframe. DECISION.**

**The sketch.** Page 1, "Result": upload control up top, prominent; on submit
the form collapses and the result renders in the same place, same page; a
chart with the target's own line and the selected reference overlaid, outage
window visibly shaded; headline kWh, accumulated-energy chart, wind RMSE/MAE,
power deviation, financial summary, link down to the full report. Default
landing state (before any upload) still shows the live BayWa T3 headline
record -- the graded submission must be visible without an upload action.
Page 2, "Methodology": merges the old Analysis (validation) + How-it-works
(method) + report actions into one page, framed as "play around with the
behavioural analysis." Keeps the editable price and live-recalculating
estimate, the wind-first/reference-selection/uncertainty narrative.

**A real correctness gap, not just copy (fixed at the source).** Anna's margin
note: if the best-ranked reference turbine doesn't actually have data covering
the target's outage window, don't silently predict from it -- fall back to the
next-best reference that does, and say so. Checked: `select_reference_turbine()`
(`reconstruct.py`) ranked candidates purely by pre-outage holdout R², with zero
check on whether the top pick has any readings during the window actually being
reconstructed -- a candidate could be the best historical fit and still be
itself down (or simply never uploaded) for the exact window needed, silently
producing an empty/degenerate reconstruction with no coverage (the existing
`reference_coverage_pct` field would have shown 0%, but nothing would have
substituted a working reference). Fixed by extending the function with optional
`full_df`/`window_start`/`window_end` kwargs (backward-compatible, default
`None`): when given, the top-ranked candidate with zero coverage in the window
is skipped in favor of the next-best-ranked candidate that does have coverage,
surfaced via a new `reference_fallback_note` string (never silent). Wired into
BOTH callers that matter: `run_baywa_assessment.py` (the official T1/T2/T3
record generator -- confirmed no fallback triggers there; O1/O2 fully cover
the hidden window as expected) and `upload_tool.py::run_pipeline` (the live
upload path, where a user's own files are far more likely to have gaps). Two
new tests in `test_reconstruct.py` cover the fallback firing and staying
silent when unneeded.

**The overlay chart needed new data the committed `assessment-data.js` didn't
have.** The existing `series.points` field only carries the hidden window's
432 *reconstructed* values -- no raw target/reference readings, no pre/post-gap
context. Built a one-off script (not committed, run from scratch via the venv
python) pulling T3's and O1's real readings from `data/derived/baywa_canonical.csv`
across Aug 29 - Sept 7 (3 days before/after the hidden window), hourly-
downsampled to 216 points, with an `in_outage` flag per point. Inserted as a
new `overlay_series` top-level field via the same safe
`json.loads`/`assert`/`json.dumps` pattern used throughout this project for
hand-edited data files -- never a blind overwrite. Also added
`validation.power_rmse_kw`/`power_mae_kw`/`power_signed_bias_kw` (pulled from
`data/derived/baywa_assessment_result.json`'s existing shown-window power-error
numbers, which were computed but never surfaced in the committed JS) so the
Result page's "power deviation" stat has a real number, not a placeholder. For
live uploads, `upload_tool.py` gained an equivalent `_overlay_series()` that
builds the same shape directly from the uploaded `wind_df` (margin = outage
duration either side, capped to ~400 points) -- no extra files needed, since
the full history is already in memory.

**Unifying the Result view.** `buildResultViewModel(source, data)` in `app.js`
normalizes either the official assessment object or one `/run` target entry
into one small shape (target/reference ids, window, lost kWh, wind/power
error -- `null` with an honest "not applicable" reason where a live upload
has no ground truth), and `renderResultView(vm)` is the only thing that
touches that part of the DOM. Uploading a file now replaces the SAME view in
place (hides the form, shows a "Show the live BayWa record again" reset
button) rather than opening a separate, visually lesser result area below a
form -- directly satisfying Anna's "should feel like it replaces/updates that
same view" note. The financial-impact summary on Page 1 is read-only and
mirrors whatever price is set on the Methodology page's (unchanged) editable
input, via a shared `refreshFinancialSummary()`.

**"Send an email": scoped down per the coordinator's answer to Anna's
question.** No SMTP, no server-side send (credentials risk this close to
deadline, and unnecessary). The existing `email_draft` (already generated
server-side by `insurance_report.py`, already returned by `/insurance-report`)
is now wired into a real `mailto:` link -- `mailto:?subject=...&body=...`,
built client-side by splitting the draft's leading `Subject: ...` line from
its body -- so clicking it opens the user's own mail client with the draft
prefilled, ready for them to review and send themselves. Replaces the old
"download .txt" behaviour for that action entirely (not kept alongside it --
Anna's brief named exactly two report actions for this page, PDF and email).

**Evidence-tiers cut down, not deleted.** Anna: "we will remove analysis on
the other data sets in full... mention those in other ideas we considered
under methodology and show some small results there, but not extensive info."
The full Kelmarsh/Penmanshiel/Hill-of-Towie tier grid/scale/footnote no longer
renders in the jury-facing demo; replaced with one paragraph plus one summary
stat under "Other validation approaches we considered" on the Methodology
page (`renderOtherApproachesSummary()`). `evidence-tiers-data.js` and the
scripts that produced it are untouched -- this only stops surfacing the
extensive version, per Anna's own framing.

**Trust gates relocated, not dropped.** The detailed pass/fail/not-evaluated
gate list (with the Round 2 amber "not evaluated" styling, contrast-checked)
is not named in Anna's sketch for either page; rather than deleting carefully-
tuned existing content, it was moved to Methodology under "Why to trust this
record" -- consistent with that page's framing and with the standing
instruction to flag rather than silently override anything already verified
working. Flagging this relocation here as the one place this round made an
interpretive call beyond the literal sketch.

**Verification:** 189/189 tests pass (3 new: the reference-coverage fallback
firing, the no-fallback-needed case, and the upload overlay-series shape/gap
assertions). `node --check workspace/app.js` clean. All three check scripts
clean (`check_demo_copy.py` caught one instance of literal "the demo" in new
copy, fixed). Dev server restarted and a real browser session driven against
it: zero console errors on fresh loads of both `#overview` and `#method`
(after forcing a hard reload -- the data files have no cache-busting query
string by default and the browser was serving a stale cached copy across the
hash-only navigation during verification, caught and fixed by bumping their
query strings); the official T3 record renders correctly (112,411 kWh,
overlay chart showing T3's real gap against O1's continuous line with the
outage window shaded, loss chart, EUR 9,555 at the default price); the price
input on Methodology live-updates Page 1's read-only financial summary; the
insurance-report `mailto:` link was generated and its decoded subject/body
inspected directly (correct, no duplicated "Subject:" line in the body). A
real end-to-end live-upload pass was run IN THE BROWSER (not just curl) by
fetching the three sample files client-side and POSTing to `/run` exactly as
the real upload form does, then calling the same `renderResultView()`/
`buildResultViewModel()` code path the form itself calls: T2 target, O1
reference, 100% coverage, in-domain, 10-minute cadence, 432-point overlay
series with the gap and shading rendering correctly, "YOUR LIVE RUN" tag
displayed, honest "not applicable" wind/power error, and the reset button
correctly restoring the official record afterward. The one gap unchanged from
prior rounds: this session's browser tools still cannot drive the native
`<input type=file>` picker itself, so the actual drag-and-drop/file-dialog
interaction was not driven end-to-end -- everything downstream of file
selection (the fetch, the server round-trip, and the client-side rendering)
was.

---

**2026-10-24 (latest+9): IA-rebuild follow-up round -- further copy trim,
README rewrite, a second real correctness gap, multi-target Result UI.
DECISION.**

**1. "Other validation approaches" cut further, per Anna's exact words.**
Her own framing: "we can totally remove analysis done for the other external
data sets... I would only include mention for those that we considered it...
but to future opportunities." The paragraph from the prior round (still
quoting "6.8% WAPE, Kelmarsh KWF1") was still result-shaped. Removed entirely
as a standalone section; folded into the existing "What we'd build next" list
as one forward-looking bullet, no numbers, no tier language: public-farm
validation at a range of distances, and a turbine-location registry's effect
on reference selection, both named as open directions "not part of this
submission's evidence." `renderOtherApproachesSummary()` and its DOM target
removed from `app.js`/`index.html` since nothing renders there now;
`evidence-tiers-data.js`'s own `<script>` tag also dropped from `index.html`
(nothing in `app.js` reads `window.WINDLENS_EVIDENCE_TIERS` any more) --
the underlying data file and the scripts that generated it are untouched on
disk, just no longer loaded into the live page, which is the literal
reading of "don't surface the extensive version."

**2. Root `README.md` was not a trim job -- it predated the real BayWa data
arriving and needed a rewrite.** On inspection: every section (scope note,
"what it does," the WAPE/coverage tables, "honest limitations") described the
Kelmarsh/Hill-of-Towie same-farm-proxy study from before the real BayWa
challenge data arrived -- 19 separate mentions of those two farms, zero
mentions of T1/T2/T3 or the real submission anywhere in the file. Not what a
reader opening the repo on GitHub should see first. Rewrote it to center the
real submission: the real hidden-window prediction (T3, 112,411 kWh, O1
reference, no ground truth by construction) and the real shown-window
self-validation numbers (T3 5.19%, T2 2.73%, T1 39.36% outlier) up front,
followed by an updated "What it does" (matching the real pipeline, including
the 2026-10-24 reference-coverage-fallback fix), updated "Honest limitations"
(rewritten for the real-data caveats: no ground truth for the hidden window
by construction, pure behavioral reference selection with no geography
registry, proxy "truth" power, no calibrated uncertainty yet), one
"Future opportunities" section (the same brief, non-numeric framing as the
Methodology page bullet above -- Kelmarsh/Penmanshiel/Hill-of-Towie mentioned
once, pointing to `docs/DECISION_LOG.md`/`docs/METHOD_BAKEOFF_2026-10-23.md`/
`docs/REDTEAM_2026-10-23_adversarial_review.md` for full history without
featuring them), and an updated repository-layout/running-it-locally section
reflecting the two-page Result/Methodology workspace. The docs/ files
themselves are untouched, just no longer the README's main content.

**3. A second real correctness gap, this time in how a whole-farm-down
upload applies power curves.** Anna asked how the upload tool handles several
turbines going down at once, and whether it's annoying (one at a time).
Checked: `run_pipeline()` already loops over every auto-detected target in
one combined upload -- that part was already right, already least-touch-point
(drop every file together, auto-classified). But `baywa_tool_server.py` did
`power_curve_df = load_power_curve(*power_curve_items[0])` -- only the FIRST
uploaded power-curve file, applied to every target. BayWa ships one power
curve per turbine (`T1_power_curve.xlsx`, `T2_power_curve.xlsx`, etc.); a
real whole-farm-down upload with each target's own curve would have silently
applied turbine 1's curve to every other target too -- wrong kWh for every
target after the first, no error, no warning. Fixed with
`_find_power_curve_for_target()` in `upload_tool.py`: matches an uploaded
power-curve filename to a target turbine by the same word-boundary-safe
pattern as the turbine id (e.g. `T2_power_curve.xlsx` -> T2), resolved
separately for EACH target inside `run_pipeline`'s loop via a new
`power_curve_items` parameter (the existing single-DataFrame `power_curve_df`
parameter stays for simple single-curve callers, including the existing unit
tests, so nothing there needed to change). A target with no matching curve
among what was uploaded gets an explicit, per-target
`estimated_lost_kwh_unavailable_reason` ("No power curve uploaded for T1 --
showing wind-speed reconstruction only") -- never a silent substitution of
someone else's curve. `baywa_tool_server.py` now passes the raw
`power_curve_items` list through to `run_pipeline` instead of pre-loading
just the first file; its now-unused `load_power_curve` import was removed.
Two new tests in `test_upload_tool.py` (`RunPipelineMultiTargetPowerCurveTests`)
cover both the correct-curve-per-target case (two targets, two curves with
deliberately different flat kW values so a swap would be caught) and the
named-reason-no-fallback case.

**Verified against the real files, not just synthetic fixtures:** curl'd
`/run` with T1+T3's real data, O1+O2 as references, and both T1's and T3's
real power curves together in one upload -- T1 came back at 118,373 kWh and
T3 at 112,411 kWh, matching the official per-target hidden-window figures
exactly (T3 identical to the graded record; T1 matching the comparison
figure already shown on the Methodology page), confirming no cross-target
curve mixing.

**4. Multi-target Result UI, agreed design with Anna.** When `/run` returns
2+ targets, a single-target-shaped result page doesn't scale (stacking N
overlay charts, or silently showing only one). Built: a summary row per
returned target renders immediately with zero clicks (turbine id, its own
outage window, headline kWh or its unavailable-reason), with the existing
single-target detail view (hero, overlay chart, loss chart, financial
summary) switched underneath by clicking a row -- explicitly NOT one shared
chart across targets' potentially non-overlapping windows, which would
compress or mislead, matching Anna's own call on this. Single-target uploads
(the common case) render exactly as before: the summary section stays
`hidden`, detail renders directly. Implemented as
`renderUploadTargetsSummary()` in `app.js`, reusing the existing
`buildResultViewModel()`/`renderResultView()` pair per-row on click; the
"Show the live BayWa record again" reset button also hides the summary.
Live-verified in-browser with the real T1+T3 two-target upload above: both
summary rows render with correct per-target kWh, clicking the inactive row
switches the detail view to that target (confirmed via `asset-id`/`lost-kwh`
changing and the `active` class moving), and the reset button correctly
hides the summary and restores the single-target official view.

**Also this round (smaller, same honesty standard):** the upload form gained
explicit "what to upload" requirements copy (every broken turbine's own
file, at least one reference file, and that turbine's own power-curve file
for a financial figure) and an honest, undeferred-limitation note that
auto-detection only finds a turbine's single longest gap -- a second,
separate outage on the same turbine needs the manual-window fields run a
second time; this is staying as a known limitation for this submission, not
silently unstated.

**Verification:** 191/191 tests pass (2 new beyond the prior round's 189:
per-target power-curve matching, and the no-match-named-reason case).
`node --check workspace/app.js` clean. All three check scripts clean. Live-
verified in a FRESH browser tab (not a reused one with stale console history)
against the restarted server: zero console errors on both `#overview` and
`#method`. The real multi-target `/run` test above required temporarily
adding T1/T3's files and their power curves to the server's sample-file
whitelist (`SAMPLE_FILES` in `baywa_tool_server.py`) so the in-browser
`fetch()` could reach them the same way a real upload form would -- reverted
immediately after verification, confirmed reverted by a 404 on
`/sample/T1_data.xlsx` and a clean server restart before reporting back. Same
file-picker limitation as every prior round: the actual click-to-select step
was not driven; the fetch-and-render path downstream of it was, using the
real server's real response to real files.
