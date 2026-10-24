# WindLens — current product brief

**This document is the current product specification.** If anything elsewhere in
this repository (an older plan, a research note, a historical dataset doc)
disagrees with what's written here, this file wins for *current* behavior —
see "Documentation authority" below.

**Last updated:** 2026-10-24.

## Purpose

WindLens estimates the energy a wind turbine would have produced during an
outage (a period with no usable readings), using real wind data from a
nearby reference turbine. It converts that reconstructed wind into an
estimated energy loss in kilowatt-hours (kWh), optionally priced into an
indicative financial figure.

It is decision support, not autonomous automation, and not a legal,
contractual, settlement, or insurance determination. A telemetry gap alone
does not prove a physical outage — confirming the cause is the user's job,
not the tool's.

## Current user

An analyst or reviewer (e.g. an asset manager or an insurer's technical
reviewer) assessing how much energy a specific turbine lost during a known
or suspected outage, who needs an estimate they can see the evidence behind,
not a black-box number.

## Current user workflow

1. **Upload** the affected (target) turbine's own data file, at least one
   other turbine's file to act as a reference, and — for a financial
   figure — that target's own power-curve file.
2. **Detect** — WindLens classifies each uploaded turbine as a target (has a
   qualifying data gap) or a reference candidate (does not), and detects
   every qualifying outage window per turbine, not just one.
3. **Reconstruct** — for each detected outage, WindLens selects the
   best-correlated reference turbine (falling back to the next-best one if
   the top pick lacks data during that specific window) and reconstructs the
   target's wind speed for the gap.
4. **Estimate** — reconstructed wind is converted to expected power via the
   target's own power curve, then integrated into estimated lost kWh.
5. **Review** — the result carries its reference selection, a domain/coverage
   check, and (for the real BayWa submission) a separate self-validation
   result on a different, known window — so the user can judge whether to
   trust it before acting.
6. **Report** — generate a short, insurer-facing report and an emailable
   draft for the specific target and outage being viewed.

## Current UI

A two-page local browser tool, served by the local upload/reconstruction
server (`windlens.baywa_tool_server`):

- **The analysis/result page** — upload control, the live reconstruction
  result (your own uploaded run, or the official BayWa demo record), and the
  outage-overlay chart.
- **The methodology page** — full validation detail, the editable indicative
  price, the method's limitations, and report actions.

Exact page labels and navigation are defined in the live code
(`workspace/index.html`, `workspace/app.js`) — treat those as authoritative
over this paragraph's wording if they ever diverge.

## Target vs. reference turbines

- **Target turbines** are turbines WindLens estimates missing production for
  — auto-detected as any turbine with a contiguous run of missing
  (`NaN`) wind-speed readings at least `MIN_OUTAGE_RUN_LENGTH` rows long.
  Only target turbines ever receive a loss estimate.
- **Reference turbines** supply the wind readings used to reconstruct a
  target's missing wind speed. Any uploaded turbine not itself flagged as a
  target is a reference candidate; WindLens ranks candidates by pre-outage
  behavioral correlation (time-ordered holdout R²) and picks the
  best-correlated one that actually has data covering the specific outage
  window.
- A reference turbine never receives its own loss estimate, and never
  silently becomes a target just because part of its own history has gaps —
  only a gap that itself reaches the qualifying length flips a turbine's
  role for that period.

## Supported upload formats

