const pptxgen = require('pptxgenjs');
const fs = require('fs');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_16x9';
pptx.author = 'WindLens';
pptx.company = 'WindLens / BayWa r.e. Energy & AI Hackathon';
pptx.subject = 'WindLens methodology';
pptx.title = 'WindLens — Evidence-first wind outage reconstruction';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Aptos Display',
  bodyFontFace: 'Aptos',
  lang: 'en-US'
};

const C = {
  green: '008C46',
  greenDark: '006B37',
  greenPale: 'E8F3EC',
  greenMid: 'B8DCC6',
  charcoal: '333333',
  ink: '1E2A24',
  muted: '607067',
  line: 'D8E2DC',
  white: 'FFFFFF',
  amber: 'F2B544',
  amberPale: 'FFF5D9',
  red: 'B84A3A',
  redPale: 'FBE9E6'
};
const W = 10, H = 5.625;
const evidence = JSON.parse(fs.readFileSync('workspace/evidence-tiers-data.js', 'utf8').replace(/^window\.WINDLENS_EVIDENCE_TIERS\s*=\s*/, '').replace(/;\s*$/, ''));

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, { x, y, w, h, margin: 0, breakLine: false, fontFace: opts.fontFace || 'Aptos', fontSize: opts.fontSize || 16, color: opts.color || C.charcoal, bold: opts.bold || false, italic: opts.italic || false, align: opts.align || 'left', valign: opts.valign || 'top', fit: 'shrink', paraSpaceAfterPt: 0, ...opts });
}
function box(slide, x, y, w, h, fill, line = fill, radius = false) {
  slide.addShape(radius ? pptx.ShapeType.roundRect : pptx.ShapeType.rect, { x, y, w, h, rectRadius: radius ? 0.08 : undefined, fill: { color: fill }, line: { color: line, width: 1 } });
}
function line(slide, x, y, w, h, color = C.line, width = 1, dash = 'solid') {
  slide.addShape(pptx.ShapeType.line, { x, y, w, h, line: { color, width, dashType: dash, beginArrowType: 'none', endArrowType: 'none' } });
}
function logo(slide, dark = false) {
  box(slide, 0.45, 0.28, 0.48, 0.48, C.green, C.green);
  addText(slide, 'BayWa', 0.49, 0.38, 0.40, 0.12, { fontSize: 8, color: C.white, bold: true, align: 'center' });
  addText(slide, 'WindLens', 1.06, 0.34, 1.1, 0.2, { fontSize: 12, color: dark ? C.white : C.charcoal, bold: true });
}
function header(slide, n, section, title, dark = false) {
  logo(slide, dark);
  addText(slide, `${String(n).padStart(2, '0')} / 07   ${section.toUpperCase()}`, 8.1, 0.36, 1.4, 0.15, { fontSize: 8, color: dark ? 'CFE8D7' : C.muted, bold: true, align: 'right', charSpacing: 1.5 });
  addText(slide, title, 0.62, 0.98, 8.8, 0.55, { fontSize: 28, color: dark ? C.white : C.ink, bold: true, fontFace: 'Aptos Display' });
  line(slide, 0.62, 1.66, 8.76, 0, dark ? '6EA985' : C.greenMid, 2);
}
function footer(slide, n, dark = false) {
  const y = 5.28;
  line(slide, 0.62, y, 8.76, 0, dark ? '5A8D6D' : C.line, 1);
  addText(slide, 'WindLens · Evidence-first reconstruction', 0.62, 5.36, 4.0, 0.12, { fontSize: 7.5, color: dark ? 'CFE8D7' : C.muted });
  addText(slide, `${String(n).padStart(2, '0')} / 07`, 8.65, 5.36, 0.7, 0.12, { fontSize: 7.5, color: dark ? 'CFE8D7' : C.muted, align: 'right' });
}
function callout(slide, x, y, w, h, label, body, tone = 'green') {
  const fill = tone === 'amber' ? C.amberPale : tone === 'red' ? C.redPale : C.greenPale;
  const accent = tone === 'amber' ? C.amber : tone === 'red' ? C.red : C.green;
  box(slide, x, y, w, h, fill, fill, true);
  slide.addShape(pptx.ShapeType.rect, { x, y, w: 0.08, h, fill: { color: accent }, line: { color: accent } });
  addText(slide, label.toUpperCase(), x + 0.22, y + 0.16, w - 0.34, 0.16, { fontSize: 8, color: accent, bold: true, charSpacing: 1.2 });
  addText(slide, body, x + 0.22, y + 0.42, w - 0.34, h - 0.55, { fontSize: 11.5, color: C.charcoal, breakLine: false, valign: 'mid' });
}
function step(slide, x, y, num, label, detail, active = false) {
  slide.addShape(pptx.ShapeType.ellipse, { x, y, w: 0.46, h: 0.46, fill: { color: active ? C.green : C.greenPale }, line: { color: C.green, width: 1.5 } });
  addText(slide, String(num), x, y + 0.08, 0.46, 0.18, { fontSize: 13, color: active ? C.white : C.greenDark, bold: true, align: 'center' });
  addText(slide, label, x + 0.62, y - 0.02, 1.85, 0.18, { fontSize: 13, color: C.ink, bold: true });
  addText(slide, detail, x + 0.62, y + 0.22, 1.85, 0.42, { fontSize: 9.5, color: C.muted });
}

