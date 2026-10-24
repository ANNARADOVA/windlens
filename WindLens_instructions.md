You are the senior engineer taking over an in-progress hackathon prototype called WindLens.

Your job is to continue the work systematically, with production-quality engineering judgment, without turning it into a generic AI dashboard or a one-shot demo. Work in small, verified slices. Do not rewrite the application wholesale. Do not claim capabilities the system has not demonstrated.

# 1. Challenge

BayWa r.e. challenge:

“When a wind farm loses power, it stops generating electricity and recording wind data. Without these measurements, calculating the resulting energy yield loss becomes difficult.

Build a tool that uses wind data from a neighboring reference wind farm to predict missing wind speeds and calculate the resulting energy yield loss (kWh).”

The required core is therefore:

reference wind data
→ reconstruct missing target-farm wind during an outage
→ estimate target-farm expected generation
→ calculate estimated lost energy in kWh

This is counterfactual reconstruction during or after an outage. It is NOT future-failure prediction.

# 2. Product thesis and business framing

Do not position this as “an AI dashboard that predicts losses.”

Position it as:

“A trusted outage-reconstruction workspace that estimates missing wind and expected generation when primary site telemetry is unavailable, with enough evidence for a performance analyst to review and act on the result.”

The core value is not merely producing a number. It is producing a reproducible, challengeable estimate with:
- validated reference data;
- visible assumptions;
- back-test performance;
- uncertainty;
- a traceable evidence record.

Commercial/claims/financing relevance is a future extension. The MVP must not claim:
- legal settlement value;
- final root cause;
- final Redispatch eligibility;
- OEM liability;
- lender-grade or “bankable” certification.

Use safer language: “audit-ready / reviewable evidence trail” or “bankability-relevant methodology,” never “bankable result.”

# 3. Resilient Cognitive Systems principles

This is a joint human-machine decision-support system, not autonomous automation.

The product must help an analyst:
- Monitor: understand data health, reference quality, gaps, and validity risks.
- Respond: obtain a loss estimate plus a clear next action.
- Anticipate: identify weak reference coverage / model-domain risk before a future outage.
- Learn: reconcile estimates against later evidence and version the model.

Graceful degradation is mandatory:
- If reference data is unavailable, unsuitable, stale, out of validated range, or uncertain: switch reference, widen uncertainty, or abstain.
- Do not invent precision.
- A SCADA gap alone does not prove a generation outage. In this hackathon, use simulated outages made by masking known healthy observations.

# 4. User and workflow

Primary user: performance analyst reviewing an outage.

Workflow:

1. Normal operation: target and reference assets have overlapping historical data.
2. An outage/data-loss interval is identified.
3. Reference asset data remains available.
4. The system reconstructs missing target wind.
5. The system converts reconstructed wind to expected power and lost kWh.
6. The analyst sees evidence, validation metrics, uncertainty, and any failed quality gates.
7. The assessment is saved as a traceable loss record.

Do not build event-cause classification from wind/power data alone. Cause should eventually come from an operator ticket, alarm, grid instruction, or human review.

# 5. Current approved MVP scope

Approved sequence:

0. Freeze a real case dataset and data dictionary.
1. Validate timestamps, units, gaps, and healthy training intervals.
2. Mask known target intervals to simulate an outage.
3. Build reference → target wind reconstruction.
4. Convert reconstructed wind to expected power / lost kWh.
5. Back-test against known hidden truth.
6. Build the analyst-facing evidence workspace.
7. Add optional price/PPA API connector only after the core passes quality gates.

Do not start live price/PPA APIs now. Create an interface boundary later, but the current milestone is proving the physical kWh reconstruction.

# 6. Dataset and data assumptions

Use the public Kelmarsh Wind Farm v4 dataset:

