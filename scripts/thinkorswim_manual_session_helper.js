(function () {
  const STOCKNOGS_BASE = "http://127.0.0.1:8090";
  const POLL_INTERVAL_MS = 1500;
  const POST_SWITCH_WAIT_MS = 2500;
  const SYMBOL_INPUT_SELECTORS = [
    '#navigation-symbol-search',
    'input#navigation-symbol-search[aria-label="Find a symbol"]',
    'div[data-testid="navigation-symbol-search"] input[aria-label="Find a symbol"]',
    '#main-header > div.left.center-align > div.symbol-search input#navigation-symbol-search',
    '#main-header > div.left.center-align > div.symbol-search input[placeholder*="Find a Symbol"]',
    'form#navigation-symbol-search-form input[role="combobox"]',
    'input[aria-label*="Find a symbol"]',
    'input[placeholder*="Find a Symbol"]',
    'input[placeholder*="Symbol"]',
    'input[type="search"]',
  ];
  const SYMBOL_CONTAINER_SELECTORS = [
    '#main-header > div.left.center-align > div.symbol-search',
    'div[data-testid="navigation-symbol-search"]',
    'form#navigation-symbol-search-form',
  ];
  const AGGREGATION_BUTTON_SELECTORS = [
    'button[data-testid="timeframe-aggregation-dropdown-value"]',
    '#price-chart-wrapper-trade-page-chart button[data-testid="timeframe-aggregation-dropdown-value"]',
    '#price-chart-wrapper-trade-page-chart > div.sc-eeDRCY.sc-koXPp.sc-jhlPcU.kLUocn.ihXwcj.gUQVPY > div > div:nth-child(2) > div:nth-child(2) > button',
  ];
  const RANGE_BUTTON_SELECTORS = [
    'button[data-testid="timeframe-range-dropdown-value"]',
    '#price-chart-wrapper-trade-page-chart button[data-testid="timeframe-range-dropdown-value"]',
  ];
  const TIMEFRAME_DISPLAY_SELECTORS = [
    'button[data-testid="timeframe-aggregation-dropdown-value"] .aggregation-dropdown__anchor-text',
    '#price-chart-wrapper-trade-page-chart button[data-testid="timeframe-aggregation-dropdown-value"] .aggregation-dropdown__anchor-text',
    '#price-chart-wrapper-trade-page-chart > div.sc-eeDRCY.sc-koXPp.sc-jhlPcU.kLUocn.ihXwcj.gUQVPY > div > div:nth-child(2) > div:nth-child(2) > button .aggregation-dropdown__anchor-text',
    'button[data-testid="timeframe-range-dropdown-value"] .aggregation-dropdown__anchor-text',
    '#price-chart-wrapper-trade-page-chart button[data-testid="timeframe-range-dropdown-value"] .aggregation-dropdown__anchor-text',
    '[data-testid*="interval"]',
    '[data-testid*="timeframe"]',
    '.timeframe',
  ];
  const TIMEFRAME_OPTION_SELECTORS = [
    'li[role="option"][data-testid^="timeframe-aggregation-dropdown:"]',
    'li[role="option"][data-testid^="timeframe-range-dropdown:"]',
  ];
  const TIMEFRAME_TARGET_TESTIDS = {
    '5m': ['MIN5'],
    '15m': ['MIN15'],
    '30m': ['MIN30'],
    '1h': ['MIN60', 'HOUR1', 'HR1'],
    '1d': ['DAY1', 'D1', 'DAY'],
  };
  const TIMEFRAME_TARGET_CONTROL = {
    '5m': 'aggregation',
    '15m': 'aggregation',
    '30m': 'aggregation',
    '1h': 'aggregation',
    '1d': 'range',
  };
  const SYMBOL_LOOKUP_RETRIES = 10;
  const SYMBOL_LOOKUP_WAIT_MS = 200;
  const TIMEFRAME_LOOKUP_RETRIES = 10;
  const TIMEFRAME_LOOKUP_WAIT_MS = 150;
  let helperBlockedNoticeShown = false;

  function textFrom(selectors) {
    for (const selector of selectors) {
      try {
        const node = document.querySelector(selector);
        const text = (node?.textContent || node?.value || "").trim();
        if (text) {
          return { text, selector };
        }
      } catch (error) {
        continue;
      }
    }
    return { text: "", selector: "" };
  }

  function maybeNumber(text) {
    if (!text) return null;
    const cleaned = String(text).replace(/[$,%(),]/g, " ").replace(/\s+/g, " ").trim();
    const match = cleaned.match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function normalizeTimeframeTarget(value) {
    const text = String(value || '').trim().toLowerCase();
    if (!text) return '';
    if (text === '60m') return '1h';
    if (text === 'day') return '1d';
    return text;
  }

  function stopHelper() {
    if (window.__stocknogsHelperTimer) {
      window.clearInterval(window.__stocknogsHelperTimer);
      window.__stocknogsHelperTimer = null;
    }
  }

  function isBlockedFetchError(error) {
    const text = String(error?.message || error || "").toLowerCase();
    return text.includes("failed to fetch") || text.includes("content security policy") || text.includes("refused to connect");
  }

  function symbolInput() {
    for (const selector of SYMBOL_INPUT_SELECTORS) {
      const node = document.querySelector(selector);
      if (node) return { node, selector };
    }
    return { node: null, selector: "", containerSelector: "" };
  }

  function clickSymbolContainer() {
    for (const selector of SYMBOL_CONTAINER_SELECTORS) {
      const node = document.querySelector(selector);
      if (!node) continue;
      try {
        node.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
        node.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
        node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      } catch (error) {
        continue;
      }
      return selector;
    }
    return "";
  }

  function timeframeButton(target) {
    const normalized = normalizeTimeframeTarget(target);
    const selectorGroup =
      TIMEFRAME_TARGET_CONTROL[normalized] === 'range'
        ? RANGE_BUTTON_SELECTORS
        : AGGREGATION_BUTTON_SELECTORS;
    for (const selector of selectorGroup) {
      const node = document.querySelector(selector);
      if (node) return { node, selector, controlKind: TIMEFRAME_TARGET_CONTROL[normalized] || 'aggregation' };
    }
    return { node: null, selector: '', controlKind: TIMEFRAME_TARGET_CONTROL[normalized] || 'aggregation' };
  }

  function clickTimeframeButton(node) {
    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }

  async function openTimeframeMenu(target) {
    const found = timeframeButton(target);
    if (!found.node) {
      throw new Error(`No visible thinkorswim ${found.controlKind} timeframe button was found.`);
    }
    if (found.node.getAttribute('aria-expanded') !== 'true') {
      clickTimeframeButton(found.node);
    }
    for (let attempt = 0; attempt < TIMEFRAME_LOOKUP_RETRIES; attempt += 1) {
      if (found.node.getAttribute('aria-expanded') === 'true') {
        return found;
      }
      await new Promise((resolve) => window.setTimeout(resolve, TIMEFRAME_LOOKUP_WAIT_MS));
    }
    throw new Error('The thinkorswim timeframe menu did not open.');
  }

  function timeframeOptionCandidates(target) {
    const normalized = normalizeTimeframeTarget(target);
    const testIds = TIMEFRAME_TARGET_TESTIDS[normalized] || [];
    const labelNeedles = {
      '5m': ['5 minute', '5 min', '5m'],
      '15m': ['15 minute', '15 min', '15m'],
      '30m': ['30 minute', '30 min', '30m'],
      '1h': ['60 minute', '60 min', '1 hour', '1h'],
      '1d': ['1 day', 'day', '1d'],
    }[normalized] || [];
    return { normalized, testIds, labelNeedles };
  }

  function timeframeOption(target) {
    const { normalized, testIds, labelNeedles } = timeframeOptionCandidates(target);
    const prefix = TIMEFRAME_TARGET_CONTROL[normalized] === 'range' ? 'timeframe-range-dropdown' : 'timeframe-aggregation-dropdown';
    for (const testId of testIds) {
      const node = document.querySelector(`li[data-testid="${prefix}:${testId}"]`);
      if (node) {
        return {
          node,
          selector: `li[data-testid="${prefix}:${testId}"]`,
        };
      }
    }
    const options = Array.from(document.querySelectorAll(TIMEFRAME_OPTION_SELECTORS.join(',')));
    for (const node of options) {
      const label = (node.textContent || '').trim().toLowerCase();
      if (labelNeedles.some((needle) => label.includes(needle))) {
        return {
          node,
          selector: `li[data-testid="${node.getAttribute('data-testid') || ''}"]`,
        };
      }
    }
    return { node: null, selector: '' };
  }

  async function switchTimeframe(target) {
    const menu = await openTimeframeMenu(target);
    const option = timeframeOption(target);
    if (!option.node) {
      throw new Error(`No thinkorswim timeframe option was found for ${target}.`);
    }
    option.node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    option.node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    option.node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, POST_SWITCH_WAIT_MS));
    return {
      controlKind: menu.controlKind,
      buttonSelector: menu.selector,
      optionSelector: option.selector,
      target: normalizeTimeframeTarget(target),
    };
  }

  async function resolveSymbolInput() {
    let containerSelector = "";
    for (let attempt = 0; attempt < SYMBOL_LOOKUP_RETRIES; attempt += 1) {
      const found = symbolInput();
      if (found.node) {
        return { ...found, containerSelector };
      }
      if (!containerSelector) {
        containerSelector = clickSymbolContainer();
      } else {
        clickSymbolContainer();
      }
      await new Promise((resolve) => window.setTimeout(resolve, SYMBOL_LOOKUP_WAIT_MS));
    }
    return { node: null, selector: "", containerSelector };
  }

  async function switchSymbol(symbol) {
    const inputResult = await resolveSymbolInput();
    if (!inputResult.node) {
      throw new Error("No visible thinkorswim symbol input was found (expected #navigation-symbol-search).");
    }
    inputResult.node.focus();
    inputResult.node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    if (typeof inputResult.node.setSelectionRange === "function") {
      try {
        inputResult.node.setSelectionRange(0, String(inputResult.node.value || "").length);
      } catch (error) {
        // Some browsers throw if selection is not supported on this input subtype.
      }
    }
    inputResult.node.value = "";
    inputResult.node.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    inputResult.node.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    inputResult.node.value = symbol;
    inputResult.node.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    inputResult.node.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    inputResult.node.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    inputResult.node.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", bubbles: true }));
    const form = inputResult.node.closest("form");
    if (form) {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    }
    return inputResult.containerSelector
      ? `${inputResult.selector} (via ${inputResult.containerSelector})`
      : inputResult.selector;
  }

  function collectPayload(symbol, searchSelector) {
    const symbolResult = textFrom([
      '#navigation-symbol-search',
      'input#navigation-symbol-search[aria-label="Find a symbol"]',
      'div[data-testid="navigation-symbol-search"] input[aria-label="Find a symbol"]',
      'input[placeholder*="Find a Symbol"]',
      'input[placeholder*="Symbol"]',
      '.symbol',
      'h1',
      'h2',
    ]);

    const priceResult = textFrom([
      '.quote-price',
      '.mark',
      '[data-testid*="price"]',
      '[data-testid*="last"]',
      '.positions .value',
    ]);

    const timeframeResult = textFrom(TIMEFRAME_DISPLAY_SELECTORS);

    return {
      symbol: (symbol || symbolResult.text || "").replace(/[^A-Z0-9.\-]/gi, "").toUpperCase(),
      visible_ticker_text: symbolResult.text || null,
      latest_visible_price: maybeNumber(priceResult.text),
      visible_timeframe: timeframeResult.text || null,
      page_title: document.title || null,
      page_url: window.location.href,
      selector_debug: {
        symbol: symbolResult.selector,
        price: priceResult.selector,
        timeframe: timeframeResult.selector,
        symbol_search: searchSelector || "",
      },
      visible_data: {
        symbol_text: symbolResult.text || null,
        price_text: priceResult.text || null,
        timeframe_text: timeframeResult.text || null,
      },
      warnings: [],
    };
  }

  function exposeManualPayload(symbol, searchSelector, error) {
    const payload = collectPayload(symbol, searchSelector);
    if (error) {
      payload.warnings.push(`Helper could not post back automatically: ${error?.message || String(error)}`);
    }
    window.__stocknogsManualPayload = payload;
    console.log("[stocknogs helper] manual payload", payload);
    try {
      if (typeof copy === "function") {
        copy(JSON.stringify(payload, null, 2));
      }
    } catch (copyError) {
      console.warn("[stocknogs helper] could not copy manual payload automatically", copyError);
    }
    return payload;
  }

  function showBlockedFetchNotice(symbol, searchSelector, error) {
    if (helperBlockedNoticeShown) return;
    helperBlockedNoticeShown = true;
    stopHelper();
    exposeManualPayload(symbol, searchSelector, error);
    alert(
      "thinkorswim blocked the helper from calling your local stocknogs app because of this page's Content Security Policy. The auto-link mode will not work from DevTools here. A manual JSON payload has been logged to the console and copied if your browser allowed it. Paste that JSON into stocknogs under Live Analysis -> Manual Session Payload, then click Submit Session JSON."
    );
  }

  async function fetchCommand() {
    try {
      const response = await fetch(`${STOCKNOGS_BASE}/api/manual-session/next-command`);
      return response.json();
    } catch (error) {
      if (isBlockedFetchError(error)) {
        showBlockedFetchNotice("", "manual_capture", error);
      }
      throw error;
    }
  }

  async function reportPayload(payload) {
    try {
      const response = await fetch(`${STOCKNOGS_BASE}/api/manual-session/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return response.json();
    } catch (error) {
      if (isBlockedFetchError(error)) {
        showBlockedFetchNotice(payload.symbol || "", payload.selector_debug?.symbol_search || "", error);
      }
      throw error;
    }
  }

  async function reportDebug(event, extras = {}) {
    try {
      await fetch(`${STOCKNOGS_BASE}/api/manual-session/debug`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event,
          page_url: window.location.href,
          page_title: document.title || null,
          ...extras,
        }),
      });
    } catch (error) {
      if (isBlockedFetchError(error)) {
        showBlockedFetchNotice(extras.symbol || "", extras.selector || "manual_capture", error);
        return;
      }
      console.error("[stocknogs helper] debug report failed", error);
    }
  }

  async function tick() {
    try {
      const commandResponse = await fetchCommand();
      const command = commandResponse.command;
      if (!command || !command.symbol) return;
      await reportDebug("switch_started", {
        symbol: command.symbol,
        message: `Helper received ${command.symbol} and is trying to switch the live tab.`,
      });
      const searchSelector = await switchSymbol(command.symbol);
      await new Promise((resolve) => window.setTimeout(resolve, POST_SWITCH_WAIT_MS));
      await reportDebug("switch_finished", {
        symbol: command.symbol,
        message: `Helper switched the live tab to ${command.symbol} and is reading selectors.`,
        selector: searchSelector,
      });
      const payload = collectPayload(command.symbol, searchSelector);
      const reportResponse = await reportPayload(payload);
      await reportDebug("report_finished", {
        symbol: command.symbol,
        message: `Helper reported selector data for ${command.symbol}.`,
        latest_scan_id: reportResponse.record?.scan_id || null,
      });
      console.log("[stocknogs helper] reported symbol", command.symbol, payload, reportResponse);
    } catch (error) {
      if (isBlockedFetchError(error)) {
        showBlockedFetchNotice("", "manual_capture", error);
        return;
      }
      await reportDebug("helper_error", {
        error: error?.message || String(error),
        message: `Helper hit an in-tab error: ${error?.message || String(error)}`,
      });
      console.error("[stocknogs helper] failed", error);
    }
  }

  if (window.__stocknogsHelperRunning) {
    alert("stocknogs helper is already running in this tab.");
    return;
  }

  window.__stocknogsHelperRunning = true;
  window.__stocknogsHelperTimer = window.setInterval(tick, POLL_INTERVAL_MS);
  window.stocknogsExtractManualPayload = function stocknogsExtractManualPayload(symbol) {
    return exposeManualPayload(symbol || "", "manual_capture");
  };
  window.stocknogsSwitchTimeframe = function stocknogsSwitchTimeframe(target) {
    return switchTimeframe(target);
  };
  reportDebug("helper_started", { message: "Helper script started and is polling stocknogs." });
  alert("stocknogs helper is now running in this thinkorswim tab. Leave this tab open. When you request a symbol in stocknogs, this page will switch to it and report the DOM data back.");
})();
