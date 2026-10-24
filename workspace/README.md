# WindLens evidence workspace — quickstart

This is a dependency-free local analyst workspace: two pages, no build step,
no JSON fetched at runtime for the official record (the assessment data is
generated ahead of time and inlined as a `<script>` tag — see "Regenerating
the official record" below).

## Start the server and open the tool

```bash
PYTHONPATH=src /Users/annaradova/.venv/bin/python3 -m windlens.baywa_tool_server
```

(Substitute your own venv's `python3` if you did not use the path above --
`ModuleNotFoundError: No module named 'numpy'` means the wrong interpreter is
being used. Needs pandas, numpy, and openpyxl.)

Then open <http://127.0.0.1:8765/>. This one process serves the static
workspace files and the live `/run`/`/preview`/`/insurance-report` endpoints
together — the upload form will not work without it.

If you only need to read the pages (no live upload), a plain static server
also works, with the upload form showing an error directing you to the
command above instead:

```bash
python3 -m http.server 8000   # then open http://localhost:8000/workspace/
```

## What a target turbine file is

A wind-data file for the turbine that stopped reporting — the one with a
gap in its `wind_speed_ms` readings. WindLens detects this automatically
from the file's own data (a contiguous run of missing readings at least
`MIN_OUTAGE_RUN_LENGTH` rows long); you don't mark it yourself. A turbine
with two separate such gaps produces two independent results.

## What a reference turbine file is

Any other uploaded turbine's wind-data file, with no qualifying gap.
WindLens ranks every reference candidate by how well its pre-outage
readings correlate with the target's, and picks the best one that actually
has data covering the target's specific outage window — falling back to the
next-best covered candidate if the top pick doesn't.

## How power curves are matched

Each power-curve file is matched to its own target turbine by filename
(e.g. `T2_power_curve.xlsx` → target T2) — upload one per target you want a
financial figure for. A target with no matching curve among the files you
uploaded still gets its wind-speed reconstruction; it just won't have a
kWh/financial figure, and the result says so explicitly rather than
borrowing another turbine's curve.

## What's detected automatically vs. what needs manual confirmation

Automatic: file role (wind data vs. power curve, from column headers, not
filename), target vs. reference role per turbine, every qualifying outage
window per turbine.

Needs manual input: a dropout shorter than the auto-detection threshold, or
any outage type auto-detection doesn't cover (a flatlined/stuck reading, a
zero-output period with no missing timestamp) — use the manual outage-window
start/end fields for these. If you give one of those fields, you must give
both; a half-filled manual window is rejected rather than silently falling
back to auto-detection.

## What the result means

The headline kWh figure is the estimated energy the target turbine would
have produced during its outage, had it kept operating normally — not a
measurement, a reconstruction from a reference turbine's real wind data run
through the target's own power curve. It carries its reference selection,
a domain/coverage check, and (for the official BayWa record) a separate
self-validation result on a different, known window, so you can judge
whether to trust it before acting.

## How to generate the report

The report button generates a short, insurer-facing report for whichever
specific result you're currently looking at — your own uploaded run, or the
official demo — naming that turbine and its own dates, never a stale or
different one. It isn't available until that result has finished
calculating.

## What the tool cannot prove

A telemetry gap alone does not prove a physical or generation outage —
WindLens estimates the lost production if there was one; confirming the
actual cause (mechanical failure, sensor fault, grid curtailment, or
something else) is on you, from evidence outside this tool. The kWh range
shown is an observed-error bracket, not a calibrated statistical confidence
interval. Nothing here is a settlement, contractual, regulatory, or legal
figure.

## Regenerating the official record

```bash
PYTHONPATH=src /Users/annaradova/.venv/bin/python3 -m windlens.run_baywa_assessment
```

This regenerates `data/derived/baywa_assessment_result.json` and
`workspace/assessment-data.js` (the official T3 record `index.html` loads
as an inline `<script>` tag — the page does not fetch this over the
network).
