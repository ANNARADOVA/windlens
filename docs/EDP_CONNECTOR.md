# EDP Excel connector contract

WindLens has an explicit Excel connector boundary for the public EDP Portugal
SCADA source described at <https://data.mendeley.com/datasets/zjxjnjp3xs/1>.

The source covers 2016–2017, uses 10-minute UTC timestamps, and includes four
monitored turbines (T01, T06, T07, T11), wind speed/direction, active/reactive
power, met-mast observations, event logs, and failure logs. The source is listed
as CC BY 4.0. The original download is approximately 219 MB and is intentionally
not included in this workspace.

`ExcelFarmConnector` requires:

- an explicit workbook path;
- an explicit sheet name;
- an exact mapping from canonical fields to source columns;
- verified registry metadata for each turbine; and
- a source/license identifier.

The connector normalizes to the WindLens canonical fields:

`timestamp_utc`, `turbine_id`, `wind_speed_ms`, `wind_direction_deg`,
`active_power_kw`.

Source-specific unit conversion is deliberately outside this boundary. A real
EDP adapter should document and test any conversion before it supplies the
canonical mapping. This keeps a workbook schema change from silently changing
the model inputs.
