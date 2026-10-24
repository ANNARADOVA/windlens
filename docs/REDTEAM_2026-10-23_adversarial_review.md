# Red-team review: WindLens, everything challenged

**Date:** 2026-10-22 (evening). The filename's 2026-10-23 date was set by the brief.
**Reviewer:** separate Claude Code session (Opus 5.5). It was briefed to break the project's claims, not confirm them.
**Scope:** read-only. No code, data, `workspace/` or other doc was modified. This file is the only new project file. Every recomputation ran from scratch scripts outside the repo (in the session scratchpad). They used the project's own unmodified functions and the existing `.venv` (pandas 3.0.6 / numpy 2.5.4). Nothing was installed and no git command was run.

> **One-line verdict:** the engineering is careful and every number I re-ran reproduces exactly. However, the project's two headline conclusions are both partly artefacts:
> - **"Uncertainty coverage target not met."** This is driven by a target that even a perfectly calibrated interval would miss about 45% of the time.
> - **"Direct power is about 2x better than wind-first."** This is inflated by a timestamp-alignment bug in the wind-first scorer, by the known-biased OLS variant of MCP, and by a same-farm validation setup that does not match the BayWa challenge.
>
> Most seriously, the "Estimate — reviewable" trust label depends on hidden truth that will not exist in a real outage. It has already approved an estimate that was 70% wrong.

---

## 0. The brief's own premise was wrong

The brief says the overnight bake-off "hit a usage-limit error before producing anything" and that no `docs/METHOD_BAKEOFF_*.md` exists. **That is false.** The bake-off ran to completion and produced:

- `docs/METHOD_BAKEOFF_2026-10-23.md` (23.6 KB, last modified 18:40 today);
- `data/derived/validation/method_bakeoff_2026_10_23.json`;
- `src/windlens/split_conformal.py` and `src/windlens/run_method_bakeoff_2026_10_23.py`;
- 6 new tests in `tests/test_split_conformal.py`;
- a 2026-10-23 entry at `docs/DECISION_LOG.md:1011`.

It is reviewed below (§F9) like every other claim. The coordinating session's picture of project state is therefore stale, and anything it plans on top of that picture should be re-checked.

---

## Findings, most damaging first

Severity scale: **Critical**, the pitch or a headline number is wrong as stated; **High**, a material distortion of a headline number or of method choice; **Medium**, a real defect with a bounded effect; **Low**, wording, labelling or hygiene.

### F1 — Critical. The "Estimate — reviewable" label is computed from hidden truth and cannot be produced in a real outage

**Claim challenged.** `README.md:14` and the demo's trust panel present the review gate as the product's decision-support mechanism. `HANDOVER.md` says the demo block "passes every current gate".

**Evidence.** In `src/windlens/backtest.py`, two of the five gates read the held-out truth of the very event being labelled:

- **`beats_baseline`** (`backtest.py:229-231`) compares ensemble and baseline wind RMSE, where both RMSEs come from `wind_speed_errors(reconstruction, hidden_truth)`.
- **`uncertainty_gate_passed`** (`backtest.py:239-241`) uses `event_evaluation.coverage_pct`, which is coverage scored against `hidden_truth` (`backtest.py:103-111`).

In a real outage there is no target wind or power for the window, so neither gate can be evaluated and the label cannot be produced. The spec asks for something different. `WindLens_instructions.md:222` requires that "back-test performance beats the agreed baseline", meaning a property established beforehand in back-tests and then applied to new events. The code turned it into a per-event oracle. The demo also displays "Coverage met the calibration target on this block" (`app.js:55`), which is unknowable in production.

Two related defects:

- The `input_qa` gate is hard-coded `True` (`backtest.py:234`, `assessment.py:83`) and always renders a ✓ in the UI (`app.js:59`).
- `uncertainty_gate`'s failure reason `"insufficient_calibration_observations"` actually checks the event's observation count, not the calibration count (`uncertainty_business.py:151-154`).