// 1 — Detect
{
  const s = pptx.addSlide(); s.background = { color: C.green };
  header(s, 1, 'Detect', 'Find the gap', true);
  addText(s, 'A missing interval is evidence of missing telemetry — not proof of why production stopped.', 0.65, 1.92, 5.4, 0.6, { fontSize: 20, color: C.white, bold: true, fontFace: 'Aptos Display' });
  // visual timeline
  box(s, 6.45, 1.98, 2.65, 1.45, C.white, C.white, true);
  addText(s, 'TURBINE T1 · SHOWN WINDOW', 6.7, 2.17, 2.1, 0.14, { fontSize: 8, color: C.green, bold: true, charSpacing: 1 });
  line(s, 6.75, 2.75, 2.05, 0, C.line, 2);
  box(s, 6.82, 2.62, 0.58, 0.26, C.greenPale, C.greenPale);
  box(s, 7.62, 2.62, 0.75, 0.26, C.green, C.green);
  box(s, 8.58, 2.62, 0.23, 0.26, C.greenPale, C.greenPale);
  addText(s, 'healthy', 6.75, 3.0, 0.7, 0.14, { fontSize: 8, color: C.muted });
  addText(s, 'gap', 7.86, 3.0, 0.35, 0.14, { fontSize: 8, color: C.greenDark, bold: true, align: 'center' });
  addText(s, 'healthy', 8.55, 3.0, 0.7, 0.14, { fontSize: 8, color: C.muted, align: 'right' });
  callout(s, 0.65, 3.2, 4.55, 1.12, 'What you can rely on', 'The outage window shown for this record comes directly from BayWa’s own data.', 'green');
  callout(s, 5.45, 3.62, 3.65, 0.96, 'What to check yourself', 'A gap does not identify the cause. Confirm sensor fault vs. mechanical outage independently.', 'amber');
  footer(s, 1, true);
}

// 2 — Select
{
  const s = pptx.addSlide(); s.background = { color: C.white };
  header(s, 2, 'Select', 'Pick a reference turbine');
  addText(s, 'Behavior first. Geography only as a plausibility check.', 0.65, 1.88, 4.5, 0.32, { fontSize: 17, color: C.greenDark, bold: true });
  const xs = [0.9, 2.65, 4.4, 6.15];
  ['T1 target', 'O1', 'O2', 'H5'].forEach((label, i) => {
    const active = i === 1; box(s, xs[i], 2.56, 1.12, 0.72, active ? C.green : C.greenPale, active ? C.green : C.greenPale, true);
    addText(s, label, xs[i], 2.76, 1.12, 0.16, { fontSize: 12, color: active ? C.white : C.greenDark, bold: true, align: 'center' });
    if (i < 3) line(s, xs[i] + 1.12, 2.92, xs[i + 1] - xs[i] - 1.12, 0, C.greenMid, 2);
  });
  addText(s, 'pre-outage history', 2.72, 3.46, 3.0, 0.16, { fontSize: 9, color: C.muted, align: 'center', italic: true });
  callout(s, 0.65, 4.05, 4.15, 0.78, 'Selected reference', 'O1 · holdout R² 0.419 · 8,424 paired observations', 'green');
  callout(s, 5.02, 4.05, 4.08, 0.78, 'Limitation', 'No turbine-location registry exists in this BayWa dataset.', 'amber');
  footer(s, 2);
}