- Source: https://doi.org/10.5281/zenodo.16807551
- Licence: CC BY 4.0 — preserve attribution in docs/demo.
- Source archive: `Kelmarsh_SCADA_2016_3082.zip`
- Verified source MD5: `ca8efbb6dbcfae3516583937eb5b5402`
- Six Senvion MM92 turbines, 10-minute UTC SCADA.
- Turbine rating: 2,050 kW.
- Target/affected asset: `KWF1`.
- Reference assets: `KWF2`–`KWF6`.

Critical honesty constraint:
Kelmarsh’s reference assets are turbines in the same farm, not a separate neighboring wind farm. It is a peer-reference proxy used for a reproducible MVP. The architecture must later accept a true external neighboring-farm connector without redesign.

Canonical schema:

- `timestamp_utc`
- `turbine_id`
- `wind_speed_ms`
- `wind_direction_deg`
- `active_power_kw`

The current derived slice is:

- `data/derived/kelmarsh_2016_90d_canonical.csv`
- Window: `[2016-05-01T00:00:00Z, 2016-07-30T00:00:00Z)`
- 64,406 valid records
- Derived file MD5: `15abb74500b414bff35f21e313da6827`

Read these workspace documents first:

- `DATASET_DISCOVERY.md`
- `docs/superpowers/specs/2026-10-20-windlens-mvp-design.md`
- `data/derived/kelmarsh_2016_90d_canonical.manifest.md`

# 7. Existing implementation

Current files:

- `src/windlens/prepare_dataset.py`
- `tests/test_prepare_dataset.py`
- `src/windlens/__init__.py`

Run the existing tests before any edits:

PYTHONPATH=src /Users/annaradova/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v

The current code is a deliberately small first slice. Do not assume it is sufficient.

# 8. Mandatory next engineering work

First: strengthen ingestion/QA before implementing outage masking.

An independent review found these required fixes:

1. Generate the provenance manifest programmatically from the extraction run. Require and record:
   - source DOI;
   - licence;
   - expected and observed archive checksum;
   - extraction window;
   - implementation/version identifier;
   - output checksum.

2. Report coverage and contiguous gaps:
   - expected 10-minute slots;
   - actual valid slots per turbine;
   - contiguous missing intervals;
   - simultaneous target/reference overlap.

3. Validate required source headers explicitly. Fail clearly if columns are absent. Fail if no valid records are produced.

4. Enforce configurable physical plausibility:
   - wind speed bounds;
   - direction normalization or explicit `[0, 360)` policy;
   - target-turbine rated-power bound with a documented tolerance.

5. Write derived output atomically. A failure must never overwrite an existing valid output.

6. Add tests for:
   - realistic Kelmarsh header preamble / filename;
   - missing required fields;
   - empty valid output;
   - duplicates;
   - `360°` and invalid directions;
   - physically implausible values;
   - gaps and coverage;
   - preservation of a previous output on extraction failure.

Only after these pass, create deterministic outage masking:

- input: clean canonical dataset;
- target: `KWF1`;
- mask a contiguous known-healthy target interval;
- leave peer references intact;
- write a masked dataset and a separate hidden-truth dataset;
- preserve timestamps and target identity;
- record the exact mask interval and truth checksum;
- test all of this.

# 9. Reconstruction and evaluation requirements

Use a transparent baseline first.

Baseline:
- train only on pre-outage overlapping healthy observations;
- start with linear measure-correlate-predict, using one reference and then a simple peer ensemble;
- never random-split time series.

Evaluation:
- use 3–5 contiguous held-out outage-like blocks;
- distribute blocks across different weather regimes where possible;
- compare against a simple single-reference linear baseline;
- freeze model configuration before scoring.

Metrics:
- wind MAE, RMSE, signed bias;
- per-event kWh absolute error;
- energy-weighted WAPE or equivalent robust energy metric;
- signed aggregate energy bias;
- prediction-interval coverage and width once uncertainty is implemented;
- abstention/escalation rate.

Do not rely on MAPE alone because near-zero generation makes it misleading.

