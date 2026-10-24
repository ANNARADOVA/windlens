# WindLens

WindLens is a prototype built for the BayWa r.e. "Energy & AI" hackathon challenge: when a wind turbine stops reporting during an outage, estimate the wind speed and generation it would have produced, using real data from a reference turbine, then convert that into an estimated energy loss in kilowatt-hours (kWh).

**Scope note:** WindLens estimates the counterfactual production during an outage; it does not determine or classify the cause (mechanical failure vs. grid curtailment vs. other) — that must come from an external source.

It is an evidence-first analyst workspace, not an automated settlement tool. Every estimate carries its reference selection, self-validation performance, a domain/coverage check, and a pass/fail review gate, so an analyst can see exactly why a result is or is not ready to act on.

## The real BayWa r.e. submission

The graded record uses BayWa's own real challenge dataset (`data_hackathon_baywa_re (1)/`): three target turbines with a real data gap (T1, T2, T3) and seven other real turbines as reference candidates (O1, O2, H1–H5). T3 is the primary record shown by default in the workspace:

- **Hidden-window prediction (2026-09-01 to 2026-09-04, the actual graded submission):** 112,411 kWh, reconstructed from reference turbine O1. No ground truth exists for this window to check against, by construction.
- **Separate self-validation (2026-09-04 to 2026-09-10, a different window with real recorded wind to check against):** T3 5.19% energy error (WAPE), T2 2.73%, T1 39.36% (a wind-match outlier, investigated and explained — see `docs/DECISION_LOG.md`).
- **Reference selection is pure behavioral correlation** (time-ordered holdout R² against each candidate's pre-outage history) — no turbine-location registry exists for this dataset, so geographic proximity is not used or verified. See `src/windlens/reconstruct.py::select_reference_turbine`, which also falls back to the next-best-ranked candidate if the top pick turns out to have no readings covering the actual outage window (2026-10-24 correctness fix).

## What it does

1. Identify the target turbine's outage window (the real BayWa challenge data's own hidden window; or, for an uploaded file, auto-detected from the file's own data gap).
2. Select a reference turbine by pre-outage behavioral correlation, falling back to the next-best candidate that actually has data covering the window if the top-ranked one does not.
3. Reconstruct the target turbine's wind speed from the reference turbine's wind speed during the missing interval (a variance-matched linear measure-correlate-predict fit).
4. Convert reconstructed wind into expected power using the target turbine's own empirical power curve, fitted on its pre-outage data.
5. Integrate expected power into estimated lost energy (kWh).
6. Separately self-validate the method on a different, known window where real recorded wind exists to check against, and run the result through a review gate (input QA, reference/target alignment, tested wind-speed domain) before presenting it.
7. Optionally convert lost kWh into an indicative financial value from a manually entered, clearly labeled illustrative price. This is never a settlement, contractual, or legal figure.

## Upload workflow

Upload the target turbine's own file (the one with the gap), at least one
other turbine's file as a reference, and that target's power-curve file —
all into one upload control; WindLens classifies each by its column
headers, not by filename or a separate field. It detects every qualifying
outage per turbine, reconstructs each one, and only ever estimates loss for
detected targets — a reference turbine never gets its own loss figure. The
result replaces the view in place, labeled clearly as your own run versus
the official BayWa demo record; generate a report for whichever one you're
currently looking at.

## Two-page UI

- **The Analysis page** — upload control, the live result (your own run or
  the official demo), the outage-overlay chart, the editable indicative
  price/financial impact, and report actions (PDF, email).
- **The Methodology page** — full validation detail, limitations, and the
  method itself. No price input or financial figure here — those are part
  of the active result, not an explanation of the method (2026-10-24,
  Anna's correction).

Exact labels and routes live in `workspace/index.html`/`workspace/app.js`,
authoritative over this paragraph if they ever diverge.

## Current verified state

As of October 24, 2026, the full test suite is **217 tests, 217 pass**. Run with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

The only third-party dependencies are pandas and numpy (plus openpyxl, for reading BayWa's `.xlsx` source files); no machine-learning library is used anywhere in the pipeline. If `python3` on your PATH doesn't have them installed (`ModuleNotFoundError: No module named 'numpy'`), install them (`pip install pandas numpy openpyxl`) or point `python3` at a virtual environment that has them, then re-run the command above.

## Honest limitations

- **The hidden-window prediction (T3, 2026-09-01 to 2026-09-04) has no ground truth to check against, by construction.** That is what makes it the real graded submission rather than a validated estimate — its accuracy is supported only by the separate self-validation on a different, known window.
- **Reference selection is pure behavioral correlation.** No turbine-location/geography registry exists for this dataset, so geographic proximity between target and reference is not verified, only inferred from how well their historical readings correlate.
- **Self-validation "truth" is a power-curve-derived proxy, not an independent power measurement.** No BayWa source file for any turbine contains a power column — shown-window "truth" power is the measured power curve applied to the real, shown wind-speed reading.
- **No guaranteed statistical confidence interval exists yet for this pipeline.** The kWh range shown is an observed-error bracket across the 3 real validation targets (n=3), using the worst (largest) of the three errors as a deliberately conservative bound — not a statistical confidence interval; the review gate marks this "not evaluated" rather than claiming a coverage figure it hasn't earned.
- **This is not an outage-cause detector.** The tool estimates lost production; it does not and currently cannot distinguish a real mechanical outage from a sensor fault or other benign data gap — confirm the cause independently before relying on the number.
- **Commercial output is indicative only.** The kWh-to-currency conversion uses a manually entered, clearly labeled illustrative price and carries no settlement, contractual, regulatory, or legal weight.
- **This is a hackathon prototype**, not production software. It has not been reviewed for production security, scaling, or operational hardening.

## Future opportunities (not part of this submission's evidence)

- A reliable, guaranteed confidence interval for the real BayWa pipeline, once enough held-out BayWa data exists to build one.
- Automatic outage-cause classification.
- A multi-turbine machine-learning ensemble, if accuracy on harder targets outweighs its added complexity and run time (more accurate on one real target, comparable on the other two, but ~30-90x slower — see `docs/DECISION_LOG.md`).

## Repository layout

- `src/windlens/` — the reconstruction, uncertainty, and review-gate pipeline, plus the upload tool and local server.
- `tests/` — the test suite (217 tests, 217 pass; see "Current verified state" above).
- `data/` — raw source archives (including BayWa's real challenge data) and derived canonical datasets, with provenance manifests.
- `workspace/` — the dependency-free evidence-first analyst workspace: two pages, **Analysis** (the live result — the official demo or your own uploaded run — with the editable price and report actions) and **Methodology** (validation detail and the method itself only).
- `docs/` — `PRODUCT_BRIEF.md` (the current product specification), `DATA_PROVENANCE.md` (current dataset provenance), `DECISION_LOG.md` (the full, append-only history of decisions and results, including unsuccessful attempts and earlier proxy-farm validation work), `HANDOVER.md` (the concise cross-session summary), and `archive/` (superseded documents, each marked historical).
- `WindLens_instructions.md` — the original challenge brief this prototype was built against. Marked historical at the top of the file; see `docs/PRODUCT_BRIEF.md` for current product framing.

## Documentation authority

For current product behavior, use: (1) the current code and tests, (2) `docs/PRODUCT_BRIEF.md`, (3) this README, (4) `workspace/README.md`. Use `docs/DECISION_LOG.md`, audit/red-team reviews, and `docs/archive/` as historical evidence only — not current implementation instructions unless a task explicitly points to them.

## Running it locally

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # run the test suite
PYTHONPATH=src python3 -m windlens.baywa_tool_server          # serve the workspace + the live upload endpoint
```

Then open <http://127.0.0.1:8765/#overview>. (All `python3` calls need a Python with pandas, numpy, and openpyxl installed -- see the dependency note under "Current verified state" above if you hit `ModuleNotFoundError`. `workspace/README.md` has more detail, including a plain-static-server option for read-only viewing with no live upload.)
