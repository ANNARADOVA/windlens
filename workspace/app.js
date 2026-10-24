const $ = (id) => document.getElementById(id);

const fmt = (value, digits = 0) => Number(value).toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const shortDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric', timeZone:'UTC' });
let chartTruthVisible = false;
let currentResultVM = null;
let lastExportPayload = null;

function applyRoute() {
  const requested = (window.location.hash || '#overview').slice(1);
  const view = requested === 'method' ? 'method' : 'overview';
  document.body.classList.remove('view-overview', 'view-method');
  document.body.classList.add(`view-${view}`);
  document.querySelectorAll('.nav-item').forEach((item) => {
    const target = item.getAttribute('href').slice(1);
    item.classList.toggle('active', target === view);
  });
  const title = { overview: 'Outage reconstruction', method: 'Methodology' }[view];
  const heading = document.querySelector('.topbar h1');
  if (heading) heading.textContent = title;
}

const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]));

// ---- Result view (Page 1): works identically for the default official BayWa T3
// record and for a live uploaded run -- buildResultViewModel() normalizes either
// shape into one small object, and renderResultView() is the only thing that
// touches the DOM. Uploading should feel like it replaces this same view, not
// like it opens a separate, lesser result area.
function buildResultViewModel(source, data) {
  if (source === 'official') {
    const a = data.assessment;
    const validation = a.validation;
    return {
      source,
      targetId: a.incident.asset_id,
      referenceId: a.reference.selected_asset_id,
      referenceFallbackNote: null,
      windowStartUtc: a.incident.window_start_utc,
      windowEndUtc: a.incident.window_end_utc,
      reviewLabel: a.review.label,
      nextAction: a.next_action,
      lostKwh: a.estimate.lost_energy_kwh,
      kwhInterval: a.estimate.kwh_interval,
      lostKwhUnavailableReason: null,
      windowCaveatText: a.assessment_type === 'real_baywa_submission_hidden_window_prediction'
        ? 'This is a prediction for the hidden outage, based on a reconstruction method whose accuracy was separately checked on a different, known window (see Methodology for the self-validation detail).'
        : '',
      windRmseMs: a.estimate.wind_rmse_ms ?? null,
      windMaeMs: a.estimate.wind_mae_ms ?? null,
      powerRmseKw: validation?.power_rmse_kw ?? null,
      powerMaeKw: validation?.power_mae_kw ?? null,
      overlaySeries: data.overlay_series,
      lossSeries: data.series,
    };
  }
  const t = data; // one target entry from the /run response
  const hasKwh = 'estimated_lost_kwh' in t;
  return {
    source,
    targetId: t.target_turbine,
    referenceId: t.selected_reference,
    referenceFallbackNote: t.reference_fallback_note || null,
    windowStartUtc: t.outage_window_utc[0],
    windowEndUtc: t.outage_window_utc[1],
    reviewLabel: null,
    nextAction: null,
    lostKwh: hasKwh ? t.estimated_lost_kwh : null,
    kwhInterval: null,
    lostKwhUnavailableReason: hasKwh ? null : (t.estimated_lost_kwh_unavailable_reason || 'No power curve uploaded — wind-speed prediction only.'),
    windowCaveatText: t.raw_reconstruction_notice || 'This is a raw reconstruction from your uploaded data, not validated against ground truth for this event.',
    windRmseMs: null,
    windMaeMs: null,
    powerRmseKw: null,
    powerMaeKw: null,
    overlaySeries: { points: t.overlay_series || [] },
    lossSeries: hasKwh
      ? { interval_minutes: t.inferred_cadence_minutes, points: t.predictions.map((p) => ({ timestamp_utc: p.timestamp_utc, reconstructed_ms: p.wind_speed_ms_predicted })) }
      : null,
  };
}

function refreshFinancialSummary() {
  const profile = window.WINDLENS_DATA?.commercial;
  if (!profile || !currentResultVM || !$('result-financial-value')) return;
  const priceInput = $('commercial-price');
  const price = priceInput && priceInput.value !== '' ? Number(priceInput.value) : profile.fixed_price_eur_per_mwh;
  if (currentResultVM.lostKwh == null) {
    $('result-financial-value').textContent = '—';
    $('result-financial-note').textContent = currentResultVM.lostKwhUnavailableReason || 'No energy estimate available for this record.';
    return;
  }
  const value = currentResultVM.lostKwh / 1000 * price;
  $('result-financial-value').textContent = `${profile.currency} ${fmt(value, 0)}`;
  $('result-financial-note').textContent = `At ${profile.currency} ${fmt(price, 2)}/MWh (demo price, ${currentResultVM.source === 'official' ? 'adjustable' : 'same demo price'} on the Methodology page). Indicative only.`;
}