A result is “Estimate — reviewable” only if:
- input QA passes;
- reference/target data align;
- the interval is within the model’s validated domain;
- back-test performance beats the agreed baseline;
- no abstention gate has failed.

Otherwise label it:
“Unverified — manual evidence required.”

# 10. OpenOA usage

OpenOA is allowed and desirable as a credible supporting layer, but it is not the product itself.

Upstream:
- https://github.com/NatLabRockies/OpenOA
- https://openoa.readthedocs.io/en/latest/

Use OpenOA later for:
- standard data schema/QA comparison;
- power-curve methods;
- imputation baseline;
- operational-assessment context.

Do not assume OpenOA alone implements our cross-farm outage reconstruction workflow.

Avoid adding OpenOA, scikit-learn, or other packages until you inspect the local environment and justify the dependency. The bundled Python currently has pandas/numpy but not scikit-learn/pytest. Ask before downloading/installing dependencies if network access or material environment changes are needed.

# 11. Design direction

The product must feel like an institutional energy-intelligence terminal: Modo Energy is the visual benchmark, not a template to copy.

Reference:
- https://modoenergy.com/product
- https://help.modo.energy/en/articles/13057275-what-is-the-modo-energy-terminal

Design rules:
- original branding and UI;
- sober, precise, dense-but-calm analyst workspace;
- persistent navigation and clear hierarchy;
- tables, time series, methodology, and evidence lead;
- every material value exposes source, date range, method, uncertainty, and exportability;
- methodology and data quality are first-class screens/sections;
- restrained palette and one meaningful status accent;
- no gradients, glassmorphism, rainbow charts, chatbot-first UX, fake live activity, oversized metric-card theatre, generic stock wind imagery, or vague “AI confidence” language.

The eventual hero screen must answer:

“During this outage, how much energy was likely lost—and how trustworthy is that number?”

It should display:
- incident/asset/window;
- estimated lost kWh;
- interval/uncertainty;
- reference integrity;
- back-test metrics;
- main time series;
- evidence/source table;
- methodology and validation panel;
- explicit next action or abstention reason.

No dashboard work until the core back-test works.

# 12. Working principles

- Read existing files and run tests before editing.
- Follow test-driven development: add/adjust a failing test, implement the smallest correct change, run tests, then refactor.
- Make small, cohesive commits/checkpoints if this workspace is a Git repository. It may not be; verify first.
- Never overwrite or delete user files. Preserve raw source data.
- Keep derived data reproducible and documented.
- Do not make up external data, outages, prices, contracts, or results.
- Cite external sources in docs when they materially inform methodology.
- Use subagents only for independent research/review tasks; do not allow parallel agents to edit the same files.
- Challenge assumptions, perform a brief pre-mortem before each major slice, and document meaningful decisions.
- Report progress after each vertical slice: changed files, tests run, results, limitations, next gate.
- If blocked, explain the exact blocker and the smallest safe next action.

# 13. Relevant market and methodology sources

Business/operations:
- BayWa technical operations / InSite: https://www.baywa-re.de/en/services/asset-operations/technical-operations-wind
- DNV operational energy assessment and uncertainty: https://www.dnv.com/services/operational-energy-assessment-of-renewables-3961/
- German Redispatch context: https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK08/BK8_07a_Redispatchkosten/BK8_Redispatchkosten.html

Operational analysis:
- OpenOA: https://github.com/NatLabRockies/OpenOA
- OpenOA docs: https://openoa.readthedocs.io/en/latest/
- NREL OpenOA overview: https://www.nrel.gov/wind/openoa.html
- Brightwind resource-analysis library: https://github.com/brightwind-dev/brightwind
- windpowerlib: https://github.com/wind-python/windpowerlib

Resilience:
- https://www.resilience-engineering-association.org/resources/where-do-i-start/
- https://www.sciencedirect.com/science/article/pii/S0951832015000848

Begin with Section 8 only. Do not jump ahead to modelling or UI until the strengthened data-quality gate is tested and reported.