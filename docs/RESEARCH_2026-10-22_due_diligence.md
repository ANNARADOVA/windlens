# Due Diligence: Literature and Competitive Positioning (Deep Pass)

**Date:** 2026-10-22
**Author:** separate Claude Code session, dispatched specifically to redo the earlier
"2026-10-22 — RESEARCH: literature and market scan" entry in `docs/DECISION_LOG.md`
properly — that entry was explicitly web-search-only (no full paper reads, no vendor
pages fetched directly) and Anna asked for a real pass. This document supersedes that
entry's conclusions where they differ; it does not replace the independent calibration
audit (`docs/AUDIT_2026-10-22_uncertainty_calibration.md`), which remains the source of
truth on the two open methodology problems referenced throughout.

**One-line verdict:** split-conformal prediction is a real, well-evidenced fix for the
audit's Problem 1 (near-training-data calibration residuals) if implemented with a
genuinely held-out, time-disjoint calibration slice — and a very recent, more specialized
paper directly fixes Problem 2 (calibration-method selection bias) without new data
splitting — but neither guarantees the resulting coverage number will actually clear
90%, and the competitive-differentiation claim ("we show uncertainty, nobody else
visibly does") survives this closer look, with one real caveat: it is a claim about
public marketing pages, not about what vendors disclose privately to paying customers,
which this pass had no access to.

---

## Part 1 — Literature: does a known-good method exist for WindLens's calibration problem?

Five sources were read in depth (full text or near-full text extracted via the arXiv
HTML/PDF renderings, not abstracts alone), chosen to cover both the methodology side
(measure-correlate-predict + power-curve loss accounting) and the uncertainty side
(split-conformal prediction, its small-sample behavior, and its specific failure modes
under model selection and distribution shift).

### 1. Angelopoulos & Bates, "A Gentle Introduction to Conformal Prediction and
Distribution-Free Uncertainty Quantification" (arXiv 2107.07511, read in full)

**What it proposes:** split conformal prediction — fit a model on a training split,
score residuals on a *disjoint* calibration split, take the
⌈(n+1)(1-α)⌉-th smallest calibration residual as the interval half-width, apply it to
new predictions.

**What it guarantees:** Theorem 1 (citing Vovk, Gammerman & Saunders): if the
calibration points and the test point are exchangeable (i.i.d. is sufficient but not
required), then `P(Y_test ∈ C(X_test)) ≥ 1-α`, with a matching upper bound of
`1-α + 1/(n+1)`. This is a finite-sample, distribution-free guarantee — it holds for
any n, not just asymptotically.

**Sample-size guidance (their own words, not an outside inference):** "our conclusion
will be that choosing a calibration set of size n = 1000 is sufficient for most
purposes." They give exact numbers: to get the *conditional* coverage (coverage given
the specific calibration draw) within ±10 percentage points of the target with 90%
probability requires n ≈ 22 calibration points; within ±5 points needs n ≈ 102. Below
that, the distribution of achieved coverage (exactly `Beta(n+1-l, l)`, l = ⌊(n+1)α⌋) is
wide — this is the same phenomenon the parallel audit found empirically for "N/5" and
"N/3" block-pass-rate statistics, now with an exact closed form.

**Applicability to WindLens, stated plainly:** split conformal directly targets the
audit's Problem 1 — "calibration residuals should come from held-out, time-contiguous
validation blocks... never from the same observations used to fit the reconstruction"
is *exactly* the method this paper formalizes with a coverage guarantee attached, which
WindLens's own `uncertainty.py` docstring already states as a rule but the current
`_calibrate_and_evaluate_interval` violates in practice. Two conditions matter for
whether switching would actually work, and neither is free:

- **n is not WindLens's real bottleneck if applied correctly.** The guarantee is about
  per-observation calibration residuals, not per-block pass/fail counts. WindLens
  already has thousands of per-observation residuals available per block (the audit
  measured 1,463–8,132 "calibration" observations per Kelmarsh block) — comfortably
  above the n≈1000 the authors recommend, *if* a genuinely disjoint, temporally
  separate slice of that history is carved out and held back from fitting, rather than
  scored against (near-)the same window used to fit the model as happens today.