// 3 — Estimate
{
  const s = pptx.addSlide(); s.background = { color: C.white };
  header(s, 3, 'Estimate', 'Reconstruct wind, then power');
  step(s, 0.78, 2.15, 1, 'Reference wind', 'O1 reports\nwind readings.', true);
  step(s, 3.18, 2.15, 2, 'Target wind', 'Fit a transparent\nmeasure–correlate–predict line.');
  step(s, 5.58, 2.15, 3, 'Target power', 'Apply T1’s own\npre-outage power curve.');
  step(s, 7.98, 2.15, 4, 'Lost energy', 'Integrate expected\npower into kWh.');
  line(s, 1.24, 3.08, 1.72, 0, C.green, 2); line(s, 3.64, 3.08, 1.72, 0, C.green, 2); line(s, 6.04, 3.08, 1.72, 0, C.green, 2);
  addText(s, 'A calculation you can inspect end to end: every number traces back to a real reading.', 0.78, 3.65, 5.7, 0.55, { fontSize: 19, color: C.ink, bold: true, fontFace: 'Aptos Display' });
  callout(s, 6.78, 3.65, 2.32, 1.04, 'Check before reuse', 'No single method wins everywhere. Review alternative methods before assuming this is universal.', 'amber');
  footer(s, 3);
}

// 4 — Gate
{
  const s = pptx.addSlide(); s.background = { color: C.white };
  header(s, 4, 'Gate', 'Check the result before trusting it');
  const gates = [
    ['01', 'Input quality', 'Are the source readings usable?'],
    ['02', 'Reference overlap', 'Does the reference explain the target?'],
    ['03', 'Tested range', 'Is this inside validated conditions?'],
    ['04', 'Completeness', 'Are enough points reconstructed?'],
    ['05', 'Calibration', 'Does uncertainty behave honestly?']
  ];
  gates.forEach((g, i) => {
    const x = 0.72 + i * 1.78;
    box(s, x, 2.08, 1.48, 1.42, i === 4 ? C.amberPale : C.greenPale, i === 4 ? C.amber : C.greenMid, true);
    addText(s, g[0], x + 0.16, 2.24, 0.34, 0.2, { fontSize: 14, color: i === 4 ? C.amber : C.green, bold: true });
    addText(s, g[1], x + 0.16, 2.62, 1.1, 0.3, { fontSize: 12, color: C.ink, bold: true });
    addText(s, g[2], x + 0.16, 3.04, 1.12, 0.26, { fontSize: 8.5, color: C.muted });
  });
  addText(s, 'A gate is not a guarantee. It is an honest boundary around the number.', 0.78, 4.08, 6.2, 0.34, { fontSize: 19, color: C.ink, bold: true, fontFace: 'Aptos Display' });
  callout(s, 7.25, 3.95, 1.85, 0.78, 'Rule', 'Failed or unevaluated checks stay visible.', 'green');
  footer(s, 4);
}

// 5 — Evidence
{
  const s = pptx.addSlide(); s.background = { color: C.greenDark };
  header(s, 5, 'Evidence', 'Three tiers, never one number', true);
  const widths = [2.68, 2.68, 2.68];
  evidence.tiers.forEach((t, i) => {
    const x = 0.72 + i * 2.92;
    box(s, x, 1.95, widths[i], 2.62, i === 2 ? '0A5A31' : C.green, i === 2 ? '5EA67A' : '5EA67A', true);
    addText(s, t.tag.toUpperCase(), x + 0.22, 2.17, 2.1, 0.16, { fontSize: 8, color: 'CFE8D7', bold: true, charSpacing: 1.2 });
    addText(s, t.headline_value, x + 0.22, 2.5, 1.4, 0.55, { fontSize: 34, color: C.white, bold: true, fontFace: 'Aptos Display' });
    addText(s, 'WAPE', x + 1.75, 2.82, 0.58, 0.18, { fontSize: 10, color: C.greenMid, bold: true });
    addText(s, t.name, x + 0.22, 3.24, 2.18, 0.42, { fontSize: 12, color: C.white, bold: true });
    addText(s, i === 0 ? 'same-farm baseline' : i === 1 ? 'same-farm stress test' : 'cross-farm floor proxy', x + 0.22, 3.84, 2.1, 0.2, { fontSize: 9, color: 'CFE8D7' });
  });
  addText(s, 'The questions differ, so the numbers stay separate.', 0.75, 4.88, 7.0, 0.2, { fontSize: 15, color: C.white, bold: true });
  footer(s, 5, true);
}

