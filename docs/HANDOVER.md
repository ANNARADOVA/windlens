# WindLens handover

**2026-10-24 (latest+14, read first): Follow-up round on the IA rebuild --
further-trimmed other-datasets mention, root README.md rewritten for the real
submission, a second real correctness gap fixed (power curves in multi-target
uploads), and multi-target Result UI built. In priority order from the
coordinator: (1) the "Other validation approaches we considered" copy cut
further per Anna's exact words -- no WAPE numbers, no tier-ceiling language,
folded into "What we'd build next" as one forward-looking bullet (not a
dedicated section); root `README.md` fully rewritten (it predated the real
BayWa data arriving and was entirely about the Kelmarsh/Penmanshiel/Hill-of-
Towie proxy-farm study, 19 mentions, with no mention of the real T1/T2/T3
submission at all -- now centers the real submission, with proxy-farm work
cut to one line under "Future opportunities"; `docs/` files referenced but not
featured). (2) README test count and the two-page Result/Methodology structure
updated. (3) A second real correctness gap, found by Anna asking how a whole-
farm-down upload (several targets at once) handles power curves:
`baywa_tool_server.py` was silently applying whichever power-curve file was
uploaded FIRST to every target, regardless of which turbine it actually
belonged to -- wrong kWh for every target after the first, no error. Fixed
with `_find_power_curve_for_target()` in `upload_tool.py` (filename-pattern
matching, e.g. `T2_power_curve.xlsx` -> T2), wired through `run_pipeline`'s
new `power_curve_items` parameter; a target with no matching curve gets an
explicit per-target `estimated_lost_kwh_unavailable_reason` ("No power curve
uploaded for T1...") rather than someone else's curve. (4) Multi-target Result
UI: a summary row per target renders immediately (turbine id, window, kWh or
why not), with the existing single-target detail view below switched by
clicking a row; single-target uploads are unaffected (summary stays hidden).
Also added: explicit "what to upload" requirements copy on the upload form,
and an honest note that auto-detection only finds a turbine's single longest
gap (a known, undeferred limitation -- manual-window fields are the stated
workaround for a second gap). 191/191 tests pass (2 more: per-target
power-curve matching and its no-match-named-reason case), all three check
scripts clean, live-verified in a fresh browser tab with zero console errors
on both routes, plus a real end-to-end multi-target `/run` round-trip
(T1+T3, their own O1/O2 references, their own power curves) confirming each
target got its OWN curve (T1: 118,373 kWh: T3: 112,411 kWh -- matching the
official record exactly, not swapped) and the summary-row click-to-switch
behavior. Full story in `docs/DECISION_LOG.md`'s matching 2026-10-24
"(latest+9)" entry.**

**2026-10-24 (latest+13): IA rebuild -- two pages, not four. Result
(`#overview`) now leads with the upload form, with the live BayWa T3 record
shown by default below it (not an empty page); submitting a live run replaces
that same view in place via a shared `buildResultViewModel()`/`renderResultView()`
pair that normalizes either the official record or an uploaded target entry into
one shape, so a live run is never a lesser, separate result area. The reference
chart is new: target's own actual readings overlaid with the selected
reference's, with the outage window shaded -- not the old reconstructed-vs-truth
chart (that one moved to Methodology, unchanged, as the self-validation chart).
A real correctness gap Anna flagged is fixed at its source
(`reconstruct.py::select_reference_turbine`): the top-ranked reference by
historical fit is no longer used blindly if it has zero readings during the
actual outage window -- it now falls back to the next-best covered candidate
and surfaces this plainly (`reference_fallback_note`), wired into both the
official-record generator and the upload tool. Methodology (`#method`) merges
the old Analysis + How-it-works + report-actions pages, framed as "play around
with the behavioural analysis": the editable price (unchanged logic) now lives
only here and live-updates Result's read-only financial summary too; the
extensive Kelmarsh/Penmanshiel/Hill-of-Towie evidence-tiers section no longer
renders in the jury-facing demo (condensed to one paragraph + one stat under
"Other validation approaches we considered" -- underlying data/scripts
untouched). "Send an email" is now a real `mailto:` link built from the
existing server-side `email_draft` (opens the user's own mail client,
prefilled; no SMTP, nothing sent from the server) -- replaces the old
"download .txt" behaviour for that action. 189/189 tests pass (3 new: the
reference-coverage fallback, its no-fallback-needed case, and the upload
overlay-series shape), all three check scripts clean, verified live via a
real browser session against the running server plus a real end-to-end
`/run` round-trip against BayWa's own linked sample files (T2+O1+power
curve): reference O1 selected, 100% coverage, in-domain, 10-min cadence,
432-point overlay series with the gap and shading rendering correctly, and
the unified result view correctly swapping into "YOUR LIVE RUN" mode and
back. Full story in `docs/DECISION_LOG.md`'s matching 2026-10-24
"(latest+8)" entry.**

**2026-10-24 (latest+12): P2 round -- nav tabs relabeled to signal
sequence (Result / Why to trust it / How it works / Run your own data), the
Upload tool's result now carries the same evidence fields as the official
record (reference coverage %, wind-speed domain check, inferred cadence, a
"not validated against ground truth" notice), the upload page reordered
task-first with a new pre-run file-role confirmation summary (`/preview`
endpoint), an analyst checklist added under the Overview's "Next action", two
remaining ambiguous labels fixed, and the EUR commercial figure visually
demoted relative to the kWh headline. 186/186 tests pass, all three check
scripts clean, live-verified fresh across all four routes AND a second
real-sample-file regression caught and fixed (the file-role preview initially
mislabeled the real reference turbine's file as a "target" because of a
too-naive NaN check -- fixed to match the real pipeline's own
MIN_OUTAGE_RUN_LENGTH threshold).**

Full story in `docs/DECISION_LOG.md`'s matching 2026-10-24 "(latest+7)" entry
-- this block is the short version.

- **Category 7:** sidebar nav relabeled (routes/hashes unchanged); every
  in-copy reference to a tab by its old name ("Real BayWa r.e. submission",
  "Overview and Analysis pages") updated to match, across `app.js`,
  `index.html`, and 7 occurrences spread across the two hand-assembled data
  files (`assessment-data.js`, `evidence-tiers-data.js`).
- **Category 8:** `run_pipeline()` now returns `reference_coverage_pct`,
  `domain_check` (reusing the SAME `reference_within_training_domain()` the
  official record's gate uses), unconditional `inferred_cadence_minutes`, and
  a `raw_reconstruction_notice` -- all rendered in the Upload result UI. The
  upload page is now task-first (schema detail moved into a collapsed "File
  format details" section). New `/preview` endpoint + `describe_uploaded_files()`
  give a pre-run per-file role guess, wired to the file input's `change` event.
  **Bug caught by live-testing this round's own change:** the first version of
  `describe_uploaded_files()` flagged any file with any NaN as a "target",
  which mislabeled the real sample reference file (O1 has isolated single-row
  NaN readings elsewhere, below the real pipeline's 3-row-run threshold for
  counting as an outage) -- fixed to reuse `detect_target_turbines()`'s own
  `MIN_OUTAGE_RUN_LENGTH` logic; re-verified against the real sample files.
- **Category 9:** a 4-item "Before acting on this estimate" checklist added
  inside the Overview's existing "Next action" panel (no new hero-area
  section).
- **Category 10:** the Analysis page's hidden-window card now shows
  "Prediction window points: 432" alongside the shown-window card's
  "Training-history points compared: 864" (symmetric, unambiguous); "Tested
  wind-speed range" gained a qualifying note about what it does NOT check.
- **Category 11:** the EUR commercial figure's styling changed from 28px in
  the warning/accent color to 21px in plain body-text color -- still shown,
  just no longer visually competing with the kWh headline.

---

**2026-10-24 (latest+11): second independent-review (Codex) round
-- six copy/presentation-wording categories fixed, hidden/shown-window
visual separation redesigned on the Analysis page, inferred upload cadence
surfaced in the UI, README command fixed, and a live-verification-caught
cadence-inference regression fixed (the previous round's fix broke the
Upload tool's own linked sample files -- 1 of 12,959 gaps was irregular and
the old code rejected on ANY irregular gap; now tolerates up to 2% of gaps
being irregular before rejecting). 183/183 tests pass, all three check
scripts clean, live-verified fresh across all four routes AND via a direct
`curl` POST against the real sample files (not just unit tests, for the
first time this round -- this is what caught the regression).**

Full story in `docs/DECISION_LOG.md`'s matching 2026-10-24 "(latest+6)"
entry -- this block is the short version.

- **Category 1 (stale copy):** `app.js`'s per-target Overview-selection
  framing text still described the pre-swap Overview (shown-window median
  drove the headline). Fixed, AND a second independent copy of the same
  stale text was found in `assessment-data.js`'s `baywa_comparison.intro`
  field during this round's own live verification (not caught by the
  original grep audit -- different field, same wording).
- **Category 2 (calibration-implying wording):** "Confidence range" card ->
  "Uncertainty status"; "...matches the validated estimate" -> "...matches
  the calculated prediction" (loss-chart caption); "...supports confidence
  in this method" -> "...provides an accuracy check for this method" (fixed
  in both the dead `app.js` string and the live `assessment-data.js`
  `next_action` field that actually renders).
