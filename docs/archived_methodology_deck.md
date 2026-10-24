# Archived: Methodology slide-deck carousel (removed 2026-10-23)

This is the interactive 6→7-slide carousel that used to sit at the top of
the Methodology page, before it was deleted (per the coordinating session's
explicit instruction — its content was fully duplicated in the plain-prose
"Full methodology and limitations" section that remains on the page).

**This file is reference only — not wired into the live site.** The CSS
classes it depends on (`.deck`, `.slide`, `.deck-bar`, `.deck-rail`,
`.deck-tab`, `.deck-stats`, `.slide-claims`, etc.) are still present,
unchanged, in `workspace/styles.css` (left in place as a low-priority
cleanup item), so this would mostly work again if ever re-wired — the
`esc()`, `tierCardsHtml()`, and `shortDate()` helpers it calls are also
still present in `workspace/app.js`.

## HTML (used to sit in `workspace/index.html`, inside `#method`, right
after the section heading and before "Full methodology and limitations")

```html
<div class="deck" id="deck" tabindex="0" aria-roledescription="carousel" aria-label="WindLens methodology presentation">
  <div class="deck-stage" id="deck-stage"></div>
  <div class="deck-wipe" aria-hidden="true"></div>
  <div class="deck-bar">
    <div class="deck-rail" id="deck-rail" role="tablist" aria-label="Slides"></div>
    <div class="deck-nav">
      <span class="deck-counter" id="deck-counter">01 / 07</span>
      <button type="button" class="deck-btn" id="deck-prev" aria-label="Previous slide">&larr;</button>
      <button type="button" class="deck-btn" id="deck-next" aria-label="Next slide">&rarr;</button>
      <button type="button" class="deck-btn deck-present" id="deck-present">Download PDF</button>
    </div>
  </div>
</div>
```

## JavaScript (used to be `initDeck()` in `workspace/app.js`, called once at boot)

