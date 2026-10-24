# Registry and EDP Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable turbine-registry import/evidence flow and run EDP as a separate validation farm without mixing it into Kelmarsh training.

**Architecture:** A CSV registry importer validates operator-supplied metadata and returns both a `FarmRegistry` and an evidence report. A separate EDP validation runner consumes the existing EDP Excel connector plus that registry, writes a standalone artifact, and never writes to Kelmarsh derived data. The workspace reads the report/artifact and presents metadata provenance and blocking issues alongside the existing assessment.

**Tech Stack:** Python 3, pandas, stdlib `unittest`, JSON/CSV contracts, dependency-free HTML/CSS/JavaScript workspace.

---

### Task 1: Define registry import and evidence report behavior

**Files:**
- Create: `src/windlens/registry_import.py`
- Create: `tests/test_registry_import.py`

- [x] **Step 1: Write failing tests** for a valid CSV import, missing required fields, invalid coordinates/rated power, duplicate farm/turbine keys, missing provenance, and a report that records accepted/rejected rows plus source filename/checksum.
- [x] **Step 2: Run `PYTHONPATH=src python3 -m unittest tests.test_registry_import -v` and confirm failure because the importer does not exist.
- [x] **Step 3: Implement `RegistryImportResult`, `RegistryImportIssue`, and `load_registry_csv(path, *, data_source, require_verified=True)` using `FarmRegistry.from_records`, `file_md5`, and row-level validation. The function must never fabricate coordinates or rated power.
- [x] **Step 4: Run the focused test file and confirm it passes.

### Task 2: Add an explicit EDP validation runner

**Files:**
- Create: `src/windlens/run_external_validation.py`
- Create: `tests/test_external_validation.py`

- [x] **Step 1: Write failing tests** proving the runner accepts only a separate farm registry, writes a standalone JSON result, refuses a registry with `farm_id=KELMARSH`, and records duplicate-source quality issues as unverified.
- [x] **Step 2: Run the focused test file and confirm the expected missing-module failure.
- [x] **Step 3: Implement `run_edp_validation(workbook_paths, registry_path, output_path)` to load the registry, load EDP through `EDPPortugalSCADAConnector`, calculate source coverage and duplicate-policy status, and write a versioned artifact containing source, registry evidence, row counts, turbine IDs, time range, and validation status. Do not call Kelmarsh loaders or write under `data/derived/kelmarsh*`.
- [x] **Step 4: Run focused tests and confirm they pass.

### Task 3: Add a checked-in EDP registry template and evidence artifact contract

**Files:**
- Create: `data/raw/edp_portugal/edp_registry_template.csv`
- Create: `schemas/registry_import_report.schema.json`
- Create: `docs/registry-import.md`
- Create: `tests/test_workspace_registry_evidence.py`
- Modify: `docs/PROJECT_STATE.md`
- Modify: `docs/DECISION_LOG.md`

- [x] **Step 1: Add a template with the required headers and no invented coordinates.
- [x] **Step 2: Define the JSON report fields: source path/checksum, accepted/rejected counts, issues, farm IDs, turbine IDs, quality status, and `usable_for_geo_selection`.
- [x] **Step 3: Document operator workflow, provenance requirements, EDP duplicate handling, and the rule that EDP remains a separate validation farm.
- [x] **Step 4: Record the change, assumptions, evidence, limitations, and next handoff step in the persistent project documents.

### Task 4: Add registry evidence to the analyst workspace

**Files:**
- Modify: `workspace/index.html`
- Modify: `workspace/styles.css`
- Modify: `workspace/app.js`
- Modify: `workspace/assessment-data.js`
- Test: `tests/test_workspace_registry_evidence.py`

- [x] **Step 1: Add a failing static HTML/JavaScript assertion for a registry evidence section showing source, farm, turbine count, quality state, and blocking issue.
- [x] **Step 2: Add a compact “Farm metadata evidence” panel, keeping the evidence-first visual system and avoiding a dashboard-style map or decorative import wizard.
- [x] **Step 3: Render `usable_for_geo_selection=false` as a visible abstention/blocking state, not as a warning hidden in a tooltip.
- [x] **Step 4: Run `node --check workspace/app.js` and inspect the local workspace manually.

### Task 5: Run full verification

**Files:**
- Modify: `docs/PROJECT_STATE.md`
- Modify: `docs/DECISION_LOG.md`

- [x] **Step 1: Run the complete Python suite with the bundled Python runtime.
- [x] **Step 2: Run `node --check workspace/app.js`.
- [x] **Step 3: Run the EDP validation smoke path only with an explicitly labelled fixture registry unless verified production coordinates are available.
- [x] **Step 4: Record exact test counts, generated artifacts, and any abstention/blocking state.
