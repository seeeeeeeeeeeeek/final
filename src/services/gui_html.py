from __future__ import annotations


_NAV_ITEMS = (
    ("home", "Home"),
    ("live", "Live Analysis"),
    ("detail", "Analysis Detail"),
    ("replay", "Replay Lab"),
    ("settings", "Strategy Settings"),
    ("tradingview", "TradingView Setup"),
    ("history", "History"),
    ("diagnostics", "Diagnostics"),
)


def _nav_markup() -> str:
    buttons: list[str] = []
    for page_id, label in _NAV_ITEMS:
        active = ' class="active"' if page_id == "home" else ""
        buttons.append(f'<button{active} data-page="{page_id}">{label}</button>')
    return "\n".join(buttons)


def build_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>stocknogs</title>
  <style>
    :root {
      --bg: #090b14;
      --bg-2: #121727;
      --panel: rgba(17, 22, 37, 0.92);
      --panel-2: rgba(22, 28, 47, 0.96);
      --text: #eef2ff;
      --muted: #93a0c4;
      --line: rgba(111, 130, 189, 0.24);
      --violet: #8a5cff;
      --violet-2: #b284ff;
      --cyan: #3ac8ff;
      --mint: #47d7ac;
      --amber: #ffbf5e;
      --danger: #ff6f9f;
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.32);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(138, 92, 255, 0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(58, 200, 255, 0.12), transparent 24%),
        linear-gradient(180deg, #070911 0%, #0b1020 100%);
      min-height: 100vh;
    }
    .app { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
    .sidebar {
      padding: 28px 20px;
      border-right: 1px solid var(--line);
      background: rgba(8, 11, 21, 0.86);
      backdrop-filter: blur(16px);
    }
    .brand { font-size: 1.5rem; font-weight: 800; letter-spacing: 0.02em; }
    .brand span { color: var(--violet-2); }
    .tagline { margin: 8px 0 22px; color: var(--muted); line-height: 1.5; font-size: 0.95rem; }
    .sidebar-label { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.73rem; color: var(--muted); margin-bottom: 10px; }
    .nav button {
      display: flex;
      align-items: center;
      width: 100%;
      margin-bottom: 10px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--text);
      cursor: pointer;
      font-size: 0.96rem;
    }
    .nav button.active {
      background: linear-gradient(135deg, rgba(138, 92, 255, 0.20), rgba(58, 200, 255, 0.12));
      border-color: rgba(138, 92, 255, 0.36);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    .main { padding: 28px; }
    .page { display: none; animation: fadeIn 0.22s ease; }
    .page.active { display: block; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
    .page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 18px; }
    .page-header h1 { margin: 0; font-size: 1.9rem; }
    .page-header p { margin: 8px 0 0; color: var(--muted); max-width: 760px; }
    .grid { display: grid; gap: 16px; }
    .cards { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
    .two-col { grid-template-columns: 1.15fr 0.85fr; }
    .card {
      background: linear-gradient(180deg, rgba(18, 23, 39, 0.94), rgba(13, 17, 31, 0.98));
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 18px;
      box-shadow: var(--shadow);
    }
    .card h2, .card h3, .card h4 { margin: 0 0 10px; }
    .muted { color: var(--muted); }
    .small { font-size: 0.9rem; }
    .hero {
      padding: 22px;
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(138, 92, 255, 0.18), rgba(58, 200, 255, 0.08) 55%, rgba(71, 215, 172, 0.08));
      border: 1px solid rgba(138, 92, 255, 0.28);
    }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    .button-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    button.action, button.secondary, button.ghost { border-radius: 14px; padding: 11px 16px; cursor: pointer; font-weight: 600; }
    button.action { border: none; color: white; background: linear-gradient(135deg, var(--violet), var(--cyan)); box-shadow: 0 12px 26px rgba(95, 87, 255, 0.24); }
    button.secondary { border: 1px solid rgba(138, 92, 255, 0.32); color: var(--text); background: rgba(138, 92, 255, 0.10); }
    button.ghost { border: 1px solid var(--line); color: var(--text); background: transparent; }
    input, select, textarea {
      width: 100%;
      border-radius: 14px;
      border: 1px solid var(--line);
      padding: 11px 12px;
      background: rgba(7, 11, 20, 0.88);
      color: var(--text);
    }
    textarea { min-height: 240px; resize: vertical; font-family: "Cascadia Code", "Consolas", monospace; }
    .kpi-label { color: var(--muted); font-size: 0.84rem; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
    .kpi-value { font-size: 1.38rem; font-weight: 700; }
    .pill, .score-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
      font-size: 0.86rem;
    }
    .score-chip { background: rgba(58, 200, 255, 0.08); border-color: rgba(58, 200, 255, 0.18); }
    .status-qualified { color: var(--mint); }
    .status-skipped { color: var(--amber); }
    .status-rejected, .status-no_trade { color: var(--danger); }
    .record-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: rgba(22, 28, 47, 0.72);
      cursor: pointer;
    }
    .record-card:hover { border-color: rgba(138, 92, 255, 0.34); }
    .table { display: grid; gap: 10px; }
    .table-header, .table-row {
      display: grid;
      grid-template-columns: 100px 150px 120px 110px 1fr;
      gap: 12px;
      align-items: start;
      padding: 10px 12px;
      border-radius: 14px;
    }
    .table-header { color: var(--muted); font-size: 0.85rem; }
    .table-row { background: rgba(22, 28, 47, 0.66); border: 1px solid var(--line); cursor: pointer; }
    .details-stack { display: grid; gap: 14px; }
    details.collapsible { border: 1px solid var(--line); border-radius: 16px; background: rgba(17, 22, 37, 0.72); padding: 0 14px; }
    details.collapsible summary { list-style: none; cursor: pointer; padding: 14px 0; font-weight: 700; }
    details.collapsible summary::-webkit-details-marker { display: none; }
    .kv { display: grid; gap: 6px; padding-bottom: 14px; }
    .kv-row { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; border-top: 1px solid var(--line); }
    .kv-row .label { color: var(--muted); }
    .mono { white-space: pre-wrap; word-break: break-word; font-family: "Cascadia Code", "Consolas", monospace; }
    .empty-state { padding: 24px; border-radius: 22px; border: 1px dashed rgba(138, 92, 255, 0.35); background: rgba(138, 92, 255, 0.07); }
    .helper-list { margin: 0; padding-left: 18px; color: var(--muted); line-height: 1.7; }
    .settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
    .section-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
    .footer-note { margin-top: 12px; color: var(--muted); font-size: 0.9rem; }
    .summary-stack { display: grid; gap: 8px; margin-top: 12px; }
    .summary-line { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; border-top: 1px solid var(--line); }
    .summary-line strong { color: var(--muted); font-weight: 600; }
    .helper-copy { color: var(--muted); margin-top: 6px; line-height: 1.6; }
    .status-panel { min-height: 220px; }
    .status-line { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-top: 1px solid var(--line); }
    .status-line strong { color: var(--muted); font-weight: 600; }
    .action-card {
      padding: 22px;
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(138, 92, 255, 0.18), rgba(58, 200, 255, 0.10), rgba(71, 215, 172, 0.08));
      border: 1px solid rgba(138, 92, 255, 0.28);
      box-shadow: var(--shadow);
    }
    .chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .chip-soft {
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--line);
      font-size: 0.84rem;
      color: var(--muted);
    }
    .bullet-list { margin: 12px 0 0; padding-left: 18px; line-height: 1.6; }
    .subtle-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-top: 14px; }
    .mini-card { border: 1px solid var(--line); border-radius: 16px; padding: 14px; background: rgba(255,255,255,0.03); }
    .mini-card .label { color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.06em; }
    .mini-card .value { margin-top: 8px; font-weight: 700; }
    @media (max-width: 1100px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { border-right: none; border-bottom: 1px solid var(--line); }
      .two-col, .settings-grid { grid-template-columns: 1fr; }
      .table-header, .table-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">stock<span>nogs</span></div>
      <div class="tagline">A local TradingView companion for breakout review, replay, and webhook-driven analysis.</div>
      <div class="sidebar-label">Workspace</div>
      <nav class="nav">""" + _nav_markup() + """</nav>
    </aside>
    <main class="main">
      <section id="home" class="page active">
        <div class="page-header"><div><h1>Home</h1><p>See app status, recent analyses, and the clearest next step when the workspace is still empty.</p></div></div>
        <div id="home-top" class="grid cards"></div>
        <div style="margin-top:16px;" id="home-body"></div>
      </section>
      <section id="live" class="page">
        <div class="page-header"><div><h1>Live Analysis</h1><p>Newest records first, with source, bias, confidence, and the current multi-timeframe thesis.</p></div></div>
        <div class="grid two-col">
          <div class="card">
            <h2>Analyze Ticker</h2>
            <div class="helper-copy">Enter a ticker, choose the source mode, and run a new analysis without refreshing the app.</div>
            <div class="settings-grid" style="margin-top:12px;">
              <div><label>Ticker</label><input id="analyze-symbol" placeholder="NVDA"></div>
              <div><label>Source mode</label><select id="analyze-source-mode"></select></div>
            </div>
            <div class="button-row">
              <button class="action" id="analyze-submit">Analyze</button>
              <button class="ghost" id="open-latest-result">Open latest result</button>
              <button class="ghost" id="clear-current-selection">Clear current selection</button>
            </div>
            <div class="footer-note">Auto and Twelve Data run live analysis. Webhook reuses received webhook records. Replay uses a sample payload. OCR stays disabled until implemented.</div>
          </div>
          <div class="card status-panel">
            <h2>Run Status</h2>
            <div class="helper-copy">See which source path the app is trying, what stage it is in, and whether higher timeframe context is missing.</div>
            <div id="run-status-panel" class="summary-stack"></div>
          </div>
        </div>
        <div class="card" style="margin-top:16px;"><div id="live-signals" class="grid"></div></div>
      </section>
      <section id="detail" class="page">
        <div class="page-header"><div><h1>Analysis Detail</h1><p>Inspect one result in a structured format. Friendly labels appear first, with raw data available below.</p></div></div>
        <div id="detail-shell" class="empty-state">Select a record from Home, Live Signals, or History to open its analysis detail.</div>
      </section>
      <section id="replay" class="page">
        <div class="page-header"><div><h1>Replay Lab</h1><p>Paste a TradingView-style alert, validate it through the same backend path, and inspect the result immediately.</p></div></div>
        <div class="grid two-col">
          <div class="card">
            <div class="section-title">Replay Payload</div>
            <div class="button-row">
              <button class="secondary sample-btn" data-sample="qualified">Qualified example</button>
              <button class="secondary sample-btn" data-sample="no_trade">No-trade example</button>
              <button class="secondary sample-btn" data-sample="skipped">Skipped example</button>
            </div>
            <div style="margin-top:14px;"><textarea id="replay-payload"></textarea></div>
            <div class="button-row">
              <button class="ghost" id="replay-validate">Validate</button>
              <button class="action" id="replay-submit">Submit replay</button>
            </div>
            <div class="footer-note">Replay uses the same validation, mapping, scoring, explanation, and logging path as incoming webhook alerts.</div>
          </div>
          <div class="card"><div class="section-title">Result</div><div id="replay-result" class="muted">No replay submitted yet.</div></div>
        </div>
      </section>
      <section id="settings" class="page">
        <div class="page-header"><div><h1>Strategy Settings</h1><p>Adjust a small set of local thresholds without touching the shipped defaults. Save, reset, or load the demo preset.</p></div></div>
        <div class="card">
          <div class="settings-grid" id="settings-form"></div>
          <div class="button-row">
            <button class="action" id="settings-save">Save</button>
            <button class="ghost" id="settings-reset">Reset to defaults</button>
            <button class="secondary" id="settings-demo">Load demo preset</button>
          </div>
          <div id="settings-result" class="footer-note">Local overrides are stored separately from the core defaults.</div>
        </div>
      </section>
      <section id="tradingview" class="page">
        <div class="page-header"><div><h1>TradingView Setup</h1><p>Use this page when you are ready to connect a TradingView alert to the local receiver.</p></div></div>
        <div id="tradingview-panel" class="grid two-col"></div>
      </section>
      <section id="history" class="page">
        <div class="page-header"><div><h1>History</h1><p>Browse saved records across sessions. Filter by symbol, setup status, or a simple date window.</p></div></div>
        <div class="card">
          <div class="settings-grid">
            <div><label>Symbol</label><input id="history-symbol" placeholder="NVDA"></div>
            <div><label>Setup Status</label><select id="history-status"><option value="">All</option><option value="qualified">Qualified</option><option value="skipped">Skipped</option><option value="rejected">Rejected</option><option value="no_trade">No-trade</option></select></div>
            <div><label>Start date</label><input id="history-start-date" type="date"></div>
            <div><label>End date</label><input id="history-end-date" type="date"></div>
          </div>
          <div class="button-row"><button class="ghost" id="history-refresh">Refresh</button></div>
          <div class="table" style="margin-top:12px;">
            <div class="table-header"><div>Symbol</div><div>Time</div><div>Setup</div><div>Confidence</div><div>Summary</div></div>
            <div id="history-table"></div>
          </div>
        </div>
      </section>
      <section id="diagnostics" class="page">
        <div class="page-header"><div><h1>Diagnostics</h1><p>See source selection, fallback behavior, freshness, missing fields, and current system warnings.</p></div></div>
        <div id="diagnostics-panel" class="grid two-col"></div>
      </section>
    </main>
  </div>
  <script>
    let settingsCache = null;
    let selectedScanId = null;
    let runStatePoller = null;
    function statusClass(status) { return `status-${status}`; }
    function prettyStatus(status) { return String(status || '').replace('_', ' ').replace(/\\b\\w/g, (char) => char.toUpperCase()); }
    function displayStatus(record) { return record.setup_status_label || prettyStatus(record.status); }
    function setPage(pageId) {
      document.querySelectorAll('.page').forEach((page) => page.classList.toggle('active', page.id === pageId));
      document.querySelectorAll('.nav button').forEach((button) => button.classList.toggle('active', button.dataset.page === pageId));
    }
    async function fetchJson(url, options = undefined) {
      const response = await fetch(url, options);
      const payload = await response.json();
      if (!response.ok) { throw new Error(payload.error || 'Request failed.'); }
      return payload;
    }
    function escapeHtml(value) {
      return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }
    function renderTrustSignals(signals) {
      if (!signals || !signals.length) { return ''; }
      return `<div class="chip-row">${signals.map((signal) => `<span class="chip-soft">${escapeHtml(signal)}</span>`).join('')}</div>`;
    }
    function renderReasonBullets(reasons) {
      if (!reasons || !reasons.length) { return '<div class="muted small">No key reasons available yet.</div>'; }
      return `<ul class="bullet-list">${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join('')}</ul>`;
    }
    function renderCompactCard(record) {
      return `<div class="record-card" data-scan-id="${record.scan_id}"><div class="row"><strong>${escapeHtml(record.symbol)}</strong><span class="pill ${statusClass(record.status)}">${escapeHtml(displayStatus(record))}</span><span class="score-chip">${escapeHtml(record.confidence_label)} confidence</span></div><div class="summary-stack"><div class="summary-line"><strong>Direction</strong><span>${escapeHtml(record.bias)}</span></div><div class="summary-line"><strong>Best action</strong><span>${escapeHtml(record.best_action || 'Watch Only')}</span></div><div class="summary-line"><strong>Target</strong><span>${escapeHtml(record.short_term_target || 'Not available yet')}</span></div><div class="summary-line"><strong>Source</strong><span>${escapeHtml(record.source_path?.requested || 'unknown')} -> ${escapeHtml(record.source_path?.used || 'unknown')}</span></div></div>${renderTrustSignals(record.trust_signals)}<div class="helper-copy">${escapeHtml(record.why_it_matters)}</div></div>`;
    }
    function renderLabelValueRows(rows) {
      if (!rows || !rows.length) { return '<div class="muted small">Not available yet.</div>'; }
      return rows.map((row) => `<div class="kv-row"><div class="label">${escapeHtml(row.label)}</div><div>${escapeHtml(row.value)}</div></div>`).join('');
    }
    function renderRunState(state) {
      const runState = state || {};
      const fallbackText = runState.fallback_chain && runState.fallback_chain.length ? runState.fallback_chain.join(' -> ') : 'None';
      const warningItems = runState.warnings && runState.warnings.length ? runState.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join('') : '<li>No warnings</li>';
      const stageItems = runState.completed_steps && runState.completed_steps.length ? runState.completed_steps.map((step) => `<li>${escapeHtml(step)}</li>`).join('') : '<li>Waiting to start</li>';
      return `<div class="summary-line"><strong>Status</strong><span>${escapeHtml(runState.status || 'idle')}</span></div><div class="summary-line"><strong>Ticker</strong><span>${escapeHtml(runState.current_ticker || 'None')}</span></div><div class="summary-line"><strong>Requested source</strong><span>${escapeHtml(runState.source_mode_requested || 'Not selected')}</span></div><div class="summary-line"><strong>Current step</strong><span>${escapeHtml(runState.current_step || 'Waiting to start')}</span></div><div class="summary-line"><strong>Used source</strong><span>${escapeHtml(runState.source_used || 'Not resolved')}</span></div><div class="summary-line"><strong>Coverage</strong><span>${escapeHtml(runState.coverage_text || 'Not available yet')}</span></div><div class="summary-line"><strong>Missing context</strong><span>${escapeHtml((runState.missing_context || []).join(', ') || 'None')}</span></div><div class="summary-line"><strong>Fallback chain</strong><span>${escapeHtml(fallbackText)}</span></div>${runState.failure_reason ? `<div class="summary-line"><strong>Failure</strong><span>${escapeHtml(runState.failure_reason)}</span></div>` : ''}<div class="helper-copy">Completed stages</div><ul class="bullet-list">${stageItems}</ul><div class="helper-copy">Warnings</div><ul class="bullet-list">${warningItems}</ul>`;
    }
    function kvRows(entries) {
      if (!entries || !Object.keys(entries).length) { return '<div class="muted small">Not available yet.</div>'; }
      return Object.entries(entries).map(([key, value]) => `<div class="kv-row"><div class="label">${escapeHtml(key)}</div><div class="mono">${escapeHtml(JSON.stringify(value))}</div></div>`).join('');
    }
    async function loadSettings() { settingsCache = await fetchJson('/api/settings'); return settingsCache; }
    async function loadRunState() { return fetchJson('/api/run-state'); }
    function buildSettingsFields(settings) {
      const editable = settings.editable_settings;
      const groups = [
        ['Trend Filter', 'trend_filter', [['minimum_trend_strength_score', 'Minimum trend strength'], ['minimum_slope_pct', 'Minimum slope %']]],
        ['Compression', 'compression', [['maximum_pullback_depth_pct', 'Max pullback depth %'], ['minimum_range_contraction_pct', 'Min range contraction %'], ['minimum_volatility_contraction_pct', 'Min volatility contraction %']]],
        ['Breakout', 'breakout_trigger', [['breakout_buffer_pct', 'Breakout buffer %'], ['minimum_breakout_range_vs_base_avg', 'Min breakout expansion'], ['minimum_relative_volume', 'Min relative volume']]],
        ['Trap Risk', 'trap_risk', [['maximum_distance_from_trend_ref_pct', 'Max trend distance %'], ['maximum_rejection_wick_pct', 'Max rejection wick %'], ['minimum_overhead_clearance_pct', 'Min overhead clearance %']]],
        ['Scoring Weights', 'scoring', [['trend_alignment', 'Trend alignment weight'], ['squeeze_quality', 'Squeeze quality weight'], ['breakout_impulse', 'Breakout impulse weight'], ['path_quality', 'Path quality weight'], ['trap_risk_penalty', 'Trap-risk penalty weight']]],
      ];
      return groups.map(([title, key, fields]) => `<div class="card"><h3>${title}</h3>${fields.map(([fieldKey, label]) => `<div style="margin-top:10px;"><label>${label}</label><input data-settings-group="${key}" data-settings-key="${fieldKey}" value="${editable[key][fieldKey] ?? ''}"></div>`).join('')}</div>`).join('') + `<div class="card"><h3>Webhook Visibility</h3><div class="small muted">Use a public tunnel URL here if you want the setup page to show a copy-ready TradingView endpoint.</div><div style="margin-top:10px;"><label>Public webhook URL</label><input id="settings-public-webhook-url" value="${settings.public_webhook_url ?? ''}" placeholder="https://your-public-endpoint.example/webhook"></div><div class="footer-note">Override file: ${escapeHtml(settings.override_path || 'Not configured')}</div></div>`;
    }
    function renderAnalyzeModeOptions(settings) {
      const select = document.getElementById('analyze-source-mode');
      if (!select) { return; }
      const modes = settings.analyze_modes || [];
      select.innerHTML = modes.map((mode) => `<option value="${escapeHtml(mode.value)}" ${mode.disabled ? 'disabled' : ''}>${escapeHtml(mode.label)}</option>`).join('');
      if (!select.value) { select.value = 'auto'; }
    }
    function currentSettingsPayload() {
      const editable = { trend_filter: {}, compression: {}, breakout_trigger: {}, trap_risk: {}, scoring: {} };
      document.querySelectorAll('[data-settings-group]').forEach((input) => { editable[input.dataset.settingsGroup][input.dataset.settingsKey] = input.value; });
      return { editable_settings: editable, public_webhook_url: document.getElementById('settings-public-webhook-url')?.value || null };
    }
    async function renderHome() {
      const [health, settings, recentPayload] = await Promise.all([fetchJson('/api/health'), settingsCache ? Promise.resolve(settingsCache) : loadSettings(), fetchJson('/api/recent')]);
      const cards = [['App Status', health.app_status], ['Webhook Status', health.webhook_status], ['Webhook URL', settings.active_webhook_url], ['Stored Records', String(health.record_count)]];
      document.getElementById('home-top').innerHTML = cards.map(([label, value]) => `<div class="card"><div class="kpi-label">${escapeHtml(label)}</div><div class="kpi-value">${escapeHtml(value)}</div></div>`).join('');
      const records = recentPayload.records || [];
      const homeBody = document.getElementById('home-body');
      if (!records.length) {
        homeBody.innerHTML = `<div class="hero"><h2>No signals yet</h2><p class="muted">This workspace is ready, but no webhook or replay records have been stored yet. Start with a sample to see the full analysis flow.</p><div class="button-row"><button class="action" id="home-run-sample">Run sample replay</button><button class="secondary" id="home-open-replay">Open Replay Lab</button><button class="ghost" id="home-open-tv">View TradingView setup</button></div></div>`;
        document.getElementById('home-run-sample').onclick = async () => {
          document.getElementById('replay-payload').value = JSON.stringify(settings.sample_payloads.qualified, null, 2);
          await submitReplay();
        };
        document.getElementById('home-open-replay').onclick = () => setPage('replay');
        document.getElementById('home-open-tv').onclick = () => setPage('tradingview');
        return;
      }
      homeBody.innerHTML = `<div class="grid two-col"><div class="card"><h2>Latest analyses</h2><div class="grid">${records.slice(0, 4).map((record) => renderCompactCard(record)).join('')}</div></div><div class="card"><h2>Next step</h2><div class="helper-copy">If you want a quick answer, start with the setup status, direction, confidence, and target. Open Analysis Detail when you want the fuller reasoning behind the call.</div><ol class="helper-list"><li>Run a sample replay.</li><li>Check whether the setup is usable now.</li><li>Open Analysis Detail for the action card and timeframe story.</li><li>Use TradingView Setup when you are ready for live alerts.</li></ol></div></div>`;
      document.querySelectorAll('[data-scan-id]').forEach((element) => { element.onclick = () => loadDetail(element.dataset.scanId); });
    }
    async function renderLiveSignals() {
      const payload = await fetchJson('/api/recent');
      const records = payload.records || [];
      const container = document.getElementById('live-signals');
      if (!records.length) { container.innerHTML = '<div class="empty-state">No live or replayed signals yet. Use Replay Lab to generate the first record.</div>'; return; }
      container.innerHTML = records.map((record) => renderCompactCard(record)).join('');
      document.querySelectorAll('#live-signals [data-scan-id]').forEach((element) => { element.onclick = () => loadDetail(element.dataset.scanId); });
    }
    async function renderRunStatus() {
      const payload = await loadRunState();
      const panel = document.getElementById('run-status-panel');
      if (panel) { panel.innerHTML = renderRunState(payload.run_state || {}); }
    }
    function detailSection(title, body) { return `<details class="collapsible" open><summary>${title}</summary><div class="kv">${body}</div></details>`; }
    async function loadDetail(scanId) {
      const payload = await fetchJson(`/api/records/${scanId}`);
      selectedScanId = scanId;
      const record = payload.record;
      const display = payload.display;
      const shell = document.getElementById('detail-shell');
      shell.className = 'details-stack';
      shell.innerHTML = `<div class="action-card"><div class="row"><h2 style="margin:0;">${escapeHtml(record.symbol)}</h2><span class="pill ${statusClass(record.status)}">${escapeHtml(display.setup_status)}</span><span class="score-chip">${escapeHtml(display.confidence)} confidence</span><span class="pill">${escapeHtml(display.best_action)}</span></div><div class="subtle-grid"><div class="mini-card"><div class="label">Direction / Bias</div><div class="value">${escapeHtml(display.bias)}</div></div><div class="mini-card"><div class="label">Primary target</div><div class="value">${escapeHtml(display.short_term_target)}</div><div class="helper-copy">${escapeHtml(display.helper_copy.target)}</div></div><div class="mini-card"><div class="label">Invalidation</div><div class="value">${escapeHtml(display.invalidation)}</div><div class="helper-copy">${escapeHtml(display.helper_copy.invalidation)}</div></div><div class="mini-card"><div class="label">Confidence</div><div class="value">${escapeHtml(display.confidence)}</div><div class="helper-copy">${escapeHtml(display.helper_copy.confidence)}</div></div></div>${renderTrustSignals(display.trust_signals)}<div class="helper-copy">${escapeHtml(display.one_sentence_summary)}</div>${renderReasonBullets(display.reason_bullets)}<div class="button-row"><button class="ghost" id="detail-analyze-another">Analyze another ticker</button><button class="ghost" id="detail-clear-selection">Clear current selection</button></div></div>` +
        detailSection('What Matters Now', `<div class="kv-row"><div class="label">Best current action</div><div>${escapeHtml(display.best_action)}</div></div><div class="kv-row"><div class="label">Setup Status</div><div>${escapeHtml(display.setup_status)}</div></div><div class="kv-row"><div class="label">Direction</div><div>${escapeHtml(display.bias)}</div></div><div class="kv-row"><div class="label">How much should I trust it?</div><div>${escapeHtml(display.confidence_explanation)}</div></div><div class="kv-row"><div class="label">Why this matters</div><div>${escapeHtml(display.why_it_matters)}</div></div>`) +
        detailSection('Timeframe Story', `${(display.timeframe_story || []).map((part) => `<div class="kv-row"><div class="label">${escapeHtml(part.label)}</div><div>${escapeHtml(part.value)}</div></div>`).join('')}`) +
        detailSection('Analysis Source', `<div class="kv-row"><div class="label">Requested source</div><div>${escapeHtml(display.source_path.requested)}</div></div><div class="kv-row"><div class="label">Used source</div><div>${escapeHtml(display.source_path.used)}</div></div><div class="kv-row"><div class="label">Run type</div><div>${escapeHtml(display.source_path.mode_kind)}</div></div><div class="kv-row"><div class="label">Fallback chain</div><div>${escapeHtml((display.source_path.fallback_chain || []).join(' -> ') || 'None')}</div></div><div class="kv-row"><div class="label">Coverage</div><div>${escapeHtml(display.source_path.coverage_text)}</div></div><div class="kv-row"><div class="label">Missing context</div><div>${escapeHtml(display.source_path.missing_context_text)}</div></div>`) +
        detailSection('Detailed Analysis', `<div class="kv-row"><div class="label">Strategy match</div><div>${escapeHtml(payload.sections?.detailed_analysis?.strategy_match || 'Not matched yet')}</div></div><div class="kv-row"><div class="label">What passed</div><div>${renderReasonBullets(payload.sections?.detailed_analysis?.passed_summary || [])}</div></div><div class="helper-copy">Levels = the most relevant nearby structure from this analysis.</div>${renderLabelValueRows(payload.sections?.detailed_analysis?.levels_summary || [])}<div class="helper-copy">Timeframe summary = what each timeframe is currently contributing.</div>${renderLabelValueRows(payload.sections?.detailed_analysis?.timeframe_summary || [])}<div class="helper-copy">Score summary = how the confidence score was built.</div>${renderLabelValueRows(payload.sections?.detailed_analysis?.score_summary || [])}`) +
        detailSection('Technical / Advanced', `<div class="kv-row"><div class="label">Flags</div><div class="mono">${escapeHtml(JSON.stringify(record.flags, null, 2))}</div></div><div class="kv-row"><div class="label">Metrics</div><div class="mono">${escapeHtml(JSON.stringify(record.metrics, null, 2))}</div></div><div class="kv-row"><div class="label">Diagnostics</div><div class="mono">${escapeHtml(JSON.stringify(record.diagnostics, null, 2))}</div></div><div class="kv-row"><div class="label">Snapshot</div><div class="mono">${escapeHtml(JSON.stringify(record.snapshot, null, 2))}</div></div><div class="kv-row"><div class="label">Raw JSON</div><div class="mono">${escapeHtml(JSON.stringify(record, null, 2))}</div></div><div class="kv-row"><div class="label">Raw payload</div><div class="mono">${escapeHtml(JSON.stringify(payload.raw_payload || {}, null, 2))}</div></div>`);
      const analyzeAnother = document.getElementById('detail-analyze-another');
      if (analyzeAnother) { analyzeAnother.onclick = () => { setPage('live'); document.getElementById('analyze-symbol')?.focus(); }; }
      const clearSelection = document.getElementById('detail-clear-selection');
      if (clearSelection) { clearSelection.onclick = clearCurrentSelection; }
      setPage('detail');
    }
    async function renderHistory() {
      const query = new URLSearchParams();
      const symbol = document.getElementById('history-symbol').value.trim();
      const status = document.getElementById('history-status').value;
      const startDate = document.getElementById('history-start-date').value;
      const endDate = document.getElementById('history-end-date').value;
      if (symbol) query.set('symbol', symbol);
      if (status) query.set('status', status);
      if (startDate) query.set('start_date', startDate);
      if (endDate) query.set('end_date', endDate);
      const payload = await fetchJson(`/api/records?${query.toString()}`);
      const records = payload.records || [];
      const table = document.getElementById('history-table');
      if (!records.length) { table.innerHTML = '<div class="empty-state">No records match the current filters.</div>'; return; }
      table.innerHTML = records.map((record) => `<div class="table-row" data-scan-id="${record.scan_id}"><div><strong>${escapeHtml(record.symbol)}</strong><div class="helper-copy">${escapeHtml(record.bias)}</div></div><div>${escapeHtml(record.timestamp_utc)}</div><div class="${statusClass(record.status)}">${escapeHtml(displayStatus(record))}</div><div>${escapeHtml(record.confidence_label)}</div><div>${escapeHtml(record.why_it_matters)}<div class="chip-row"><span class="chip-soft">${escapeHtml(record.short_term_target || 'No target yet')}</span></div></div></div>`).join('');
      document.querySelectorAll('#history-table [data-scan-id]').forEach((row) => { row.onclick = () => loadDetail(row.dataset.scanId); });
    }
    async function renderTradingViewSetup() {
      const settings = settingsCache || await loadSettings();
      const panel = document.getElementById('tradingview-panel');
      panel.innerHTML = `<div class="card"><h2>Webhook endpoint</h2><div class="small muted">Paste a public webhook URL into TradingView. The local endpoint below is useful for replay and local checks, but TradingView cannot reach 127.0.0.1 directly.</div><div style="margin-top:14px;"><label>Local webhook URL</label><div class="row"><input id="local-webhook-url" value="${escapeHtml(settings.webhook_endpoint)}" readonly><button class="ghost" data-copy-target="local-webhook-url">Copy</button></div></div><div style="margin-top:14px;"><label>Public / tunnel webhook URL</label><div class="row"><input id="public-webhook-url-display" value="${escapeHtml(settings.public_webhook_url || '')}" placeholder="https://your-public-endpoint.example/webhook" readonly><button class="ghost" data-copy-target="public-webhook-url-display">Copy</button></div></div><div class="footer-note">If you want this field filled in, save a public URL in Strategy Settings.</div></div><div class="card"><h2>Setup steps</h2><ol class="helper-list"><li>Start the GUI locally.</li><li>Open the Pine template in TradingView and add it to your chart.</li><li>Create a TradingView alert on the indicator.</li><li>Enable webhook delivery and paste your public webhook URL.</li><li>Use the alert JSON body shown below.</li></ol><div style="margin-top:14px;"><div class="section-title">Minimal JSON payload</div><div class="mono">${escapeHtml(JSON.stringify(settings.payload_example, null, 2))}</div></div></div>`;
      document.querySelectorAll('[data-copy-target]').forEach((button) => {
        button.onclick = async () => {
          const target = document.getElementById(button.dataset.copyTarget);
          try { await navigator.clipboard.writeText(target.value); } catch (error) { console.error(error); }
        };
      });
    }
    async function renderDiagnostics() {
      const payload = await fetchJson('/api/diagnostics');
      const panel = document.getElementById('diagnostics-panel');
      panel.innerHTML = `<div class="card"><h2>Source Diagnostics</h2><div class="helper-copy">Where the data came from, how fresh it is, and what was missing.</div><div class="mono">${escapeHtml(JSON.stringify(payload.source || {}, null, 2))}</div></div><div class="card"><h2>Strategy Diagnostics</h2><div class="helper-copy">Which setup rules passed or failed.</div><div class="mono">${escapeHtml(JSON.stringify(payload.strategy || {}, null, 2))}</div><h2 style="margin-top:18px;">System Diagnostics</h2><div class="helper-copy">App/runtime issues and provider warnings.</div><div class="mono">${escapeHtml(JSON.stringify(payload.system || {}, null, 2))}</div><h2 style="margin-top:18px;">OCR Diagnostics</h2><div class="helper-copy">Only relevant when screen-reading fallback exists.</div><div class="mono">${escapeHtml(JSON.stringify(payload.ocr || {}, null, 2))}</div></div>`;
    }
    async function renderSettings() {
      const settings = settingsCache || await loadSettings();
      document.getElementById('settings-form').innerHTML = buildSettingsFields(settings);
      renderAnalyzeModeOptions(settings);
    }
    function clearCurrentSelection() {
      selectedScanId = null;
      const shell = document.getElementById('detail-shell');
      if (shell) {
        shell.className = 'empty-state';
        shell.textContent = 'Select a record from Home, Live Signals, or History to open its analysis detail.';
      }
      setPage('live');
    }
    async function openLatestResult() {
      const payload = await fetchJson('/api/recent');
      if (payload.records && payload.records.length) { await loadDetail(payload.records[0].scan_id); }
    }
    async function pollRunStateOnce() {
      try { await renderRunStatus(); } catch (error) { console.error(error); }
    }
    function startRunStatePolling() {
      stopRunStatePolling();
      runStatePoller = setInterval(pollRunStateOnce, 500);
    }
    function stopRunStatePolling() {
      if (runStatePoller) { clearInterval(runStatePoller); runStatePoller = null; }
    }
    async function analyzeTicker() {
      const symbol = document.getElementById('analyze-symbol').value.trim().toUpperCase();
      const sourceMode = document.getElementById('analyze-source-mode').value;
      startRunStatePolling();
      try {
        const response = await fetchJson('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol, source_mode: sourceMode }),
        });
        await renderRunStatus();
        await refreshAll();
        if (response.record && response.record.scan_id) { await loadDetail(response.record.scan_id); }
      } catch (error) {
        await renderRunStatus();
        console.error(error);
      } finally {
        stopRunStatePolling();
      }
    }
    async function submitReplay() {
      const resultEl = document.getElementById('replay-result');
      try {
        const payload = JSON.parse(document.getElementById('replay-payload').value.trim());
        const response = await fetchJson('/api/replay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const simple = response.result?.simple_summary;
        const raw = response.result?.raw_result || response;
        resultEl.innerHTML = simple ? `<div class="action-card"><div class="row"><span class="pill">${escapeHtml(simple.setup_status)}</span><span class="score-chip">${escapeHtml(simple.confidence)} confidence</span><span class="pill">${escapeHtml(simple.best_action)}</span></div><div class="summary-stack"><div class="summary-line"><strong>Direction</strong><span>${escapeHtml(simple.bias)}</span></div><div class="summary-line"><strong>Target</strong><span>${escapeHtml(simple.short_term_target)}</span></div><div class="summary-line"><strong>Invalidation</strong><span>${escapeHtml(simple.invalidation)}</span></div><div class="summary-line"><strong>Source path</strong><span>${escapeHtml(simple.source_path?.requested || 'replay')} -> ${escapeHtml(simple.source_path?.used || 'tradingview_webhook')}</span></div></div>${renderTrustSignals(simple.trust_signals)}<div class="helper-copy">${escapeHtml(simple.why_it_matters)}</div><div class="footer-note">${escapeHtml(simple.confidence_explanation)}</div></div><details class="collapsible" style="margin-top:12px;"><summary>Raw Replay Response</summary><div class="mono">${escapeHtml(JSON.stringify(raw, null, 2))}</div></details>` : `<div class="mono">${escapeHtml(JSON.stringify(response, null, 2))}</div>`;
        await refreshAll();
        if (response.record && response.record.scan_id) { await loadDetail(response.record.scan_id); }
      } catch (error) {
        resultEl.textContent = String(error.message || error);
      }
    }
    function validateReplayJson() {
      const resultEl = document.getElementById('replay-result');
      try {
        const payload = JSON.parse(document.getElementById('replay-payload').value.trim());
        resultEl.innerHTML = `<div class="helper-copy">Payload JSON is valid and ready to submit.</div><details class="collapsible" style="margin-top:12px;" open><summary>Validated Payload</summary><div class="mono">${escapeHtml(JSON.stringify(payload, null, 2))}</div></details>`;
      } catch (error) {
        resultEl.textContent = String(error.message || error);
      }
    }
    async function saveSettings() {
      const payload = await fetchJson('/api/settings/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentSettingsPayload()) });
      settingsCache = payload.settings;
      document.getElementById('settings-result').textContent = payload.message;
      await refreshAll();
    }
    async function resetSettings() {
      const payload = await fetchJson('/api/settings/reset', { method: 'POST' });
      settingsCache = payload.settings;
      document.getElementById('settings-result').textContent = payload.message;
      await refreshAll();
    }
    async function loadDemoPreset() {
      const payload = await fetchJson('/api/settings/load-demo', { method: 'POST' });
      settingsCache = payload.settings;
      document.getElementById('settings-result').textContent = payload.message;
      await refreshAll();
    }
    async function refreshAll() {
      settingsCache = await loadSettings();
      await Promise.all([renderHome(), renderLiveSignals(), renderSettings(), renderTradingViewSetup(), renderHistory(), renderDiagnostics(), renderRunStatus()]);
      if (selectedScanId) { try { await loadDetail(selectedScanId); } catch (error) { console.error(error); } }
    }
    document.querySelectorAll('.nav button').forEach((button) => { button.onclick = () => setPage(button.dataset.page); });
    document.querySelectorAll('.sample-btn').forEach((button) => { button.onclick = async () => { const settings = settingsCache || await loadSettings(); document.getElementById('replay-payload').value = JSON.stringify(settings.sample_payloads[button.dataset.sample], null, 2); }; });
    document.getElementById('replay-submit').onclick = submitReplay;
    document.getElementById('replay-validate').onclick = validateReplayJson;
    document.getElementById('history-refresh').onclick = renderHistory;
    document.getElementById('settings-save').onclick = saveSettings;
    document.getElementById('settings-reset').onclick = resetSettings;
    document.getElementById('settings-demo').onclick = loadDemoPreset;
    document.getElementById('analyze-submit').onclick = analyzeTicker;
    document.getElementById('open-latest-result').onclick = openLatestResult;
    document.getElementById('clear-current-selection').onclick = clearCurrentSelection;
    loadSettings().then((settings) => {
      document.getElementById('replay-payload').value = JSON.stringify(settings.sample_payloads.qualified, null, 2);
      renderAnalyzeModeOptions(settings);
      refreshAll();
      setInterval(renderHome, 6000);
      setInterval(renderLiveSignals, 7000);
      setInterval(renderHistory, 9000);
    });
  </script>
</body>
</html>"""
