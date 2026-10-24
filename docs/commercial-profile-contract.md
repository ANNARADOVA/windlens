# Commercial profile contract

WindLens may calculate an **indicative commercial impact** after an analyst supplies a saved pricing profile. The profile is an input record, not a contract interpreter.

The dashboard should present profiles as named records, for example “Demo fixed-price offtake”, with an explicit source and effective date range. A profile can be entered through the form or imported from JSON/CSV. Excel can be supported as an import convenience, but the normalized saved form should be the JSON contract in `schemas/commercial_profile.schema.json`.

Required fields:

- `profile_id` and `display_name`;
- three-letter `currency`;
- `settlement_interval_minutes`;
- `price_basis`: `fixed` or `time_series`;
- `source` describing where the input came from.

Fixed profiles also require `fixed_price_eur_per_mwh`. Time-series profiles require timestamped `price_series` values. Optional fields capture effective dates, negative-price treatment, curtailment exclusions, and analyst notes.

The calculation is:

```text
estimated lost kWh / 1,000 × applicable price per MWh
= indicative value in the profile currency
```

The output must be labelled **indicative**. It cannot determine contractual settlement, Redispatch eligibility, force-majeure treatment, OEM liability, or legal damages. Those require verified contract, grid, metering, event, and human-review evidence.