- **Exchangeability is the condition that actually has to be checked, not assumed.**
  The guarantee requires the calibration data and the test event to be exchangeable —
  informally, drawn from a comparable distribution. WindLens's calibration window is
  calm pre-event history; the test block is a specific 5-day outage-simulation window.
  If wind regime differs systematically between "typical calibration period" and
  "event period" (plausible for wind data — see the decision log's own finding that
  Kelmarsh's weakest blocks are explained by short calibration history, and Hill of
  Towie's by no single clean variable at all, consistent with regime effects that
  aren't fully characterized), the marginal coverage guarantee is still mathematically
  valid but may be *practically* uninformative for any individual event, which is a
  distinct problem from Problem 1 and not fixed by switching calibration methods alone.

### 2. Liang, Zhu & Barber, "Conformal prediction after data-dependent model selection"
(arXiv 2408.07066, read in full — most directly relevant source found)

**What it proposes:** a formal fix for exactly the audit's Problem 3 finding on
calibration-*method* selection. The paper's own framing of the problem it solves:
"If we use the same hold-out data set both to select a model... and then to construct
a conformal prediction set based on that selected model, we suffer a loss of coverage
due to selection bias." Their own "YK-baseline" (pick whichever of several candidate
conformal models scores narrowest/best on the same hold-out set, no correction) is a
close formal match for what WindLens's calibration-fix session did: four candidate
calibration variants (original buggy refit, fixed trailing windows, conditional
intervals, fit-once/score-on-full-history) were all scored against the same 5 Kelmarsh
blocks and the best-scoring one was shipped.

**What it guarantees:** two methods, `ModSel-CP` and `ModSel-CP-LOO`, both give a
finite-sample marginal coverage guarantee `P(Y ∈ C(X)) ≥ 1-α` under exchangeability —
*without* requiring the usual fix of splitting the data into a selection portion and a
separate calibration portion (which "comes at a steep cost if the size of the dataset
is limited," exactly WindLens's situation with 19–28 blocks). The mechanism: treat
model selection itself as part of the conformal procedure by including the
(hypothesized) test point in the selection criterion, which restores the symmetry
that split conformal needs for its proof to go through (full-conformal framework,
Theorem 3.1/3.3). They further show asymptotically optimal interval width under
regularity conditions (Theorem 4.2), and give a concrete bound (Eq. 8) for how much
uncoordinated selection among |Λ| candidate methods degrades coverage, as a function of
n and |Λ| — informally, with few candidates (WindLens had 4) and enough exchangeable
calibration points, the degradation is small; with the few, non-independent "blocks"
WindLens effectively used as its implicit n in the original comparison, the same bound
is not reassuring (the correction term stays large at n≈19–28), consistent with the
audit's qualitative concern.

**Honest caveats, stated plainly, not oversold:** this is a 2024 paper with an April
2026 revision — recent, and its own abstract says validation is "synthetic datasets in
various settings and a real data example" (singular) — the real-data validation is
thin, and I could not confirm from the available text what that one real dataset was
or whether it resembles wind/energy time series at all (**not verified**). It is also a
heavier engineering lift than plain split conformal: it requires reformulating the
"compare N calibration-method candidates" step as a formal model-selection-with-full-
conformal procedure, not just swapping a quantile calculation.

### 3. Moradi, Tanneau, Zandehshahvar & Van Hentenryck, "Enhanced Renewable Energy
Forecasting using Context-Aware Conformal Prediction" (arXiv 2510.15780, read in full)

**Scope, stated upfront because it limits applicability directly:** this paper
validates **solar only**. Wind is explicitly named as future work — there is no
published wind result in this paper at all. This directly answers (negatively) the
question of whether an off-the-shelf, wind-validated context-aware conformal method
already exists in the recent literature: it does not, at least not from this group.

**What it shows that is still useful:** at scale (1,149 NREL solar sites, hourly 2019
data, daily-updated calibration sets drawn from the preceding week), plain
conformalized quantile regression (CQR, no context-aware weighting) already lands close
to a 90% target at the site level in their Table III (ERCOT 90.10%, MISO 91.16%, SPP
89.28%) — meaning straightforward split-conformal-style methods *can* hit a 90% target
on renewable generation data, but with far more calibration data per site (effectively
continuous daily recalibration against a full week of history) than WindLens's
per-event, per-block setup provides. Their context-aware weighting mainly helps *within-
day conditional* coverage (Fig. 3/Table IV: slight over-coverage at peak hours, mild
under-coverage off-peak for plain CQR), not the headline marginal number.

**The paper's own statement that matters most for WindLens:** "conventional split CP
relies on the exchangeability assumption," which "is not valid in time series" without
adaptation — the same caveat flagged under source 1 above, now from a paper written
specifically for renewable-energy forecasting, reinforcing that this is a known,
named problem in this literature, not a WindLens-specific oversight.

### 4. Wind turbine hybrid physics+ML paper with conformalized quantile regression
(arXiv 2502.07344, read in full)

This is the closest published analogue to WindLens's own situation found in this pass:
a wind-turbine power-prediction model (four MM82 turbines, La Haute Borne, ~700k
10-minute records 2013–2020) wrapped with CQR (via the MAPIE library) to produce 5–95%
prediction intervals.

**Reported result:** "the coverage is 86%, and the prediction intervals have a mean
length of 49 kW," against an *implied* 90% target (the paper never states a target
coverage explicitly — inferred from the 5%/95% quantiles used; this inference is mine,
flagged as such). **This is a concrete, published example of a textbook-correct
conformal method still falling short of a 90% nominal target on real wind turbine
data** — direct evidence against assuming that switching WindLens to valid
split-conformal calibration would, by itself, close the gap from ~47–61%-of-blocks to
the 90%-of-blocks target Anna wants. It would make the reported number trustworthy; it
would not necessarily make the number big.