- Wind-data files: one turbine per file (matching BayWa's own shape) or a
  combined file with a `turbine_id` column — either way, every uploaded
  wind-data file is combined before target/reference roles are decided.
- Power-curve files: matched to their own target turbine by filename
  (e.g. `T2_power_curve.xlsx` → target `T2`). A target with no matching
  curve among the uploaded files still gets its wind-speed reconstruction,
  just no kWh/financial figure, with an explicit note why.
- File kind (wind data vs. power curve) is detected from column headers, not
  from the filename or a separate upload field — every file goes into one
  upload control.

## Current BayWa dataset

The real BayWa r.e. "Energy & AI" hackathon challenge dataset
(`data_hackathon_baywa_re (1)/`, gitignored — proprietary, not published):

- **Target turbines:** T1, T2, T3 — each with its own data gap and its own
  power-curve file.
- **Reference candidates:** O1, O2, H1–H5 — no data gaps, no power curves.
- No turbine-location registry exists for this dataset, so reference
  selection is pure behavioral correlation; geographic proximity is neither
  used nor verified.
- The primary official/demo record is **T3**: a hidden-window prediction
  (2026-09-01 to 2026-09-04, no ground truth by construction, since that's
  the actual graded submission) of **112,411 kWh**, reconstructed from
  reference turbine O1.

## Methodology, at a high level

A time-ordered statistical best-fit line from the reference turbine's wind
to the target's (measure-correlate-predict), using a single best-correlated
reference turbine chosen by pure behavioral ranking. The fit matches the
predicted wind's variance to the target's own (not ordinary least squares,
which under-predicts energy once pushed through a power curve). Reconstructed
wind is converted to power via the target's own pre-outage empirical power
curve, then integrated into kWh over the outage window.

Separately, the method is self-validated on a different, known window (where
real recorded wind exists to check against) — this is how its accuracy is
supported, since the actual graded hidden-window prediction has no ground
truth to check against by construction.

Full detail: the methodology page in the live tool, and `docs/DECISION_LOG.md`
for the complete history of how this method was chosen.

## Outage-detection scope

WindLens auto-detects every qualifying outage per turbine — a contiguous run
of missing (`NaN`) wind-speed readings at least `MIN_OUTAGE_RUN_LENGTH` rows
long. A turbine with two separate such gaps in its uploaded history produces
two independent results, each correctly scoped to its own pre-window
history.

**What this does not detect:** a shorter dropout (below the length
threshold), a flatlined/stuck sensor reading, a zero-output period with no
missing timestamp, or anything an explicit status/event column would flag —
none of those exist in the BayWa dataset's own columns. For any of these,
use the manual outage-window fields instead of relying on auto-detection.

## Report behavior

A report is generated for whichever specific target and outage window is
currently being viewed — the official BayWa demo record, or your own
uploaded run — never a different, stale, or hardcoded target. The report
names the actual turbine and dates it was built from, and is not available
until that result has finished calculating. See the live code
(`src/windlens/insurance_report.py`) for exact field provenance.

## Current limitations and non-claims

- The hidden-window prediction (the real graded submission) has no ground
  truth to check against, by construction — its accuracy is supported only
  by the separate self-validation on a different, known window.
- Reference selection is pure behavioral correlation; geographic proximity
  is not verified for this dataset.
- Self-validation "truth" is a power-curve-derived proxy from real wind
  readings, not an independent power measurement — no BayWa file contains a
  power column.
- No guaranteed statistical confidence interval exists for this pipeline yet.
  The kWh range shown is an observed-error bracket across 3 real validation
  targets (n=3), using the worst of the three as a conservative bound, not a
  statistical confidence interval.
- This is not an outage-cause detector. A telemetry gap alone does not prove
  a physical or generation outage — confirm the cause independently.
- Commercial output is indicative only, from a manually entered demo price —
  never a settlement, contractual, regulatory, or legal figure.
- This is a hackathon prototype, not production software.

## How to run the tool

```bash
PYTHONPATH=src python3 -m windlens.baywa_tool_server
```

Then open <http://127.0.0.1:8765/>. See `workspace/README.md` for the full
quickstart, including the dependency-free static-server option for
read-only viewing (no live upload).

## How to run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

## Documentation authority

For current product behavior, use:

1. the current code and tests;
2. this file (`docs/PRODUCT_BRIEF.md`);
3. `README.md`;
4. `workspace/README.md`.

Use `docs/DECISION_LOG.md`, audit reports, red-team reviews, and archived
dataset documents (`docs/archive/`) as historical evidence only. They are
not current implementation instructions unless a task explicitly points to
them.
