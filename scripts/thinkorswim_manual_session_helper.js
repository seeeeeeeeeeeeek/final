(function () {
  const STOCKNOGS_BASE = "http://127.0.0.1:8090";
  const POLL_INTERVAL_MS = 1500;
  const POST_SWITCH_WAIT_MS = 2500;

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

  function symbolInput() {
    const selectors = [
      'input[placeholder*="Find a Symbol"]',
      'input[placeholder*="Symbol"]',
      'input[type="search"]',
    ];
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      if (node) return { node, selector };
    }
    return { node: null, selector: "" };
  }

  async function switchSymbol(symbol) {
    const inputResult = symbolInput();
    if (!inputResult.node) {
      throw new Error("No visible thinkorswim symbol input was found.");
    }
    inputResult.node.focus();
    inputResult.node.value = "";
    inputResult.node.dispatchEvent(new Event("input", { bubbles: true }));
    inputResult.node.value = symbol;
    inputResult.node.dispatchEvent(new Event("input", { bubbles: true }));
    inputResult.node.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    inputResult.node.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", bubbles: true }));
    return inputResult.selector;
  }

  function collectPayload(symbol, searchSelector) {
    const symbolResult = textFrom([
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

    const timeframeResult = textFrom([
      '[data-testid*="interval"]',
      '[data-testid*="timeframe"]',
      '.timeframe',
    ]);

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

  async function fetchCommand() {
    const response = await fetch(`${STOCKNOGS_BASE}/api/manual-session/next-command`);
    return response.json();
  }

  async function reportPayload(payload) {
    const response = await fetch(`${STOCKNOGS_BASE}/api/manual-session/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
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
  reportDebug("helper_started", { message: "Helper script started and is polling stocknogs." });
  alert("stocknogs helper is now running in this thinkorswim tab. Leave this tab open. When you request a symbol in stocknogs, this page will switch to it and report the DOM data back.");
})();