```js
function initDeck() {
  const tiers = window.WINDLENS_EVIDENCE_TIERS;
  const isRealRecord = window.WINDLENS_DATA?.assessment?.assessment_type === 'real_baywa_submission_shown_window_self_validation';
  const claims = (yes, no) => `<div class="slide-claims"><div class="yes"><span>What you can rely on</span><p>${yes}</p></div><div class="no"><span>What to check yourself</span><p>${no}</p></div></div>`;
  const detectBody = isRealRecord
    ? `<p>The outage window shown for this record comes straight from BayWa's own data — the turbine genuinely stopped reporting wind readings for this period, nothing is assumed or guessed. (Separately, under "External validation" on the Analysis page, we also run controlled tests where we deliberately hide known-good data on purpose, just to check how accurate the method is — that's a testing technique, not how your real result is produced.)</p>`
    : `<p>Mark the interval on the affected asset that needs reconstruction. In this test, a known-healthy interval is temporarily hidden ("masked") and the real values are set aside only to check the estimate afterward.</p>`;
  const slides = [
    { tab: 'Detect', kicker: 'Detect', title: 'Find the gap', body: [detectBody, claims('The outage window comes directly from the turbine’s own data, not an assumption.', 'A data gap by itself doesn’t tell you why production stopped — confirm the cause yourself (sensor fault vs. a real mechanical outage). WindLens estimates what was lost once you know there was a real one.')] },
    { tab: 'Select', kicker: 'Select', title: 'Pick a reference turbine', body: [`<p>How well each candidate turbine's past readings matched the target before the outage decides which one is used as the reference, and how much weight it gets; location is a secondary plausibility check, used only when it exists. This real BayWa submission has no turbine-location data at all, so its reference turbine is chosen purely on past behaviour. Selection only ever looks at data from before the outage, never during or after.</p>`, claims("The reference choice relies only on data available before the outage, so it can't be skewed by hindsight.", 'Past behavioural similarity is not a guarantee a reference turbine hundreds of km away behaves the same — check the reference distance and holdout R² before trusting a distant pairing.')] },
    { tab: 'Estimate', kicker: 'Estimate', title: 'Reconstruct wind, then power', body: [`<p>The reference turbine's wind readings are converted into an estimate for the target turbine using a statistical best-fit line &mdash; a standard wind-industry technique called measure-correlate-predict. That estimated wind is then converted into expected power using the target's own power curve from before the outage, and added up over time into kilowatt-hours (kWh).</p>`, claims('The calculation is inspectable and reproducible end to end — every number traces back to a real reading.', 'No single method wins everywhere — check the Methodology page’s "other methods we considered" before assuming this is the only valid approach for your use case.')] },
    { tab: 'Gate', kicker: 'Gate', title: 'Check the result before trusting it', body: [`<p>A gate is an automatic check run before you see a number. Five checks: input quality, reference overlap, tested range, completeness, confidence calibration. Any check that fails or can't be run is flagged on the Overview page, never hidden.</p>`, claims('A failed or not-evaluated gate is flagged openly — you see exactly which check is weak before relying on the number.', 'A passing gate is not a guarantee of accuracy. Weigh the number against what you independently know about the outage.')] },
    { tab: 'Evidence', kicker: 'Evidence', title: 'Three tiers, never one number', body: [tiers ? `<div class="deck-stats">${tiers.tiers.map((t) => `<div><strong>${esc(t.headline_value)}</strong><span>${esc(t.name)}</span></div>`).join('')}</div><p>Uses external Kelmarsh/Penmanshiel data to validate the method on other wind farms. Full detail: Analysis page, "Testing on other wind farms".</p>` : '<p>Evidence-tier record not generated.</p>'] },
    { tab: 'Limits', kicker: 'Limits', title: 'What this cannot tell you yet', body: [`<p>No open dataset offers two verified, overlapping farms close together, so the tiers above bracket the real neighbouring-farm case instead: a best-case ceiling (same site) and a realistic floor (~400&nbsp;km apart). The real BayWa submission (Overview and Analysis pages) is the actual cross-park test — use that number, not this bracket, for the real scenario.</p>`, claims("This bracket tells you roughly how much accuracy to expect to lose as reference turbines get farther apart.", 'This bracket does not tell you exactly where the real BayWa case lands — read the T1/T2/T3 record on the Overview and Analysis pages directly.')] },
    { tab: 'Next', kicker: 'Opportunities', title: "What we'd build next", body: [`<ul class="plain-list"><li><b>A calibrated uncertainty interval</b> — not possible yet with only 3 real validation targets; needs more held-out BayWa data to build one honestly.</li><li><b>Automatic outage-cause classification</b> — so a sensor fault and a real mechanical outage don't need separate manual confirmation.</li><li><b>A genuine neighbouring-farm test</b> — BayWa's dataset has no second, nearby farm; today's closest real proxy is ~399&nbsp;km apart.</li></ul>`]},
  ];
  const stage = $('deck-stage'), rail = $('deck-rail'), deck = $('deck');
  stage.innerHTML = slides.map((s, i) => `<section class="slide${s.wide ? ' wide' : ''}" data-slide="${i}" aria-label="${esc(s.title)}" aria-hidden="true"><div class="slide-aside"><div><span class="slide-kicker">${String(i + 1).padStart(2, '0')} / ${esc(s.kicker)}</span><h3>${esc(s.title)}</h3></div><div class="slide-num" aria-hidden="true">${String(i + 1).padStart(2, '0')}</div></div><div class="slide-body">${s.body.join('')}</div></section>`).join('');
  rail.innerHTML = slides.map((s, i) => `<button type="button" class="deck-tab" role="tab" data-method-step="${i}"><b>${String(i + 1).padStart(2, '0')}</b>${esc(s.tab)}</button>`).join('');
  const nodes = [...stage.children], tabs = [...rail.children];
  let current = -1, busy = false;
  const show = (i) => {
    nodes.forEach((n, k) => { n.classList.toggle('is-active', k === i); n.setAttribute('aria-hidden', String(k !== i)); });
    tabs.forEach((t, k) => { t.classList.toggle('active', k === i); t.setAttribute('aria-selected', String(k === i)); });
    tabs[i]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    $('deck-counter').textContent = `${String(i + 1).padStart(2, '0')} / ${String(slides.length).padStart(2, '0')}`;
    current = i;
  };
  const go = (i) => {
    i = Math.max(0, Math.min(slides.length - 1, i));
    if (i === current || busy) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    deck.classList.toggle('dir-back', i < current);
    if (reduce || current < 0) { show(i); return; }
    busy = true; deck.classList.remove('wiping'); void deck.offsetWidth; deck.classList.add('wiping');
    setTimeout(() => show(i), 380);
    setTimeout(() => { deck.classList.remove('wiping'); busy = false; }, 800);
  };
  tabs.forEach((t, i) => t.addEventListener('click', () => go(i)));
  $('deck-prev').addEventListener('click', () => go(current - 1));
  $('deck-next').addEventListener('click', () => go(current + 1));
  deck.addEventListener('keydown', (e) => { if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); go(current + 1); } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); go(current - 1); } });
  show(0);
  window.__deckGo = go;
}
```

(The PDF-export click handler that used to be wired to `#deck-present` inside
this function was already superseded before the deck itself was deleted —
see `docs/HANDOVER.md`'s entries from 2026-10-23/24 for that history. The
button is now gone from the live page too, per Anna's 2026-10-24 request.)