**A second, more uncomfortable parallel:** the paper's own calibration set is "half of
the test set" — a random (not stated as time-aware) split of 10-minute time-series data.
The paper does not state whether the split was done with temporal structure in mind, and
does not discuss the possibility of information leaking between adjacent 10-minute
calibration and evaluation points via autocorrelation. This is structurally similar
(though not identical) to the audit's Problem 1 finding for WindLens — a 2026 published
paper using the textbook-correct conformal recipe still has an unresolved, undiscussed
independence question of its own. This is useful context, not an excuse: it shows the
near-training-data concern is a live, easy-to-miss trap in this exact domain, not an
idiosyncratic WindLens bug.

### 5. Sheridan et al., "Loss Factors for Small Distributed Wind Turbines Based on Field
Data in the United States" (*Journal of Sustainability Research* 8(1):e260002, January
2026, DOI 10.20900/jsr20260002 — read via publisher's hosted abstract/results page,
full PDF not accessible from this environment)

This is the methodology-side match for Part 1(a): density-based filtering to identify
typical-performance periods, then regression-based measure-correlate-predict to
estimate counterfactual generation during atypical/unreported periods — converted to a
loss factor. 72 single-turbine distributed-wind projects, 2–8 years of data each,
validated with repeated 75/25 train/test splits (30 trials per project); best
configuration (neural network + bias-corrected HRRR reanalysis) gave a median
actual-to-predicted ratio of 99.9% (range 99.3–104.5% across all 2,160 trial results).
Median loss factor across projects: 17%, consistent with the 7–18% default range
current industry pre-construction tools use.

**Why this matters for WindLens specifically:** this is, as far as this pass found, the
most current (January 2026) peer-reviewed paper doing essentially WindLens's
methodology end-to-end — and it reports **no formal confidence intervals or calibrated
uncertainty quantification around its loss-factor estimates.** Its only uncertainty
treatment is the empirical spread across 30 repeated trials and the observed
year-to-year variability in the raw loss numbers (one project ranged from 5% to 96%
across eight years) — an informal resampling-based signal, not a coverage-guaranteed
interval. This independently confirms two things at once: WindLens's core
point-estimate methodology (MCP-style counterfactual + power-curve/power loss
accounting) matches current peer-reviewed practice, and attempting a *calibrated*
uncertainty interval at all — which is what WindLens is trying to do and currently
doing imperfectly — is ahead of, not behind, what this specific strand of the
literature is currently publishing.

### Part 1 answer to the brief's question

**Is there a known-good method for WindLens's specific calibration problem?** Yes, in
pieces, not as one off-the-shelf recipe:

- **For Problem 1** (residuals scored on near-training data): split conformal
  prediction (source 1) is the known-good, well-understood fix, provided it is applied
  with a genuinely held-out, time-disjoint calibration slice. This is a contained,
  well-documented engineering change — not a research risk.
- **For Problem 2** (calibration method picked by best-score-on-the-same-blocks): a
  real, recent, directly-matching method exists (source 2), but it is a heavier
  implementation lift with thin published real-data validation. A cheaper, non-paper-
  based interim fix — select the calibration method on a separate development slice of
  blocks, report the final number only on blocks never used for that selection — gets
  most of the same benefit without new machinery, and is what the parallel audit already
  suggested.
- **Neither fixes the actual coverage shortfall by itself.** Source 4's 86%-against-
  implied-90% result on real turbine data, using the textbook-correct method, is direct
  evidence that a correctly-calibrated interval on real wind data does not automatically
  reach 90%. The audit's own finding that Kelmarsh's shortfall traces to insufficient
  pre-event calibration history (not a fixable methodology bug) points the same way.

