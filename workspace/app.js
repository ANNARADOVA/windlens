const $ = (id) => document.getElementById(id);

const fmt = (value, digits = 0) => Number(value).toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const shortDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric', timeZone:'UTC' });
let chartTruthVisible = false;
let currentResultVM = null;
let lastExportPayload = null;

// Independent per-line show/hide for the "Outage window in context" overlay
// chart (2026-10-24, Anna: "we should show target, reference and
// reconstructed line (bold) and be able to hide each of them" -- three
// separate toggles, not one shared on/off). Persists across re-renders of
// whichever result is currently shown; lastOverlayArgs lets the legend
// buttons re-render with the same data after a toggle.
const overlayLineVisible = { target_ms: true, reference_ms: true, reconstructed_ms: true };
let lastOverlayArgs = null;

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
// 2026-10-24, coordinator relaying Anna: a live upload's "Not applicable" for
// wind-speed/energy error should not just stop there -- give the best
// available estimate instead, pulled from the shown-window self-validation
// figures already computed for the official record's three real targets
// (T1/T2/T3), stated honestly as a cross-reference, not this specific run's
// own number (which genuinely doesn't exist -- there is no ground truth for
// a live outage, by construction). No power-deviation equivalent here: the
// per-target power RMSE for T1/T2 isn't in this comparison data, so that
// field stays plain "Not applicable" rather than inventing a number for it.
function selfValidationContext() {
  const targets = window.WINDLENS_DATA?.baywa_comparison?.targets;
  if (!targets || !targets.length) return null;
  const windRmse = targets.map((t) => t.wind_rmse_ms);
  const energyErr = targets.map((t) => t.energy_relative_error_pct);
  return {
    n: targets.length,
    windRmseMin: Math.min(...windRmse),
    windRmseMax: Math.max(...windRmse),
    energyErrMin: Math.min(...energyErr),
    energyErrMax: Math.max(...energyErr),
  };
}

