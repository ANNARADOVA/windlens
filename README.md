# WindLens

WindLens is a prototype built for the BayWa r.e. "Energy & AI" hackathon challenge: when a wind turbine stops reporting during an outage, estimate the wind speed and generation it would have produced, using data from a nearby reference turbine, then convert that into an estimated energy loss in kilowatt-hours (kWh).

**Scope note:** WindLens estimates the counterfactual production during an outage; it does not determine or classify the cause (mechanical failure vs. grid curtailment vs. other) — that must come from an external source.

It is an evidence-first analyst workspace, not an automated settlement tool. Every estimate carries its reference selection, back-test performance, uncertainty coverage, and a pass/fail review gate, so an analyst can see exactly why a result is or is not ready to act on — and the tool is built to say "unverified" rather than invent precision when the evidence does not support a confident number.

## Validated scope — read this before the numbers below

**Added 2026-10-22 (late), acting on an adversarial red-team review (F3).** The
BayWa challenge brief (`WindLens_instructions.md`) describes a **whole-farm**
outage reconstructed from a **neighbouring farm's** reference data: "use wind
data from a neighboring reference wind farm" when the affected farm "stops
generating electricity and recording wind data." **Every number in this
project is validated against a different, narrower problem: single-turbine,
same-farm proxy reconstruction** — one turbine's data is masked while its
same-farm neighbours (0.27-0.75 km away on Kelmarsh, 0.34-0.52 km on Hill of
Towie, same turbine model in both cases) keep reporting and serve as the
reference. Hill of Towie is a genuinely different *wind farm* from Kelmarsh,
which is real and useful (it rules out Kelmarsh-specific overfitting), but
its *reference turbines* are still same-farm peers of its target, exactly
like Kelmarsh's — so it does not test the challenge's actual neighbouring-farm
reference scenario either. **The challenge's own scenario — reconstructing a
whole farm's output from a separate, neighbouring farm's wind data — is
untested by this project.** Direct power-to-power regression in particular is
near-trivial between identical same-farm peers (fitted slopes ≈0.9) and has
no demonstrated physical basis across farms with different turbine models,
power curves, and curtailment regimes; wind-first reconstruction (reference
wind → target wind → target's own power curve) is the physically appropriate
chain for the actual challenge, but has only been tested same-farm here too.
Treat every WAPE, coverage, and "reviewable" figure below as evidence about
*this narrower problem*, not as evidence the method works for the challenge
as written.

## What it does

1. Detect the missing interval on the target turbine (in this prototype, a known-healthy interval is masked to simulate an outage, so the true values are available for scoring).
2. Select a reference turbine using geography as a starting point and pre-outage behavioral correlation as the deciding evidence.
3. Reconstruct the target turbine's wind speed from the reference turbine's wind speed during the missing interval (a linear measure-correlate-predict fit).
4. Convert reconstructed wind into expected power using an empirical power curve fitted on the target's own pre-outage data.
5. Integrate expected power into estimated lost energy (kWh) and compare it against the known hidden truth.
6. Attach an empirical uncertainty interval and run the result through a review gate — domain checks, reference-target alignment, a reconstruction-completeness check, and a pre-event calibration-quality check — before labeling the result "Estimate — reviewable" or "Unverified — manual evidence required." (Updated 2026-10-22 late: the gate no longer compares against hidden truth, which would not exist in a real outage — see `docs/DECISION_LOG.md`'s priority-item-1 entry.)
7. Optionally convert lost kWh into an indicative commercial value from a manually entered, clearly labeled demo price profile. This is never a settlement, contractual, or legal figure.

## Current verified state

As of October 24, 2026, the full test suite is **186 tests, 186 pass**. Run with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

The only third-party dependencies are pandas and numpy; no machine-learning library is used anywhere in the pipeline. If `python3` on your PATH doesn't have them installed (`ModuleNotFoundError: No module named 'numpy'`), install them (`pip install pandas numpy openpyxl`) or point `python3` at a virtual environment that has them, then re-run the command above.

### Reconstruction accuracy (aggregate energy WAPE)

> **Note (2026-10-22, late):** the table below and its "direct power beats wind-first on
> both farms" conclusion predate three fixes (a WAPE scoring bug, a biased regression
> variant, a missing reference-state filter — `docs/REDTEAM_2026-10-23_adversarial_review.md`
> F6/F7/F8) and the larger 19/28-block back-test. The honest, current picture has no single
> winner: direct power still wins clearly on Hill of Towie, but wind-first now wins on
> Kelmarsh's report subset. See `docs/METHOD_BAKEOFF_2026-10-23.md`'s correction note and
> `docs/DECISION_LOG.md`'s priority-item-3 entry for the full numbers. This table's numbers
> are also stale on block count (F14, pending a fuller refresh).

WAPE (weighted absolute percentage error) is measured across every held-out back-test block on a given farm. Lower is better; the project's working target is 10% or lower, with 5% as a stretch goal.

| Farm | Method | Aggregate WAPE | Notes |
|---|---|---|---|
| Kelmarsh (same farm, 5 blocks, May–July 2016) | Wind-first, single reference | 11.6% | The review gate's baseline comparison point |
| Kelmarsh | Wind-first, behavior-weighted peer ensemble | 14.0% | What the live demo shows; worse than the single-reference baseline |
| Kelmarsh | Direct power-to-power regression, single reference | 9.30% | Below the 10% target; not yet in production |
| Hill of Towie (external farm, 21 turbines, CC BY 4.0, 2024–2026, 189 scored events) | Wind-first, single reference | 10.10% | |
| Hill of Towie | Direct power-to-power regression, single reference | 9.03% | Below the 10% target; won 13 of 21 target turbines |

Neither a naive equal-weight ensemble nor a behavior-weighted ensemble (inverse holdout-error weights) beats a single well-chosen reference turbine on either farm. Direct power-to-power regression beats wind-first reconstruction on both farms tested, including the one external farm, but has not been promoted to production: doing so changes what the workspace's evidence and chart describe, and the method has no uncertainty-interval calibration of its own yet. See `docs/DECISION_LOG.md` for the full before-and-after evidence and the reasoning.

### Uncertainty-interval coverage

> **Correction (2026-10-22, late, F4):** "90% or more of blocks individually hit 90%
> coverage" is **not a meaningful target** — it was never in the spec, and a red-team
> simulation showed a *perfectly calibrated* 90% interval, scored per 5-day block under
> this project's own measured residual autocorrelation, clears that bar only ~45-58% of
> the time by construction. The honest headline metric is **pooled coverage** (covered
> observations ÷ total observations, across every scored point): on the current 19-block
> Kelmarsh / 28-block Hill of Towie back-test, pooled coverage is **91.9% (Kelmarsh)** and
> **90.2% (Hill of Towie)** — both on target. Per-block coverage spread (std ~5-7
> percentage points, range 72-99%) is the genuine diagnostic worth watching: it shows real
> conditional variation (shorter pre-event history correlates with worse blocks), which
> the old pass/fail framing obscured rather than measured. The table below is the
> project's original 5/3-block measurement and is kept as historical record; it predates
> both the larger sample and this corrected framing. Full detail:
> `docs/DECISION_LOG.md`'s priority-item-4 entry; machine-readable:
> `data/derived/validation/kelmarsh_extended_uncertainty_backtest.json` and
> `data/derived/validation/hill_of_towie_multiyear_uncertainty_backtest.json`
> (`uncertainty_coverage.pooled_coverage`).

Each held-out block gets an empirical interval calibrated from that model's own residuals on prior data, then scored for how often the true wind speed actually falls inside the interval during the held-out block. The working target was that 90% or more of blocks individually hit their own 90% coverage target — see the correction above for why that target is retired.

| Farm | Blocks meeting 90% coverage, before fix | Blocks meeting 90% coverage, after fix |
|---|---|---|
| Kelmarsh (5 blocks) | 0 of 5 (mean coverage 79.6%) | 2 of 5 (mean coverage 89.9%) |
| Hill of Towie (3 blocks) | 1 of 3 (mean coverage 87.6%) | 2 of 3 (mean coverage 89.2%) |

On October 21, 2026, a root cause in the calibration step was found and fixed: the interval was being calibrated from a model re-fit at an earlier cutoff, which differed from the model actually used for the event and carried a bias that flipped sign from block to block. Fitting once — matching the model actually used for the event — and scoring it over the entire available pre-event history, rather than a shorter re-fit window, removed that mismatch. Mean coverage improved on both farms, and one additional Kelmarsh block now passes every review gate. The working target of 90% of blocks individually passing is still not met on either farm; three or five blocks per farm is too small a sample to assess a 90%-of-blocks rate with confidence, and the full investigation, including approaches that were tried and rejected, is recorded in `docs/DECISION_LOG.md`.

### What this means against the 90%/95% goal

> **Correction (2026-10-22, late, F4):** the "90% of blocks" coverage figures in this
> paragraph use the retired, not-meaningful framing explained above. Replace with: pooled
> coverage is 91.9% (Kelmarsh) and 90.2% (Hill of Towie), both on target.

Neither the working WAPE target (10% or lower) nor the working coverage target (90% of blocks or more) is met by the production wind-first pipeline today. Measured against the complement framing ("90% accuracy," "95% accuracy"): aggregate WAPE on the production path sits at 11.6% to 14.0% depending on farm and method, short of the 90%-accuracy reading; uncertainty coverage reaches 2 of 5 and 2 of 3 blocks against a 90%-of-blocks target. Direct power-to-power regression clears the WAPE target on both farms tested but is not yet production, and no combination tried tonight reaches the 95% stretch goal on either axis. These numbers are reported as measured, not adjusted to look better.

## Honest limitations

- **Both farms are same-farm-proxy results.** Kelmarsh's reference turbines are other turbines on the same wind farm as the target. Hill of Towie is a genuinely different wind farm from Kelmarsh (useful: it rules out Kelmarsh-specific overfitting), but its own reference turbines are *also* same-farm peers of its target, 0.34-0.52 km away — not turbines on a third, neighbouring farm. **Neither back-test tests the BayWa challenge's actual scenario** (reconstruction from a separate, neighbouring farm during a whole-farm outage); see "Validated scope" at the top of this document.
- **Sample sizes are small.** Five held-out blocks on Kelmarsh and three on Hill of Towie are not enough to assess a 90%-of-blocks coverage rate, or a WAPE figure, with real statistical confidence. Treat every percentage in this document as a measurement on a small, specific sample, not a general guarantee.
- **Uncertainty intervals are empirical, not probabilistic guarantees.** They are calibrated from each farm's own historical residuals and are a transparent quality signal for the demonstrated data, not a statistical promise that would hold for a different farm, season, or turbine model.
- **The EDP Portugal external-farm connector exists but correctly refuses to run.** The public EDP dataset does not include verified turbine coordinates or rated power, so the connector abstains rather than inventing or guessing that metadata. It stays blocked until an operator supplies a verified registry.
- **This is not an outage detector.** A telemetry gap is simulated by masking known-healthy data; the tool does not and currently cannot distinguish a real operational outage from a benign data gap. That is a deliberately deferred future extension, not part of this prototype.
- **Commercial output is indicative only.** The kWh-to-currency conversion uses a manually entered demo price profile and carries no settlement, contractual, regulatory, or legal weight.
- **This is a hackathon prototype**, not production software. It has not been reviewed for production security, scaling, or operational hardening.

## Repository layout

- `src/windlens/` — the reconstruction, uncertainty, back-test, and review-gate pipeline.
- `tests/` — the test suite (186 tests, 186 pass; see "Current verified state" above).
- `data/` — raw source archives and derived canonical datasets, with provenance manifests and checksums.
- `workspace/` — the dependency-free evidence-first analyst workspace (open `workspace/index.html` via a local server after generating the assessment artifact).
- `docs/` — `DECISION_LOG.md` (the full, append-only history of decisions and results, including unsuccessful attempts), `PROJECT_STATE.md` (current state and next steps), and `HANDOVER.md` (the concise cross-session summary).
- `WindLens_instructions.md` — the original challenge brief and product framing this prototype was built against.

## Running it locally

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # run the test suite
PYTHONPATH=src python3 -m windlens.run_assessment             # generate the demo assessment artifact
python3 -m http.server 8000                                   # then open http://localhost:8000/workspace/
```

(All three `python3` calls need a Python with pandas and numpy installed -- see the
dependency note under "Current verified state" above if you hit `ModuleNotFoundError`.
`workspace/README.md` has the separate command for the live Upload-tool server.)
