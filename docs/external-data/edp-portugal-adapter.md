# EDP Portugal external-farm adapter

## Source

The first external-farm candidate is the EDP onshore wind-farm SCADA dataset:

- Mendeley Data DOI: `10.17632/zjxjnjp3xs.1`
- Licence: CC BY 4.0
- Coverage: 2016–2017
- Format: eight Excel files, approximately 219 MB total
- Sampling: 10-minute UTC timestamps
- Turbines: T01, T06, T07, T11
- Available source material: SCADA signals, met mast measurements, event logs, and failure logs

Source page: <https://data.mendeley.com/datasets/zjxjnjp3xs/1>

## Adapter boundary

The adapter must receive an explicit mapping for each source workbook rather than guessing columns. The minimum normalized output is:

```text
timestamp_utc
turbine_id
wind_speed_ms
wind_direction_deg
active_power_kw
```

The metadata registry must also provide:

```text
farm_id
turbine_id
latitude
longitude
elevation_m
hub_height_m
rated_power_kw
data_source
time_coverage_start
time_coverage_end
quality_status
```

Event and failure logs remain separate evidence inputs. They must not be folded into the SCADA frame as invented power or wind values.

## Validation plan

1. Download the source only after confirming the bounded extraction window and local storage budget.
2. Preserve the source checksum and licence in a manifest.
3. Inspect workbook headers and write the explicit mapping configuration.
4. Extract one bounded year/window and the four turbines into the canonical schema.
5. Run the same timestamp, unit, plausibility, coverage, and gap checks as Kelmarsh.
6. Validate EDP independently; never concatenate it with Kelmarsh training data.

The source is a separate farm from Kelmarsh, but a single external farm by itself does not prove cross-farm reconstruction. That requires two farms with overlapping periods: one target and one reference.