function renderResultView(vm) {
  currentResultVM = vm;
  $('asset-id').textContent = vm.targetId;
  $('assessment-window').textContent = `${shortDate(vm.windowStartUtc)} — ${shortDate(vm.windowEndUtc)}`;
  $('reference-id').textContent = vm.referenceId;
  $('review-label').textContent = vm.reviewLabel || (vm.source === 'upload' ? 'Live run (ungraded)' : '—');
  if ($('reference-fallback-note')) {
    $('reference-fallback-note').hidden = !vm.referenceFallbackNote;
    $('reference-fallback-note').textContent = vm.referenceFallbackNote || '';
  }
  if ($('result-source-tag')) $('result-source-tag').textContent = vm.source === 'official' ? 'REAL BAYWA T3 RECORD' : 'YOUR LIVE RUN';

  $('lost-kwh').textContent = vm.lostKwh != null ? fmt(vm.lostKwh, 0) : '—';
  const windowDays = Math.max(1, Math.round((new Date(vm.windowEndUtc) - new Date(vm.windowStartUtc)) / 86400000));
  if ($('window-duration')) $('window-duration').textContent = `${windowDays} day${windowDays === 1 ? '' : 's'}`;
  $('hero-kwh-range').textContent = vm.kwhInterval
    ? (vm.kwhInterval.display_text || `${fmt(vm.kwhInterval.lower_kwh, 0)} – ${fmt(vm.kwhInterval.upper_kwh, 0)} kWh`)
    : vm.lostKwh != null
      ? 'No event-level kWh interval available for this record.'
      : (vm.lostKwhUnavailableReason || '—');
  $('hero-window-caveat').textContent = vm.windowCaveatText || '';
  $('hero-review-state').textContent = vm.reviewLabel || (vm.source === 'upload' ? 'Live, ungraded run' : '—');
  if ($('model-name')) $('model-name').textContent = `single reference turbine (${vm.referenceId})`;

  if ($('result-wind-error')) {
    $('result-wind-error').textContent = vm.windRmseMs != null
      ? `${fmt(vm.windRmseMs, 2)} / ${fmt(vm.windMaeMs, 2)} m/s`
      : 'Not applicable — no ground truth for this window, by construction';
  }
  if ($('result-power-error')) {
    $('result-power-error').textContent = vm.powerRmseKw != null
      ? `${fmt(vm.powerRmseKw, 0)} / ${fmt(vm.powerMaeKw, 0)} kW`
      : 'Not applicable — no ground truth for this window, by construction';
  }
  if ($('gate-count')) $('gate-count').textContent = vm.source === 'official' ? 'Real BayWa T3 submission' : 'Live, ungraded run';

  $('next-action').textContent = vm.nextAction || 'Review the evidence below, then decide how to act on this live run.';

  refreshFinancialSummary();
  renderOverlayChart(vm.overlaySeries, vm.windowStartUtc, vm.windowEndUtc);

  if (vm.lostKwh != null && vm.lossSeries) {
    $('loss-chart-unavailable').hidden = true;
    renderLossChart(vm.lossSeries, vm.lostKwh);
  } else {
    $('loss-chart-wrap').innerHTML = '<div class="loading">No energy estimate to chart.</div>';
    $('loss-chart-total').textContent = '—';
    $('loss-chart-range').textContent = '—';
    $('loss-chart-unavailable').hidden = false;
  }
}

