# Bonus: automatic turbine selection from a pool

The challenge's stretch goal of automatically choosing a reference turbine
from a pool of candidates -- rather than requiring a person to manually pick
one -- is already fully solved in this codebase by
`select_dynamic_references()` in
[`src/windlens/dynamic_reference.py`](../src/windlens/dynamic_reference.py).
Given a target turbine, a list of candidate turbines, and their coordinates,
it automatically ranks every candidate by out-of-sample prediction accuracy
(a time-ordered holdout fit on historical wind speed, never on the outage
window itself) blended with geographic proximity, and returns a ranked list
plus a top-k ensemble with inverse-error weights -- with no manual turbine
choice required at any step. If no candidate clears the minimum data and
distance requirements, it returns `status="abstain"` rather than guessing.

This is the same selection logic already used in production: the simpler
single-reference BayWa pipeline (`src/windlens/reconstruct.py`'s
`select_reference_turbine`) is a leaner, single-criterion version of the same
idea, and `select_dynamic_references` is the full behaviour-plus-geography
version that the rest of the project's cross-farm and ensemble work builds
on. Whoever writes the final submission text can cite
`select_dynamic_references` in `src/windlens/dynamic_reference.py` directly
as the automatic-turbine-selection bonus deliverable -- no new code was
needed for this session's task, only this note confirming it.
