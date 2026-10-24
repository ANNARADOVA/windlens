const $ = (id) => document.getElementById(id);

const fmt = (value, digits = 0) => Number(value).toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const shortDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric', timeZone:'UTC' });
let chartTruthVisible = false;

function applyRoute() {
  const requested = (window.location.hash || '#overview').slice(1);
  const view = ['analysis', 'method', 'upload'].includes(requested) ? requested : 'overview';
  document.body.classList.remove('view-overview', 'view-analysis', 'view-method', 'view-upload');
  document.body.classList.add(`view-${view}`);
  document.querySelectorAll('.nav-item').forEach((item) => {
    const target = item.getAttribute('href').slice(1);
    item.classList.toggle('active', target === view);
  });
  const title = { overview: 'Outage reconstruction', analysis: 'BayWa challenge-data prediction', method: 'Methodology', upload: 'Analyse your own outage' }[view];
  const heading = document.querySelector('.topbar h1');
  if (heading) heading.textContent = title;
}

function renderAssessment(a) {
  const incident = a.incident, estimate = a.estimate, validation = a.validation;
  $('asset-id').textContent = incident.asset_id;
  $('assessment-window').textContent = `${shortDate(incident.window_start_utc)} — ${shortDate(incident.window_end_utc)}`;
  $('reference-id').textContent = a.reference.selected_asset_id;
  $('review-label').textContent = a.review.label;
  $('lost-kwh').textContent = fmt(estimate.lost_energy_kwh, 0);
  const windowDays = Math.round((new Date(incident.window_end_utc) - new Date(incident.window_start_utc)) / 86400000);
  if ($('window-duration')) $('window-duration').textContent = `${windowDays} day${windowDays === 1 ? '' : 's'}`;
  const kwhInterval = estimate.kwh_interval;
  $('hero-kwh-range').textContent = kwhInterval
    ? (kwhInterval.display_text || `${fmt(kwhInterval.lower_kwh, 0)} – ${fmt(kwhInterval.upper_kwh, 0)} kWh (${fmt(kwhInterval.quantile_pct, 0)}th-pct event-level band, n=${kwhInterval.n_events} back-test events)`)
    : 'No event-level kWh interval available for this record.';
  $('hero-review-state').textContent = a.review.label;
  if ($('hero-window-caveat')) {
    // 2026-10-24 (Category 4, independent review): one short, consistent line next
    // to the headline number stating the hidden/shown-window distinction plainly --
    // previously this was only explained deep in "Next action" or the Why to trust it page.
    const worst = estimate.kwh_interval?.worst_observed_relative_error_pct;
    $('hero-window-caveat').textContent = a.assessment_type === 'real_baywa_submission_hidden_window_prediction'
      ? `This is a prediction for the hidden outage (${fmt(estimate.lost_energy_kwh, 0)} kWh), based on a reconstruction method whose accuracy was separately checked on a different, known window (${fmt(validation.relative_error_pct, 1)}% error for ${incident.asset_id}${worst != null ? `; up to ${fmt(worst, 1)}% across the three targets tested` : ''}). It is not a calibrated confidence interval, and there is no measured generation to check this specific prediction against.`
      : '';
  }
  if ($('chart-note')) {
    $('chart-note').textContent = a.assessment_type === 'real_baywa_submission_hidden_window_prediction'
      ? 'This is the real graded prediction — no ground truth exists for this window to check it against, by construction. See the Why to trust it page for the separate shown-window self-validation that provides an accuracy check for this method.'
      : 'The actual recorded wind is hidden by default — it exists only to check accuracy in this simulated back-test.';
  }
  $('model-name').textContent = a.model.key === 'ensemble' ? 'three-turbine blend' : `single reference turbine (${a.reference.selected_asset_id})`;
  $('paired-count').textContent = fmt(validation.compared_observations);
  $('reference-detail').textContent = a.reference.selected_asset_id;
  if ($('hidden-window-points')) {
    // 2026-10-24 (Category 10): the hidden-window point count was previously only
    // visible in the chart's "N plotted observations" caption, not in this card --
    // show it explicitly next to the training-history count so the two windows'
    // sample sizes (432 vs 864) are never ambiguous about which is which.
    const checked = (a.reference.domain_checks || []).reduce((sum, c) => sum + (c.observations_during || 0), 0);
    $('hidden-window-points').textContent = checked ? fmt(checked) : '—';
  }
  $('domain-status').textContent = a.reference.within_validated_domain ? 'Within tested range' : 'Outside tested range';
  $('alignment-status').textContent = a.reference.target_aligned ? 'Matches' : 'Needs review';
  $('error-value').textContent = `${fmt(validation.relative_error_pct, 1)}%`;
  $('wind-rmse').textContent = `${fmt(estimate.wind_rmse_ms, 2)} m/s`;
  $('wind-bias').textContent = `${estimate.wind_signed_bias_ms >= 0 ? '+' : ''}${fmt(estimate.wind_signed_bias_ms, 2)} m/s`;
  $('hidden-kwh').textContent = `${fmt(validation.proxy_truth_kwh ?? validation.hidden_truth_kwh, 0)} kWh`;
  if ($('hidden-kwh-label')) $('hidden-kwh-label').textContent = validation.proxy_truth_kwh != null ? 'Proxy truth (curve-derived)' : 'Actual value';
  $('next-action').textContent = a.next_action;
  $('next-action').parentElement.classList.toggle('caution', (a.review.failed_gates?.length || 0) > 0);
  $('method-version').textContent = a.provenance.method_version;
  $('method-reconstruction').textContent = a.method.reconstruction;
  $('method-energy').textContent = a.method.energy_integration;
  const u = estimate.uncertainty;
  if (u?.status === 'available') {
    const target = u.calibration.coverage_target * 100;
    const observed = u.event_evaluation.coverage_pct;
    $('coverage-value').textContent = `${fmt(observed, 1)}%`;
    $('target-coverage').textContent = `${fmt(target, 0)}% target`;
    $('interval-width').textContent = `${fmt(u.event_evaluation.mean_width_ms, 2)} m/s`;
    $('uncertainty-note').textContent = observed < target ? 'Under target on this held-out block; treat as a review signal.' : 'Coverage met the calibration target on this block.';
  } else { $('coverage-value').textContent = 'n/a'; $('uncertainty-note').textContent = u?.reason || 'No interval available.'; }
  if (a.review.gates) {
    // Data-driven gate list (2026-10-23, BayWa T3 wiring): the real BayWa pipeline
    // doesn't honestly map onto the old fixed 5-gate Kelmarsh shape (e.g. no
    // calibrated uncertainty exists yet) -- each record now supplies its own gate
    // list with an explicit state ('pass' | 'fail' | 'not_evaluated') instead of
    // forcing every record through one hardcoded pass/fail reason table.
    const failedCount = a.review.gates.filter((g) => g.state === 'fail').length;
    const notEvaluatedCount = a.review.gates.filter((g) => g.state === 'not_evaluated').length;
    $('gate-count').textContent = [
      failedCount ? `${failedCount} failed` : '',
      notEvaluatedCount ? `${notEvaluatedCount} not evaluated` : '',
    ].filter(Boolean).join(', ') || 'All gates passed';
    $('trust-gates').innerHTML = a.review.gates.map((g) => {
      const cls = g.state === 'pass' ? '' : g.state === 'not_evaluated' ? 'not-evaluated' : 'fail';
      const mark = g.state === 'pass' ? '✓' : g.state === 'not_evaluated' ? '?' : '!';
      const reason = g.state === 'pass' ? '' : `<p class="gate-reason">${g.reason || 'This gate failed.'}</p>`;
      return `<div class="gate ${cls}"><span class="gate-mark">${mark}</span><span>${g.label}</span><small>${g.detail || ''}</small>${reason}</div>`;
    }).join('');
  } else {
    const failedSet = new Set(a.review.failed_gates);
    // 2026-10-23 (Priority 4): a bare "Unverified" label is ambiguous -- always show the
    // plain-language, specific reason for each gate that failed, never just a pass/fail dot.
    const GATE_REASONS = {
      input_qa: "The source data for this period didn't pass basic quality checks.",
      reference_target_alignment: "The stand-in turbine didn't have enough matching data with the affected one during this period.",
      validated_domain: "Conditions during this outage were outside anything we've tested before — the model would be guessing beyond its range.",
      completeness: `The stand-in turbine was itself missing data for ${fmt(100 - (validation.completeness_pct ?? 100), 0)}% of the outage window — not enough to trust the estimate.`,
      abstention: "There wasn't enough usable data to produce a reliable estimate at all.",
      uncertainty: "This stand-in turbine's track record for similar situations hasn't been reliable enough to meet our confidence target.",
    };
    $('gate-count').textContent = a.review.failed_gates.length ? `${a.review.failed_gates.length} failed` : 'All gates passed';
    $('trust-gates').innerHTML = [
      ['Input QA', 'input_qa', 'canonical source'],
      ['Data overlap', 'reference_target_alignment', `${fmt(validation.compared_observations)} matched readings`],
      ['Tested range', 'validated_domain', 'within range tested'],
      ['Completeness', 'completeness', validation.completeness_pct != null ? `${fmt(validation.completeness_pct, 1)}% complete` : 'n/a'],
      ['Uncertainty gate', 'uncertainty', failedSet.has('uncertainty') ? `${fmt(u?.event_evaluation?.coverage_pct || 0, 1)}% / ${fmt((u?.calibration?.coverage_target || 0) * 100, 0)}% target` : 'coverage target met'],
    ].map(([label, key, detail]) => {
      const ok = !failedSet.has(key);
      const reason = ok ? '' : `<p class="gate-reason">${GATE_REASONS[key] || 'This gate failed.'}</p>`;
      return `<div class="gate ${ok ? '' : 'fail'}"><span class="gate-mark">${ok ? '✓' : '!'}</span><span>${label}</span><small>${detail}</small>${reason}</div>`;
    }).join('');
  }
  $('limitations').innerHTML = a.limitations.map((item) => `<li>${item}</li>`).join('');
  $('export-button').onclick = () => { const blob = new Blob([JSON.stringify(a, null, 2)], {type:'application/json'}); const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'windlens-assessment.json' }); link.click(); URL.revokeObjectURL(link.href); };
}