**Recommendation:** prototyping split-conformal (source 1's exact recipe) on a
genuinely time-disjoint calibration window is worth doing next — it is the
lowest-risk, best-evidenced single change available, and it directly answers the
audit's Problem 1. Treat it as a validity fix, not a coverage-number fix: budget for
the realistic possibility that honestly-computed coverage stays below 90% afterward,
because the literature's own closest analogue (source 4) landed at 86%, not above
target. The data-dependent-model-selection fix (source 2) is the theoretically correct
answer to Problem 2 but is a larger, less field-tested investment; the cheap
interim fix (separate development/report blocks) is the better use of limited budget
unless Anna specifically wants to prototype the newer method.

---

## Part 2 — Competitive positioning: what do comparable vendors actually show?

Six vendors named in the brief or found to be genuinely comparable (counterfactual
loss/performance-assessment tools for wind, not general SCADA/CMMS) were checked by
fetching their actual product and case-study pages directly, not search snippets. Two
named vendors turned out not to be comparable at all, reported below as such rather
than silently dropped.

| Vendor | What they claim | Public metrics shown | Uncertainty/confidence/validation disclosed? | Target customer | Independent validation found? |
|---|---|---|---|---|---|
| **Delfos Energy** | Energy Losses module: waterfall comparing expected vs. measured production, IEC 61400-based manageable/unmanageable loss split, monetization of losses | Platform-wide banner claim "up to 10% revenue recovered, 18% downtime cut" (not tied specifically to the loss module); 18% downtime reduction cited for one named customer (V2i Energia) | **None found.** No confidence intervals, error margins, or methodology disclosed for how "expected production" is modeled | Asset managers, O&M leads, portfolio managers | None — ISO 27001 (security) and trade-association memberships only, neither validates analytical accuracy |
| **Clir Renewables** | Derate Detector: AI-based detection and quantification of derate-driven losses; peer-group loss benchmarking across global project data | "1,300 MWh recovered through a 50% reduction in derate losses"; portfolio-level "6+ GWh in recoverable energy" | **None found.** No baseline, time period, turbine count, or calculation method disclosed for the headline figures | Asset owners/managers, investment managers, corporate offtakers | None — "validated upgrades" mentioned with no named validator or method |
| **DNV WindGEMINI** (now folded into GreenPowerMonitor's "GPM Horizon Gemini" — the original WindGEMINI product pages and FAQ now redirect there, a real finding in itself about market consolidation, not an assumption) | Digital-twin power-curve watchdog; case study: caught a pitch-control fault worth ~$10,000/month (>$100,000/yr) in lost revenue at one turbine | Revenue-loss figure only; no kWh/MWh recovered figure found; "used at 33+ wind farms, 3 GW" (2020 release) | **None found** on the live pages reachable from this pass (the original FAQ page, which might have held methodology detail, now 301-redirects to the GreenPowerMonitor homepage, which itself discloses nothing) | Asset owners, O&M, EPC | None found |
| **3E SynaptiQ (Wind Analytics)** | IEC-guideline-based power-curve verification using high-frequency data; business-plan verification, outage management, anomaly detection | Only quantified claim found is a 2011 launch-era vendor projection of "2–5% yield increase" — outdated, pre-dates the current product | **None found** | Not clearly stated on pages reached; likely asset owners/O&M given product framing | None found |
| **WindESCo (now rebranded "PulseSense")** | "Detect and address hidden wind turbine underperformance" using high-resolution turbine data beyond conventional SCADA analytics; separately, Swarm (wake-steering) | **None** — no public numbers found on the current PulseSense pages at all (prior WindESCo material cited "1–2% Annual Energy Improvement," not independently confirmed here) | **None found** | Wind and hydro owners/operators | None found |
| **Modo Energy** — *named in `WindLens_instructions.md` §11 as a design/positioning benchmark, confirmed here to be a different product category, not a technical competitor* | Market-wide revenue benchmarking and forecasting indices across battery storage, solar, wind, data centers; wind is explicitly a minor, under-described part of the platform per their own help documentation | None found specific to wind; indices are described as "certified by the Financial Conduct Authority (FCA) and IOSCO" for their *methodology governance*, not an accuracy/uncertainty claim | Partial — FCA/IOSCO certification is a real, named, independently-auditable governance signal, but it certifies *methodology transparency/reproducibility*, not a confidence interval on any specific number | Investors, lenders, boards, developers reviewing business cases | **Yes, in a narrow sense** — FCA/IOSCO oversight is genuine third-party governance, the only such signal found across all vendors checked — but it does not extend to counterfactual outage-loss estimation, which Modo does not appear to do at all |

**Two named vendors ruled out as not comparable, reported honestly rather than
stretched to fit:**

- **OxMaint** — checked directly. This is a general CMMS/predictive-maintenance
  platform (manufacturing, facilities, healthcare, food & beverage, etc.), not a
  wind-specific counterfactual-loss tool. It lists a generic "Power Plant Management"
  industry link with no wind-loss content, and its quantified claims (94% AI
  prediction accuracy, 99.2% detection accuracy, 99.9% accuracy) are platform-wide
  marketing figures unrelated to counterfactual wind-energy-loss estimation, with zero
  uncertainty disclosure of their own. **Not a genuine comparator for WindLens**; the
  earlier shallow pass's inclusion of it alongside Delfos/Clir/DNV was not supported by
  what the product actually is.
- **"WPO"** — **not found.** No company matching this name was identified in the
  counterfactual wind-loss space after a direct search. This may refer to a vendor
  under a different name, an internal/non-public tool, or a misremembered acronym —
  reporting as not found rather than guessing.

### Does the "we show honest uncertainty, nobody else visibly does" claim hold up?

**Mostly yes, with the scope tightened.** Across the five genuinely comparable vendors
whose actual product/case-study pages were fetched directly (Delfos, Clir, DNV
WindGEMINI/GreenPowerMonitor, 3E SynaptiQ, WindESCo/PulseSense), **none disclosed any
uncertainty, confidence interval, or accuracy-validation information alongside their
headline performance claims**, on the specific public pages reached in this pass. This
is now evidence from the vendors' own pages, not a search-snippet inference — a
materially stronger basis than the prior shallow pass had.

The claim needs tightening in two specific ways, not walking back:

1. **Scope it to public marketing/case-study pages.** This pass had no access to any
   vendor's private technical documentation, SLAs, or sales-engineering material that
   might be shared under NDA with paying customers. "No vendor discloses uncertainty
   publicly" is verified; "no vendor has any internal validation rigor" is not, and the
   claim should not imply the latter.
2. **Modo Energy is a different category, not a weaker version of the same claim.**
   It has a real, named, independently-auditable governance signal (FCA/IOSCO
   certification) that none of the counterfactual-loss vendors have — but that signal
   covers market-index methodology, not outage-loss-estimation accuracy, and Modo does
   not appear to do counterfactual outage-loss estimation at all. Comparing WindLens to
   Modo on "who shows uncertainty" is comparing different products; comparing WindLens
   to Modo on presentation/trust-signaling style (as §11 already frames it) remains a
   fair and useful comparison.

---

## Not verified / could not confirm

- **Source 2's real-data validation.** Liang/Zhu/Barber's paper states its empirical
  validation is "synthetic datasets... and a real data example" (singular); the
  identity and domain of that one real dataset could not be confirmed from the text
  available in this pass.
- **Exhaustiveness of the vendor scan.** Six named/likely vendors were checked; this is
  not an exhaustive market scan of every counterfactual-loss tool for wind. Several
  fetch attempts hit redirects, 403s, or truncated/JS-rendered content (DNV's original
  FAQ page, 3E's wind-specific case studies, PulseSense's Technology/Resources
  sections) — content behind those barriers was not reached and could contain
  uncertainty disclosures this pass missed.
- **Private/paywalled vendor material.** As stated above, no vendor's internal
  validation reports, customer-only technical specs, or NDA'd accuracy data were
  accessible; "not found" for uncertainty disclosure applies only to public pages.
- **Whether split-conformal, once correctly implemented on WindLens's data, would
  actually clear 90% coverage.** Not tested in this pass (no code was touched, per the
  brief's guardrails) — source 4's 86%-against-90% result is evidence this is not a
  safe assumption, not proof either way for WindLens's own data.
- **The DNV WindGEMINI → GreenPowerMonitor relationship.** The redirect is real and
  directly observed, but whether "GPM Horizon Gemini" is a renamed continuation of the
  same product or a related-but-distinct offering was not confirmed from the pages
  reached.

---

**Guardrails followed:** no code changed, no `.py` files or `workspace/`/data files
touched, no git command run (not a git repository). Only new file is this one. All
numeric/factual claims above are cited to the specific source fetched; passages
extracted via automated tooling (arXiv HTML/PDF renderings, WebFetch page summaries)
are reported as such, not re-verified character-by-character against the original —
treat direct quotes as faithful paraphrase-with-quotation rather than a hand-checked
transcription.
