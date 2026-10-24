# Example insurance-report deliverable: Turbine T3

This is a real, generated example of the insurance-report bonus deliverable
(`src/windlens/insurance_report.py`), run against the project's current
primary/representative BayWa record: turbine **T3**'s entry in
`data/derived/baywa_assessment_result.json` (T3 is the median-error result
of the three validated targets -- see `docs/HANDOVER.md`'s 2026-10-23
entry -- so it is used here as the representative example rather than
T2, which has the lowest observed error).

Regenerate it (or produce one for T1, T2, or any future record) with:

```bash
PYTHONPATH=src python3 -m windlens.insurance_report --target T3
```

Everything below this line is the generator's actual output, unedited.

**2026-10-24: rewritten as a genuine one-page, insurer-facing document**
(Anna: "the document should be one pager... that a company like BayWa
would literally send to an insurance company"). The previous version read
as an internal audit log (multiple sections, generation timestamps,
pipeline-version strings, "Data-quality checks performed"). This version
is what an operator would actually attach to a claim: a dateline, four
short sections (Summary / Estimated loss / Method / Confidence), no
internal metadata.

**2026-10-24, later: "nearby reference turbine" replaced with "behaviorally
selected reference turbine (geographic proximity not verified)"** in the
Summary and Method sections below, matching the fix in
`src/windlens/insurance_report.py` -- there is no farm-location registry
for this dataset, so the reference turbine is chosen purely on how well its
historical readings matched the target's, not on physical proximity, and
the report must not claim otherwise.

---

## Attached report

# WindLens -- Outage Loss Assessment: Turbine T3

Assessment date: 2026-10-23

## Summary

Turbine T3 was offline from 2026-09-01 to 2026-09-04. Based on wind conditions recorded by a behaviorally selected reference turbine (O1; geographic proximity not verified) during the same period, we estimate the turbine would have produced 112,411 kWh had it continued operating normally.

## Estimated loss

- Energy: 112,411 kWh (estimated range: 68,164 kWh to 156,659 kWh)
- Financial impact: EUR 9,555 (estimated range: EUR 5,794 to EUR 13,316), based on an illustrative energy price of 85 EUR/MWh -- to be replaced with the operator's actual contracted price.

## Method

We reconstruct the wind this turbine would have experienced using readings from a behaviorally selected reference turbine (O1; geographic proximity not verified) whose historical wind closely tracked this turbine's before the outage, then convert that wind into expected power using the turbine's own power curve. The reference turbine is chosen only from data available before the outage, never from the outage window itself.

## Confidence

This estimate's range reflects the largest error observed when validating this method against the other real targets in this dataset with comparable outages (3 targets, up to 39.4%); it is not a formal statistical confidence interval.

This is a decision-support estimate, not an independent power measurement or a settlement, contractual, regulatory, or legal determination.

---

## Accompanying email draft

Subject: Outage loss estimate -- Turbine T3, 2026-09-01 to 2026-09-04

Hello,

Please find attached the WindLens outage loss assessment for turbine T3, covering the data gap from 2026-09-01T00:00:00Z to 2026-09-04T00:00:00Z.

Estimated lost production: 112,411 kWh (68,164 kWh to 156,659 kWh as an observed-error range rather than a calibrated confidence interval -- see the attached report for how this range was built).
Illustrative financial impact: EUR 9,555 at a demo energy price -- not a verified PPA figure; please substitute your own confirmed price before relying on this number.

The attached one-page assessment sets out the method and the basis for the estimated range. Happy to walk through any part of it on a call.

Best regards,