- **Category 3 (BayWa-scenario overclaim):** "Real BayWa r.e. submission" ->
  "BayWa challenge-data prediction" (3 places); "Real cross-park test" /
  "cross-park case" -> "cross-asset test" / "cross-asset case" (3 places in
  `evidence-tiers-data.js`); "Naive averaging of nearby turbines" -> "Naive
  averaging of other turbines in the uploaded dataset"; Analysis heading
  "What happened during the outage" -> "What the model estimates during the
  gap".
- **Category 4 (hidden/shown-window separation, the highest-leverage fix):**
  the Analysis page's "Reference integrity" card mixed a shown-window metric
  (864 matched points) with hidden-window metrics (domain/alignment checks
  on the 432-reading gap) in one unlabeled card. Restructured into two
  headed `.window-group` sections ("Hidden-window prediction -- the graded
  record" / "Separate self-validation -- shown window, 04-10 Sept"); moved
  the 864-count field into the correct section. Added one new explanatory
  line under the Overview's hero kWh number stating the
  hidden/shown-window distinction with live data. Made the "not evaluated"
  gate visually pop (amber highlight box, contrast-checked by hand).
- **Category 5:** `upload_tool.py` already computed the inferred cadence but
  discarded it -- now returned as `inferred_cadence_minutes` and shown in
  the Upload tool's result UI.
- **Category 6:** `workspace/README.md`'s live-server command used plain
  `python3` (which lacks numpy on this machine) while two lines above it
  used the project's venv path -- fixed to match; also fixed the identical
  root-cause break in the top-level `README.md`'s own run commands.
- **The regression:** confirmed by POSTing the real sample files
  (`T2_data.xlsx` + `O1_data.xlsx` + `T2_power_curve.xlsx`, the Upload tab's
  own linked downloads) to the running server's `/run` endpoint -- got
  `ValueError: ... 1 of 12959 gaps differ from it by more than 5%`, i.e. the
  demo's own documented path was completely broken. Fixed with a new
  `IRREGULAR_CADENCE_MAX_FRACTION = 0.02` tolerance in
  `loss_estimate.py::infer_interval_hours()` -- still rejects genuinely
  irregular cadence (>2% of gaps bad) but no longer rejects a single
  one-off gap in thousands. Re-verified the same curl request after the fix:
  `estimated_lost_kwh: 133507.17`, `inferred_cadence_minutes: 10.0`.

---

**2026-10-24 (latest+10): independent-review 7-item fix batch --
Overview's primary record swapped to the hidden-window prediction (fixing a
direct contradiction with the insurance report), methodology text now
matches the variance-ratio code, manual-override upload bug fixed at root
cause, hardcoded 10-minute integration cadence replaced with inference from
the data, "nearby"-reference wording fixed, EUR false-precision rounded,
README test count corrected. 182/182 tests pass, all three check scripts
clean, live-verified fresh across all four routes.**

Full story in `docs/DECISION_LOG.md`'s matching 2026-10-24 "(latest+5)"
entry -- this block is the short version.

- **Overview/Analysis contradiction fixed by aligning Overview to the
  insurance report's number, not the reverse.** Both showed T3, but
  Overview's headline was the shown-window self-validation (285,766 kWh,
  04-10 Sept, a real-wind check), while the insurance report used the
  hidden-window prediction (112,411 kWh, 01-04 Sept, no ground truth by
  construction -- the actual graded deliverable). Swapped Overview's primary
  record to the hidden-window number; the shown-window validation moved to
  a labelled "How we validated this method" role on Analysis, not deleted.
  `assessment-data.js` rewritten (incident window, `estimated_lost_kwh`,
  `kwh_interval` bracket -- now exactly matches the insurance report's
  "68,164 - 156,659 kWh" -- gates, `next_action`, `limitations[]`, and the
  chart's `series` data, which now has no `truth_ms` field at all).
  `app.js`'s `renderChart` made genuinely truth-optional (hides the
  truth-toggle/legend entirely, not just by default, and no longer tries a
  NaN-producing `fmt(point.truth_ms, 2)`); `renderAnalysisNarrative`
  rewritten to state the hidden-window prediction plainly, then cite the
  shown-window percentages separately as supporting evidence, not as if
  they validated the new number. Fixed a newly-spotted hardcoded "5 days"
  window-duration string (now computed from the actual incident dates --
  would have silently been wrong for the new 3-day window).
- **Methodology formula caption rewritten to match the code.** It claimed
  unqualified "least-squares regression"; the actual reconstruction code
  (`fit_linear(..., method="variance_ratio")`) matches the target's own
  variance instead (least-squares is only used for holdout-R² reference
  ranking, a deliberate fix per the 2026-10-22 red-team review's F7
  finding -- OLS under-predicts energy through a power curve). Fixed the
  copy, not the code.
- **Manual outage-window override bug fixed at the root cause.**
  `upload_tool.py`'s `run_pipeline()` called `detect_target_turbines()`
  unconditionally and raised before it could ever reach the manual-window
  branch, so a manual override could never rescue a turbine with no NaN
  gap. Restructured to branch on manual-window presence first; new
  `_targets_missing_in_window()` + 5 new tests in
  `tests/test_upload_tool.py`.
- **Hardcoded 10-minute integration cadence replaced.**
  `loss_estimate.py`'s `integrate_energy_kwh()` silently assumed the
  canonical research dataset's 10-minute spacing for *every* caller,
  including live uploads -- an hourly upload would have silently produced
  a 6x energy error. Added an `interval_hours` parameter (default
  unchanged, so the ~13 internal research-script callers are unaffected)
  and a new `infer_interval_hours()` that computes the median gap between
  consecutive timestamps and raises on >5% irregular spacing.
  `upload_tool.py` now infers cadence from the selected reference
  turbine's own full timestamp series before integrating. New test
  confirms an hourly-cadence synthetic upload gives ~400 kWh, not the
  ~66.7 kWh the old hardcoded assumption would have silently given.
- **"Nearby"/"neighbouring reference turbine" wording fixed** everywhere it
  claimed unverified geographic proximity (no farm-location registry exists
  for this dataset): `app.js`'s upload-results card, and
  `insurance_report.py`'s Summary + Method sections (regenerated
  `docs/EXAMPLE_INSURANCE_REPORT_T3.md` to match). Review-status label
  "Reviewed -- all applicable checks passed" (contradictory next to a
  visible "1 not evaluated") changed to "Evidence checks passed;
  uncertainty not calibrated." Overview's EUR figure rounded from
  `fmt(value, 2)` ("EUR 9,554.95", false precision) to `fmt(value, 0)`
  ("EUR 9,555"), matching the bracket beside it. README's stale "163
  tests, 153 pass" corrected to "182 tests, 182 pass" (two locations) --
  `openpyxl` is now installed, the prior 10 failures no longer apply.
- **Incidental fix while running `check_demo_copy.py` this round:** an
  unused, never-rendered `schema_version` JSON field in
  `assessment-data.js` (present before this round, previously left as a
  known non-rendered exception) was deleted outright rather than kept as a
  standing exception, since it had no callers anywhere in `app.js`.
- **Verification:** 182/182 tests pass (17 new: 5 in
  `test_upload_tool.py` for the manual-override fix + 1 cadence-integration
  regression test, 7 in `test_loss_estimate.py` for
  `infer_interval_hours`/the new `integrate_energy_kwh` parameter). `node
  --check workspace/assessment-data.js` clean. `check_demo_copy.py`,
  `check_contrast.py`, `check_dead_controls.py` all clean. Live-verified on
  a fresh server restart + fresh-tab reload across Overview, Analysis,
  Methodology, Upload: zero console errors on any route; Overview headline
  confirmed reading 112,411 kWh / 01-04 Sept / the corrected review label /
  the "no ground truth" caveat; Analysis's T1/T2/T3 cards confirmed
  correctly separating hidden-window predictions from shown-window
  validation percentages with no contradiction; EUR figure confirmed
  rendering without cents post-fix. The Upload tool's live file-picker flow
  could not be driven through the browser tool (file-input `.value` is not
  settable via JS/CDP there), so the manual-override and
  cadence-inference fixes are verified by the new unit tests plus a direct
  `run_pipeline()` call, not by an in-browser file upload.

---

**2026-10-24 (latest+9): ran `scripts/check_demo_copy.py` and
fixed every real hit, rewrote the insurance report as a genuine one-pager,
fixed the PDF filename bug, raised body-text size, fixed one real contrast
failure, and two small jargon/badge cleanups.**

- **`scripts/check_demo_copy.py`** (new, from the coordinating session) found
  6 real hits; fixed 5, confirmed the 6th is a non-rendered internal field:
  - `app.js`: `'One of the three real BayWa targets tested tonight.'` --
    "tonight" revealed the build timeline to a jury; now "...in this
    assessment."
  - `app.js` + `index.html`: two "fabricat(e/ing)" instances (the same
    self-narrating-honesty pattern fixed elsewhere today) -- reworded as
    plain statements.
  - `assessment-data.js`: the commercial-profile note said "this demo" (now
    "Illustrative price only...") -- this one *is* rendered (on Overview's
    commercial-impact panel), unlike the `schema_version` hit.
  - `schema_version` **confirmed non-rendered** -- grepped `app.js`/
    `index.html`, it has no output call site; it's a JSON key in the data
    file only. Left as-is per the script's own stated exception.
  - `docs/EXAMPLE_INSURANCE_REPORT_T3.md`'s "pipeline version" -- fixed by
    regenerating the whole file from the rewritten report below.
