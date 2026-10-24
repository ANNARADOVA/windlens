# Data provenance — current product

This covers only the data the active product actually uses. For the earlier
Kelmarsh/Penmanshiel/Hill of Towie/EDP research datasets, see
"Historical/research datasets" below — they are not part of the current
BayWa submission's evidence.

## BayWa r.e. challenge dataset (current, active)

- **Source:** the official BayWa r.e. "Energy & AI" hackathon dataset,
  supplied directly by the challenge organizers.
- **Location:** `data_hackathon_baywa_re (1)/` — proprietary challenge data,
  gitignored, not published in this repository.
- **Shape:** one Excel file per turbine (`T#_data.xlsx` / `H#_data.xlsx` /
  `O#_data.xlsx`), plus one power-curve file per target turbine
  (`T#_power_curve.xlsx`). 10-minute cadence, 90 days, 12,960 rows per
  turbine.
- **Turbines:** T1, T2, T3 (targets, each with a real data gap and its own
  power curve); O1, O2, H1–H5 (reference candidates, no data gap, no power
  curve).
- **No turbine-location registry exists for this dataset** — reference
  selection is pure behavioral correlation, not geography.

### Canonical derived dataset

- **Generator:** `src/windlens/build_baywa_dataset.py`.
- **Output:** `data/derived/baywa_canonical.csv`, 129,600 rows (10 turbines ×
  12,960 rows).
- **Manifest:** `data/derived/baywa_canonical.manifest.json` — per-turbine
  source file, observed MD5, row count, and NaN-wind-speed row count.
- Regenerate with:

  ```bash
  PYTHONPATH=src python3 -m windlens.build_baywa_dataset
  ```

### Generated assessment artifacts

The official/demo record (T3, 112,411 kWh) and its supporting self-validation
data are generated from the canonical dataset above and written to:

- `data/derived/baywa_assessment_result.json` — the per-target assessment
  result the demo record and the insurance-report generator read.
- `workspace/assessment-data.js` — the same data, inlined for the
  dependency-free browser workspace.

Regenerate with:

```bash
PYTHONPATH=src python3 -m windlens.run_baywa_assessment
```

## Historical/research datasets (not current product evidence)

These were used to validate the reconstruction *method* before the real
BayWa data arrived, and remain referenced only as a brief "future
opportunities" mention in the current product (see `docs/PRODUCT_BRIEF.md`).
Full detail is historical record only:

- **Kelmarsh** (Plumley & Takeuchi / Cubico Sustainable Investments, Zenodo
  DOI `10.5281/zenodo.16807551`, CC BY 4.0) — see
  `docs/archive/DATASET_DISCOVERY_KELMARSH_PHASE_0_1.md`,
  `data/derived/kelmarsh_2016_90d_canonical.manifest.md`, and
  `data/derived/kelmarsh_2016_full_year_canonical.manifest.md`.
- **Penmanshiel** — see `data/derived/penmanshiel_2016_canonical.manifest.json`.
- **Hill of Towie** and **EDP Portugal** — see `docs/PROJECT_STATE.md`'s
  historical section and `docs/DECISION_LOG.md` for the full external-farm
  validation history, including why the EDP geo-aware run was blocked
  (no verified turbine registry in the public release).

None of these are published in this repository (large archives, kept local)
and none of them feed the current BayWa T1/T2/T3 submission.

## Documentation authority

See `docs/PRODUCT_BRIEF.md`'s "Documentation authority" section — this file
is current-state reference material, not a historical record; it should be
updated whenever the current product's data sources change.
