# Registry import and evidence workflow

WindLens needs turbine metadata to make a geo-aware reference decision. The
metadata is deliberately supplied separately from SCADA telemetry so the
system can show where the location and rated-power assumptions came from.

## Operator input

Start from [`edp_registry_template.csv`](../data/raw/edp_portugal/edp_registry_template.csv).
Each row must contain:

- `farm_id` and `turbine_id`;
- latitude and longitude in decimal degrees;
- rated power in kW;
- `data_source` describing the authoritative source;
- `quality_status=verified` when the values have been checked by the operator.

The importer rejects missing columns, invalid coordinates, non-positive rated
power, duplicate farm/turbine keys, and rows that cannot be parsed by the shared
`FarmRegistry` domain model. It never fills missing coordinates with guesses.

## Evidence report

`load_registry_csv()` returns both a validated registry and a report containing
the source filename, MD5, accepted/rejected row counts, farm/turbine IDs,
quality state, and row-level issues. Any issue or unverified row makes
`usable_for_geo_selection=false`. That state is an explicit abstention gate.

## EDP validation

`run_edp_validation()` accepts explicit EDP workbook paths and a registry path,
then writes a standalone `external-validation.v1` JSON artifact. It records
the registry evidence, source rows, time range, duplicate policy, and the fact
that Kelmarsh training was not used. A Kelmarsh registry is rejected by the
runner so external validation cannot silently become same-farm evaluation.

The public EDP workbooks contain repeated UTC labels around apparent clock
resets. The default duplicate policy is `reject`. The exploratory
`keep_first` policy is allowed only when the resulting artifact is marked
`unverified_data_quality`.