function buildResultViewModel(source, data) {
  if (source === 'official') {
    const a = data.assessment;
    const validation = a.validation;
    return {
      source,
      targetId: a.incident.asset_id,
      referenceId: a.reference.selected_asset_id,
      referenceRanking: a.reference.selection?.ranking || null,
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
      energyErrorPct: validation?.relative_error_pct ?? null,
      selfValidationContext: null,
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
    referenceRanking: t.reference_ranking || null,
    referenceFallbackNote: t.reference_fallback_note || null,
    windowStartUtc: t.outage_window_utc[0],
    windowEndUtc: t.outage_window_utc[1],
    reviewLabel: null,
    nextAction: null,
    lostKwh: hasKwh ? t.estimated_lost_kwh : null,
    kwhInterval: null,
    lostKwhUnavailableReason: hasKwh ? null : (t.estimated_lost_kwh_unavailable_reason || 'No power curve uploaded — wind-speed prediction only.'),
    windowCaveatText: t.raw_reconstruction_notice || 'This is a raw reconstruction from your uploaded data, not validated against ground truth for this event.',
    // 2026-10-24, Anna, high priority: a real wind/power error figure for
    // THIS upload's own data, not just a cross-reference to the official
    // record -- backend finds one clean, same-duration window elsewhere in
    // the same upload and reconstructs it the same way (see upload_tool.py
    // _self_validate()). Falls back to the n=3 cross-reference below only
    // when no clean window exists anywhere in the uploaded data.
    windRmseMs: t.self_validation?.wind_rmse_ms ?? null,
    windMaeMs: t.self_validation?.wind_mae_ms ?? null,
    powerRmseKw: t.self_validation?.power_rmse_kw ?? null,
    powerMaeKw: t.self_validation?.power_mae_kw ?? null,
    energyErrorPct: t.self_validation?.energy_relative_error_pct ?? null,
    selfValidationWindowUtc: t.self_validation?.window_utc ?? null,
    selfValidationContext: selfValidationContext(),
    overlaySeries: { points: t.overlay_series || [] },
    lossSeries: hasKwh
      ? { interval_minutes: t.inferred_cadence_minutes, points: t.predictions.map((p) => ({ timestamp_utc: p.timestamp_utc, reconstructed_ms: p.wind_speed_ms_predicted })) }
      : null,
  };
}

// 2026-10-24 (Anna's correction): financial impact is part of THIS result, not
// an explanation of the method -- the editable price and the estimated impact
// now live on the Analysis page next to whichever result (official demo or
// uploaded run) is currently showing, driven directly by the view-model
// instead of the official assessment object alone.
let commercialPanelRequestId = 0;
// Tracks whatever price source is CURRENTLY shown in the financial panel, so
// a generated report can use the exact same price/source instead of silently
// re-loading the fixed illustrative demo profile (2026-10-24 correctness fix
// -- the report used to show a different EUR figure than the page itself).
let currentPriceSourceLabel = 'Illustrative demo price, not sourced from BayWa data';
let currentPriceIsReal = false;

function renderCommercialPanel(vm) {
  const profile = window.WINDLENS_DATA?.commercial;
  if (!profile || !$('commercial-price')) return;
  const requestId = ++commercialPanelRequestId;
  const illustrativeCaption = `${profile.currency}, priced in ${profile.settlement_interval_minutes}-minute intervals, from Illustrative demo price, not sourced from BayWa data`;

  $('commercial-profile-name').textContent = 'Demo price (illustrative)';
  $('commercial-profile-note').textContent = 'Replace with a verified PPA or market-price feed before operational use.';
  currentPriceSourceLabel = 'Illustrative demo price, not sourced from BayWa data';
  currentPriceIsReal = false;
  $('commercial-price').value = profile.fixed_price_eur_per_mwh ?? '';
  $('commercial-source').textContent = illustrativeCaption;
  if ($('commercial-disclaimer')) $('commercial-disclaimer').textContent = 'Indicative only — not a settlement, contractual, or legal value.';

  const update = () => {
    const price = Number($('commercial-price').value);
    if (vm.lostKwh == null) {
      $('commercial-value').textContent = '—';
      $('commercial-range').textContent = vm.lostKwhUnavailableReason || 'No energy estimate available for this result.';
      return;
    }
    const value = vm.lostKwh / 1000 * price;
    $('commercial-value').textContent = `${profile.currency} ${fmt(value, 0)}`;
    $('commercial-range').textContent = vm.kwhInterval
      ? `Interval: ${profile.currency} ${fmt(vm.kwhInterval.lower_kwh / 1000 * price, 0)}–${fmt(vm.kwhInterval.upper_kwh / 1000 * price, 0)} (±${fmt(vm.kwhInterval.worst_observed_relative_error_pct, 0)}%)`
      : 'No comparable range for a single run.';
  };
  $('recalculate-commercial').onclick = update;
  update();

  // 2026-10-24: default the price to the real German balancing-energy price
  // (reBAP) for THIS result's own outage window, when it's available, instead
  // of the illustrative 85 EUR/MWh -- the editable field still allows a manual
  // override on top. Never lets a missing/unreachable price crash the panel;
  // falls back to the illustrative price with a plain note instead.
  if (vm.windowStartUtc && vm.windowEndUtc) {
    const params = new URLSearchParams({
      window_start: vm.windowStartUtc.slice(0, 10),
      window_end: vm.windowEndUtc.slice(0, 10),
    });
    fetch(`/energy-price?${params}`)
      .then((response) => response.json())
      .then((priceResult) => {
        if (requestId !== commercialPanelRequestId) return; // a newer result is now showing
        if (priceResult.error) {
          $('commercial-source').textContent = `${illustrativeCaption} (real reBAP price unavailable for this window)`;
          return;
        }
        $('commercial-price').value = priceResult.average_price_eur_per_mwh;
        $('commercial-profile-name').textContent = 'reBAP — Germany’s real balancing-energy price';
        $('commercial-profile-note').textContent = `Monthly average for this outage window (${fmt(priceResult.n_price_points)} real price readings).`;
        $('commercial-source').innerHTML = `Unit: EUR/MWh · Source: <a href="${esc(priceResult.source_url)}" target="_blank" rel="noopener">${esc(priceResult.source_name)}</a>`;
        if ($('commercial-disclaimer')) $('commercial-disclaimer').textContent = 'Indicative only — not a settlement, contractual, or legal value.';
        currentPriceSourceLabel = priceResult.source_name;
        currentPriceIsReal = true;
        update();
      })
      .catch(() => {
        if (requestId !== commercialPanelRequestId) return;
        $('commercial-source').textContent = `${illustrativeCaption} (could not reach the price lookup)`;
      });
  }
}

function renderResultView(vm) {
  currentResultVM = vm;
  $('asset-id').textContent = vm.targetId;
  $('assessment-window').textContent = `${shortDate(vm.windowStartUtc)} — ${shortDate(vm.windowEndUtc)}`;
  $('reference-id').textContent = vm.referenceId;
  if (vm.referenceRanking && vm.referenceRanking.length) {
    const sorted = [...vm.referenceRanking].sort((a, b) => b.holdout_r2 - a.holdout_r2);
    const selected = sorted.find((r) => r.turbine_id === vm.referenceId);
    const others = sorted.filter((r) => r.turbine_id !== vm.referenceId).map((r) => r.turbine_id);
    $('reference-id').dataset.tooltip = selected
      ? `Selected for the best pre-outage correlation with the target (holdout R² ${fmt(selected.holdout_r2, 3)})${others.length ? `, ranked above ${others.join(', ')}` : ''}.`
      : '';
  } else {
    $('reference-id').dataset.tooltip = '';
  }
  $('review-label').textContent = vm.reviewLabel || '—';
  if ($('reference-fallback-note')) {
    $('reference-fallback-note').hidden = !vm.referenceFallbackNote;
    $('reference-fallback-note').textContent = vm.referenceFallbackNote || '';
  }
  if ($('result-source-tag')) $('result-source-tag').textContent = vm.source === 'official' ? 'BayWa challenge demo' : 'Your uploaded analysis';

  $('lost-kwh').textContent = vm.lostKwh != null ? fmt(vm.lostKwh, 0) : '—';
  if ($('loss-chart-kwh')) $('loss-chart-kwh').textContent = vm.lostKwh != null ? `${fmt(vm.lostKwh, 0)} kWh` : '—';
  const windowDays = Math.max(1, Math.round((new Date(vm.windowEndUtc) - new Date(vm.windowStartUtc)) / 86400000));
  if ($('window-duration')) $('window-duration').textContent = `${windowDays} day${windowDays === 1 ? '' : 's'}`;
  $('hero-kwh-range').textContent = vm.kwhInterval
    ? `Interval: ${fmt(vm.kwhInterval.lower_kwh, 0)}–${fmt(vm.kwhInterval.upper_kwh, 0)} kWh (±${fmt(vm.kwhInterval.worst_observed_relative_error_pct, 0)}%)`
    : vm.lostKwh != null
      ? 'No interval available for this record.'
      : (vm.lostKwhUnavailableReason || '—');
  if ($('model-name')) $('model-name').textContent = 'single reference turbine';

  const svc = vm.selfValidationContext;
  if ($('result-wind-error')) {
    $('result-wind-error').textContent = vm.windRmseMs != null
      ? `${fmt(vm.windRmseMs, 2)} / ${fmt(vm.windMaeMs, 2)} m/s (checked on a different window with known data)`
      : svc
        ? `Not computable for this window (no recorded truth exists) — typically ${fmt(svc.windRmseMin, 1)}–${fmt(svc.windRmseMax, 1)} m/s wind RMSE, from the n=${svc.n} shown-window backtest on the real BayWa targets (see Methodology)`
        : 'Not applicable — no ground truth for this window, by construction';
  }
  if ($('result-power-error')) {
    $('result-power-error').textContent = vm.powerRmseKw != null
      ? `${fmt(vm.powerRmseKw, 0)} / ${fmt(vm.powerMaeKw, 0)} kW (checked on a different window with known data)`
      : 'Not applicable — no ground truth for this window, by construction (no comparable power-deviation backtest available)';
  }
  if ($('result-energy-error')) {
    $('result-energy-error').textContent = vm.energyErrorPct != null
      ? `${fmt(vm.energyErrorPct, 1)}%`
      : svc
        ? `Not computable for this window (no recorded truth exists) — ranges ${fmt(svc.energyErrMin, 1)}–${fmt(svc.energyErrMax, 1)}% across the n=${svc.n} real validation targets (see Methodology)`
        : 'Not applicable — no ground truth for this window, by construction';
  }
  if ($('gate-count')) $('gate-count').textContent = vm.source === 'official' ? 'Real BayWa T3 submission' : 'Your own upload — not independently reviewed';

  renderCommercialPanel(vm);
  renderOverlayChart(vm.overlaySeries, vm.windowStartUtc, vm.windowEndUtc);

  if (vm.lostKwh != null && vm.lossSeries) {
    $('loss-chart-unavailable').hidden = true;
    renderLossChart(vm.lossSeries, vm.lostKwh);
  } else {
    $('loss-chart-wrap').innerHTML = '<div class="loading">No energy estimate to chart.</div>';
    $('loss-chart-range').textContent = '—';
    $('loss-chart-unavailable').hidden = false;
  }
}

function renderOverlayChart(overlay, windowStartUtc, windowEndUtc) {
  const wrap = $('overlay-chart-wrap');
  if (!wrap) return;
  lastOverlayArgs = [overlay, windowStartUtc, windowEndUtc];
  const points = (overlay && overlay.points) || [];
  if (!points.length) { wrap.innerHTML = '<div class="loading">No overlay series available for this run.</div>'; $('overlay-chart-range').textContent = '—'; return; }

  const width = 1000, height = 240, pad = { left:42, right:18, top:12, bottom:30 };
  const values = points.flatMap((p) => [p.target_ms, p.reference_ms, p.reconstructed_ms]).filter((v) => v != null);
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

  const hiddenClass = (key) => (overlayLineVisible[key] ? '' : ' is-hidden');
  wrap.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Target, reference, and reconstructed wind speed, with the outage window shaded"><g class="chart-grid">${grid}</g>${band}<path class="chart-truth${hiddenClass('reference_ms')}" d="${linePath('reference_ms')}"/><path class="chart-reconstructed${hiddenClass('target_ms')}" d="${linePath('target_ms')}"/><path class="chart-predicted-line${hiddenClass('reconstructed_ms')}" d="${linePath('reconstructed_ms')}"/><line class="chart-crosshair" x1="0" x2="0" y1="${pad.top}" y2="${height-pad.bottom}"/><rect class="chart-hit-area" x="${pad.left}" y="${pad.top}" width="${width-pad.left-pad.right}" height="${height-pad.top-pad.bottom}"/><text class="axis-label" x="${pad.left}" y="${height-5}">${shortDate(points[0].timestamp_utc)}</text><text class="axis-label" text-anchor="end" x="${width-pad.right}" y="${height-5}">${shortDate(points[points.length-1].timestamp_utc)}</text></svg>`;
  $('overlay-chart-range').textContent = `${points.length} plotted points`;

  const svg = wrap.querySelector('svg'), crosshair = svg.querySelector('.chart-crosshair'), tooltip = $('overlay-chart-tooltip');
  svg.querySelector('.chart-hit-area').addEventListener('mousemove', (event) => {
    const box = svg.getBoundingClientRect(), ratio = (event.clientX - box.left) / box.width, i = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    const point = points[i], xPos = x(i);
    crosshair.setAttribute('x1', xPos); crosshair.setAttribute('x2', xPos); crosshair.classList.add('visible');
    const reconstructedLine = point.reconstructed_ms != null ? `<span>Reconstructed: ${fmt(point.reconstructed_ms, 2)} m/s</span>` : '';
    tooltip.innerHTML = `<strong>${new Date(point.timestamp_utc).toLocaleString('en-GB', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'UTC'})} UTC</strong><span>Target: ${point.target_ms != null ? fmt(point.target_ms, 2) + ' m/s' : 'gap — reconstructed from reference'}</span><span>Reference: ${point.reference_ms != null ? fmt(point.reference_ms, 2) + ' m/s' : '—'}</span>${reconstructedLine}`;
    tooltip.style.left = `${Math.min(Math.max(event.clientX - box.left + 12, 8), box.width - 190)}px`; tooltip.classList.add('visible');
  });
  svg.querySelector('.chart-hit-area').addEventListener('mouseleave', () => { crosshair.classList.remove('visible'); tooltip.classList.remove('visible'); });
}

// ---- Methodology detail (Page 2): validation and method content for the real
// BayWa T3 record only -- a live upload's own result stays on Page 1 and is not
// repeated here.
function renderMethodologyDetail(a) {
  $('method-version').textContent = a.provenance.method_version;
  $('method-reconstruction').textContent = a.method.reconstruction;
  $('method-energy').textContent = a.method.energy_integration;
  $('limitations').innerHTML = a.limitations.map((item) => `<li>${item}</li>`).join('');

  // 2026-10-24 (Anna's correction): procedural, not persuasive -- a plain,
  // factual, ordered list of the validation steps taken, not a pass/fail
  // gate UI with reasons/colors. Still driven by the same gate data so it
  // stays accurate; a step not yet evaluated says so plainly, in the same
  // neutral list, not flagged with its own styling.
  if (a.review.gates && $('trust-gates')) {
    $('trust-gates').innerHTML = a.review.gates.map((g) => {
      const detail = g.state === 'not_evaluated' ? (g.reason || g.detail || '') : (g.detail || '');
      return `<li><strong>${esc(g.label)}</strong> — ${esc(detail)}</li>`;
    }).join('');
  }
}

function tierCardsHtml(tiers) {
  return tiers.map((t) => `<article class="tier"><span class="tier-tag">${esc(t.tag)}</span><h3>${esc(t.name)}</h3><div class="tier-value">${esc(t.headline_value)}<small>${esc(t.headline_label)}</small></div><div class="tier-stats">${t.stats.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div>${t.framing ? `<p class="tier-frame"><b>Framing:</b> ${esc(t.framing)}</p>` : ''}${t.does_not_prove ? `<p class="tier-frame"><b>Check before relying on this:</b> ${esc(t.does_not_prove)}</p>` : ''}</article>`).join('');
}

// 2026-10-24: restored as a collapsed <details> disclosure (Anna's call --
// keep it, just not prominent) after an earlier round removed it entirely.
// Still load-bearing: the n=3 observed-error bracket and the Limitations
// text both reference this comparison.
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
    // 2026-10-24 minimalism pass: the generic "one of the three real BayWa
    // targets" framing and the "every target reconstructs well, see T1"
    // caveat were identical, word-for-word, on both the T2 and T3 cards --
    // said once now, in the section intro above the grid, instead of twice.
    framing: t.is_overview_record
      ? `${t.target_turbine} is the primary graded target for this submission. It was selected for presentation because its shown-window self-validation error (${fmt(t.energy_relative_error_pct, 2)}%) is the median of the three targets' errors — a reasonable match to expect for the ungraded hidden window too.`
      : t.is_outlier
        ? 'This target’s error is materially worse than the other two.'
        : '',
    does_not_prove: t.is_outlier ? data.outlier_explanation : '',
  }));
  $('baywa-targets-grid').innerHTML = tierCardsHtml(cards);
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