**Verdict: confirmed problem.** The prior audit and the research doc both missed it. It is a design-level issue, not a bug. A deployable gate would have to use only information available at outage time: reference completeness, domain check, history length, and a back-test-derived error quantile for this reference and regime.

### F2 — Critical. No completeness gate: a −70% kWh estimate was labelled "Estimate — reviewable"

**Claim challenged.** The gates ensure a "reviewable" estimate is trustworthy. The audit (§4) described silent dropping of timestamps as structurally possible but "small here".

**Evidence.** I reproduced the Hill of Towie (HoT) 28-block back-test; every per-block coverage matched the published JSON. Block **2024-08-13 → 08-18** is labelled **"Estimate — reviewable"**, with every gate passed and 93.7% coverage.

| Item | Value |
|---|---|
| Selected reference | T04 |
| Event timestamps with T04 data | **221 of 720** (31%) |
| Ensemble estimate | **28,600 kWh** |
| Hidden truth | **95,059 kWh** |
| Error | **−69.9%** |
| Coverage computed over | the 221 rows that exist |

The wind-first scorer sums predicted power only over timestamps where the reference reported, so the missing 69% of the outage contributes zero kWh with no warning. Why this happened:

- HoT blocks were picked by scanning for ≥95% coverage of the target T01 only (`DECISION_LOG.md:744`), not of the references.
- No gate checks that the reconstruction covers the outage window.

A second, smaller case is 2024-05-20: the ensemble has 509 of 720 rows. There the misalignment happens to cancel the model error. The reported error is −3.1% when the error on matched rows is +25.0%.

**Verdict: confirmed problem.** This is the exact failure an analyst would act on: a confidently labelled number that is 70% low.

### F3 — Critical (external validity). The validated problem is not the BayWa challenge

**Claim challenged.** The challenge (`WindLens_instructions.md:9-11`) reads: "When a wind farm loses power, it stops generating electricity **and recording wind data** … use wind data from a **neighboring reference wind farm**."

**Evidence.** Every number in this project reconstructs one turbine from turbines on the same farm, of the same model, a few hundred metres away:

| Farm | Target | Peer distances | Turbine model |
|---|---|---|---|
| Kelmarsh | KWF1 | KWF2–6 at **0.27–0.75 km** (computed from `Kelmarsh_WT_static.csv`) | all Senvion MM92 |
| Hill of Towie | T01 | nearest four at **0.34–0.52 km**, farthest 3.3 km | all 2,300 kW |

In the challenge's scenario, a farm-wide outage, these same-farm peers would be dark too.

- **Kelmarsh** discloses the same-farm proxy (`WindLens_instructions.md:106`, `assessment.py:113`).
- **Hill of Towie** has a misleading `honesty_note` in `hill_of_towie_multiyear_uncertainty_backtest.json`: "This is a genuinely external farm (not same-farm, unlike Kelmarsh)." HoT is a second farm, but its references are same-farm too.

This matters most for the method recommendation. Direct power-to-power regression is near-trivial between identical neighbouring turbines (fitted slopes about 0.9). It has no physical basis across farms with different turbines, power curves, curtailment regimes and availability. Wind-first (reference wind → target wind → target power curve) is the physically appropriate chain for the actual challenge.

**Verdict: confirmed problem.** The disclosure is partial (Kelmarsh only) and never framed as "we have not validated the challenge's scenario". No WAPE or coverage number here transfers to neighbouring-farm reconstruction. That scenario is untested.

### F4 — High. The "90% of blocks must individually reach 90% coverage" target is unattainable by construction, so the headline negative result is an artefact

**Claim challenged.** HANDOVER/PROJECT_STATE: "the 90%-of-blocks coverage target is **not met on either farm, with 95% confidence**". The bake-off repeats this.

**Evidence.**