function renderOverlayChart(overlay, windowStartUtc, windowEndUtc) {
  const wrap = $('overlay-chart-wrap');
  if (!wrap) return;
  const points = (overlay && overlay.points) || [];
  if (!points.length) { wrap.innerHTML = '<div class="loading">No overlay series available for this run.</div>'; $('overlay-chart-range').textContent = '—'; return; }

  const width = 1000, height = 240, pad = { left:42, right:18, top:12, bottom:30 };
  const values = points.flatMap((p) => [p.target_ms, p.reference_ms]).filter((v) => v != null);
  const min = Math.floor(Math.min(...values) - 0.5), max = Math.ceil(Math.max(...values) + 0.5);
  const x = (i) => pad.left + i / (points.length - 1) * (width - pad.left - pad.right);
  const y = (v) => height - pad.bottom - (v - min) / (max - min) * (height - pad.top - pad.bottom);

  const outageIdx = points.map((p, i) => (p.in_outage ? i : -1)).filter((i) => i >= 0);
  let band = '';
  if (outageIdx.length) {
    const bx0 = x(outageIdx[0]), bx1 = x(outageIdx[outageIdx.length - 1]);
    band = `<rect class="overlay-outage-band" x="${bx0.toFixed(1)}" y="${pad.top}" width="${Math.max(2, bx1 - bx0).toFixed(1)}" height="${height - pad.top - pad.bottom}"/>`;
  }

  const linePath = (key) => {
    let path = '', drawing = false;
    points.forEach((p, i) => {
      const v = p[key];
      if (v == null) { drawing = false; return; }
      path += `${drawing ? 'L' : 'M'} ${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
      drawing = true;
    });
    return path.trim();
  };
  const grid = [min, min + (max - min) / 2, max].map((v) => `<line x1="${pad.left}" x2="${width-pad.right}" y1="${y(v)}" y2="${y(v)}"/><text x="0" y="${y(v)+4}">${v.toFixed(1)}</text>`).join('');

  wrap.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Target and reference wind speed, with the outage window shaded"><g class="chart-grid">${grid}</g>${band}<path class="chart-truth" d="${linePath('reference_ms')}"/><path class="chart-reconstructed" d="${linePath('target_ms')}"/><line class="chart-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height-pad.bottom}"/><rect class="chart-hit-area" x="${pad.left}" y="${pad.top}" width="${width-pad.left-pad.right}" height="${height-pad.top-pad.bottom}"/><text class="axis-label" x="${pad.left}" y="${height-5}">${shortDate(points[0].timestamp_utc)}</text><text class="axis-label" text-anchor="end" x="${width-pad.right}" y="${height-5}">${shortDate(points[points.length-1].timestamp_utc)}</text></svg>`;
  $('overlay-chart-range').textContent = `${points.length} plotted points`;

  const svg = wrap.querySelector('svg'), crosshair = svg.querySelector('.chart-crosshair'), tooltip = $('overlay-chart-tooltip');
  svg.querySelector('.chart-hit-area').addEventListener('mousemove', (event) => {
    const box = svg.getBoundingClientRect(), ratio = (event.clientX - box.left) / box.width, i = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    const point = points[i], xPos = x(i);
    crosshair.setAttribute('x1', xPos); crosshair.setAttribute('x2', xPos); crosshair.classList.add('visible');
    tooltip.innerHTML = `<strong>${new Date(point.timestamp_utc).toLocaleString('en-GB', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'UTC'})} UTC</strong><span>Target: ${point.target_ms != null ? fmt(point.target_ms, 2) + ' m/s' : 'gap — reconstructed from reference'}</span><span>Reference: ${point.reference_ms != null ? fmt(point.reference_ms, 2) + ' m/s' : '—'}</span>`;
    tooltip.style.left = `${Math.min(Math.max(event.clientX - box.left + 12, 8), box.width - 190)}px`; tooltip.classList.add('visible');
  });
  svg.querySelector('.chart-hit-area').addEventListener('mouseleave', () => { crosshair.classList.remove('visible'); tooltip.classList.remove('visible'); });
}

// ---- Methodology detail (Page 2): validation and method content for the real
// BayWa T3 record only -- a live upload's own result stays on Page 1 and is not
// repeated here.
function renderMethodologyDetail(a) {
  const validation = a.validation;
  $('reference-detail').textContent = a.reference.selected_asset_id;
  if ($('hidden-window-points')) {
    const checked = (a.reference.domain_checks || []).reduce((sum, c) => sum + (c.observations_during || 0), 0);
    $('hidden-window-points').textContent = checked ? fmt(checked) : '—';
  }
  $('domain-status').textContent = a.reference.within_validated_domain ? 'Within tested range' : 'Outside tested range';
  $('alignment-status').textContent = a.reference.target_aligned ? 'Matches' : 'Needs review';
  $('error-value').textContent = `${fmt(validation.relative_error_pct, 1)}%`;
  $('paired-count').textContent = fmt(validation.compared_observations);
  $('wind-rmse').textContent = `${fmt(a.estimate.wind_rmse_ms, 2)} m/s`;
  $('wind-bias').textContent = `${a.estimate.wind_signed_bias_ms >= 0 ? '+' : ''}${fmt(a.estimate.wind_signed_bias_ms, 2)} m/s`;
  $('hidden-kwh').textContent = `${fmt(validation.proxy_truth_kwh ?? validation.hidden_truth_kwh, 0)} kWh`;
  if ($('hidden-kwh-label')) $('hidden-kwh-label').textContent = validation.proxy_truth_kwh != null ? 'Proxy truth (curve-derived)' : 'Actual value';
  $('method-version').textContent = a.provenance.method_version;
  $('method-reconstruction').textContent = a.method.reconstruction;
  $('method-energy').textContent = a.method.energy_integration;
  const u = a.estimate.uncertainty;
  if (u?.status === 'available') {
    const target = u.calibration.coverage_target * 100;
    const observed = u.event_evaluation.coverage_pct;
    $('coverage-value').textContent = `${fmt(observed, 1)}%`;
    $('target-coverage').textContent = `${fmt(target, 0)}% target`;
    $('interval-width').textContent = `${fmt(u.event_evaluation.mean_width_ms, 2)} m/s`;
    $('uncertainty-note').textContent = observed < target ? 'Under target on this held-out block; treat as a review signal.' : 'Coverage met the calibration target on this block.';
  } else {
    $('coverage-value').textContent = 'n/a';
    $('uncertainty-note').textContent = u?.reason || 'No interval available.';
  }
  $('limitations').innerHTML = a.limitations.map((item) => `<li>${item}</li>`).join('');

  if (a.review.gates && $('trust-gates')) {
    const failedCount = a.review.gates.filter((g) => g.state === 'fail').length;
    const notEvaluatedCount = a.review.gates.filter((g) => g.state === 'not_evaluated').length;
    const label = [
      failedCount ? `${failedCount} failed` : '',
      notEvaluatedCount ? `${notEvaluatedCount} not evaluated` : '',
    ].filter(Boolean).join(', ') || 'All gates passed';
    if ($('method-gate-count')) $('method-gate-count').textContent = label;
    $('trust-gates').innerHTML = a.review.gates.map((g) => {
      const cls = g.state === 'pass' ? '' : g.state === 'not_evaluated' ? 'not-evaluated' : 'fail';
      const mark = g.state === 'pass' ? '✓' : g.state === 'not_evaluated' ? '?' : '!';
      const reason = g.state === 'pass' ? '' : `<p class="gate-reason">${g.reason || 'This gate failed.'}</p>`;
      return `<div class="gate ${cls}"><span class="gate-mark">${mark}</span><span>${g.label}</span><small>${g.detail || ''}</small>${reason}</div>`;
    }).join('');
  }
}

function tierCardsHtml(tiers) {
  return tiers.map((t) => `<article class="tier"><span class="tier-tag">${esc(t.tag)}</span><h3>${esc(t.name)}</h3><div class="tier-value">${esc(t.headline_value)}<small>${esc(t.headline_label)}</small></div><div class="tier-stats">${t.stats.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div><p class="tier-frame"><b>Framing:</b> ${esc(t.framing)}</p><p class="tier-frame"><b>Check before relying on this:</b> ${esc(t.does_not_prove)}</p></article>`).join('');
}

function renderAnalysisNarrative(data, assessment) {
  const el = $('analysis-narrative-text');
  if (!data || !el) return;
  const primary = data.targets.find((t) => t.is_overview_record) || data.targets[0];
  const others = data.targets.filter((t) => t !== primary);
  const othersText = others
    .map((t) => `${t.target_turbine} ${fmt(t.energy_relative_error_pct, 2)}%${t.is_outlier ? ' (a wind-match outlier, not a general problem)' : ''}`)
    .join(', ');
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

function renderChart(series) {
  const points = series.points;
  const hasBand = points.length > 0 && points[0].lower_ms !== undefined && points[0].upper_ms !== undefined;
  if ($('band-legend')) $('band-legend').hidden = !hasBand;
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
  const weights = points.map((p) => Math.max(p.reconstructed_ms, 0) ** 3);
  const weightSum = weights.reduce((a, b) => a + b, 0) || 1;
  let running = 0;
  const cumulative = weights.map((w) => { running += (w / weightSum) * totalKwh; return running; });

  const width = 1000, height = 200, pad = { left:52, right:18, top:12, bottom:30 };
  const max = Math.ceil(totalKwh / 1000) * 1000 || 1;
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
    refreshFinancialSummary();
  };
  $('recalculate-commercial').onclick = update;
  update();
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
      const rows = result.files.map((f) => {
        if (f.error) return `<div class="metric-row"><span>${esc(f.filename)}</span><strong class="upload-error">Could not read: ${esc(f.error)}</strong></div>`;
        const turbineNote = f.turbines ? ` (${esc(f.turbines.join(', '))})` : '';
        return `<div class="metric-row"><span>${esc(f.filename)}</span><strong>${esc(f.role_guess)}${turbineNote}</strong></div>`;
      }).join('');
      summary.innerHTML = `<p class="small-note">Detected from the files you selected — check this matches what you meant before running:</p>${rows}`;
    })
    .catch(() => { summary.innerHTML = '<p class="small-note">Could not preview the selected files — they will still be classified when you click Run reconstruction.</p>'; });
}

// 2026-10-24: when a whole-farm-down upload returns 2+ reconstructed targets,
// show a summary row per target immediately (zero clicks) -- turbine id, its
// own outage window, and its headline kWh or why it has none -- with one
// detail view below (the existing single-target hero/chart/loss-chart) that
// switches between targets on click. Single-target uploads (the common case)
// skip this entirely and render the detail view directly, unchanged.
function renderUploadTargetsSummary(targets) {
  const section = $('upload-targets-summary');
  const list = $('upload-targets-list');
  if (!section || !list) return;
  const okTargets = targets.filter((t) => !t.error);
  if (okTargets.length <= 1) { section.hidden = true; list.innerHTML = ''; return; }
  section.hidden = false;
  $('upload-targets-count').textContent = fmt(okTargets.length);
  list.innerHTML = okTargets.map((t, i) => {
    const kwh = 'estimated_lost_kwh' in t
      ? `${fmt(t.estimated_lost_kwh, 0)} kWh`
      : (t.estimated_lost_kwh_unavailable_reason || 'No power curve uploaded');
    return `<button type="button" class="upload-target-row${i === 0 ? ' active' : ''}" data-index="${i}">
      <span class="upload-target-row-id">${esc(t.target_turbine)}</span>
      <span class="upload-target-row-window">${esc(shortDate(t.outage_window_utc[0]))} — ${esc(shortDate(t.outage_window_utc[1]))}</span>
      <span class="upload-target-row-kwh">${esc(kwh)}</span>
    </button>`;
  }).join('');
  list.querySelectorAll('.upload-target-row').forEach((button) => {
    button.addEventListener('click', () => {
      list.querySelectorAll('.upload-target-row').forEach((b) => b.classList.remove('active'));
      button.classList.add('active');
      renderResultView(buildResultViewModel('upload', okTargets[Number(button.dataset.index)]));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
}

function showOfficialRecord() {
  renderResultView(buildResultViewModel('official', window.WINDLENS_DATA));
  lastExportPayload = window.WINDLENS_DATA;
  $('upload-reset').hidden = true;
  $('upload-form').hidden = false;
  $('upload-error').hidden = true;
  if ($('upload-targets-summary')) { $('upload-targets-summary').hidden = true; $('upload-targets-list').innerHTML = ''; }
}

function initUploadForm() {
  const form = $('upload-form');
  if (!form) return;
  $('upload-files')?.addEventListener('change', (event) => renderUploadSelectionSummary(event.target.files));
  $('upload-reset')?.addEventListener('click', showOfficialRecord);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const files = $('upload-files').files;
    $('upload-error').hidden = true;
    if (files.length < 2) { $('upload-error').hidden = false; $('upload-error').textContent = 'Choose at least two files — a target turbine’s data and a reference turbine’s data.'; return; }
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    if ($('upload-manual-start').value) formData.append('manual_start', $('upload-manual-start').value);
    if ($('upload-manual-end').value) formData.append('manual_end', $('upload-manual-end').value);
    try {
      const response = await fetch('/run', { method: 'POST', body: formData });
      const result = await response.json();
      if (result.error) { $('upload-error').hidden = false; $('upload-error').textContent = result.error; return; }
      const ok = result.targets.find((t) => !t.error);
      if (!ok) {
        $('upload-error').hidden = false;
        $('upload-error').textContent = (result.targets[0] && result.targets[0].error) || 'Could not reconstruct any target from the uploaded files.';
        return;
      }
      const extraErrors = result.targets.filter((t) => t.error);
      lastExportPayload = result;
      renderUploadTargetsSummary(result.targets);
      renderResultView(buildResultViewModel('upload', ok));
      if (extraErrors.length) {
        $('upload-error').hidden = false;
        $('upload-error').textContent = `Showing ${ok.target_turbine} above. ${extraErrors.length} other target(s) in this upload could not be reconstructed: ${extraErrors.map((t) => `${t.target_turbine} (${t.error})`).join('; ')}`;
      }
      $('upload-form').hidden = true;
      $('upload-reset').hidden = false;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (error) {
      $('upload-error').hidden = false;
      $('upload-error').textContent = 'Could not reach the reconstruction server. This tab needs the workspace served by PYTHONPATH=src python3 -m windlens.baywa_tool_server (not a plain static server) — see docs/HANDOVER.md.';
      console.error(error);
    }
  });
}

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
        const previousTitle = document.title;
        document.title = pdfTitle;
        setTimeout(() => {
          frame.contentWindow.print();
          setTimeout(() => { document.title = previousTitle; }, 500);
        }, 300);
      };
      // mailto: link, not a server-side send -- opens the user's own mail client
      // with the draft prefilled, ready for them to review and send themselves
      // (2026-10-24: replaces the old "download .txt" behaviour for this action).
      const draft = result.email_draft || '';
      const subjectMatch = draft.match(/^Subject: (.*)$/m);
      const subject = subjectMatch ? subjectMatch[1] : `WindLens outage loss estimate — ${target}`;
      const body = draft.replace(/^Subject: .*\n+/, '');
      const emailLink = $('insurance-report-email-link');
      if (emailLink) emailLink.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    } catch (error) {
      $('insurance-report-text').textContent = 'Could not reach the report generator. This needs the workspace served by PYTHONPATH=src python3 -m windlens.baywa_tool_server (not a plain static server).';
      console.error(error);
    }
  });
}

