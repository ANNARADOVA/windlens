# Dataset discovery — Phase 0/1

## Chosen case data

**Kelmarsh wind farm data, v4** (Plumley & Takeuchi / Cubico Sustainable Investments), Zenodo DOI: https://doi.org/10.5281/zenodo.16807551

- **Licence:** CC BY 4.0. Attribution is required in the product/demo and any derived data.
- **Why this case:** six identical Senvion MM92 turbines at one UK wind farm, with 10-minute SCADA, event, static and meter data. For the MVP, turbine 1 is the affected asset and turbines 2–6 are *peer-reference proxies*; this is not a claim that they are separate neighbouring farms.
- **Raw source:** `Kelmarsh_SCADA_2016_3082.zip` (97.9 MB; MD5 `ca8efbb6dbcfae3516583937eb5b5402`). It is the smallest published annual SCADA archive, but still contains all six turbines. Later ingestion must extract only the needed columns and a bounded time window; raw archives must remain unmodified.
- **Companion metadata:** `Kelmarsh_WT_static.csv` (807 B; MD5 `af3a038f0f7fddfc1608ad0bfc8cf5ba`) and `Kelmarsh_WT_dataSignalMapping.csv` (3.1 kB; MD5 `ca8fe399ab15ae7111d3214c632efd36`).

No raw data has been added to this workspace yet. The local terminal process is currently unavailable in this session (`CreateProcess … No such file or directory` even for `ls`), so a reproducible download/extract check could not be executed. Do not substitute fabricated records.

## Required analysis schema

The source exports use one turbine CSV per turbine/year. The minimal normalised schema for this MVP is:

| Canonical field | Kelmarsh source field | Unit | Use |
|---|---|---:|---|
| `timestamp_utc` | `# Date and time` | UTC | 10-minute alignment |
| `turbine_id` | derived from filename | — | affected/reference role |
| `wind_speed_ms` | `Wind speed (m/s)` | m/s | reconstruction target/input |
| `wind_direction_deg` | `Wind direction (°)` | ° | suitability/stratification |
| `active_power_kw` | `Power (kW)` | kW | power curve and loss calculation |

Useful QA fields to retain where available: turbine status/event data, nacelle position, ambient temperature, rotor speed and pitch angle.

## Known quality observations and safeguards

1. Source SCADA is 10-minute data; expected timestamp cadence is `:00, :10, :20, :30, :40, :50` UTC.
2. Turbine data files have nine leading comment lines; the header begins on line 10 and its first column is literally `# Date and time`.
3. Missing/erroneous values can be encoded as the string `NaN`; they must be parsed as missing, not zero generation/wind.
4. Not every signal is present for every period. Training must use only simultaneous, valid target/reference observations and exclude planned/known abnormal operation once event data is inspected.
5. Do **not** use original 2023–24 files without a repair step: a published provenance audit reports cumulative-block duplicates. If those years are needed, use the separately published reconstructed files/flags: https://doi.org/10.5281/zenodo.23171808 (also CC BY 4.0).
6. A data gap in SCADA does not itself prove an energy outage. The MVP will simulate outages by masking known healthy target intervals, then score reconstruction against the hidden truth.

## Data acquisition gate

Before download, retain the above DOI, version, filename and MD5 in a data manifest. The next permitted download is the 2016 archive plus the two metadata CSVs; then extract a small, versioned working slice (for example, 60–90 days and turbines 1–6) into a derived-data directory with a README. This keeps the hackathon dataset reproducible while avoiding large unnecessary storage.

## Citations

- Plumley, C. & Takeuchi, R. (2025). *Kelmarsh wind farm data* (v4). Zenodo. https://doi.org/10.5281/zenodo.16807551
- Park, A. et al. (2026). *Kelmarsh wind farm SCADA data (v4): reconstructed 2023–2024 files, signal onset manifest and flag table*. Zenodo. https://doi.org/10.5281/zenodo.23171808