// 6 — Limits
{
  const s = pptx.addSlide(); s.background = { color: C.white };
  header(s, 6, 'Limits', 'What this cannot tell you yet');
  addText(s, 'The evidence brackets distance — it does not close the neighbouring-farm gap.', 0.68, 1.9, 7.6, 0.34, { fontSize: 18, color: C.ink, bold: true });
  line(s, 1.2, 3.1, 7.15, 0, C.green, 4);
  [
    { x: 1.35, label: 'Tier 1', km: '~0.5 km', sub: 'same-farm baseline' },
    { x: 3.15, label: 'Tier 2', km: '<1 km', sub: 'stress-test ceiling' },
    { x: 8.0, label: 'Tier 3', km: '~399 km', sub: 'cross-farm floor' }
  ].forEach((p, i) => {
    s.addShape(pptx.ShapeType.ellipse, { x: p.x, y: 2.87, w: 0.46, h: 0.46, fill: { color: i === 2 ? C.amber : C.green }, line: { color: i === 2 ? C.amber : C.green } });
    addText(s, p.label, p.x - 0.25, 3.55, 0.95, 0.17, { fontSize: 10, color: C.greenDark, bold: true, align: 'center' });
    addText(s, p.km, p.x - 0.45, 3.82, 1.35, 0.24, { fontSize: 18, color: C.ink, bold: true, align: 'center' });
    addText(s, p.sub, p.x - 0.58, 4.15, 1.6, 0.2, { fontSize: 8.5, color: C.muted, align: 'center' });
  });
  box(s, 5.0, 2.62, 2.45, 0.96, C.amberPale, C.amber, true);
  addText(s, 'UNTESTED GAP', 5.22, 2.82, 1.95, 0.15, { fontSize: 8, color: C.amber, bold: true, charSpacing: 1.1, align: 'center' });
  addText(s, '2–100 km', 5.22, 3.08, 1.95, 0.22, { fontSize: 16, color: C.ink, bold: true, align: 'center' });
  callout(s, 0.72, 4.62, 8.35, 0.46, 'Honest boundary', 'The BayWa challenge’s actual whole-farm / neighbouring-farm scenario remains untested by this prototype.', 'amber');
  footer(s, 6);
}

// 7 — Opportunities
{
  const s = pptx.addSlide(); s.background = { color: C.green };
  header(s, 7, 'Opportunities', 'What we would build next', true);
  const items = [
    ['01', 'Calibrated uncertainty interval', 'More held-out BayWa data to build one honestly.'],
    ['02', 'Automatic outage-cause classification', 'Separate sensor faults from real mechanical outages.'],
    ['03', 'A genuine neighbouring-farm test', 'A verified nearby second farm — not a distant proxy.']
  ];
  items.forEach((it, i) => {
    const y = 1.96 + i * 0.9;
    addText(s, it[0], 0.78, y + 0.03, 0.42, 0.24, { fontSize: 14, color: C.greenMid, bold: true });
    addText(s, it[1], 1.45, y, 4.2, 0.22, { fontSize: 17, color: C.white, bold: true });
    addText(s, it[2], 1.45, y + 0.31, 5.4, 0.2, { fontSize: 10.5, color: 'D7EDE0' });
    line(s, 1.45, y + 0.67, 6.55, 0, '5EA67A', 1);
  });
  box(s, 7.45, 2.0, 1.72, 2.38, C.white, C.white, true);
  addText(s, 'BUILD\nWITH\nEVIDENCE', 7.7, 2.45, 1.2, 1.2, { fontSize: 20, color: C.greenDark, bold: true, align: 'center', valign: 'mid', fontFace: 'Aptos Display' });
  addText(s, 'WindLens prototype · October 2026', 0.78, 4.75, 4.0, 0.16, { fontSize: 9, color: 'D7EDE0' });
  footer(s, 7, true);
}

pptx.writeFile({ fileName: 'WindLens_BayWa_Methodology.pptx' });