async function boot() {
  try {
    if (!window.WINDLENS_DATA) throw new Error('window.WINDLENS_DATA not found -- assessment-data.js did not load');
    renderResultView(buildResultViewModel('official', window.WINDLENS_DATA));
    lastExportPayload = window.WINDLENS_DATA;
    renderCommercial(window.WINDLENS_DATA.assessment, window.WINDLENS_DATA.commercial);
    renderMethodologyDetail(window.WINDLENS_DATA.assessment);
    renderBaywaComparison(window.WINDLENS_DATA.baywa_comparison);
    renderAnalysisNarrative(window.WINDLENS_DATA.baywa_comparison, window.WINDLENS_DATA.assessment);
    renderChart(window.WINDLENS_DATA.series);
  }
  catch (error) { document.querySelectorAll('.loading').forEach(el => { el.textContent = 'Could not load the local evidence record. Serve the repository root with: python -m http.server'; }); console.error(error); }
}

$('export-button').onclick = () => {
  const blob = new Blob([JSON.stringify(lastExportPayload, null, 2)], {type:'application/json'});
  const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'windlens-assessment.json' });
  link.click(); URL.revokeObjectURL(link.href);
};

window.addEventListener('hashchange', applyRoute);
applyRoute();
document.getElementById('truth-toggle')?.addEventListener('click', (event) => { chartTruthVisible = !chartTruthVisible; event.currentTarget.setAttribute('aria-pressed', String(chartTruthVisible)); event.currentTarget.textContent = chartTruthVisible ? 'Hide validation overlay' : 'Show validation overlay'; if (window.WINDLENS_DATA?.series) renderChart(window.WINDLENS_DATA.series); });

boot();
initUploadForm();
initInsuranceReport();