1. **Origin.** The target is not in the spec. It is an agent's interpretation of Anna's "push toward 90%, ideally 95%" (`DECISION_LOG.md:332-355`).
2. **A perfect interval fails it.** I simulated a perfectly calibrated 90% interval (errors with the exactly known distribution) scored per 5-day block of 720 ten-minute points. With the lag-1 error autocorrelation measured on the real blocks (median ρ ≈ 0.6–0.7), a block reaches ≥90% coverage **53–58%** of the time. Results for ρ = 0, 0.8, 0.9, 0.95, 0.98 were 53.1%, 53.4%, 54.9%, 54.1% and 57.8%. To pass 90% of blocks, the interval would have to be deliberately mis-calibrated wide (well above nominal 90%).
3. **The observed pass rates match a perfect interval.** Kelmarsh's 9/19 (47%, Wilson CI [27%, 68%]) and HoT's 17/28 (61%, CI [42%, 76%]) both contain about 54%.
4. **Pooled coverage is on target.** Recomputed over all scored points it is Kelmarsh **90.4%** baseline / **90.8%** ensemble and HoT **90.3% / 89.8%**.

The statement "statistically distinguishable from met" is arithmetically correct but refers to a target no method could meet.

What the data does show is that per-block coverage is over-dispersed. The Kelmarsh range is 80.0–99.4%, wider than autocorrelation alone produces (simulated 10th–90th percentile about 85–95% at ρ ≈ 0.9). That points to real conditional mis-calibration: short history (Kelmarsh's four blocks with <30 days of history all fail) and regime effects. That is the honest problem statement.

**Verdict: confirmed problem.** The project has been reporting failure on its calibration where the marginal evidence says it roughly works, and has not reported the actual weakness (below). Coverage should be reported as pooled/marginal coverage with a CI, plus a per-block dispersion diagnostic. "% of blocks ≥ 90%" should be dropped or re-based (e.g. "% of blocks ≥ 80%").

### F5 — High. The product's actual promise, a kWh figure with an uncertainty interval, is neither shown nor validated

**Claim challenged.** The pitch is "lost kWh with honest uncertainty".

**Evidence.**

- **Nothing in the UI carries a range.** The hero number `lost-kwh` (`app.js:31`) and the EUR exposure (`app.js:83`) are point values. The only "90% interval" on screen is a 10-minute **wind-speed** band (`index.html:60`).
- **Every coverage number measures wind, not energy.** All coverage figures in every doc are pointwise wind-speed (or kW) coverage. None is coverage of the event's kWh total, which is the number an analyst signs off.
- **The kWh propagation exists but is dead code.** `uncertainty_business.propagate_power_interval` has no caller in the demo path. I ran it on every block:

| Farm | kWh interval covers the true total | Median width, % of the true kWh | Width range |
|---|---|---|---|
| Kelmarsh (ensemble) | 19/19 | **98%** | 55–173% |
| Hill of Towie (ensemble) | 27/28 | **76%** | 26–346% |

These intervals are almost uninformative (roughly "estimate ± half of itself"). The cause: the propagation shifts every 10-minute point to the same residual quantile at once, which assumes errors are perfectly correlated across the event. Measured error autocorrelation at a 6-hour lag is only about 0.05–0.14.

**Verdict: confirmed problem.** The honest, simple fix is an event-level kWh interval calibrated on back-test events (see §Methodology).

### F6 — High. The WAPE comparison between wind-first and direct power is not like-for-like (scoring bug)

**Claim challenged.** "Direct power ≈ 2x lower WAPE than wind-first" (bake-off; `DECISION_LOG.md:1018`). The README says wind-first does not meet the ≤10% WAPE target.

**Evidence.** The two scorers sum over different timestamps:

- **Wind-first** (`backtest._score`, `backtest.py:181-187`) sums estimated power over reconstruction timestamps and actual power over **all** hidden-truth timestamps. `estimate_loss` (`loss_estimate.py:85-91`) silently accepts arrays of different lengths and different timestamps.
- **Direct power** (`run_method_bakeoff_2026_10_23.py:132-134`, `run_direct_power_uncertainty_backtest.py:84-88`) inner-joins first.

Wind-first is therefore penalised for every reference gap; direct power is not. Recomputed over all 47 blocks with identical scoring on matched timestamps:

| Farm | Method | WAPE as shipped | WAPE, timestamp-aligned | Bias shipped → aligned |
|---|---|---|---|---|
| Kelmarsh | wind-first baseline | 10.04% | 9.89% | −9.4% → −9.3% |
| Kelmarsh | wind-first ensemble | 11.71% | 11.39% | −11.4% → −11.1% |
| Kelmarsh | direct power | 6.34% | 6.34% | −4.7% |
| HoT | wind-first baseline | 13.88% | **10.61%** | −9.7% → **−6.3%** |
| HoT | wind-first ensemble | 12.99% | **9.72%** | −9.7% → **−5.8%** |
| HoT | direct power | 6.98% | 6.98% | −0.8% |

- **Kelmarsh:** small effect.
- **Hill of Towie:** the gap shrinks from about 2x to about 1.4–1.5x, and aligned wind-first ensemble (9.72%) *meets* the 10% target the README says it misses.

Separately, the bake-off's own report subset never showed "2x":

| Farm | Direct power | Wind-first | Ratio |
|---|---|---|---|
| Kelmarsh | 7.60% | 9.21% / 9.73% | 1.2–1.3x |
| HoT | 6.82% | 9.16% / 11.85% | 1.3–1.7x |

Its verdict sentence (`METHOD_BAKEOFF_2026-10-23.md:286-287`, "roughly 2x … on both farms, on both subsets") overclaims.

**Verdict: confirmed problem.** This is a real code defect, untested (§F13), with a material effect on HoT. Direct power still wins on aggregate WAPE, but by less than reported. F7 and F8 show the margin is partly explained by fixable wind-first implementation choices and partly offset by worse tail risk.

### F7 — High. Wind-first's systematic negative bias has diagnosable causes that were never diagnosed; one standard fix closes most of the Kelmarsh gap

**Claim challenged.** "Direct-power regression is the genuinely best-performing method" (bake-off verdict).

**Evidence.** Wind-first underestimates energy in 18/19 Kelmarsh blocks. I decomposed the bias on timestamp-aligned data:

1. **OLS MCP shrinks variance.** `reconstruct.fit_linear` is ordinary least squares. OLS predictions regress to the mean: the predicted/true wind standard-deviation ratio is **0.81–0.83** on Kelmarsh (0.92–0.96 on HoT). Feeding a variance-shrunk wind series through the convex part of a power curve underestimates energy (Jensen's inequality). This is why the MCP literature uses **variance-ratio** (or orthogonal/matrix) MCP for energy estimates. I swapped only the regression for variance ratio (same reference, same power curve, aligned scoring):
   - **Kelmarsh** WAPE **9.89% → 5.85%**, bias −9.3% → −5.0%, matching direct power (6.34%).
   - **HoT** changes nothing (10.61% → 10.44%), consistent with its much smaller variance shrinkage.
2. **The power curve has seasonal drift and no air-density normalisation.** Feeding the *true* target wind through the fitted power curve (`power_curve.py`, binned means of all pre-outage rows, no density correction, no filtering of stops or derates) gives a per-block energy error of about 0% in May–Aug drifting to **−5% … −10% in Oct–Dec** on Kelmarsh. That matches denser winter air producing more power at the same wind speed than a summer-weighted curve predicts. The power-curve step alone contributes about −3% aggregate bias on both farms (WAPE 3.5% Kelmarsh, 6.8% HoT, even with perfect wind).

**Verdict: confirmed (1)**, measured. **Plausible (2)**: the seasonal pattern is measured, but density can't be confirmed because the canonical schema has no temperature or pressure. "Direct power is best" is partly "wind-first was implemented with the variant known to be biased for energy". The literature review (`RESEARCH_2026-10-22_due_diligence.md`) did not cover MCP-variant literature at all; it went straight to conformal prediction.

### F8 — High. Direct power has a worse failure mode and worse tails than the aggregate WAPE shows

**Claim challenged.** Direct power is recommended for production promotion.

**Evidence.**

- **When the reference turbine is itself stopped but still reporting, direct power predicts about 0.** HoT 2024-08-13 (reference T04): **447 kWh** predicted vs **30,243 kWh** actual (−98.5%), with event coverage **9%**. Wind-first on the same rows was −5.4%, because the reference anemometer still reads.
- **There is no reference-availability or operating-state filter anywhere** in `direct_power_uncertainty.py`.

Per-event absolute kWh error (the spec's own metric, `WindLens_instructions.md:210`):

| Farm | Method | Median | 90th percentile | Max | Events with \|error\| > 20% |
|---|---|---|---|---|---|
| Kelmarsh | wind-first ensemble | 10.5% | 16.6% | 27.8% | 1 |
| Kelmarsh | direct power | 4.0% | 13.9% | 20.8% | 1 |
| HoT | wind-first ensemble (aligned) | 7.2% | 25.4% | 54.3% | 4 |
| HoT | direct power | 6.0% | **37.2%** | **98.5%** | **6** |

**Verdict: confirmed problem.** Direct power wins the median, not the tail. Any promotion needs a reference-operating-state gate first, and should be framed as the same-farm method only (§F3).

### F9 — Medium. The bake-off's dev/report split is not disjoint, and its write-up has factual errors

**Evidence.**

- **The Kelmarsh block list contains overlapping blocks.** 2016-05-17→05-22 and 05-20→05-25 share 2 days. 05-27→06-01 and 05-29→06-03 share 3 days. In both pairs the parity rule put one block in **dev** and the other in **report**, so ~720 hidden-truth rows were scored on both sides of the "locked, disjoint" split.
- **The overlap was never disclosed.** `DECISION_LOG.md:731` and the docstring of `run_kelmarsh_extended_backtest.py` describe the blocks as "non-overlapping". That docstring also still says "21 blocks / 16 new"; the true count is 19/14.
- **A stale comment.** `run_backtest.py:20-21` says no original block overlaps the spike week 2016-07-05→07-10, but the original 07-07→07-12 block (also the demo block) overlaps it by 3 days.
- **A factual error in the bake-off doc.** `METHOD_BAKEOFF_2026-10-23.md:294-298` says the split-conformal 95% CI upper bound "modestly exceeds" 90% on Kelmarsh. It is **81.1%**.
- **"2x on both subsets" overclaims** (see F6).
- **The guarantee is overstated.** The doc says split-conformal "carr[ies] an actual finite-sample guarantee". That guarantee needs exchangeability, which autocorrelated 10-minute residuals (lag-1 ≈ 0.6–0.7) and a calm-history-vs-event-window split do not satisfy. The doc's own pre-mortem (c) says so, then the verdict drops the caveat.

**Verdict: confirmed problems, bounded effect.** Two overlapping pairs out of 19 don't change any conclusion. The "split-conformal ≈ current" result is robust (11/24 ties on dev), and I agree with it.

### F10 — Medium. The showcased demo block was chosen by its outcome

**Evidence.** `run_assessment.py:29` picks `min(events, key=len(failed_gates))`, the best-scoring of the 5 original blocks (failed-gate counts 2, 2, 1, **0**, 2). The demo therefore shows the one block that passed everything:

| Item | Value |
|---|---|
| Showcase block's error | **8.4%** (107,495 kWh vs 117,373 kWh, reproduced exactly) |
| Typical error for this method (Kelmarsh per-event median) | 10.5% |
| Kelmarsh blocks labelled reviewable | 3 of 19 |

HANDOVER does disclose "1 of 19 … do not present as evidence the method is reliable". The UI does not say the block was picked *because* it passed.

**Verdict: defensible with a fix.** Showing the best case is normal for a demo if labelled. Add "showcase block selected as the best of N" to the UI, or show a median block.

### F11 — Low. UI statements that the code contradicts

- **"Empirical residual interval calibrated on a prior contiguous block"** (`app.js:68`, Evidence register). This is false since the 2026-10-21 fix. The interval is calibrated on in-sample residuals from the *entire* pre-event history (7,325 observations for the demo block).
- **"30 days · not calculated in this record" / "180 days · not calculated"** (`index.html:59`). This is false. `select_dynamic_references` evaluated 30/90/180 and chose 90 (verified on the demo event's `dynamic_selection.windows`). They were calculated and rejected.
- **The chart does not plot the scored model.** The line is `reconstruct_wind_speed_ensemble`, an *equal-weight* mean (`run_assessment.py:50`). The scored model and its interval use inverse-RMSE weights 0.45/0.30/0.25. The difference is mean 0.07 m/s, max 0.41 m/s; the band as drawn covers 95.1% vs the 95.9% printed beside it.
- **Method slide 03 implies a comparison the record doesn't contain.** It says "Compare transparent wind-first and direct-power challengers". No direct-power result exists in the demo record.
- **The Input QA ✓ is unconditional** (see F1).

**Verdict: confirmed, all low-effort fixes.**

### F12 — Medium. Re-deriving the prior audit: where I agree, where I don't

I re-traced the masking and fitting filters myself: `backtest.py:137-176`, `reconstruct.py:112-127, 227`, `direct_power_uncertainty.py:62, 108-121`. **I agree there is no leakage of the masked window.** I also agree with the audit's §1 that calibration residuals are in-sample. The demo block uses 7,325 residuals from the full pre-event history, against `uncertainty.py:25-26`'s own rule.

I go further than the audit on **why that doesn't matter much**. With thousands of residuals and two fitted parameters, in-sample optimism is negligible. The bake-off's empirical result (split-conformal statistically tied with the in-sample method) confirms it. The binding constraint was never Problem 1. It is non-stationarity: one unconditional, constant-width band calibrated over up to 230 days of mixed seasons and applied to a specific 5-day regime. That is what the over-dispersed per-block coverage in F4 shows.

**I disagree that the audit's Problem 2 (method-selection bias) is still open in any practical sense.** Three reasons:

- The chosen method was the only one of the four without a fit/predict model mismatch, so it is justifiable a priori, not just by score.
- 41 blocks never used in that selection reproduce mean coverage of about 90%.
- The bake-off's untouched report subset agrees.

**Verdict:** audit §1 is correct but low-impact. Audit §3 is correct in principle and now empirically moot. The audit's Clopper–Pearson figures check out ([5.3%, 85.3%] for 2/5 and [9.4%, 99.2%] for 2/3), as do the Wilson intervals in the decision log ([27.3%, 68.3%] for 9/19) and the bake-off ([18.9%, 73.3%] for 4/9).

### F13 — Medium. Tests: some tautological, and the critical paths are untested

Current suite: **116 tests, 106 pass, 10 errors** (`openpyxl` not installed). No document quotes this count; see F14.

- **Tautological assertions.**
  - `test_backtest.py:117` accepts either label (`assertIn(label, (REVIEWABLE, UNVERIFIED))`).
  - `test_direct_power_uncertainty.py:95-96` only asserts `0 ≤ coverage ≤ 100`.
  - Neither can fail on a calibration bug.
- **The published path is untested.** No test exercises `run_backtest_event(..., metadata_df=…)`, the dynamic-selection path every published number uses. `test_backtest` only runs the `metadata_df=None` branch.
- **The F6 bug's input is never tested.** `test_loss_estimate.py` only feeds `estimate_loss` equal-length, already-aligned arrays.
- **No statistical validity test** of either interval method, e.g. "on i.i.d. synthetic residuals, empirical coverage ≈ 90% ± tolerance". `test_split_conformal.py` checks order-statistic arithmetic only.
- **No test** that gates avoid hidden truth (F1), that a reconstruction covers the window (F2), that back-test blocks don't overlap or that the dev/report split is disjoint (F9), or that the workspace record matches a fresh `run_assessment` output.
- **Synthetic fixtures are too clean** to surface any real failure here: no gaps, reference values in the block identical to the target.

**Verdict: confirmed.** The tests verify plumbing and arithmetic well, but not the behaviours that produced F1, F2 and F6.

### F14 — Low. Documentation has drifted out of sync with code and with itself

| Statement | Where | Reality |
|---|---|---|
| "105 of 105 tests" | `README.md:19, 69` | 116 tests / 106 pass |
| "105 tests pass" | `PROJECT_STATE.md:113` | 116 / 106 |
| "110 tests, 100 pass" | `HANDOVER.md:139` | 116 / 106 (bake-off added 6) |
| Coverage/WAPE tables on 5 and 3 blocks only | `README.md:31-54` | 19/28-block results exist; README never updated |
| "1 block out of five passing" | `PROJECT_STATE.md:108-110` | 3 of 19 Kelmarsh blocks reviewable |
| Audit concerns "unresolved"; no bake-off mention | `HANDOVER.md:13-18` | bake-off partly addresses them (§F9, §F12); HANDOVER skipped by design (`DECISION_LOG.md:1033`) |
| "21 non-overlapping blocks … 16 new" | `run_kelmarsh_extended_backtest.py:1-2, 134` | 19 blocks, 14 new, two overlapping pairs |
| "genuinely external farm (not same-farm)" | HoT multi-year JSON `honesty_note` | references are same-farm (F3) |

**Verdict: confirmed.** Mostly harmless individually, but a reader using README as the entry point gets a materially different picture than one using HANDOVER.

### F15 — Medium (plausible). The hidden truth is not "known-healthy" operation, which confounds method ranking

The spec requires masking a "contiguous **known-healthy** target interval" (`WindLens_instructions.md:186`). Blocks were chosen by data completeness only. In 4 HoT blocks, feeding the target's *own true wind* through its power curve over-predicts its real output by **+22% to +44%**:

| Block | Over-prediction on true wind |
|---|---|
| 2025-10-13 | +43.9% |
| 2025-05-11 | +26.6% |
| 2024-09-12 | +24.7% |
| 2025-08-14 | +22.7% |

The likely cause is that the target was curtailed, derated or partly stopped during "healthy" truth. Direct power copies such farm-wide curtailment from the reference, so it scores better against this truth even when wind-first estimates the right counterfactual for a different loss definition.

**Verdict: plausible.** The mechanism is inferred; status and alarm logs were not checked. It needs an operating-state filter on both the truth and the power-curve training data.

---

## Value proposition, challenged

**Pitch:** "resilient, trustworthy counterfactual loss estimation with honest uncertainty."

- **"Trustworthy" rests on a gate that only works in hindsight** (F1) and has passed a −70% estimate (F2). As built, the trust layer is a back-test scorecard, not a deployable decision gate.
- **"Honest uncertainty" is real as a culture, not as a product feature.** The decision log is unusually candid, and every number I re-ran reproduced exactly. That deserves credit. But the user-facing uncertainty is on the wrong quantity (wind, not kWh: F5), and the headline uncertainty verdict is mis-framed (F4).
- **"Counterfactual loss estimation" is validated only for single-turbine, same-farm outages** (F3). For that narrower problem, the simpler, cheaper tool already delivers most of the value: per-turbine availability loss from the nearest same-model peer's power, which is industry-standard practice and essentially this project's "direct power" winner. Add a per-event error band from back-tests and that covers about 90% of the demonstrated value with a fraction of the machinery. The wind-first MCP chain earns its complexity only in the challenge's actual scenario (neighbouring farm), which is untested.
- **The defensible differentiator** is the vendor-scan finding that no competitor publicly shows uncertainty next to its loss claims. That claim is only credible if WindLens itself shows a validated kWh interval, which it currently doesn't (F5).

## Methodology: my own assessment (agreements and disagreements)

- **MCP + power curve:** sound and the right chain for the challenge as written, but implemented in its most bias-prone form.
  - Use variance-ratio or orthogonal MCP (F7: Kelmarsh 9.9% → 5.9%).
  - For a neighbouring farm, sector the fit by wind direction.
  - Density-normalise the power curve (needs temperature/pressure, which the schema lacks).
  - Fit the power curve on normal-operation rows only.
- **Direct power:** appropriate for same-farm, same-model peers with a reference-state filter. Not appropriate as the default for the challenge's cross-farm case.
  - **I disagree with the bake-off** that it is "the genuinely best method" without that qualification.
- **Calibration:** I **agree** with the research doc that split-conformal is a validity fix and not a coverage fix, and the bake-off confirmed it. I **disagree** that it was the right next step.
  - The product number is event kWh. The direct route is an **event-level** interval: take the empirical distribution of relative kWh error across back-test events and use its quantile as the band. Over these 47 events the 90th-percentile |error| is about 17% (Kelmarsh wind-first), 14% (Kelmarsh direct), 25% (HoT wind-first) and 37% (HoT direct).
  - That is simple, honest and directly testable. With n = 19–28 events per farm, report it with its sampling uncertainty, and condition it on history length (Kelmarsh's <30-day blocks are systematically worse).
- **The audit's two problems** (in-sample residuals, method selection): correct in principle, but neither was the binding constraint (F12). The binding constraints are non-stationarity of errors, data completeness (F2), and that the validated quantity is the wrong one (F5).

## What held up (re-derived, not trusted)

- **Kelmarsh 19-block wind-first** WAPE 10.04% / 11.71%, bias −9.42% / −11.40%, 9/19 blocks ≥90%, 3/19 reviewable: reproduced exactly.
- **HoT 28-block** WAPE 13.88% / 12.99%, 17/28, 11/28 reviewable, and every per-block coverage value: reproduced exactly.
- **Direct power** 6.34% (−4.68%) Kelmarsh and 6.98% (−0.79%) HoT: reproduced (docs say 6.3% / 7.0%).
- **Demo record** 107,494.95 kWh estimated vs 117,372.94 kWh truth, 95.9% coverage, zero failed gates: reproduced from `run_backtest.run_all_blocks()`.
- **Wilson and Clopper–Pearson intervals** quoted in the docs: arithmetic correct.
- **No masked-window leakage** into fitting, reference selection or calibration (independent code trace).
- **`node --check workspace/app.js`** passes.

## What I could not check

- **Live browser render** of `workspace/`. I did a static trace of `app.js` and `index.html` plus `node --check` only, and did not re-test the known 375 px mobile overflow.
- **Air-density cause of the seasonal power-curve drift** (F7.2). No temperature or pressure in the canonical schema; the raw Kelmarsh SCADA may have nacelle temperature, which was not examined.
- **Turbine status/alarm logs** to confirm the stopped-reference (F2/F8) and curtailed-target (F15) explanations. The numbers are measured; the causes are inferred.
- **Re-running the bake-off itself.** I reviewed its code, write-up and JSON, and recomputed the same 47 blocks with my own scorer, but did not re-execute its dev/report runs or the split-conformal per-block results. Aligned WAPE was computed over all 47 blocks, not per subset.
- **HoT raw → canonical extraction correctness and checksums** (the bake-off reports these pass; not repeated).
- **The 10 Excel-connector tests** (`openpyxl` not installed, per guardrail).
- **EDP Portugal evidence and the outage-detection extension** (out of scope for the time available).
- **Literature and vendor claims in the research doc.** I did not re-fetch papers or vendor pages. My methodological disagreements above are from first principles and this project's own data, not from re-reading those sources.
- **Whether a public neighbouring-farm dataset pair exists** to test F3's scenario properly. Not searched; this is the most valuable follow-up.

## Suggested priority order for Anna

None of these changes was made here. Each is Anna's decision.

1. Re-scope the trust gate to outage-time information only, and add a reconstruction-completeness gate (F1, F2).
2. Show an event-level kWh interval on the hero number (F5).
3. Fix the WAPE timestamp alignment, re-state the method comparison, and try variance-ratio MCP before promoting direct power (F6, F7, F8).
4. Replace the "% of blocks ≥ 90%" target with pooled coverage plus a dispersion check (F4).
5. Re-frame the pitch: validated for single-turbine, same-farm outages; the neighbouring-farm scenario is untested (F3).
6. Hygiene: F9–F11, F13, F14.