function renderCommercial(a, profile) {
  if (!profile) return;
  $('commercial-profile-name').textContent = profile.display_name || profile.profile_id;
  $('commercial-profile-note').textContent = profile.notes || 'Saved commercial profile.';
  $('commercial-price').value = profile.fixed_price_eur_per_mwh ?? '';
  $('commercial-source').textContent = `${profile.currency}, priced in ${profile.settlement_interval_minutes}-minute intervals, from ${profile.source}`;
  const update = () => {
    const price = Number($('commercial-price').value);
    const value = a.estimate.lost_energy_kwh / 1000 * price;
    $('commercial-value').textContent = `${profile.currency} ${fmt(value, 0)}`;
    const interval = a.estimate.kwh_interval;
    $('commercial-range').textContent = interval
      ? `${profile.currency} ${fmt(interval.lower_kwh / 1000 * price, 0)} – ${fmt(interval.upper_kwh / 1000 * price, 0)} (same event-level band as the kWh estimate)`
      : '—';
  };
  $('recalculate-commercial').onclick = update;
  update();
}

const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]));

function markdownToHtml(md) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const lines = md.split('\n');
  const out = [];
  let inList = false;
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith('- ')) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${inline(line.slice(2))}</li>`);
      continue;
    }
    if (inList) { out.push('</ul>'); inList = false; }
    if (line.startsWith('### ')) out.push(`<h3>${inline(line.slice(4))}</h3>`);
    else if (line.startsWith('## ')) out.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (line.startsWith('# ')) out.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (line.startsWith('*') && line.endsWith('*') && !line.startsWith('**')) out.push(`<p><em>${inline(line.slice(1, -1))}</em></p>`);
    else if (line.trim() === '') continue;
    else out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push('</ul>');
  return out.join('\n');
}

function tierCardsHtml(tiers) {
  return tiers.map((t) => `<article class="tier"><span class="tier-tag">${esc(t.tag)}</span><h3>${esc(t.name)}</h3><div class="tier-value">${esc(t.headline_value)}<small>${esc(t.headline_label)}</small></div><div class="tier-stats">${t.stats.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div><p class="tier-frame"><b>Framing:</b> ${esc(t.framing)}</p><p class="tier-frame"><b>Check before relying on this:</b> ${esc(t.does_not_prove)}</p></article>`).join('');
}

function renderEvidenceTiers() {
  const data = window.WINDLENS_EVIDENCE_TIERS;
  if (!data) { $('tiers-grid').innerHTML = '<div class="loading">Evidence-tier record not generated. Run windlens.build_evidence_tiers_data.</div>'; return; }
  $('tiers-grid').innerHTML = tierCardsHtml(data.tiers);
  // Log-scale distance axis: where each tier sits, and the untested gap the challenge actually asks about.
  const lo = Math.log10(0.1), hi = Math.log10(1000), pos = (km) => ((Math.log10(km) - lo) / (hi - lo)) * 100;
  const pins = data.scale.pins.map((p) => `<div class="scale-pin" style="left:${pos(p.km).toFixed(1)}%"><span>${esc(p.label)}</span><i></i><em>${esc(p.km_label)}</em></div>`).join('');
  const g = data.scale.untested_gap;
  $('tiers-scale').innerHTML = `<div class="scale-axis"></div><div class="scale-gap" style="left:${pos(g.from_km).toFixed(1)}%;width:${(pos(g.to_km) - pos(g.from_km)).toFixed(1)}%"></div><div class="scale-gap-label" style="left:${((pos(g.from_km) + pos(g.to_km)) / 2).toFixed(1)}%">${esc(g.label)}</div>${pins}`;
  $('tiers-footnote').textContent = data.footnote;
  const findings = data.other_findings;
  if (findings && $('other-findings-grid')) $('other-findings-grid').innerHTML = tierCardsHtml(findings);
}

function renderChart(series) {
  const points = series.points;
  // 2026-10-23 (BayWa T3 wiring): no calibrated per-point uncertainty band exists for
  // this record (see estimate.uncertainty.status) -- draw the chart without one rather
  // than invent lower_ms/upper_ms, and hide the "confidence range" legend swatch too.
  const hasBand = points.length > 0 && points[0].lower_ms !== undefined && points[0].upper_ms !== undefined;
  if ($('band-legend')) $('band-legend').hidden = !hasBand;
  // 2026-10-24: the hidden-window prediction (the real graded record) has no
  // truth at all -- not "hidden by default", genuinely unavailable -- so hide
  // the toggle button and its legend entry entirely rather than offer a
  // control that does nothing.
  const hasTruth = points.length > 0 && points[0].truth_ms !== undefined;
  if ($('truth-toggle')) $('truth-toggle').hidden = !hasTruth;
  const truthLegend = document.querySelector('.truth-legend');
  if (truthLegend) truthLegend.hidden = !hasTruth;
  const width = 1000, height = 240, pad = { left:42, right:18, top:12, bottom:30 };
  const all = points.flatMap(p => hasBand ? [p.reconstructed_ms, p.truth_ms, p.lower_ms, p.upper_ms] : hasTruth ? [p.reconstructed_ms, p.truth_ms] : [p.reconstructed_ms]);
  const min = Math.floor(Math.min(...all) - .5), max = Math.ceil(Math.max(...all) + .5);
  const x = (i) => pad.left + i / (points.length - 1) * (width - pad.left - pad.right);
  const y = (v) => height - pad.bottom - (v - min) / (max - min) * (height - pad.top - pad.bottom);
  const line = (key) => points.map((p,i) => `${i ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(' ');
  const band = hasBand ? `${points.map((p,i) => `${i ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(p.upper_ms).toFixed(1)}`).join(' ')} ${points.slice().reverse().map((p,i) => `L ${x(points.length-1-i).toFixed(1)} ${y(p.lower_ms).toFixed(1)}`).join(' ')} Z` : '';
  const grid = [min, min + (max-min)/2, max].map(v => `<line x1="${pad.left}" x2="${width-pad.right}" y1="${y(v)}" y2="${y(v)}"/><text x="0" y="${y(v)+4}">${v.toFixed(1)}</text>`).join('');
  const truthPath = hasTruth ? `<path class="chart-truth ${chartTruthVisible ? '' : 'is-hidden'}" d="${line('truth_ms')}"/>` : '';
  $('chart-wrap').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Reconstructed wind speed over the outage window"><g class="chart-grid">${grid}</g><path class="chart-band" d="${band}"/>${truthPath}<path class="chart-reconstructed" d="${line('reconstructed_ms')}"/><line class="chart-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height-pad.bottom}"/><rect class="chart-hit-area" x="${pad.left}" y="${pad.top}" width="${width-pad.left-pad.right}" height="${height-pad.top-pad.bottom}"/><text class="axis-label" x="${pad.left}" y="${height-5}">${shortDate(points[0].timestamp_utc)}</text><text class="axis-label" text-anchor="end" x="${width-pad.right}" y="${height-5}">${shortDate(points[points.length-1].timestamp_utc)}</text></svg>`;
  $('chart-range').textContent = `${points.length} plotted observations / ${series.interval_minutes}-minute cadence`;
  const svg = $('chart-wrap').querySelector('svg'), crosshair = svg.querySelector('.chart-crosshair'), tooltip = $('chart-tooltip');
  svg.querySelector('.chart-hit-area').addEventListener('mousemove', (event) => {
    const box = svg.getBoundingClientRect(), ratio = (event.clientX - box.left) / box.width, i = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    const point = points[i], xPos = pad.left + i / (points.length - 1) * (width - pad.left - pad.right);
    crosshair.setAttribute('x1', xPos); crosshair.setAttribute('x2', xPos); crosshair.classList.add('visible');
    const truthLine = !hasTruth ? 'No ground truth exists for this window' : (chartTruthVisible ? `Actual ${fmt(point.truth_ms, 2)} m/s` : 'Validation overlay hidden');
    tooltip.innerHTML = `<strong>${new Date(point.timestamp_utc).toLocaleString('en-GB', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'UTC'})} UTC</strong><span>Reconstructed ${fmt(point.reconstructed_ms, 2)} m/s</span><span>${truthLine}</span>`;
    tooltip.style.left = `${Math.min(Math.max(event.clientX - box.left + 12, 8), box.width - 190)}px`; tooltip.classList.add('visible');
  });
  svg.querySelector('.chart-hit-area').addEventListener('mouseleave', () => { crosshair.classList.remove('visible'); tooltip.classList.remove('visible'); });
}

