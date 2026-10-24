# WindLens MVP design

## Purpose

WindLens reconstructs the wind and expected generation of an unavailable wind asset from healthy nearby reference assets. It presents an estimated energy yield loss with validation evidence, not a settlement or bankability determination.

## Demonstration case

The MVP uses the CC-BY-4.0 Kelmarsh wind-farm 2016 SCADA archive. Turbine 1 is the simulated affected asset and turbines 2–6 are peer-reference proxies. This is a data proxy for the challenge's neighbouring reference farm, not a claim that the turbines are separate farms.

## First vertical slice

1. Extract a reproducible 90-day, 10-minute working dataset from the raw archive.
2. Normalise the five required fields: UTC timestamp, turbine ID, wind speed, wind direction and active power.
3. Reject invalid timestamps, duplicate rows, out-of-cadence samples and impossible readings.
4. Retain only a data-quality report and a clean source slice; no loss claim is made yet.

## Later slices

1. Mask a known healthy target interval.
2. Fit and score a target-wind reconstruction from reference turbines using only prior valid overlap.
3. Fit an expected-power curve and calculate kWh loss with a prediction interval.
4. Store a traceable assessment record and build the analyst evidence workspace.
5. Add a commercial-value connector only after the core back-test passes.

## Quality gates

- Every derived file retains the source DOI, licence, archive checksum and extraction window.
- A 10-minute series must have UTC timestamps, one row per turbine/time pair, physically plausible wind speed and non-negative active power.
- Outages are simulated by masking known observations; a data gap alone never becomes a generation-loss claim.
- Model output will later abstain when references, coverage or validated domain are insufficient.

## Non-goals

The MVP does not infer event causality, determine legal settlement, parse contracts or claim lender-grade certification.
