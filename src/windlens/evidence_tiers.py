"""Single source of truth for the labels of WindLens's three evidence tiers.

Every place a tier's number appears (JSON artifacts, workspace UI, docs) must use
these exact strings, so a tier can never be quoted without its limitation attached.
Added 2026-10-23 together with the whole-site masking and Kelmarsh/Penmanshiel tests.
"""

from __future__ import annotations

TIER_SAME_FARM = "same-farm single-turbine reconstruction"
TIER_WHOLE_SITE = "whole-site masking stress test"
TIER_CROSS_FARM = "distant cross-farm backtest (Kelmarsh vs. Penmanshiel)"

# Agreed verbatim framing (Anna + prior session, 2026-10-23). Do not paraphrase.
WHOLE_SITE_FRAMING = (
    "whole-site masking stress test, ~300-400m reference separation "
    "— a best-case ceiling bound, NOT a neighbouring-farm validation."
)

CROSS_FARM_FRAMING = (
    "real cross-farm backtest at ~{distance_km:.0f}km separation (Kelmarsh, "
    "Northamptonshire vs. Penmanshiel, Scottish Borders) — a realistic-distance "
    "floor, NOT a neighbouring-farm validation: the challenge's actual neighbouring "
    "farm is expected to land between this and the whole-site ceiling."
)