function renderUploadSelectionSummary(files) {
  const summary = $('upload-selection-summary');
  if (!summary) return;
  if (!files.length) { summary.hidden = true; summary.innerHTML = ''; return; }
  summary.hidden = false;
  summary.innerHTML = '<p class="small-note loading-row"><span class="spinner" aria-hidden="true"></span>Checking selected files…</p>';
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
      const selected = okTargets[Number(button.dataset.index)];
      currentActiveSource = 'upload';
      currentActiveTargetEntry = selected;
      renderResultView(buildResultViewModel('upload', selected));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
}

// ---- Start/Result state (2026-10-24, Anna's explicit ask): the Analysis page
// shows nothing hardcoded on load -- a clean "Start your analysis" prompt with
// an explicit "Load BayWa demo" button, not an automatic official record. The
// result view (whichever source) only appears once the user acts.
function showStartState() {
  $('start-state').hidden = false;
  $('result-state').hidden = true;
}

function showResultState() {
  $('start-state').hidden = true;
  $('result-state').hidden = false;
}

// Tracks whichever result is currently on screen, globally -- read by the
// report-generation button (physically on the Methodology page) so it always
// reports on what the user is actually looking at, not a hardcoded lookup.
let currentActiveSource = null; // 'official' | 'upload'
let currentActiveTargetEntry = null; // raw /run target dict, only set for 'upload'
let currentActiveOfficialTargetId = null; // e.g. 'T3', only set for 'official'