- **Insurance report rewritten as a genuine one-page insurer-facing
  document** (Anna: "a company like BayWa would literally send to an
  insurance company"), not an internal audit log. Old: multi-section
  markdown with a generation timestamp, "pipeline version" string, "Data-
  quality checks performed." New: `# WindLens -- Outage Loss Assessment:
  Turbine T3` / dateline / Summary / Estimated loss / Method / Confidence --
  211 words, genuinely one page, no internal metadata. Two tests
  (`test_report_without_commercial_profile_omits_financial_section`,
  `test_report_states_uncertainty_was_not_calibrated`) updated to match the
  new wording, not just deleted. `docs/EXAMPLE_INSURANCE_REPORT_T3.md`
  regenerated from the real new output.
- **PDF filename bug fixed.** Anna's downloaded file was literally named
  "Claude" -- some browsers take the print-to-PDF filename from the *top*
  page's title, not the printed iframe's own `<title>`. Now sets
  `document.title` to `WindLens Insurance Report - T3` right before
  printing and restores it after, rather than relying on the iframe title
  alone.
- **Font sizes raised** (coordinating session: "16px+ body text as a
  floor"): base body 15px->16px; `.topbar-summary` (the subtitle under
  every page heading) 12px->15px; `.small-note`/`.plain-note` 12-13px->14px;
  `.gate-reason`, `.tier-frame` 13px->14px; `.considered-box`, `.plain-list`
  14px->15px; `.upload-hint` 12px->13px. Left small-caps UI *labels*
  (eyebrows, table headers, chart controls -- all-caps mono-font tags, a
  deliberate design convention, not reading prose) untouched; bumping those
  to 16px would blow up the "evidence terminal" aesthetic without
  addressing the actual complaint (sentences being too small to read).
- **WCAG AA contrast actually computed**, not eyeballed, for every real
  color pair in the palette (relative-luminance formula, not "looks fine").
  Found one real failure: `--signal` (#d57641) as *text* color is 2.90:1
  on the cream background (fails both the 4.5:1 text and 3:1 non-text
  thresholds) -- but grepping every use showed it's used as a border color
  everywhere except one spot, the disclosure's "+"/"-" expand icon, which
  is now `--signal-dark` (5.24:1, passes). Everything else checked (ink,
  muted, signal-dark, sage, the navy-hero light-text pairs) already passes
  AA.
- Oliver Wyman/Marsh writing-style skill invoked as asked, but it turned
  out to be a corporate copy-style guide (naming conventions, number/date
  formatting, punctuation) with nothing about font size or color contrast,
  and its Marsh-specific branding rules (e.g. "colleagues" not
  "employees", "Oliver Wyman" spelled out) don't apply to a non-Marsh
  project -- not misapplied here. Font-size and contrast were handled
  directly as the CSS/accessibility work they actually are.
- "Holdout R²" jargon on the Upload results card reworded to "Checked
  against N nearby turbine(s)' historical readings" (left as-is inside the
  Analysis page's "More detail" disclosure, where it's appropriate
  technical-reader content, not the primary view).
- The floating "indicative demo price" pill badge next to the commercial-
  impact EUR figure folded into the single disclaimer line below it, so it
  reads as one deliberate caption instead of two overlapping ones.

**170/170 tests pass.** `node --check`/`py_compile` clean, HTML balance/
duplicate-id checks clean, `check_demo_copy.py` clean except the one
confirmed-non-rendered field. Verified live: screenshotted Overview with
the new font sizes and the merged commercial disclaimer; re-ran the full
Upload flow end-to-end and confirmed the new reference-ranking wording in
the real rendered result; zero console errors throughout.

**2026-10-24 (latest+8, read first): found and fixed a real silent-failure
bug (PDF download), deleted two redundant Analysis panels, archived the old
deck's code for reference, tightened the insurance report.**

- **Methodology's "Download PDF" button removed entirely** (Anna: "we do not
  need the button"). Its full HTML/JS source is archived in
  `docs/archived_methodology_deck.md` for reference, alongside the deck
  carousel's own source (also archived there, from when it was deleted) --
  neither is wired into the live site.
- **Real bug found and fixed: the insurance report's "Download report
  (PDF)" button silently did nothing.** Root cause: it used
  `window.open('', '_blank')`, which real browsers' popup blockers often
  block silently with no visible error -- exactly the "button does nothing"
  failure mode this whole project has been hunting all day, just in a spot
  no one had clicked yet. Fixed by switching to a same-page hidden
  `<iframe>` + `iframe.contentWindow.print()`, which cannot be popup-blocked
  since no new window/tab is ever opened. Verified live: a real click now
  blocks the tab with the browser's own print dialog (confirmed via the
  automation tooling itself hanging on a native modal, and zero console
  errors) -- the old version produced neither of those.
- **Deleted two redundant panels from Analysis's "More detail" disclosure**
  (Anna: "could even be deleted" / "is this clear... does this belong"):
  the standalone "Farm metadata evidence" panel (its one fact -- no
  farm-location registry exists for this dataset -- was already stated in
  the T1/T2/T3 intro paragraph right above it) and the "Evidence Register"
  table (Reference integrity, Confidence-range check and Review gate are
  all already shown, with more context, in the three-column panel and the
  Overview page). Removed the HTML, the two render functions/call sites in
  `app.js`, and updated `tests/test_workspace_registry_evidence.py` to
  assert the panel's one surviving fact (now just the intro-paragraph
  sentence) instead of the deleted panel's markup.
- Fixed the cramped `chart-foot` spacing on the reconstructed-wind chart
  (two caption lines were sitting too close together) with proper
  wrap+gap CSS.
- Shortened and added the "why" to the calibrated-uncertainty gate's reason
  text: now states plainly that only 3 real validation targets exist, too
  few to calibrate against, instead of a longer, vaguer sentence.
- **Insurance report content reviewed for appropriateness to an external
  reader** (Anna's "review it as a literal intruder" ask): removed
  `pipeline version: run_baywa_assessment.v1` from the report header -- an
  internal build-version string with no meaning to an external
  risk/reinsurance reviewer, the kind of dev-facing metadata that
  undermines a document meant to look professional to an outside party.
  Generation date and dataset provenance (legitimately useful to an
  external reader) are kept.

**170/170 tests pass** (one test rewritten, not just deleted, to match the
new intentional behavior). `node --check`/`py_compile` clean. Verified live:
Methodology page screenshotted with the button gone; Analysis page's
"More detail" disclosure confirmed to no longer contain either removed
panel via direct DOM query; chart-foot spacing confirmed visually; the
PDF-download fix confirmed via a real (not simulated) button click.

**2026-10-24 (latest+7, read first): full click-through audit of every
control on the site** (functionality + no-contradictions, per Anna's
explicit priority ranking: works end-to-end > nothing ambiguous > easy to
navigate). Clicked every button, submitted every form, expanded every
disclosure, in a real browser, not read-only review:

- Overview: export (downloads real JSON), insurance-report open/close + all
  3 downloads (PDF/md/email), commercial price recalculate -- all confirmed
  working with real output, zero console errors.
- Analysis: validation-overlay toggle, both `<details>` disclosures -- all
  confirmed working. **Found and fixed one real contradiction**: the
  Evidence Register's "Review gate" row showed value text "Reviewed — all
  applicable checks passed" next to a "PENDING" state badge in the same
  row -- reads as self-contradictory. Fixed: when the state is pending, the
  row's own value text now says "All applicable gates passed — 1 not
  evaluated" instead of reusing the primary badge's shorter label, so the
  value and the state agree.
- Methodology: "Download methodology (PDF)" confirmed working post-deck-
  deletion.
- Upload: all 3 sample-file links confirmed live (not dead, real 200
  responses); submit-with-zero-files correctly blocked by native HTML5
  validation ("Please select one or more files"); submit-with-one-file
  correctly shows the custom "choose at least two files" message;
  submit-with-all-three-samples confirmed working end-to-end with correct
  output, in a fresh browser tab, after restarting the server to pick up
  today's fixes.

**170/170 tests pass.** Every item above was verified by actually clicking
it and reading the real result back out of the DOM (or, for downloads,
intercepting the blob/anchor to confirm real content and filename) -- not
assumed working because the code looked right.

**2026-10-23 (latest+6, read first): the Methodology slide deck is deleted.**
Per the coordinating session: every piece of the deck's content already
existed in better plain-prose form in "Full methodology and limitations"
right below it (or on the Analysis page), so nothing is lost. Removed the
whole `.deck` block from `workspace/index.html` and `initDeck()` (plus its
call site) from `workspace/app.js` entirely. The "Download methodology
(PDF)" button is kept (relocated to the section heading) and now exports
the static "Full methodology" content directly from the DOM instead of the
deck's slide array — verified by intercepting `window.open` and confirming
the generated HTML contains Reconstruction/Limitations/Opportunities
content. Methodology page reloaded fresh: no deck, no counter, no carousel
buttons, zero console errors, zero dangling `deck-*` element references
(`node --check` + `grep` both clean). 170/170 tests pass. CSS cleanup for
now-unused `.deck`/`.slide`/`.deck-*` classes left alone, as explicitly
told not to spend time on.

**2026-10-23 (latest+5, read first): the upload flow was genuinely broken by
design, not just badly explained — rebuilt it, plus fixed the deck,
insurance-panel routing, and PDF buttons, all verified live with real
end-to-end browser tests (not assumptions).**

- **Upload tool rebuilt, not just re-worded.** Root cause of "upload doesn't
  work": the form had two separate fields (wind-data vs power-curve), so a
  user who downloaded 3 sample files naturally put the wrong file in the
  wrong box (e.g. target-data + power-curve, no reference turbine — exactly
  what happened live). Fixed by removing the two-field split entirely:
  `upload_tool.classify_file_kind()` reads each uploaded file's own column
  headers and sorts it into wind-data or power-curve automatically, so
  there's one box, "drop everything in". `baywa_tool_server.py`'s `/run`
  now takes one `files` field. Verified three ways: curl with 2 files, curl
  with 3 files, curl with Anna's exact original combination (now a clear
  error since a reference truly is still missing) -- then a full real
  browser test fetching the actual `/sample/*` files, assigning them to the
  real file input, submitting the real form, in a genuinely fresh tab, and
  reading the rendered result back out of the DOM.
- **Insurance-report panel only worked on Overview** -- it was
  `data-route="overview"`-gated, so clicking "Generate insurance report"
  from any other tab fetched successfully but showed nothing. Removed the
  route restriction; verified by clicking it live from the Analysis page.
- **"Present" button did nothing (requestFullscreen silently failing) --
  replaced with a working "Download PDF"** that renders all deck slides
  into a print-ready window and calls the browser's native print dialog.
  Verified by intercepting `window.open` in a live page and checking the
  generated HTML actually contains all slide content (not just assuming the
  popup worked) -- same verification done for the insurance report's PDF
  button.
- **Deck slides were overflowing/unreadable, not just "small text."** The
  Gate slide's content didn't fit its fixed-height container; the Evidence
  slide embedded the full Analysis-page tier cards (way too dense for a
  presentation slide). Shortened Gate's text, replaced Evidence's embedded
  cards with 3 compact stat tiles, bumped slide body text 14px->15px.
  Verified visually: screenshotted both slides before describing them fixed.
- **Added a 7th deck slide, "Opportunities"** (07/07) -- the same "what
  we'd build next" content that was previously only in the text block below
  the deck now also exists in the presentation itself, and directly answers
  the two questions Anna asked in chat: a calibrated uncertainty interval
  isn't possible yet because only 3 real validation targets exist (too few
  to calibrate against); a genuine neighbouring-farm test isn't possible
  because BayWa's dataset has no second nearby farm at all (today's closest
  real proxy, Kelmarsh-Penmanshiel, is ~399 km apart).
- Fixed the 7th tab being scrollable-out-of-view in the deck's tab rail
  (`scrollIntoView` added on slide change).
- Deleted the page footer ("WindLens / evidence workspace") -- pure
  duplication of the sidebar's own branding, added nothing.

**170/170 tests pass**, `node --check`/`py_compile` clean. Every fix in this
entry was verified live in the browser with real end-to-end interaction
(real files, real form submission, real button clicks, intercepted
`window.open` to inspect actual generated content) -- not just read back as
rendered text, given today's repeated reports of things that looked fixed
but weren't actually tested through.

**2026-10-23 (latest+4, read first): a real visual regression fix, a round of
direct feedback from Anna acted on live, plus a blind first-time-user test
agent's findings.** This round came directly from Anna in the terminal, not
relayed through a coordinating session, and included "run an agent that
navigates with no context and tells us what a real human experiences" -- done,
see below.

**Regression caught and fixed first:** restructuring the Analysis page into
`<details>` blocks (previous entry) accidentally dropped the `panel` CSS
class from three sections (`baywa-targets`, `evidence-tiers`,
`other-findings` went from `class="tiers-panel panel"` to just
`class="tiers-panel"`), which lost their card background/border -- this was
the "visual broken, small text, different font" Anna reported. Restored the
class on all three. Also bumped the `styles.css`/`app.js` cache-busting
query strings so the fix actually reaches a reloaded browser.

**Blind first-time-user test agent (as asked):** dispatched a fresh
general-purpose agent with zero project context, told only "explore this
running app as a first-time visitor, report what's confusing or broken."
Its findings, independent of anything said in this chat today, closely
matched and extended Anna's own complaints:
- **New bug found: overlapping, unreadable text on the Methodology deck's
  "Evidence" slide** (step 05/06) -- the slide title rendered on top of its
  own body paragraph. Root-caused via DOM measurement (not guessing): the
  CSS rule `.slide.wide .slide-aside { align-items:baseline; ... }` made the
  flex row under-report its own height versus its larger `h3` child, so the
  next grid row (the body) started before the title had actually finished
  rendering. Fixed by switching to `align-items:center` and adding a small
  top margin. Verified visually fixed via direct DOM bounding-rect
  measurement before and after, then a screenshot.
- **Orange "warning" colour used for states that are not warnings**, exactly
  what Anna separately flagged (the red description text annoyed her) but
  with more instances found: the Overview "NEXT ACTION" box was always
  orange even when its own text says "no gate failed"; the Evidence
  Register table's "Confidence-range check" and "Review gate" rows showed
  "CAUTION" in orange for a merely *not-evaluated* gate, not an actual
  failure. Fixed site-wide: `.small-note`'s default colour flipped from
  orange to neutral grey (new `.plain-note` class added for purely
  informational text); added a genuine third state, `pending` (neutral
  grey), distinct from `caution` (orange, now reserved for real failures)
  -- in both the evidence table and the Overview's "next action" box, which
  now only turns orange when `failed_gates.length > 0`.
- **A dead-end dropdown** ("History used to pick the reference turbine" --
  looked clickable, had exactly one option) replaced with plain text.
- **Leaked internal-looking codes** ("R01", "U01", "V01" panel badges)
  removed -- added no information, read like database row IDs.
- **A lab-notebook timestamp and self-congratulatory finding text**
  ("A genuinely surprising, material finding (2026-10-23).", "We tested the
  alternative we expected to lose, too.") rewritten as plain findings
  statements in `evidence-tiers-data.js`.
- **"Abstained" ML-practitioner jargon** ("Not abstained --", "ABSTAIN --")
  replaced with plain language in the registry-evidence status text.
- **The Upload tab was a genuine dead end** for a visitor with no turbine
  files on hand -- added a new `GET /sample/<file>` route serving two of
  BayWa's own real challenge files (`T2_data.xlsx`, `O1_data.xlsx`, plus
  `T2_power_curve.xlsx`) with `Content-Disposition: attachment`, and three
  download links on the Upload tab so a visitor can try the real flow
  immediately. Verified the route serves the real files with correct
  headers via curl.

**Anna's direct feedback, acted on:**
- Topbar summary reworded from an instruction ("Estimate missing turbine
  production...") to a statement of what the tool does ("WindLens estimates
  missing turbine production...").
- The review-status badge's long jargon label ("...uncertainty calibration
  not evaluated") shortened to "Reviewed — all applicable checks passed" in
  the primary badge; the detailed nuance stays in the gate list itself,
  where it was already explained in plain language.
- The hero kWh-range caption trimmed to just the number range, dropping the
  "not a calibrated statistical interval" explanation from the primary view
  (it's still covered on the Methodology page).
- The hero caption ("Real BayWa r.e. challenge dataset... using O1")
  deleted outright -- it was pure duplication of the incident-strip's own
  "Reference: O1" field directly above it.
- The loss-chart's explanatory paragraph moved from above the chart to
  below it, as a caption, and shortened.
- "proxy-truth energy" reworded to "the actual energy for that window" in
  the Analysis narrative paragraph.
- "before BayWa's own data arrived" (the timing-framing Anna specifically
  asked to change) replaced everywhere it appeared (6 places across
  `evidence-tiers-data.js`, `app.js`'s deck, and the disclosure label) with
  consistent "used to validate the method on other wind farms" framing.
- Both Analysis-page `<details>` disclosure labels shortened and clarified:
  "Full evidence: all three targets, reference selection, and
  data-quality checks" → "More detail on this result"; "External
  validation, done before BayWa's data arrived (not part of the real
  submission)" → "Testing on other wind farms (not the real BayWa result)".
- Added a "Download report (PDF)" button on the insurance report panel
  (alongside the existing .md/.txt downloads) -- opens a print-styled view
  and calls the browser's native print dialog (Save as PDF), no new
  dependency.
- Verified the insurance email draft is genuinely data-driven, not
  hardcoded (generated different, correct numbers for T1 vs T3) -- but
  found and removed three more instances of the same self-referential
  "honest" language already fixed elsewhere today, in
  `insurance_report.py`'s own templates.
- Added an explicit sentence on the Upload tab answering Anna's staleness
  question directly: uploading and running a reconstruction there is a
  live, separate calculation -- it does **not** change the official T3
  record shown on Overview/Analysis (those are generated ahead of time by
  the Python pipeline and written into `assessment-data.js`; the Upload
  tool is an intentionally separate sandbox, so a visitor's own test run
  can never overwrite the real submission).

**170/170 tests pass.** `node --check`/`py_compile` clean on every touched
file, HTML tag-balance and duplicate-id checks clean. Verified live on a
full fresh-tab reload across all four routes with zero console errors;
re-screenshotted the Methodology "Evidence" slide to confirm the overlap is
gone; confirmed the evidence table now shows "pending" (not "caution") for
not-evaluated gates via direct DOM inspection; confirmed the sample-file
route serves real files with correct `Content-Disposition` headers via curl.

**2026-10-23 (latest+3, read first): default-to-delete chrome pass, Analysis page
restructured to match a real analytics-tool density (Montel/EnAppSys reference
Anna sent as a direct contrast).** Two more rounds of feedback from the
coordinating session, both independently re-verified before acting:

**Chrome deletion:**
- `workspace/index.html`'s `.sidebar-footer` ("OFFICIAL BAYWA R.E. CHALLENGE
  DATA / Shown-window self-validation (T3)") deleted -- it just repeated the
  main panel's REVIEW STATUS line word-for-word, and was hardcoded to always
  say "(T3)" even if a different record were ever shown (a latent bug, not
  just clutter).
- The page footer's `dataset checksum ...` text (and its "not published by
  the challenge organiser" fallback) cut entirely -- a provenance detail with
  zero relevance to any reader. Footer is now just "WindLens / evidence
  workspace". Removed the now-dead `footer-record` population code in
  `app.js`.
- Upload results' `<h3>Target: T2</h3>` (an internal field name with no
  explanation) renamed to `<h3>Reconstructing T2 (the turbine with the data
  gap)</h3>` in both result paths (success and per-target error).

**Analysis page restructure (the bigger change):** Anna sent a screenshot of
a real energy-analytics tool (Montel/EnAppSys) as a direct contrast -- two
clean charts, one heading, two short plain-prose paragraphs, nothing else.
Our Analysis page read as an engineering audit trail with a chart buried in
it. Rebuilt the primary view to match that density:
- **Primary, always visible:** page heading, the reconstructed-wind chart
  (moved to lead, was buried below three other sections), then ONE short
  plain-prose paragraph directly below it, written like briefing a colleague
  ("T3's turbine lost an estimated 285,766 kWh during its outage window...").
  This paragraph is **data-driven**, not hardcoded -- a new
  `renderAnalysisNarrative()` in `app.js` builds it from the real
  `baywa_comparison` + `assessment` data every time, so it can't drift from
  the actual numbers.
- **Moved into a collapsed `<details>` ("Full evidence: all three targets,
  reference selection, and data-quality checks"):** the T1/T2/T3 tier-card
  comparison, the three reference-integrity/confidence-range/validation
  panels, the farm-metadata registry panel, and the evidence table -- all
  still present, all still rendered by the same existing JS (every element
  id is unchanged), just not taking up the primary view by default.
- **Moved into a second collapsed `<details>`:** the external
  Kelmarsh/Penmanshiel validation tiers and the "additional findings"
  section (lazy-baseline / weighting-ablation).
- Nothing was deleted from the rigor/detail -- it's one click away, not
  gone. New CSS: `.analysis-narrative` (large serif lead paragraph) and
  `.detail-disclosure` (styled native `<details>`/`<summary>`, no new JS
  dependency).
- Fixed a duplicate-id bug this restructuring could have introduced: the
  original evidence-table section existed twice in two different
  edits-in-progress; caught and removed the stray duplicate before testing.

**170/170 tests pass.** `node --check` clean, HTML tag-balance and duplicate-id
checks clean. Verified live in-browser on a full fresh-tab reload across all
four routes with zero console errors; screenshotted the reworked Analysis
page myself and confirmed it now reads chart-then-paragraph-then-detail, not
a wall of stacked panels; clicked the "Full evidence" disclosure open and
confirmed its contents (chart, T1/T2/T3 cards, panels) still render
correctly.

**2026-10-23 (latest+2, read first): insurance report wired into the live demo,
Methodology deck's real-data contradiction fixed, site-wide voice pass (self-audit
→ reader-facing).** Three more items the coordinating session found on a fresh
read of the live site, independently re-verified before acting:

- **Insurance report was built but invisible (`grep -rln "insurance"
  workspace/*.js workspace/*.html` was empty).** `src/windlens/insurance_report.py`
  existed and worked via CLI only. Now wired in properly, not a static fallback:
  `baywa_tool_server.py` has a new `GET /insurance-report?target=<id>` route that
  calls `insurance_report.generate()` directly and returns JSON; the Overview
  page's topbar has a new "Generate insurance report" button (next to "Download
  assessment record") that opens an inline panel with the rendered markdown plus
  "Download report (.md)" / "Download email draft (.txt)" buttons. One sentence
  next to it explains who it's for (a risk/reinsurance reviewer). Verified live:
  clicked the real button, got a correctly rendered report for T3, zero console
  errors.
- **Methodology deck slide 1 contradicted the real-record text below it.** Slide
  1 ("Detect") described the synthetic masking technique used for *external
  validation* as if that's how the real BayWa record's outage window was found —
  directly contradicting the accurate text in "Full methodology" just below it
  ("the outage window is identified directly from BayWa's own data"). Slide 1 is
  now dynamic: `initDeck()` reads `window.WINDLENS_DATA.assessment.assessment_type`
  and shows the real-record explanation (window comes from BayWa's own data,
  masking is a separate testing technique used elsewhere) when viewing the real
  record, the old simulated-back-test framing otherwise.
- **Voice pass, site-wide, not just the one example quoted.** Rewrote the deck's
  "What this proves" / "What it does not prove" box labels to "What you can rely
  on" / "What to check yourself" (self-audit → reader-actionable), and rewrote
  each slide's own claims text to match (e.g. "This tool does not detect
  outages" → "...confirm the cause yourself (sensor fault vs. a real mechanical
  outage). WindLens estimates what was lost once you know there was a real
  one."). The same "Does not prove:" label is shared by `tierCardsHtml()` across
  EVERY tier card on the Analysis page (evidence tiers, other findings, the real
  T1/T2/T3 cards, and the deck's Evidence slide) — fixed once there to
  "Check before relying on this:", which fixes the pattern everywhere that
  component is used, not just one card. Also reworded the one matching
  self-referential line in `assessment-data.js`'s limitations and the
  Methodology "what we'd build next" list. Renamed the "Upload & run" nav tab to
  "Analyse your own outage" (states the action and the benefit, not a UI-pattern
  label).

**170/170 tests pass.** `node --check` clean on all 3 JS files, `python -m
py_compile` clean on all three server/report files. All 4 routes reloaded fresh
and checked live in-browser with zero console errors, including a real click of
the new insurance-report button and a real look at the fixed Methodology slide.

**2026-10-23 (latest+1, read first): fixed a real gap the coordinating session
found by spot-checking the live upload endpoint with BayWa's actual raw
files.** `curl .../run -F wind_data=@T2_data.xlsx -F power_curve=@T2_power_curve.xlsx`
failed with a cryptic error. Root cause confirmed, not guessed: BayWa's real
challenge zip (`data_hackathon_baywa_re (1)/`, present in the repo root)
ships **one turbine per file** (`T2_data.xlsx` has only T2's own readings,
no reference turbines at all) -- the pipeline itself was correct (verified
against the pre-combined `baywa_canonical.csv`, which worked perfectly and
matched the live Overview page's numbers exactly), but a juror's single most
natural action -- drop one of BayWa's own files into the upload tool -- would
hit a dead end on the #1 required deliverable.

**Fix (the coordinating session's preferred option 1, not the fallback):**
`src/windlens/baywa_tool_server.py`'s multipart parser now returns a *list*
of parts per field name (was one); the wind-data file input now has
`multiple`; `upload_tool.py` has a new `load_wind_data_files()` that
concatenates several uploaded files into one frame before running. Also
added an early, explicit error (`run_pipeline()`) for the case where only
one turbine is uploaded at all: *"Only one turbine (T2) was found across the
uploaded file(s). BayWa's challenge data ships one turbine per file --
select the target turbine's file together with at least one other turbine's
file to use as a reference (e.g. T2_data.xlsx + O1_data.xlsx)."* -- so even a
user who forgets to multi-select gets an actionable message instead of the
old pipeline-internal one.

**Verified with the exact repro plus the real files, not synthetic data:**
single `T2_data.xlsx` alone now gives the clear error above (HTTP 400);
`T2_data.xlsx` + `O1_data.xlsx` + `O2_data.xlsx` together now correctly
reconstructs T2 against O2 (136,251.41 kWh -- exact match to the live
Analysis page's T2 hidden-window figure); all 10 of BayWa's real files
uploaded together correctly reconstruct all three targets against their
known-correct references (T1→O1, T2→O2, T3→O1). Also verified live in the
browser: selected 3 real files via the actual file input (not curl),
submitted through the real form, got a correctly rendered result card, zero
console errors. **170/170 tests still pass.**

**2026-10-23 (latest): tone/honesty/IA pass across the whole
workspace, plus the upload-and-run tool is now reachable from inside the
polished demo (was a disconnected standalone server before tonight).**
Addressed Anna's full raw-feedback pass on the live site, categorized by the
coordinating session into 7 problem classes and fixed class-wide, not just at
the quoted examples:

- **Critical gap closed: the upload tool is no longer invisible.** Before
  tonight, `src/windlens/baywa_tool_server.py` was a disconnected plain-HTML
  `http.server` on :8765 that nothing in `workspace/` linked to -- a juror
  opening the polished demo would never find it. `baywa_tool_server.py` now
  also serves `workspace/`'s own static files (whitelisted exact filenames,
  no directory traversal) and `/run` now returns JSON instead of its own
  hand-rolled HTML page. `workspace/index.html` has a new 4th nav tab
  ("Upload & run", `#upload`) with a form styled in the same design system;
  `workspace/app.js`'s new `initUploadForm()`/`renderUploadResult()` POST the
  file via `fetch('/run', ...)` and render the result as styled cards. **Run
  the whole demo with one command now:** `PYTHONPATH=src
  /Users/annaradova/.venv/bin/python3 -m windlens.baywa_tool_server`, open
  `http://127.0.0.1:8765/#overview` -- Overview/Analysis/Methodology/Upload
  all come from this one process. (A plain static server, e.g. `python -m
  http.server` on `workspace/`, still renders the first three tabs, but
  `/run` 404s there -- the Upload tab shows a clear error telling the user to
  use `baywa_tool_server.py` instead, rather than failing silently.) Verified
  end-to-end live in the browser: a real multipart upload through the actual
  page (not just curl) round-tripped through the real pipeline and rendered
  correctly, zero console errors; also smoke-tested directly against the full
  129,601-row `data/derived/baywa_canonical.csv` via curl, numbers matched
  the known-correct saved assessment exactly.
- **Honesty/tone:** removed every self-narrating "honest"/"dishonest"/
  "fabricated" phrase from user-visible copy (the tool now states facts,
  never comments on its own honesty) -- `workspace/assessment-data.js`'s
  uncertainty/gate/limitations text and `workspace/app.js`'s outlier framing
  line. `workspace/evidence-tiers-data.js`'s stale "the challenge's real
  neighbouring-farm scenario is untested" framing (now false -- we have the
  real BayWa cross-park T1/T2/T3 result) is rewritten everywhere it appeared
  (Tier 3, the footnote, the scale-gap label, the Methodology "Limits"
  slide) to say these tiers are external Kelmarsh/Penmanshiel evidence run
  *before* BayWa's own data arrived, not a stand-in for the real test. Three
  leaked "Combined 90% confidence check" stats (an internal target red-team
  F4 found statistically unachievable by construction) are removed from all
  three tiers.
- **Debug strings removed from the UI:** the raw `windlens.assessment.baywa-t3.v1`
  schema string is no longer shown in the page footer; `method_version` is
  now the human label "Single-reference wind reconstruction" instead of the
  raw key `wind_first_single_reference`; the meaningless "SCENARIO / SAVED
  PROFILE" tag and the whole sidebar "Workspace state" block (redundant with
  the sidebar footer) are removed.
- **Duplicate text:** the Overview hero's gate-status line and the caption
  directly below it said almost the same thing twice -- the caption now
  states the record is real BayWa data (not a proxy) instead of repeating
  the gate status.
- **Jargon:** "gate the result" (topbar), "lazy baseline" (now "simple
  average of nearby turbines"), "80/20 shipped blend" (now "80% history /
  20% distance weighting"), the run-on gate-factor sentence (now a labeled
  list), and "no check uses the real outcome, which would be impossible in a
  real outage" (reworded for clarity) are all fixed project-wide, not just
  at Anna's quoted spots. Analysis page's WAPE/RMSE definitions paragraph
  had the `.small-note` 12px class applied to it by mistake -- fixed to
  normal body size.
- **Information architecture:** the Analysis page is reordered so the real
  BayWa T1/T2/T3 record and its chart are at the top (previously framed as
  "other scenarios tested" with the real data buried below three Kelmarsh
  tiers); the external Kelmarsh/Penmanshiel validation is now clearly
  demoted below a labeled divider ("External validation, done before
  BayWa's data arrived -- not part of the real submission"). Added a plain
  T/O/H turbine-naming explainer next to the real-targets grid (T = BayWa's
  three target turbines to reconstruct; O/H = the other real turbines used
  as reference candidates; there is no farm registry for this dataset).
  Methodology page restructured: reconstruction (with its formula) and
  energy calculation (with its formula) are now side-by-side, limitations
  full-width below, plus two new sections -- "Other methods we considered"
  (direct power regression, naive averaging, multi-turbine blend, and why
  each was not shipped) and "What we'd build next" (calibrated uncertainty,
  outage-cause classification, a genuine neighbouring-farm test).
- **Commercial price:** relabeled from an unexplained "SCENARIO / SAVED
  PROFILE" number to an explicit "Illustrative European onshore wind
  reference price" with a one-line sourcing caption; kept the "not a
  settlement, contractual, or legal value" disclaimer (Anna said keep it)
  but tightened its wording.

**170/170 tests pass** (no regression). `node --check` passes on all three
JS files; `python -m py_compile` passes on both server files. Live-verified
in-browser on all four routes (Overview/Analysis/Methodology/Upload) with
zero console errors.

**Not done / deferred, flagged rather than faked:** the slide deck
(`initDeck()`'s `claims()` text) still references Kelmarsh by name in a few
slides where that's factually correct (the external-validation slides) --
left as-is, since those slides are genuinely about that data. Anna's
broader "does the Overview/Analysis/Methodology split even make sense"
structural question is answered by tonight's reordering but not re-litigated
from scratch -- a bigger redesign, if wanted, is a separate pass. The
Methodology "Opportunities" content is a text section, not a new deck slide
(lower-risk under deadline pressure; same content, different placement).

**2026-10-23 (late): insurance-report bonus deliverable built, plus
the automatic-turbine-selection bonus confirmed.** New, independent files only
(nothing under `workspace/` touched, nor `baywa_tool_server.py`/`upload_tool.py`):
`src/windlens/insurance_report.py` generates a short markdown outage-loss report
plus a ready-to-send email draft for any target turbine (`python -m
windlens.insurance_report --target T3`), grounded entirely in the real
`data/derived/baywa_assessment_result.json` and the real, labeled-illustrative
demo commercial profile -- no invented numbers. The kWh range shown is
explicitly "not a calibrated statistical confidence interval" (none has been
run on this dataset); it is the worst observed shown-window error across the
n=3 validated targets (T1 39.36%/T2 2.73%/T3 5.19%), stated as such. A concrete
example run against T3 (the project's representative record) is saved at
`docs/EXAMPLE_INSURANCE_REPORT_T3.md`. `docs/BONUS_AUTOMATIC_TURBINE_SELECTION.md`
confirms the other named bonus ("automatic turbine selection from a pool") is
already solved by `select_dynamic_references()` in
`src/windlens/dynamic_reference.py` -- no new code needed there. **170 tests,
170 pass** (163 pre-existing + 7 new, in `tests/test_insurance_report.py`).
**Flagged, not guessed:** the official spec's exact wording for this bonus item
was never saved to a file in this repo, so this was built from the paraphrase
handed down through the session chain, not the literal spec text -- see
`docs/DECISION_LOG.md`'s 2026-10-23 (late) "Insurance-report bonus deliverable"
entry for the full detail and that caveat.

**2026-10-23 (latest, read first): the real BayWa T3 record is now the Overview
Dashboard's primary record -- the Kelmarsh<->Penmanshiel swap is done.** Per
Anna's decision, the Overview page now shows T3's shown-window
(2026-09-04..09-10) self-validation: 5.19% energy error, the literal median of
the three real targets (T1 39.36% outlier, T2 2.73%, T3 5.19%) -- the
representative result, not the best case. The Analysis page has a new "All
three real targets: T1, T2, T3" section showing all three honestly, including
T1's outlier with its "single pair of unusually mismatched turbines, not a
general pipeline problem" explanation, and each target's hidden-window
(2026-09-01..09-03) prediction explicitly labeled "no truth to score against"
-- no validation overlay or coverage claim anywhere for that window, by design.
Review-gate classification for T3 uses a simpler, honest shape (not the old
5-gate Kelmarsh schema): input QA / reference alignment / validated domain all
pass (real checks, not fabricated), calibrated uncertainty is marked **not
evaluated** (grey, distinct from pass/fail) rather than faked. The kWh range
shown is an explicitly-labeled bracket (±39.36%, the worst of 3 observed
errors) -- not a calibrated statistical interval. Full detail, including the
honesty fixes found along the way (registry-evidence ABSTAIN wording, the
Kelmarsh-specific day-lookback dropdown, a chart band-legend CSS specificity
bug) in `docs/DECISION_LOG.md`'s 2026-10-23 (late) entry. **163 tests, 163
pass** (one test updated to match the new, honest `usable_for_geo_selection:
false`, not a regression). Verified live in browser on all three routes, no
console errors. `workspace/README.md` untouched, same scope decision every
prior session made.

**2026-10-23 (Track C session close) addendum (read first): jury-facing
polish complete, BayWa record swap deliberately not done.** All five Track C
items finished: (1) plain-language pass -- WAPE/RMSE spelled out, every
"hidden truth" instance removed, the full jargon catalog fixed across
`index.html`/`app.js`/`evidence-tiers-data.js`/`assessment-data.js`'s display
strings; (2) accessibility -- `:focus-visible` on every interactive element,
all previously-flagged low-contrast colors now pass 4.5:1 (WCAG AA), base/
label font sizes raised off the 9-11px range; (3) visual direction -- warm
cream background, a serif display font (Fraunces) on headlines/hero numbers/
tier values, keeping the navy/orange/sage palette and flat-panel aesthetic;
(4) a new dedicated Energy Loss chart on the Overview page (cumulative kWh
area chart, anchored to the validated headline total); (5) hygiene -- dead
code and orphaned CSS removed, `README.md` left untouched (outside this
session's `workspace/`-only scope, flagged rather than silently skipped).
Live-browser-checked on all three routes, `node --check` passes, no console
errors. **Not done: the BayWa record swap.** Track A/B's output
(`data/derived/baywa_assessment_result.json`) exists but is not
schema-compatible with the Overview page's single-incident data contract
(three targets, no review-gate/uncertainty data, a genuinely-truthless
hidden window) -- wiring it in needs real UI/design decisions, not a safe
data swap; see `docs/DECISION_LOG.md`'s 2026-10-23 evening entries (Track C
items 1-5, then the BayWa-swap decision) for the full reasoning. The current
Kelmarsh<->Penmanshiel cross-farm record remains the Overview page's
primary record. This session worked concurrently with a peer session on the
same `workspace/` files without data loss.

**2026-10-23 (Track A done) addendum (read first): real BayWa r.e. pipeline built
and self-validated.** `src/windlens/build_baywa_dataset.py` (new connector),
`run_baywa_assessment.py` (new, wind-first single-reference), `power_errors()`
(new, in `loss_estimate.py`), and an `external_power_curve` parameter on
`backtest.run_backtest_event` (non-breaking addition) are all in and tested.
**Honest shown-window (Sept 4-9) self-validation:** wind RMSE 1.73-2.14 m/s
(holdout R² 0.42-0.52), energy relative error 2.73%/5.19%/**39.36%** for
T2/T3/T1 -- materially worse correlation than any same-farm or Kelmarsh<->
Penmanshiel cross-farm result run tonight; read as the real measured
correlation structure of this dataset, not tuned and not a bug (see
`docs/DECISION_LOG.md`'s full 2026-10-23 "Track A" entry for the full table and
the T1-outlier explanation). Hidden-window (Sept 1-3) predictions for all three
targets (432 rows each) are produced and written to
`data/derived/baywa_assessment_result.json` -- this is the actual
submission-grade output; no truth exists to score it against, by design. Test
suite: 163 tests, 163 pass (openpyxl now installed, so the prior 10 failures
are gone too).

**2026-10-23 (Track B done) addendum: minimal local upload-and-run tool built and
manually verified.** `src/windlens/upload_tool.py` (pipeline wrapper -- reuses
Track A's `select_reference_turbine`/`reconstruct_wind_speed`/`apply_power_curve`
directly, no new modeling) + `src/windlens/baywa_tool_server.py` (stdlib
`http.server`, binds `127.0.0.1:8765` only, no new dependency). Run it with
`PYTHONPATH=src /Users/annaradova/.venv/bin/python3 -m
windlens.baywa_tool_server`, open `http://127.0.0.1:8765/`, upload a wind-data
file (+ optional power curve), click Run. Caught and fixed a real bug before
calling this done: naive outage-target detection flagged any isolated one-row
sensor dropout as a target, which could crash the whole request if it sat near
the file's start -- fixed with a minimum contiguous-run threshold and per-target
error isolation (see `docs/DECISION_LOG.md`'s 2026-10-23 "Track B" entry for the
full detail, including one documented limitation: one uploaded power curve is
applied to every detected target in a multi-target upload). Manually verified via
curl against the running server with the real BayWa canonical dataset: full
upload + power curve, no-curve, and manual-window-override cases all returned
200 with correct results. Test suite: 163 tests, 163 pass, no regression.

**Both Track A and Track B are now complete and checkpointed.** Track C (jury-
facing polish) is a separate, already-running sibling session's scope
(`workspace/`-only) -- not touched here.

**2026-10-23 (latest) addendum (read first): full method x scenario matrix
complete.** Anna asked to run "the entire matrix" -- all three tiers done,
nothing cut for budget. Tier 1 (highest priority): cross-farm single-
reference wind-first (12.16%/14.52% WAPE, new) and direct power
(22.91-24.92%, new, collapses) now sit alongside the already-known cross-
farm ensemble (13.09%/14.25%) and lazy average (19.09-22.30%). Tier 2:
confirmed wind-first baseline+ensemble were already tested for whole-site
masking; added direct power (6.56-8.93%, competitive) and lazy baseline
(11.25-13.30%, now losing, unlike same-farm) there. Tier 3: ensemble-
weighting ablation (inverse-error vs equal) confirms the shipped default,
differences under 0.6pp, as expected. **Honest headline: wind-first wins
clearly at real cross-farm distance over both direct power and the lazy
average, but the shipped 3-turbine ensemble is NOT demonstrated to beat
single-reference there -- they're a tie or single-reference slightly wins.**
See `docs/DECISION_LOG.md`'s four 2026-10-23 "running the entire matrix"
entries (Tier 1, Tier 2, Tier 3, and the consolidated summary) for full
numbers and the per-tier honesty notes. No pitch/README/workspace change
made in reaction -- Anna's call. Test suite unchanged: 163 tests, 153 pass,
same 10 pre-existing `openpyxl` errors.

**2026-10-23 (later) addendum:** reference-selection weighting
ablation (Anna's request) tested the shipped 80/20 behaviour/geography blend
against three alternatives on the exact locked bake-off split; all four are
statistically indistinguishable at this sample size (every bootstrap 95% CI
overlaps), so the 80/20 default is **kept**, by a stated principle (behavior
is the directly-validated signal; geography is a plausibility regularizer),
not because it was never questioned. Red-team hygiene items F9/F11/F13/F14
(split-disjointness bug, UI-copy fixes, tautological tests, doc drift) are
now all finalized. Four "insurer's lens" fixes landed: a cause-classification
scope note, a visible EUR-exposure demo-price badge, a lazy (equal-weighted
farm-average) baseline comparison, and an opt-in curtailment-row filter for
power-curve fitting. **The lazy baseline is a material, surprising finding:
it beats every wind-first variant and is competitive with direct power on
both farms (5.67%/5.86% WAPE vs. wind-first's 10-14% and direct power's
6.3-7.0%)** -- see `docs/DECISION_LOG.md`'s 2026-10-23 entries for full
detail on all of the above. Test suite: 163 tests, 153 pass (same 10
pre-existing `openpyxl` errors).

**2026-10-23 addendum:** two new evidence tiers beyond same-farm
single-turbine tests, both logged in `docs/DECISION_LOG.md` (2026-10-23 entries).
(1) Whole-site masking stress test on Kelmarsh (WAPE ~8-9.5%, vs 7-9% same-farm on
the same targets) -- *whole-site masking stress test, ~300-400m reference
separation — a best-case ceiling bound, NOT a neighbouring-farm validation*
(measured half-to-half distances are actually 271-935 m). (2) Real Kelmarsh<->Penmanshiel
backtest at ~399 km: WAPE 13.1% / 14.2%, cross-farm wind r=0.44, 88% coverage -- a
realistic-distance floor, NOT a neighbouring-farm validation; gates did not
discriminate (70/96 "reviewable"). **Workspace (done later same day):** three-tier panel and
full-slide methodology deck are built and browser-checked (see log); regenerate data with
`python -m windlens.build_evidence_tiers_data` after any back-test change.

Updated 2026-10-22 (late). **Trust-gate redesign (2026-10-22 late, acting on
`docs/REDTEAM_2026-10-23_adversarial_review.md`):** the "Estimate — reviewable"
label used to depend on two gates that read the event's own hidden truth
(impossible in a real outage) and had no gate checking reconstruction
completeness — which had let a −70%-wrong Hill of Towie estimate through as
"reviewable". Both are fixed (`src/windlens/review_gate.py`, `backtest.py`,
`uncertainty_business.py`, `assessment.py`; see `docs/DECISION_LOG.md`'s
2026-10-22 (late) entry for the full detail). **As a direct, intended
consequence, reviewable counts changed materially and are now higher, not
lower:** Kelmarsh 11/19 reviewable (was 3/19), Hill of Towie 19/28 (was
11/28) — because the removed gates required clearing a hidden-truth bar that
cannot exist in production, not because the method itself improved. One known
residual gap: Hill of Towie 2025-10-13 (54.3% error) still passes every gate
because its likely cause (target-side curtailment, F15) is a different defect
than the one this fix addresses, and remains open.

**Session stopped after item 5 (F3), deliberately.** Items 1-5 of the
red-team review's priority order are complete and solid; item 6 (hygiene:
F9-F11, F13, F14) was not started, per the session's own guardrail and
Anna's caution about usage limits. See `docs/DECISION_LOG.md`'s "SESSION
CLOSE" entry for exactly what item 6 still covers.

**Event-level kWh uncertainty interval (2026-10-22 late, F5):** the hero kWh
number and EUR exposure now show a range, not just a point value. See
`docs/DECISION_LOG.md`'s second 2026-10-22 (late) entry.

**Pitch re-scoped honestly (2026-10-22 late, F3):** `README.md` now states
plainly, up top, that every validated number is single-turbine same-farm
proxy reconstruction, and that the BayWa challenge's actual neighbouring-farm
scenario is untested. Hill of Towie being a different farm from Kelmarsh was
previously conflated with testing the challenge's scenario; it doesn't --
its own reference turbines are same-farm peers too. See
`docs/DECISION_LOG.md`'s fourth 2026-10-22 (late) entry.

**Method comparison corrected (2026-10-22 late, F6/F7/F8):** a WAPE scoring
bug, a biased regression variant (OLS instead of variance-ratio MCP), and a
missing reference-operating-state filter are all fixed. **"Direct power wins
2x, both farms" is retired — there is no single winner.** Kelmarsh: the
methods are close, and wind-first ensemble actually wins on the report
subset (4.41% vs. direct power's 7.60%). Hill of Towie: direct power still
wins clearly (both subsets). Extended-back-test WAPE improved substantially
from the MCP fix alone: Kelmarsh 10.0%/11.7% → 5.9%/6.8%, Hill of Towie
13.9%/13.0% → 10.4%/9.4%. The demo block (`kwf1_2016-07-07`) was regenerated:
estimate 114,770 kWh vs. 117,169 kWh truth (2.0% error, was 8.4%). Full
numbers: `docs/DECISION_LOG.md`'s third 2026-10-22 (late) entry;
`docs/METHOD_BAKEOFF_2026-10-23.md`'s correction note at the top.

**Superseded by the 2026-10-22 (late) items above:** the paragraph below was
accurate when item 1's note was written, but items 3 and 4 (also 2026-10-22
late) have since corrected both the method-comparison and the coverage-target
claims it makes. Current, honest state: the uncertainty-coverage back-test
runs on 19 Kelmarsh blocks and 28 Hill of Towie blocks. The "90%-of-blocks"
target mentioned below is **retired** (F4) -- it is not a meaningful target;
pooled coverage is the headline now: **Kelmarsh 91.9%, Hill of Towie 90.2%,
both on target** (per-block std 5.4pp / 6.8pp). The WAPE numbers below
(Kelmarsh 6.3%/10.0%, Hill of Towie 7.0%/13.9%) predate the F6/F7/F8 fixes;
current: Kelmarsh wind-first 5.9%/6.8%, Hill of Towie wind-first 10.4%/9.4%,
and direct power no longer wins outright on Kelmarsh (see item 3's note
above). The paragraph is left below as historical record of what was true
before these corrections, not as current fact.

The uncertainty-coverage
back-test now runs on 19 Kelmarsh blocks and 28 Hill of Towie blocks (up
from 5 and 3) -- at this larger, statistically meaningful sample, the 90%-
of-blocks coverage target is **not met on either farm, with 95% confidence**
(Kelmarsh 9/19 = 47.4%, CI [27%,68%]; Hill of Towie 17/28 = 60.7%, CI
[42%,76%]). Direct-power regression now also has its own uncertainty
interval (previously missing): it still beats wind-first on WAPE (Kelmarsh
6.3% vs 10.0%; Hill of Towie 7.0% vs 13.9%) but its coverage is no better.
Full detail: `docs/DECISION_LOG.md`'s two 2026-10-22 entries after the
visual-quality-pass entry. **What's left:** the direct-power production-
promotion decision (Anna's call -- it changes the workspace's "reconstructed
wind" narrative); a parallel audit (`docs/AUDIT_2026-10-22_uncertainty_calibration.md`,
stopped early for budget) flagged that the calibration method itself was
selected by best-score-on-the-original-5-blocks and that residuals are
scored on near-training data -- neither is fixed by more blocks, both need
a genuinely separate holdout, unresolved. The rest of this document is the
2026-10-21 evidence-first demo and metric-policy pass, still accurate except
where the numbers above correct it.

## Visual-quality pass (2026-10-22)

`workspace/` was rebuilt to match the real-platform reference Anna gave
(see `docs/DECISION_LOG.md`'s 2026-10-22 entries): flat cards (no shadow),
plain light-grey/white surfaces instead of warm cream, normalized numeral
letter-spacing, the farm-metadata registry panel moved from `#overview` to
`#evidence`-only, and a labelled divider added between `#method`'s slide
summary and its detailed grid. No data, model numbers, or claims changed --
only `workspace/index.html` and `workspace/styles.css`. `app.js` is
untouched. Verified: `node --check workspace/app.js` passes, and all three
hash routes were checked on a local loopback server. One known pre-existing
issue, not caused by this pass: mobile width (375px) overflows horizontally
(see the decision log entry for detail) -- not fixed tonight, flagged for
next session.

## What is now usable

- Serve `workspace/` on loopback and open `http://127.0.0.1:8000/#overview`.
- `#overview` is the Assessment demo surface.
- `#evidence` is the source and review register.
- `#method` is the methodology explanation with the four implemented steps.
- The Assessment chart supports hover inspection and an explicit validation
  overlay toggle. The control is a reference-lookback selector: 90 days is
  selected in the saved record; 30 and 180 days are visibly marked as not
  calculated. The assessment window remains five days.
- The methodology steps are clickable presentation slides with “what this
  proves” and “what this does not prove” boundaries.

## Claims the current demo can support

- The Kelmarsh record is a reproducible simulated outage back-test.
- The assessment uses the saved Kelmarsh source, reference, checksum, paired
  observations, and saved uncertainty result.
- 2026-10-21 update: after fixing a calibration fit/score mismatch (see
  `docs/DECISION_LOG.md`), the displayed block now passes every current gate
  and is classified **Estimate -- reviewable** (previously "Unverified --
  manual evidence required" at 72% observed coverage against a 90% target).
  This is honest but narrow: it is 1 of now 19 Kelmarsh back-test blocks
  (expanded 2026-10-22 from 5) -- across all 19, mean ensemble coverage is
  ~91% but only 9/19 blocks (47.4%, 95% CI [27%,68%]) individually clear the
  90% target; aggregate wind-first energy WAPE is 11.7% (ensemble) / 10.0%
  (baseline) over the 19 blocks. Do not present the single displayed block
  as evidence that the method is reliable in general.
- The commercial amount is an indicative calculation from a manually saved demo
  price profile. It is not a settlement, liability, or legal result.

## Claims the current demo must not imply

- It does not prove an operational outage.
- It does not prove that Kelmarsh same-farm peers perform like a separate farm.
- It does not claim that the uncertainty interval is calibrated well enough for
  automatic use.
- It does not place Hill of Towie or EDP data into Kelmarsh training.

## Metrics currently tracked

WindLens is primarily a **regression and uncertainty** system, so the saved
back-tests track:

- wind MAE and RMSE in m/s;
- signed wind bias in m/s;
- holdout R² for reference selection;
- estimated-versus-hidden energy error;
- aggregate energy WAPE and signed aggregate bias;
- uncertainty coverage versus the target and mean interval width;
- reviewable/abstained event counts and abstention rate;
- paired-observation count, domain checks, and alignment checks.

“Accuracy” is therefore represented by these continuous error metrics rather
than a single accuracy percentage. **Precision, recall, and F1 are not currently
reported** because the present dataset does not contain labelled operational
outages or labelled non-outages. They become appropriate when WindLens adds an
outage-detection/classification task, for example:

- precision: of intervals flagged as suspected outages, how many are confirmed;
- recall: of confirmed outages, how many WindLens detects;
- false-positive and false-negative rates by site and asset.

Do not add precision/recall to the reconstruction scorecard unless a verified
event-label source exists. For the current demo, report the regression metrics,
coverage, bias, and abstention rate instead.

## Possible outage-detection extension

WindLens can evolve into a two-stage system:

1. **Detection/classification:** decide whether a telemetry pattern is
   consistent with a suspected outage or fault event.
2. **Reconstruction:** estimate the missing counterfactual generation and
   uncertainty, only after the event is accepted for review.

Public label sources exist, but their labels must remain separate:

- The public EDP Portugal release includes timestamped event/alarm logs and 28
  manual confirmed component-failure records. Its event log is not the same as
  a resolved outage register, so event alarms and confirmed failures need
  different label states.
- The public WindML project provides labelled status-log episodes for Kelmarsh
  and Penmanshiel. Its documented definition is a major fault stop lasting at
  least one hour; it explicitly says the status logs record stops, not confirmed
  component replacements.
- The CARE benchmark provides 36 turbines across three farms with labelled
  anomaly frames leading to faults and normal sequences. It is suitable for an
  independent detection benchmark, not for mixing into Kelmarsh reconstruction
  training.

For a detection model, evaluate at event level with time-ordered splits and a
matching tolerance, not only row-level accuracy. Required outputs would be
precision, recall, F1, false alarms per turbine-month, missed-event rate, and
time-to-detect. Keep detection metrics separate from kWh reconstruction
metrics. Do not call a telemetry gap a confirmed outage without an event,
failure, work-order, or operator label.

## Verification

- `node --check workspace/app.js`
- `PYTHONPATH=src /Users/annaradova/.venv/bin/python3 -m unittest discover -s tests -q`
- Latest result (2026-10-24, after the IA-rebuild follow-up round -- see this
  file's "(latest+14)" entry at the top): 191 tests, 191 pass.
  `openpyxl` is now installed, so the prior 10 Excel-connector failures
  (noted here as of 2026-10-23) no longer apply.
- Browser route check passed for both hash routes (the workspace is now two
  pages, Result and Methodology, not four) -- a fresh browser tab against the
  running server showed zero console errors on both, plus a real end-to-end
  multi-target `/run` round-trip against BayWa's own real T1/T3 files (each
  with its own power curve) rendered correctly, each target with its own
  correct kWh figure (see the "(latest+14)" entry at the top for detail).

## Next work

See the top-of-file summary for current numbers and what's left. Attach any
new headline number to a saved validation artifact first. Update
`docs/PROJECT_STATE.md` and `docs/DECISION_LOG.md` with every change.