function renderLossChart(series, totalKwh) {
  const points = series.points;
  // Each interval's share of the total loss is weighted by reconstructed wind speed cubed
  // (power output scales roughly with wind speed cubed below rated capacity) -- the running
  // total is anchored to the real, validated lost_energy_kwh figure; only its minute-to-minute
  // shape across the window is this illustrative estimate.
  const weights = points.map((p) => Math.max(p.reconstructed_ms, 0) ** 3);
  const weightSum = weights.reduce((a, b) => a + b, 0) || 1;
  let running = 0;
  const cumulative = weights.map((w) => { running += (w / weightSum) * totalKwh; return running; });

  const width = 1000, height = 200, pad = { left:52, right:18, top:12, bottom:30 };
  const max = Math.ceil(totalKwh / 1000) * 1000;
  const x = (i) => pad.left + i / (points.length - 1) * (width - pad.left - pad.right);
  const y = (v) => height - pad.bottom - (v / max) * (height - pad.top - pad.bottom);
  const line = cumulative.map((v, i) => `${i ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const area = `M ${x(0).toFixed(1)} ${y(0).toFixed(1)} ${line} L ${x(points.length - 1).toFixed(1)} ${y(0).toFixed(1)} Z`;
  const grid = [0, max / 2, max].map(v => `<line x1="${pad.left}" x2="${width-pad.right}" y1="${y(v)}" y2="${y(v)}"/><text x="0" y="${y(v)+4}">${fmt(v, 0)}</text>`).join('');
  $('loss-chart-wrap').innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative estimated lost energy, in kilowatt-hours, over the outage window"><g class="chart-grid">${grid}</g><path class="loss-chart-area" d="${area}"/><path class="loss-chart-line" d="${line}"/><line class="chart-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height-pad.bottom}"/><rect class="chart-hit-area" x="${pad.left}" y="${pad.top}" width="${width-pad.left-pad.right}" height="${height-pad.top-pad.bottom}"/><text class="axis-label" x="${pad.left}" y="${height-5}">${shortDate(points[0].timestamp_utc)}</text><text class="axis-label" text-anchor="end" x="${width-pad.right}" y="${height-5}">${shortDate(points[points.length-1].timestamp_utc)}</text></svg>`;
  $('loss-chart-total').textContent = fmt(totalKwh, 0);
  $('loss-chart-range').textContent = `${points.length} plotted intervals / ${series.interval_minutes}-minute cadence`;
  const svg = $('loss-chart-wrap').querySelector('svg'), crosshair = svg.querySelector('.chart-crosshair'), tooltip = $('loss-chart-tooltip');
  svg.querySelector('.chart-hit-area').addEventListener('mousemove', (event) => {
    const box = svg.getBoundingClientRect(), ratio = (event.clientX - box.left) / box.width, i = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    const xPos = pad.left + i / (points.length - 1) * (width - pad.left - pad.right);
    crosshair.setAttribute('x1', xPos); crosshair.setAttribute('x2', xPos); crosshair.classList.add('visible');
    tooltip.innerHTML = `<strong>${new Date(points[i].timestamp_utc).toLocaleString('en-GB', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'UTC'})} UTC</strong><span>Running loss so far: ${fmt(cumulative[i], 0)} kWh</span>`;
    tooltip.style.left = `${Math.min(Math.max(event.clientX - box.left + 12, 8), box.width - 190)}px`; tooltip.classList.add('visible');
  });
  svg.querySelector('.chart-hit-area').addEventListener('mouseleave', () => { crosshair.classList.remove('visible'); tooltip.classList.remove('visible'); });
}

function renderAnalysisNarrative(data, assessment) {
  const el = $('analysis-narrative-text');
  if (!data || !el) return;
  const primary = data.targets.find((t) => t.is_overview_record) || data.targets[0];
  const others = data.targets.filter((t) => t !== primary);
  const othersText = others
    .map((t) => `${t.target_turbine} ${fmt(t.energy_relative_error_pct, 2)}%${t.is_outlier ? ' (a wind-match outlier, not a general problem)' : ''}`)
    .join(', ');
  // 2026-10-24: the headline is now the hidden-window prediction (the real
  // graded submission, no ground truth to check against, by construction) --
  // this paragraph must not conflate that with the SEPARATE shown-window
  // self-validation window's error percentage, which was a real bug here
  // before (an independent review caught the Overview and the insurance
  // report quoting two different numbers for the same turbine).
  el.textContent = `${primary.target_turbine}'s turbine is predicted to have lost ${fmt(assessment.estimate.lost_energy_kwh, 0)} kWh during its outage window (${shortDate(assessment.incident.window_start_utc)} – ${shortDate(assessment.incident.window_end_utc)}), reconstructed from reference turbine ${primary.selected_reference}'s real wind readings — the real graded prediction, with no ground truth to check it against, by construction. This method's accuracy is supported by a separate self-validation test on a different window (${primary.target_turbine} ${fmt(primary.energy_relative_error_pct, 2)}%, ${othersText}), where real recorded wind did exist to check against.`;
}

function renderBaywaComparison(data) {
  if (!data || !$('baywa-targets-grid')) return;
  $('baywa-targets-intro').textContent = data.intro;
  const cards = data.targets.map((t) => ({
    tag: t.target_turbine + (t.is_overview_record ? ' · Overview record' : ''),
    name: t.is_outlier ? 'Shown-window self-validation (outlier)' : 'Shown-window self-validation',
    headline_value: `${fmt(t.energy_relative_error_pct, 2)}%`,
    headline_label: 'shown-window energy error (WAPE), vs. curve-derived proxy truth',
    stats: [
      ['Selected reference', t.selected_reference],
      ['Holdout R²', fmt(t.holdout_r2, 3)],
      ['Wind RMSE', `${fmt(t.wind_rmse_ms, 2)} m/s`],
      ['Hidden-window prediction', `${fmt(t.hidden_window_estimated_kwh, 0)} kWh (no truth to score against)`],
    ],
    framing: t.is_overview_record
      ? `${t.target_turbine} is the primary graded target for this submission. It was selected for presentation because its shown-window self-validation error (${fmt(t.energy_relative_error_pct, 2)}%) is the median of the three targets' errors — a reasonable match to expect for the ungraded hidden window too.`
      : t.is_outlier
        ? 'This target’s error is materially worse than the other two.'
        : 'One of the three real BayWa targets in this assessment.',
    does_not_prove: t.is_outlier ? data.outlier_explanation : 'That every target in this dataset reconstructs this well — see T1 for the counter-example.',
  }));
  $('baywa-targets-grid').innerHTML = tierCardsHtml(cards);
  $('baywa-targets-outlier').innerHTML = `<b>On T1's outlier:</b> ${esc(data.outlier_explanation)}`;
  $('baywa-targets-hidden-caveat').innerHTML = `<b>On the hidden-window figures above:</b> ${esc(data.hidden_window_caveat)}`;
  $('baywa-targets-proxy-caveat').innerHTML = `<b>On "truth" energy:</b> ${esc(data.proxy_truth_caveat)}`;
}

function renderUploadResult(result) {
  const container = $('upload-result');
  container.hidden = false;
  if (result.error) {
    container.innerHTML = `<p class="upload-error">${esc(result.error)}</p>`;
    return;
  }
  container.innerHTML = result.targets.map((t) => {
    if (t.error) {
      return `<article class="upload-target-card"><h3>Reconstructing ${esc(t.target_turbine)} (the turbine with the data gap)</h3><p class="upload-error">Could not reconstruct: ${esc(t.error)}</p></article>`;
    }
    const windowNote = t.window_auto_detected ? 'auto-detected' : 'manual override';
    // 2026-10-24 (Category 8): the upload path must surface the same kind of
    // evidence as the official record (coverage, domain check, cadence, an
    // explicit "not validated" notice) rather than just the bare prediction --
    // otherwise it reads as a lesser, unvalidated calculator by comparison.
    const cadenceRow = t.inferred_cadence_minutes != null
      ? `<div class="metric-row"><span>Inferred sampling interval</span><strong>${fmt(t.inferred_cadence_minutes, 1)} minutes</strong></div>`
      : `<div class="metric-row"><span>Inferred sampling interval</span><strong>Could not infer (irregular timestamps)</strong></div>`;
    const energyRow = 'estimated_lost_kwh' in t
      ? `<div class="metric-row"><span>Estimated lost energy</span><strong>${fmt(t.estimated_lost_kwh, 1)} kWh</strong></div>`
      : t.estimated_lost_kwh_unavailable_reason
        ? `<div class="metric-row"><span>Estimated lost energy</span><strong>Unavailable — ${esc(t.estimated_lost_kwh_unavailable_reason)}</strong></div>`
        : `<div class="metric-row"><span>Estimated lost energy</span><strong>No power curve uploaded — wind-speed prediction only</strong></div>`;
    const coverageRow = t.reference_coverage_pct != null
      ? `<div class="metric-row"><span>Reference coverage of outage window</span><strong>${fmt(t.reference_coverage_pct, 1)}%</strong></div>`
      : '';
    const d = t.domain_check;
    const domainRow = d
      ? `<div class="metric-row"><span>Within reference's tested wind-speed range</span><strong>${d.within_domain ? 'Yes' : 'No — outside tested range'} (trained on ${fmt(d.training_min_ms, 1)}–${fmt(d.training_max_ms, 1)} m/s)</strong></div>`
      : '';
    return `<article class="upload-target-card">
      <h3>Reconstructing ${esc(t.target_turbine)} (the turbine with the data gap)</h3>
      <div class="metric-row"><span>Reference turbine</span><strong>${esc(t.selected_reference)}</strong></div>
      <div class="metric-row"><span>Reference ranking</span><strong>Checked against ${t.reference_ranking.length} other turbine(s)' historical readings (behaviorally selected; geographic proximity not verified)</strong></div>
      <div class="metric-row"><span>Outage window (${esc(windowNote)})</span><strong>${esc(t.outage_window_utc[0])} → ${esc(t.outage_window_utc[1])}</strong></div>
      <div class="metric-row"><span>Rows predicted</span><strong>${fmt(t.rows_predicted)}</strong></div>
      ${coverageRow}
      ${domainRow}
      ${cadenceRow}
      ${energyRow}
      <p class="small-note">${esc(t.raw_reconstruction_notice)}</p>
    </article>`;
  }).join('');
}

function renderUploadSelectionSummary(files) {
  const summary = $('upload-selection-summary');
  if (!summary) return;
  if (!files.length) { summary.hidden = true; summary.innerHTML = ''; return; }
  summary.hidden = false;
  summary.innerHTML = '<p class="small-note">Checking selected files…</p>';
  const formData = new FormData();
  for (const f of files) formData.append('files', f);
  fetch('/preview', { method: 'POST', body: formData })
    .then((response) => response.json())
    .then((result) => {
      if (result.error) { summary.innerHTML = `<p class="upload-error">${esc(result.error)}</p>`; return; }
      // 2026-10-24 (Category 8, part 3): show what role each selected file looks
      // like it will play BEFORE the user clicks Run, so a mis-assigned file (the
      // power curve dropped in as wind data, or vice versa) is caught here, not
      // only after the fact in the result below.
      const rows = result.files.map((f) => {
        if (f.error) return `<div class="metric-row"><span>${esc(f.filename)}</span><strong class="upload-error">Could not read: ${esc(f.error)}</strong></div>`;
        const turbineNote = f.turbines ? ` (${esc(f.turbines.join(', '))})` : '';
        return `<div class="metric-row"><span>${esc(f.filename)}</span><strong>${esc(f.role_guess)}${turbineNote}</strong></div>`;
      }).join('');
      summary.innerHTML = `<p class="small-note">Detected from the files you selected — check this matches what you meant before running:</p>${rows}`;
    })
    .catch(() => { summary.innerHTML = '<p class="small-note">Could not preview the selected files — they will still be classified when you click Run reconstruction.</p>'; });
}

function initUploadForm() {
  const form = $('upload-form');
  if (!form) return;
  $('upload-files')?.addEventListener('change', (event) => renderUploadSelectionSummary(event.target.files));
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const container = $('upload-result');
    container.hidden = false;
    container.innerHTML = '<div class="loading">Running reconstruction…</div>';
    const formData = new FormData();
    const files = $('upload-files').files;
    if (files.length < 2) { container.innerHTML = '<p class="upload-error">Choose at least two files — a target turbine’s data and a reference turbine’s data.</p>'; return; }
    for (const f of files) formData.append('files', f);
    if ($('upload-manual-start').value) formData.append('manual_start', $('upload-manual-start').value);
    if ($('upload-manual-end').value) formData.append('manual_end', $('upload-manual-end').value);
    try {
      const response = await fetch('/run', { method: 'POST', body: formData });
      const result = await response.json();
      renderUploadResult(result);
    } catch (error) {
      container.innerHTML = '<p class="upload-error">Could not reach the reconstruction server. This tab needs the workspace served by <code>PYTHONPATH=src python3 -m windlens.baywa_tool_server</code> (not a plain static server) — see docs/HANDOVER.md.</p>';
      console.error(error);
    }
  });
}

