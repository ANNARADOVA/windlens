# Independent Audit: Uncertainty-Interval Calibration Methodology

**Date:** 2026-10-22
**Auditor:** separate Claude Code session, dispatched specifically to re-derive and
check the 2026-10-21 "RESULT — Uncertainty interval calibration: root cause found
and fixed" entry in `docs/DECISION_LOG.md` from the code and data directly, not
from the log's own account. This file was written read-only against
`src/windlens/`, `tests/`, and `data/derived/`; no model/calibration source or
data/evidence file was modified. Reproduction scripts were run from an ephemeral
`uv run --with pandas --with numpy ...` environment (no project file touched,
nothing installed into the project) because no Python environment or dependency
manifest (`requirements.txt`/`pyproject.toml`/`.venv`) exists in this project —
flagging that gap itself below.

**One-line verdict: sound with caveats.** The specific bug and its fix are real
and exactly reproducible from the code and saved data (not fabricated or
rounded-to-taste). But the "fix" replaces one methodology problem (fit/score
model mismatch) with a different, undocumented one (calibrating from residuals
computed on almost exactly the same observations used to fit the model — which
`uncertainty.py`'s own docstring says must never happen), and the final
calibration method was itself selected by trying four variants against the same
5 Kelmarsh blocks and keeping the one with the best score on those blocks — a
form of selection bias the decision log explicitly warns against for one
sub-choice but doesn't apply to the top-level choice. The small-sample caveat is
honestly stated in prose but under-quantified: a 95% confidence interval on "2/5
blocks passed" is roughly [5%, 85%] — at this n, "2/5" and "4/5" are barely
distinguishable statistically.

---

## 0. What I actually did (not just read)

- Read `src/windlens/backtest.py` (`_calibrate_and_evaluate_interval`,
  `run_backtest_event`), `src/windlens/uncertainty.py` (all three functions),
  and `src/windlens/reconstruct.py` (`fit_weighted_references`,
  `predict_with_fitted_references`, `reconstruct_wind_speed_weighted`,
  `_paired_series`) line by line, tracing exactly which timestamps flow into
  which computation.
- Read the full 2026-10-21 decision log entry (lines 375–488) describing the
  bug, the rejected alternatives, and the before/after tables.
- **Reproduced the "after" (current, shipped) Kelmarsh 5-block ensemble
  coverage** by running `run_backtest.run_all_blocks()` against the real
  `data/derived/kelmarsh_2016_90d_canonical.csv` in an ephemeral `uv`
  environment (pandas/numpy only, nothing written to the project).
- **Reconstructed the pre-fix ("buggy") calibration** — re-fit at an inner
  80/20 cutoff, score only the trailing 20% — using only the project's own
  existing exported functions (`fit_weighted_references`,
  `predict_with_fitted_references`, `calibrate_residual_interval`,
  `apply_residual_interval`, `evaluate_interval`), orchestrated from a
  standalone scratch script, and ran it against the same real data to check
  whether the claimed "before" numbers are genuine.
- **Reproduced the Hill of Towie 3-block "after" numbers** the same way,
  against `data/derived/validation/hill_of_towie_2026_canonical.csv`.
- Ran the full test suite (`pytest tests/`) in the same ephemeral environment
  and confirmed **105/105 pass** (10 of the 105 only pass once `openpyxl` is
  also present — a real, if minor, undocumented dependency gap: the project
  has no manifest recording that Excel-connector tests need it).
- Computed exact (Clopper-Pearson) confidence intervals on the "N/5 blocks
  meet target" and "N/3 blocks meet target" claims.

All reproduction scripts live only in my scratch directory, not in the repo.

---

## 1. Time-series leakage: does calibration ever use the held-out interval?

**Finding: No leakage of the masked/held-out event into calibration or
fitting — confirmed by tracing every timestamp filter. But there is a
different, real problem: the calibration residuals are drawn from
(very nearly) the same observations used to fit the model, which is exactly
what the project's own code says must not happen.**

Tracing `_calibrate_and_evaluate_interval` (`backtest.py:43-116`) end to end:

- `fit_weighted_references(masked_df, target_turbine, reference_weights,
  block_start)` fits on `masked_df[timestamp_utc < fit_before]` where
  `fit_before = block_start` (`reconstruct.py:227`). Strictly before the event.
- `pre_target` (`backtest.py:70-73`) is also filtered to
  `timestamp_utc < block_start`.
- `calibration_start = pre_target.iloc[0]["timestamp_utc"]` — the *earliest*
  available pre-event target timestamp — and
  `predict_with_fitted_references(masked_df, fits, calibration_start,
  block_start)` predicts over `[calibration_start, block_start)`.
- Only after calibration is `hidden_truth` (data from `[block_start,
  block_end)`) ever touched, and only to score the final event-level
  coverage — never to fit or calibrate anything.

So, strictly answering the question asked: **the held-out block itself never
leaks into model fitting or interval calibration.** That part of the brief's
worry does not hold, and I confirmed it by code tracing, not by trusting the
function docstrings.

**What I found instead, which the decision log does not mention:** the window
used to *fit* the model (`[dataset start, block_start)`, via
`fit_weighted_references`) and the window used to *score calibration residuals*
(`[calibration_start, block_start)`, via `predict_with_fitted_references`) are
not independent — `calibration_start` is defined as the earliest pre-event
*target* timestamp, which is also effectively the earliest timestamp any
target-paired fit could use. In practice these are the same span of data. I
confirmed this empirically, not just by inspection: for the last Kelmarsh
block (2016-07-13), the calibration step used **8,132 "calibration"
observations** — essentially the entire ~68-day pre-event history for that
target turbine (matches the ~79–84% per-turbine data coverage over that many
days noted elsewhere in the decision log), not a held-out slice of it. Every
Kelmarsh block showed the same pattern (1,463 to 8,132 observations, scaling
with how much pre-event history existed, not with any holdout fraction).

This directly contradicts the explicit contract stated at the top of
`uncertainty.py` itself:

> "`residuals_ms` should come from held-out, time-contiguous validation
> blocks ... **never from the same observations used to fit the
> reconstruction.**" (`uncertainty.py:24-26`)

The current `_calibrate_and_evaluate_interval` violates this docstring's own
rule: it scores the fitted model on (almost exactly) its own fitting data.
This is not "leakage" in the strict sense asked about (no information from the
future/masked block is used), but it is the same underlying sin one level
down: reusing training data to claim an honest estimate of out-of-sample
error.

**Does this inflate the reported coverage, as leakage normally would?** Not
obviously, and I want to be precise about why, because the direction matters.
Classic in-sample optimism makes the *residual quantiles narrower* than the
true population spread. A narrower interval, applied to new data (the actual
held-out event), tends to produce **lower** measured coverage, not higher —
the opposite of what "leakage inflating a good-looking number" usually means.
With thousands of calibration observations per block, the degrees-of-freedom
component of that optimism is also negligible (not a 20-points-vs-2,000-points
situation). So I do not think this specific mechanism is why coverage looks
artificially good; if anything it argues the reported ~90% is not an inflated
number through this channel.

What it does undermine is the **evidentiary weight of the near-zero
calibration bias** the decision log cites as proof the fix "worked": collapsing
to ±0.01 m/s bias is close to a mathematical guarantee of OLS fit on (almost)
its own data, not strong independent confirmation that the model is
well-calibrated for new data. The real evidence of the fix working is the
*event-level* coverage number (which is genuinely out-of-sample and which I
independently reproduced — see §2), not the calibration-residual bias number.
The decision log conflates these two signals ("bias collapse... is what raised
coverage") when they're not actually independent confirmations of the same
thing — the bias collapse is close to guaranteed by construction once you
score on (near-)training data, so citing it as *evidence for* the fix is
weaker than it reads.

**Confidence: high** on "no leakage of the masked block", verified by direct
code trace plus the observation-count numbers above. **Medium-high** on "the
in-sample-residual issue is real and undocumented as a limitation", also
verified directly; the only soft part is my claim about the *direction* of its
effect on reported coverage, which is a reasoned inference from the
mechanism (OLS optimism + large N ⇒ small effect either way), not something I
isolated experimentally (isolating it would require a dataset where the
pre-event and event periods differ enough in wind-speed variance to matter,
which this single 90-day/one-farm dataset may not have).

---

## 2. The specific bug-fix claim: is it real and are the numbers reproducible?

**Finding: Yes — fully confirmed, not just plausible. I reconstructed the
removed "buggy" calibration logic from the decision log's description (using
only the project's own existing, unmodified functions) and it reproduces the
claimed "before" numbers almost exactly; the current code reproduces the
claimed "after" numbers exactly, on both farms.**

### Current code ("after"), Kelmarsh 5-block, ensemble path — reproduced live:

| Block | My re-run coverage | Decision log "after" |
|---|---|---|
| 2016-05-17 | 85.2% | 85.2% |
| 2016-05-29 | 84.5% | 84.5% |
| 2016-06-26 | 95.8% | 95.8% |
| 2016-07-07 | 95.9% | 95.9% |
| 2016-07-13 | 88.1% | 88.1% |
| **Mean** | **89.90%** | **89.9%** |

Calibration bias per block I measured: +0.0010, +0.0049, −0.0040, −0.0076,
−0.0057 m/s — all within the claimed "±0.01 m/s" band. Baseline (single
reference) mean coverage I measured: **89.22%**, 3/5 blocks ≥90% (80.2, 83.5,
97.4, 93.4, 91.5) — matches the log's "89.2% (3/5 ≥90%)" exactly.

### Reconstructed pre-fix ("before") logic, same data:

I rebuilt the described bug — re-fit a fresh model at an inner 80/20 cutoff of
the pre-event history, score only the trailing 20% — using
`fit_weighted_references`/`predict_with_fitted_references` with the cutoff
moved to the 80% point instead of `block_start`, then applied that
calibration to the *actual* event prediction (which still comes from the
full-history model), exactly as described as the root cause. I could not
recover the literal deleted code (it's gone, this isn't a git repo), so this
is a faithful reconstruction from the written description, not a diff against
the original — flagging that distinction honestly.

| Block | My reconstruction | Decision log "before" |
|---|---|---|
| 2016-05-17 | 85.4% | 85.4% |
| 2016-05-29 | 79.4% | 79.4% |
| 2016-06-26 | 89.8% | 89.8% |
| 2016-07-07 | 72.0% | 72.0% |
| 2016-07-13 | 71.2% | 71.2% |
| **Mean** | **79.5%** | **79.6%** |

Bias range I measured: **−0.340 to +0.371 m/s** (block 2016-07-07: −0.3404;
block 2016-05-29: +0.3715) — matches the log's "+0.37 m/s (block 2) to −0.34
m/s (block 4)" to three significant figures. This is about as strong a
confirmation as is possible without the original deleted source: an
independent reconstruction from prose, built from the project's own
unmodified helper functions, reproduces the before-table to within rounding
on every block and the bias range to the exact values quoted.

### Hill of Towie 3-block, "after", reproduced live:

| Block | My re-run | Decision log |
|---|---|---|
| 2026-03-01 | 91.5% | 91.5% |
| 2026-04-01 | 91.5% | 91.5% |
| 2026-04-15 | 84.7% | 84.7% |
| **Mean** | **89.24%** | **89.2%** |

**Reasoning check:** is "fit once, matching the event model" actually the
right instinct? Yes, as far as it goes — scoring calibration against a model
*different* from the one generating the actual event prediction is a clear,
real mismatch, and matching them is the correct direction to move in. My
disagreement (§1) is only with *how* they matched them (by scoring on
near-training data instead of via proper rolling-origin/walk-forward residuals
that stay out-of-sample while still representing the same model family) — not
with the diagnosis that a mismatch existed and mattered.

**Test suite:** I ran the full suite myself (not trusting the "105/105"
line) and got **105 passed** — but only after adding `openpyxl`, which is not
declared anywhere in the project (no `requirements.txt`/`pyproject.toml`
exists at all). Without it, 10 Excel-connector tests fail with
`ModuleNotFoundError`. This is unrelated to the calibration question but is a
real, concrete reproducibility gap worth fixing: "105/105 tests pass" is true
only in whatever environment the authoring session happened to have, and that
environment isn't recorded anywhere in the repo.

**Confidence: high.** Both tables and the bias ranges reproduce to the
reported precision from the live code and real data, on both farms.

---

## 3. Overfitting / small-sample risk: is the methodology for picking blocks unbiased, and is "coverage rate" meaningful at n=5/n=3?

**Finding: the *block selection* (which 5-day windows to hold out) looks
genuinely unbiased — chosen for data completeness and calendar spread, not
backtest performance. But the *calibration-method selection* (which of four
competing calibration approaches to ship) was explicitly chosen by trying all
four against these same 5/3 blocks and keeping the best-scoring one — which is
the exact form of hindsight-tuning the decision log itself calls out as
illegitimate for one sub-choice, without applying the same standard one level
up. The small-sample caveat is stated in prose but not quantified; it should
be.**

**Block selection (not biased, as far as I can tell):** per the log
(`DECISION_LOG.md:94`), the 5 Kelmarsh blocks were picked from the per-turbine
daily coverage table built during the earlier Section 8 work, chosen for
near-full data coverage and spread across May/June/July 2016, explicitly
avoiding the week already used by the spike. That's a reasonable,
performance-blind criterion. I have no evidence it was re-picked after seeing
results. The 3 Hill of Towie blocks (`run_hill_backtest.py:15-19`) are a fixed
module-level constant, not something I can see being cherry-picked at call
time either. I'll note this is a check on *process*, not something I can
independently audit for intent — I can only confirm the current blocks are
hard-coded constants chosen before this calibration work started (both block
lists were already in place per the 2026-10-20 entries, before the 2026-10-21
calibration investigation), which is consistent with "declared before
scoring."

**Calibration-method selection (this is the real finding here):** the
decision log itself documents trying, in order, against the *same* 5
Kelmarsh blocks:
1. The original inner-cutoff refit (the bug) — mean 79.6%.
2. Fixed trailing windows of 3/5/7/10 days, refitting at each — mean 85.4% /
   81.6% / 81.1% / 83.3%.
3. Wind-speed/direction-conditioned intervals
   (`calibrate_conditional_intervals`/`apply_conditional_intervals`, which I
   confirmed exist in `uncertainty_business.py:26` and `:86`) — mean 67.9%.
4. Fit once on full history, score on (near-)full history — mean 89.9%. **Shipped.**

Option 4 was kept *because* it scored highest on these 5 blocks. The log
explicitly, correctly, flags this exact risk for option 2 — "picking whichever
window looks best in hindsight would itself be an unjustified form of tuning
to the test data" — but doesn't apply that same reasoning to the choice
between options 1/2/3/4 as a whole. All four are measured against the
identical 5 Kelmarsh blocks that the final 89.9% figure is then reported from.
This is a textbook garden-of-forking-paths setup: with four candidate
methodologies evaluated on one small, fixed test set, selecting the
best-performing one and then quoting that same test set's score as *the*
result overstates how well the chosen method would do on a genuinely new
block. A cleaner process would have picked the calibration methodology on a
separate development slice (or via simulation / theoretical argument) and
evaluated it once, un-peeked-at, on the 5+3 blocks now in the log. That
wasn't done, and nothing in the current code or tests prevents it from
happening again next time someone "tries a few things" to hit a target.

To be fair to the existing honesty norms here: the log does report all four
attempts, including the ones that failed, rather than hiding them — that's
the right instinct and is exactly the "transparency over black box" standard
this project holds itself to elsewhere. My disagreement is only that
reporting the failed attempts doesn't cancel out the selection-bias effect on
the final number; it just makes the selection bias visible instead of hidden,
which is better but not the same as not having the bias.

**Statistical meaningfulness of "N/5" and "N/3" at this sample size:** the log
already says, in its own words, "2–5 blocks per farm is not enough to assess a
90%-of-blocks rate with any precision" — I agree, and I quantified it. Using
exact (Clopper-Pearson) binomial confidence intervals, treating each block as
one independent trial of "did this block clear 90% coverage":

| Farm | Pass rate reported | 95% CI |
|---|---|---|
| Kelmarsh | 2/5 (40%) | **[5.3%, 85.3%]** |
| Hill of Towie | 2/3 (67%) | **[9.4%, 99.2%]** |
| Combined (naive pooling) | 4/8 (50%) | **[15.7%, 84.3%]** |

These intervals are enormous — at n=5, "2/5" and "4/5" are not statistically
distinguishable, and the stretch target of "≥95% of blocks" is not meaningfully
testable with 3–5 blocks regardless of the true underlying rate. Worse, the
blocks are not independent draws even within the Clopper-Pearson model's own
assumptions: Kelmarsh's 5 blocks all come from the same 90-day window on one
farm (May–July 2016), and Hill of Towie's 3 come from a 6-week window on
another single farm — same-season, same-farm weather is autocorrelated, so
the *effective* sample size for "how often does this generalize" is smaller
than 5 or 3 independent trials, meaning even the wide CIs above are somewhat
optimistic about how much these numbers tell you. **I'd report every per-block
coverage table in this project with an explicit "n=5, 95% CI [5%, 85%]
(treat with caution)"-style caption, not just the bare percentage** — the raw
numbers are honestly reported, but their precision is overstated by omission
rather than by false claim.

**Confidence: high** on the calibration-method-selection-bias finding (it's
directly visible in the decision log's own text) and on the CI calculations
(exact, not approximated). **Medium** on "block selection itself was
unbiased" — I can confirm the blocks are hard-coded and were defined before
this specific calibration investigation, but I can't fully rule out that the
*original* Section 9 block list (from 2026-10-20) was itself chosen with some
awareness of which weeks would look good, since I wasn't present for that
earlier work and am relying on the log's own stated selection criterion
(data coverage + calendar spread).

---

## 4. Correctness of the coverage statistic itself

**Finding: correct. No off-by-one, no wrong denominator, no improper mixing
of blocks. I verified this by direct inspection and by independently summing
per-block observation counts from a live run.**

`evaluate_interval` (`uncertainty.py:74-102`):

```python
covered = (actual_values >= lower_values) & (actual_values <= upper_values)
coverage_pct = float(np.mean(covered) * 100.0)
```

This is exactly "fraction of true values whose actual wind speed falls within
the stated [lower, upper] interval, inclusive on both ends" — matching the
plain-English description used everywhere else in the project. Each call to
`evaluate_interval` operates on exactly one block's `event_joined` array
(constructed by an inner join of that block's reconstructed prediction with
that block's hidden truth, `backtest.py:103-105`), so blocks are never pooled
or mixed inside the statistic; the per-block table in the decision log is
genuinely per-block, not a slippery aggregate presented as if it were.

I checked the "mean coverage across blocks" figure two ways on a live
Kelmarsh run: a simple unweighted average of the five per-block percentages
(**89.90%**, matching the log) versus a size-weighted pooled figure (total
covered points / total scored points across all five blocks = **89.99%**,
over 3,428 pooled observations). These differ by only 0.09 points because the
five 5-day blocks have very similar observation counts (608–717 points each);
there is no hidden weighting bug here, but it's worth noting for future blocks
of unequal length that the log doesn't state *which* averaging convention it
uses — it happens not to matter yet, but it isn't documented either.

One real, if minor, scoring subtlety I did **not** see flagged anywhere: the
event-level coverage is computed only over timestamps where the *ensemble
reconstruction actually produced a prediction* (the inner join at
`backtest.py:103-105`, and inside that, `predict_with_fitted_references`'s own
inner join across however many weighted references are required,
`reconstruct.py:259-263`). If a reference turbine happens to be missing data
during specifically the highest-wind-variance moments of an event (plausible
— wind-farm SCADA gaps are not always random with respect to wind speed,
e.g. communication dropouts during storms), those moments would silently
drop out of the coverage denominator rather than counting as a failure to
cover. I have no evidence this happened in the actual blocks (event_n per
Kelmarsh block ranged 608–717 out of a possible 720, i.e. 84–100% complete,
so the effect, if any, is small here) — but it's a structural way the
coverage statistic could look better than a "true" coverage against every
10-minute slot in the event would, and nothing in the code or tests currently
checks for or reports on it.

**Confidence: high.** Verified by direct reading of the formula and by
independently re-deriving both the per-block and pooled aggregate from a live
run rather than trusting the printed summary.

---

## Overall assessment

| # | Question | Verdict |
|---|---|---|
| 1 | Leakage of the masked interval | **Not found** — confirmed by code trace. But calibration residuals reuse (near-)training data, violating `uncertainty.py`'s own stated rule; direction of resulting bias is unclear, likely not the reason coverage looks good. |
| 2 | Bug-fix claim | **Confirmed real**, both before and after numbers independently reproduced from code + data to the reported precision, on both farms. |
| 3 | Small-sample / selection risk | **Real concern, understated in the log.** Calibration *method* was chosen by best-score-on-the-same-5-blocks across 4 candidates — a selection-bias pattern the log flags for one sub-choice but not the top-level choice. 95% CIs on "N/5" and "N/3" pass rates are roughly ±40 points — essentially uninformative at this n, and should be stated as such everywhere the numbers are quoted. |
| 4 | Coverage statistic correctness | **Correct.** No bug found; one undocumented (and here, minor) structural caveat about predictions silently excluding timestamps with reference-data gaps. |

**Bottom line for Anna:** the headline claim — "we found a real bug, fixed
it, and coverage went from ~80% to ~90%" — holds up; I reproduced both halves
of that from the live code and real data myself rather than taking the log's
word for it, and it's genuine. What I'd push back on before treating ~90% as
a settled number: (a) the calibration method that produced that 90% was
picked *because* it scored best on the very blocks now used to report the
90%, out of four candidates tried on those same blocks — that's a real
selection-bias risk sitting underneath an otherwise well-documented decision;
(b) the near-zero calibration bias cited as corroborating evidence is weaker
than it looks, since scoring a model on (almost) its own training data tends
to produce a near-zero bias somewhat automatically; and (c) with 5 and 3
blocks respectively, "2/5" and "2/3" carry so little statistical weight (95%
CIs of roughly [5%,85%] and [9%,99%]) that neither should be presented as a
precise rate without that caveat attached every time it's quoted, not just
once in the narrative prose.