function loadBaywaDemo() {
  renderResultView(buildResultViewModel('official', window.WINDLENS_DATA));
  lastExportPayload = window.WINDLENS_DATA;
  currentActiveSource = 'official';
  currentActiveTargetEntry = null;
  currentActiveOfficialTargetId = window.WINDLENS_DATA?.assessment?.incident?.asset_id || null;
  $('upload-error').hidden = true;
  if ($('upload-targets-summary')) { $('upload-targets-summary').hidden = true; $('upload-targets-list').innerHTML = ''; }
  showResultState();
}

function initUploadForm() {
  const form = $('upload-form');
  if (!form) return;
  $('upload-files')?.addEventListener('change', (event) => renderUploadSelectionSummary(event.target.files));
  $('load-demo-button')?.addEventListener('click', loadBaywaDemo);
  $('back-to-start-button')?.addEventListener('click', showStartState);
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
      currentActiveSource = 'upload';
      currentActiveTargetEntry = ok;
      currentActiveOfficialTargetId = null;
      renderUploadTargetsSummary(result.targets);
      renderResultView(buildResultViewModel('upload', ok));
      if (extraErrors.length) {
        $('upload-error').hidden = false;
        $('upload-error').textContent = `Showing ${ok.target_turbine} above. ${extraErrors.length} other target(s) in this upload could not be reconstructed: ${extraErrors.map((t) => `${t.target_turbine} (${t.error})`).join('; ')}`;
      }
      showResultState();
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
    // 2026-10-24 correctness fix: this used to always read the hardcoded
    // official demo's turbine id, regardless of what the user was actually
    // looking at -- a report requested after an upload silently showed the
    // official T3 record (or errored for a non-T1/T2/T3 turbine). Now it
    // follows currentActiveSource/currentActiveTargetEntry, set by whichever
    // result was last shown on the Analysis page (demo or a specific
    // uploaded/selected target).
    const isUpload = currentActiveSource === 'upload' && currentActiveTargetEntry;
    const target = isUpload ? currentActiveTargetEntry.target_turbine : (currentActiveOfficialTargetId || window.WINDLENS_DATA?.assessment?.incident?.asset_id);
    if (!target) {
      $('insurance-report-text').textContent = 'No result is currently active -- go to the Analysis page, load the BayWa demo or upload your own data, then generate the report again.';
      panel.hidden = false;
      return;
    }
    panel.hidden = false;
    $('insurance-report-text').textContent = 'Generating…';
    try {
      // 2026-10-24 correctness fix: pass the SAME price the page is currently
      // showing for this result (read from the live price input, not the
      // cached default) so the report never shows a different financial
      // figure than the page it was generated from.
      const priceParams = new URLSearchParams({
        price_eur_per_mwh: $('commercial-price').value,
        price_source: currentPriceSourceLabel,
        price_is_real: String(currentPriceIsReal),
      });
      const response = isUpload
        ? await fetch(`/insurance-report-for-upload?${priceParams}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentActiveTargetEntry),
          })
        : await fetch(`/insurance-report?target=${encodeURIComponent(target)}&${priceParams}`);
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
    // 2026-10-24 (Anna's explicit ask): the Analysis page shows nothing
    // hardcoded on load -- Start state (upload prompt + explicit "Load BayWa
    // demo" button) is the default; the official record only renders once
    // the user acts. The Methodology page's validation detail for the real
    // T3 submission is unconditional, since that page is specifically about
    // the official record regardless of what the Analysis page is showing.
    showStartState();
    lastExportPayload = window.WINDLENS_DATA;
    renderMethodologyDetail(window.WINDLENS_DATA.assessment);
    renderBaywaComparison(window.WINDLENS_DATA.baywa_comparison);
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

document.querySelectorAll('.legend-toggle[data-line]').forEach((button) => {
  button.addEventListener('click', (event) => {
    const key = event.currentTarget.dataset.line;
    overlayLineVisible[key] = !overlayLineVisible[key];
    event.currentTarget.setAttribute('aria-pressed', String(overlayLineVisible[key]));
    if (lastOverlayArgs) renderOverlayChart(...lastOverlayArgs);
  });
});

boot();
initUploadForm();
initInsuranceReport();
