window.WINDLENS_EVIDENCE_TIERS = {
 "schema": "evidence-tiers.v1",
 "tiers": [
  {
   "tag": "Tier 1 / baseline",
   "name": "Same-farm single-turbine reconstruction",
   "headline_value": "6.8%",
   "headline_label": "weighted absolute percentage error (WAPE), Kelmarsh KWF1",
   "stats": [
    [
     "Back-test events",
     "19 blocks, 1 target"
    ],
    [
     "Reference distance",
     "0.27–0.75 km, same farm"
    ],
    [
     "Signed bias",
     "-6.2%"
    ],
    [
     "Reviewable",
     "11/19"
    ]
   ],
   "framing": "Today's demo: one turbine's data is hidden while every other turbine on the same farm keeps reporting as a reference.",
   "does_not_prove": "A whole-farm outage, where no same-farm turbine is left, or any neighbouring-farm reconstruction.",
   "source": "data/derived/validation/kelmarsh_extended_uncertainty_backtest.json"
  },
  {
   "tag": "Tier 2 / ceiling",
   "name": "Whole-site masking stress test",
   "headline_value": "8.8%",
   "headline_label": "average WAPE across the two site halves",
   "stats": [
    [
     "Events",
     "114 (19 time blocks x 6 turbines; not fully separate tests, since turbines on the same farm share conditions)"
    ],
    [
     "Reference distance",
     "271–935 m (mean 534 m)"
    ],
    [
     "Same targets+blocks, same-farm refs",
     "8.0%"
    ],
    [
     "Signed bias",
     "-4.0%"
    ]
   ],
   "framing": "whole-site masking stress test, ~300-400m reference separation — a best-case ceiling bound, NOT a neighbouring-farm validation. Uses external Kelmarsh data to validate the method on a different wind farm.",
   "does_not_prove": "Anything about farms in different places: all references sit within about 1 km on the same ridge.",
   "source": "data/derived/validation/kelmarsh_whole_site_masking_backtest.json"
  },
  {
   "tag": "Tier 3 / floor",
   "name": "Distant cross-farm backtest (external data: Kelmarsh vs. Penmanshiel)",
   "headline_value": "13.9%",
   "headline_label": "average WAPE across both directions (Kelmarsh↔Penmanshiel)",
   "stats": [
    [
     "Events",
     "143 (event-count-weighted)"
    ],
    [
     "Farm-to-farm distance",
     "~399 km"
    ],
    [
     "Kelmarsh ← Penmanshiel",
     "13.1% WAPE; 19 of 47 events pass review. (For comparison, same-farm reference turbines on the same targets and grid, but a different set of events, scored 9.0%.)"
    ],
    [
     "Penmanshiel ← Kelmarsh",
     "14.2% WAPE; 70 of 96 events pass review. (For comparison, same-farm reference turbines on the same targets and grid, but a different set of events, scored 6.2%.)"
    ]
   ],
   "framing": "real cross-farm backtest at ~399km separation (Kelmarsh, Northamptonshire vs. Penmanshiel, Scottish Borders) — a realistic-distance floor, using external data to validate the method on two other wind farms. The cross-asset test is the T1/T2/T3 BayWa record on the Result and Why to trust it pages, not this proxy.",
   "does_not_prove": "The real BayWa cross-asset case directly — this uses a different turbine model, hub height and terrain (see the T1/T2/T3 BayWa record for the real test).",
   "source": "data/derived/validation/kelmarsh_penmanshiel_crossfarm_backtest.json"
  }
 ],
 "other_findings": [
  {
   "tag": "Finding / same-farm",
   "name": "Simple average of nearby turbines (no fitting)",
   "headline_value": "5.67% / 5.86%",
   "headline_label": "WAPE, Kelmarsh / Hill of Towie (same-farm)",
   "stats": [
    [
     "vs. wind-first baseline",
     "10.04% / 13.88%"
    ],
    [
     "vs. wind-first blend (3 turbines)",
     "11.71% / 12.99%"
    ],
    [
     "vs. direct power",
     "6.34% / 6.98% (competitive)"
    ],
    [
     "Mechanism",
     "Plain average of the other same-farm turbines' output level — no fitting, no wind reconstruction"
    ]
   ],
   "framing": "At same-farm distance the simplest possible method — no wind reconstruction, no fit — beats every wind-first variant and is competitive with direct power.",
   "does_not_prove": "That the simple average wins regardless of distance — it does not (see the cross-farm reversal below).",
   "source": "data/derived/validation/lazy_baseline_comparison_2026_10_23.json"
  },
  {
   "tag": "Finding / cross-farm reversal",
   "name": "Simple average loses at real cross-farm distance",
   "headline_value": "22.30% / 19.09%",
   "headline_label": "WAPE, cross-farm simple average (both directions)",
   "stats": [
    [
     "vs. wind-first single-reference",
     "12.16% / 14.52% (wins clearly)"
    ],
    [
     "vs. wind-first blend (3 turbines)",
     "13.09% / 14.25% (wins clearly)"
    ],
    [
     "vs. direct power",
     "22.91–24.92% (the simple average is comparable, both collapse)"
    ],
    [
     "Mechanism",
     "Averages the OTHER farm's turbines — ignores farm-specific scaling, hub height, power curve, climate"
    ]
   ],
   "framing": "At ~399 km the naive average reverses and loses clearly to wind-first — the sophisticated method's physical reasoning earns its complexity specifically at real cross-farm distance, even though neither its own WAPE (13–14%) nor the simple average's (19–22%) is as good as same-farm.",
   "does_not_prove": "That wind-first's extra blended-turbine approach (using 3 turbines instead of 1) helps here — it doesn't (see Tier 1 above): single-reference ties or slightly beats the blend at this distance.",
   "source": "data/derived/validation/crossfarm_lazy_baseline_comparison_2026_10_23.json"
  },
  {
   "tag": "Finding / method comparison",
   "name": "Reference-selection weighting (behavior vs. geography)",
   "headline_value": "80% history / 20% distance",
   "headline_label": "weighting kept after testing three alternatives",
   "stats": [
    [
     "Alternatives tested",
     "100% history, 50/50 history/distance, 0% history (distance-only)"
    ],
    [
     "Result",
     "All four performed the same within statistical noise (their 95% confidence intervals overlap, on both farms)"
    ],
    [
     "Decision basis",
     "Principle (past behaviour is the directly-tested signal; distance is only a secondary plausibility check), not a numeric win"
    ]
   ],
   "framing": "The shipped weighting (80% how well a candidate turbine's past readings matched the target, 20% how close it is) performed as well as every alternative tested, including a 50/50 split and a distance-only split.",
   "does_not_prove": "That the 80/20 split is measurably better than 50/50 or 100% history-based at this sample size (n=10–14 dev blocks) — it is not.",
   "source": "data/derived/validation/reference_weighting_ablation_2026_10_23_report.json"
  }
 ],
 "scale": {
  "pins": [
   {
    "label": "Tier 1",
    "km": 0.5,
    "km_label": "~0.5 km"
   },
   {
    "label": "Tier 2",
    "km": 0.9,
    "km_label": "<1 km"
   },
   {
    "label": "Tier 3",
    "km": 399.1919040044003,
    "km_label": "~399 km"
   }
  ],
  "untested_gap": {
   "from_km": 2,
   "to_km": 100,
   "label": "pre-BayWa proxy gap — see the real BayWa result instead"
  }
 },
 "footnote": "Three different questions, three numbers — never averaged or presented as one. Tier 2 is a ceiling and Tier 3 a floor, both using external Kelmarsh/Penmanshiel data to validate the method on other wind farms. The cross-asset test is the T1/T2/T3 record on the Result and Why to trust it pages. Block selection favours windy, fully-reporting periods in all three tiers."
};