async function boot() {
  try {
    if (!window.WINDLENS_DATA) throw new Error('window.WINDLENS_DATA not found -- assessment-data.js did not load');
    renderAssessment(window.WINDLENS_DATA.assessment);
    renderChart(window.WINDLENS_DATA.series);
    renderLossChart(window.WINDLENS_DATA.series, window.WINDLENS_DATA.assessment.estimate.lost_energy_kwh);
    renderCommercial(window.WINDLENS_DATA.assessment, window.WINDLENS_DATA.commercial);
    renderBaywaComparison(window.WINDLENS_DATA.baywa_comparison);
    renderAnalysisNarrative(window.WINDLENS_DATA.baywa_comparison, window.WINDLENS_DATA.assessment);
  }
  catch (error) { document.querySelectorAll('.loading').forEach(el => { el.textContent = 'Could not load the local evidence record. Serve the repository root with: python -m http.server'; }); console.error(error); }
}
window.addEventListener('hashchange', applyRoute);
applyRoute();
renderEvidenceTiers();
document.getElementById('truth-toggle')?.addEventListener('click', (event) => { chartTruthVisible = !chartTruthVisible; event.currentTarget.setAttribute('aria-pressed', String(chartTruthVisible)); event.currentTarget.textContent = chartTruthVisible ? 'Hide validation overlay' : 'Show validation overlay'; if (window.WINDLENS_DATA?.series) renderChart(window.WINDLENS_DATA.series); });
function initInsuranceReport() {
  const button = $('insurance-report-button');
  if (!button) return;
  const panel = $('insurance-report-panel');
  $('insurance-report-close')?.addEventListener('click', () => { panel.hidden = true; });
  button.addEventListener('click', async () => {
    const target = window.WINDLENS_DATA?.assessment?.incident?.asset_id;
    if (!target) return;
    panel.hidden = false;
    $('insurance-report-text').textContent = 'Generating…';
    try {
      const response = await fetch(`/insurance-report?target=${encodeURIComponent(target)}`);
      const result = await response.json();
      if (result.error) { $('insurance-report-text').textContent = result.error; return; }
      $('insurance-report-text').textContent = result.report_markdown;
      $('insurance-report-download-pdf').onclick = () => {
        // A new-tab window.open() here is routinely blocked by browser popup
        // blockers with no visible error -- the button would silently do
        // nothing. Printing via a same-page hidden iframe instead can't be
        // popup-blocked, since no new window/tab is ever opened.
        let frame = document.getElementById('pdf-print-frame');
        if (!frame) {
          frame = document.createElement('iframe');
          frame.id = 'pdf-print-frame';
          frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
          document.body.appendChild(frame);
        }
        const pdfTitle = `WindLens Insurance Report - ${target}`;
        const doc = frame.contentWindow.document;
        doc.open();
        doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(pdfTitle)}</title>
          <style>body{font-family:Georgia,serif;max-width:720px;margin:40px auto;padding:0 24px;color:#172332;line-height:1.6;}
          h1{font-size:24px;}h2{font-size:18px;border-bottom:1px solid #ccc;padding-bottom:4px;margin-top:28px;}
          li{margin:4px 0;}@media print{body{margin:0;padding:24px;}}</style></head>
          <body>${markdownToHtml(result.report_markdown)}</body></html>`);
        doc.close();
        frame.contentWindow.focus();
        // Some browsers use the TOP page's title (not the iframe's own) to
        // suggest a "Save as PDF" filename -- set it here too, and restore it
        // after printing, rather than relying on the iframe's <title> alone.
        const previousTitle = document.title;
        document.title = pdfTitle;
        setTimeout(() => {
          frame.contentWindow.print();
          setTimeout(() => { document.title = previousTitle; }, 500);
        }, 300);
      };
      $('insurance-report-download-md').onclick = () => {
        const blob = new Blob([result.report_markdown], { type: 'text/markdown' });
        const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `windlens-insurance-report-${target}.md` });
        link.click(); URL.revokeObjectURL(link.href);
      };
      $('insurance-report-download-email').onclick = () => {
        const blob = new Blob([result.email_draft], { type: 'text/plain' });
        const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `windlens-insurance-email-${target}.txt` });
        link.click(); URL.revokeObjectURL(link.href);
      };
    } catch (error) {
      $('insurance-report-text').textContent = 'Could not reach the report generator. This needs the workspace served by PYTHONPATH=src python3 -m windlens.baywa_tool_server (not a plain static server).';
      console.error(error);
    }
  });
}

initUploadForm();
initInsuranceReport();
boot();
