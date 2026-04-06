const POLL_INTERVAL_MS = 1500;
const HEARTBEAT_INTERVAL_MS = 15000;
const COMMAND_STALE_MS = 30000;
const BASE_CACHE_TTL_MS = 10000;
const STOCKNOGS_PORTS = [
  8080,
  8090,
  8100,
  8180,
  8280,
  8380,
  8480,
  8580,
  8680,
  8780,
  8880,
];
const DEFAULT_SETTINGS = {
  enabled: true,
  stocknogsBaseUrl: "",
};

const runtimeState = {
  detectedBaseUrl: "",
  detectedAt: 0,
  inflightCommand: null,
  lastHeartbeatAt: 0,
  heartbeatStarted: false,
};

function normalizeBaseUrl(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  return text.replace(/\/+$/, "");
}

function setBadge(text, color) {
  chrome.action.setBadgeText({ text }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color }).catch(() => {});
}

async function getSettings() {
  const stored = await chrome.storage.local.get(DEFAULT_SETTINGS);
  return {
    enabled: stored.enabled !== false,
    stocknogsBaseUrl: normalizeBaseUrl(stored.stocknogsBaseUrl),
  };
}

async function setSettings(patch) {
  const next = { ...patch };
  if (Object.prototype.hasOwnProperty.call(next, "stocknogsBaseUrl")) {
    next.stocknogsBaseUrl = normalizeBaseUrl(next.stocknogsBaseUrl);
  }
  await chrome.storage.local.set(next);
}

async function localStocknogsOriginsFromTabs() {
  const tabs = await chrome.tabs.query({
    url: ["http://127.0.0.1/*", "http://localhost/*"],
  });
  const origins = [];
  for (const tab of tabs) {
    if (!tab.url) {
      continue;
    }
    try {
      const url = new URL(tab.url);
      origins.push(url.origin);
    } catch (error) {
      continue;
    }
  }
  return origins;
}

async function candidateBaseUrls() {
  const settings = await getSettings();
  const bases = [];
  if (settings.stocknogsBaseUrl) {
    bases.push(settings.stocknogsBaseUrl);
  }
  const tabOrigins = await localStocknogsOriginsFromTabs();
  for (const origin of tabOrigins) {
    bases.push(origin);
  }
  for (const port of STOCKNOGS_PORTS) {
    bases.push(`http://127.0.0.1:${port}`);
  }
  return [...new Set(bases.map(normalizeBaseUrl).filter(Boolean))];
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 4000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

async function discoverStocknogsBaseUrl(force = false) {
  if (!force && runtimeState.detectedBaseUrl && Date.now() - runtimeState.detectedAt < BASE_CACHE_TTL_MS) {
    return runtimeState.detectedBaseUrl;
  }
  const candidates = await candidateBaseUrls();
  for (const baseUrl of candidates) {
    try {
      const response = await fetchWithTimeout(`${baseUrl}/api/health`, {}, 2500);
      if (!response.ok) {
        continue;
      }
      const payload = await response.json();
      if (payload && payload.ok) {
        runtimeState.detectedBaseUrl = baseUrl;
        runtimeState.detectedAt = Date.now();
        return baseUrl;
      }
    } catch (error) {
      continue;
    }
  }
  runtimeState.detectedBaseUrl = "";
  runtimeState.detectedAt = 0;
  return "";
}

async function stocknogsJson(path, options = {}, forceDetect = false) {
  const baseUrl = await discoverStocknogsBaseUrl(forceDetect);
  if (!baseUrl) {
    throw new Error("stocknogs app was not found on localhost.");
  }
  const headers = { ...(options.headers || {}) };
  const body = options.body;
  if (body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetchWithTimeout(
    `${baseUrl}${path}`,
    {
      ...options,
      headers,
    },
    5000,
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || payload.message || `HTTP ${response.status}`);
  }
  return { baseUrl, payload };
}

function rememberInflightCommand(command, tabId, baseUrl) {
  runtimeState.inflightCommand = {
    id: command.id,
    symbol: command.symbol,
    tabId,
    baseUrl,
    assignedAt: Date.now(),
  };
}

function clearInflightCommand(commandId = null) {
  if (!runtimeState.inflightCommand) {
    return;
  }
  if (commandId !== null && runtimeState.inflightCommand.id !== commandId) {
    return;
  }
  runtimeState.inflightCommand = null;
}

function inflightCommandIsStale() {
  return Boolean(
    runtimeState.inflightCommand &&
      Date.now() - runtimeState.inflightCommand.assignedAt > COMMAND_STALE_MS,
  );
}

async function postDebug(event, extras = {}, forceDetect = false) {
  try {
    const { payload, baseUrl } = await stocknogsJson(
      "/api/manual-session/debug",
      {
        method: "POST",
        body: JSON.stringify({
          event,
          ...extras,
        }),
      },
      forceDetect,
    );
    runtimeState.detectedBaseUrl = baseUrl;
    runtimeState.detectedAt = Date.now();
    return payload;
  } catch (error) {
    console.warn("[stocknogs bridge] debug post failed", error);
    return null;
  }
}

async function maybeSendHeartbeat(pageContext, tabId) {
  if (Date.now() - runtimeState.lastHeartbeatAt < HEARTBEAT_INTERVAL_MS) {
    return;
  }
  const event = runtimeState.heartbeatStarted ? "heartbeat" : "helper_started";
  const message = runtimeState.heartbeatStarted
    ? "Extension bridge is polling stocknogs from a thinkorswim tab."
    : "Extension bridge started and is polling stocknogs from a thinkorswim tab.";
  await postDebug(event, {
    message,
    page_url: pageContext.pageUrl || null,
    page_title: pageContext.pageTitle || null,
    tab_id: tabId,
  });
  runtimeState.lastHeartbeatAt = Date.now();
  runtimeState.heartbeatStarted = true;
}

async function handlePoll(pageContext, sender) {
  const settings = await getSettings();
  if (!settings.enabled) {
    setBadge("OFF", "#6b7280");
    return { ok: true, command: null, disabled: true };
  }

  if (inflightCommandIsStale()) {
    clearInflightCommand();
  }

  const tabId = sender.tab?.id ?? null;
  if (tabId === null) {
    return { ok: true, command: null };
  }

  const baseUrl = await discoverStocknogsBaseUrl();
  if (!baseUrl) {
    setBadge("ERR", "#b91c1c");
    return { ok: true, command: null, warning: "stocknogs not found" };
  }

  setBadge("ON", "#2563eb");
  await maybeSendHeartbeat(pageContext, tabId);

  if (runtimeState.inflightCommand && runtimeState.inflightCommand.tabId !== tabId) {
    return { ok: true, command: null, busy: true, baseUrl };
  }

  const { payload } = await stocknogsJson("/api/manual-session/next-command");
  const command = payload.command;
  if (!command || !command.symbol) {
    return { ok: true, command: null, baseUrl };
  }

  if (
    runtimeState.inflightCommand &&
    runtimeState.inflightCommand.id === command.id &&
    runtimeState.inflightCommand.tabId === tabId
  ) {
    return { ok: true, command: null, baseUrl, busy: true };
  }

  rememberInflightCommand(command, tabId, baseUrl);
  return { ok: true, command, baseUrl };
}

async function handlePayloadReport(message) {
  const result = await stocknogsJson("/api/manual-session/report", {
    method: "POST",
    body: JSON.stringify(message.payload || {}),
  }, Boolean(message.forceDetect));
  clearInflightCommand(message.commandId ?? null);
  return { ok: true, response: result.payload, baseUrl: result.baseUrl };
}

async function handleDebugReport(message) {
  await postDebug(message.event || "helper_event", message.payload || {}, Boolean(message.forceDetect));
  return { ok: true };
}

async function handleCommandFailure(message) {
  clearInflightCommand(message.commandId ?? null);
  if (message.error) {
    await postDebug("helper_error", {
      error: message.error,
      message: message.message || message.error,
      page_url: message.pageUrl || null,
      page_title: message.pageTitle || null,
      symbol: message.symbol || null,
    });
  }
  return { ok: true };
}

async function bridgeStatePayload() {
  const settings = await getSettings();
  const baseUrl = await discoverStocknogsBaseUrl();
  return {
    enabled: settings.enabled,
    configuredBaseUrl: settings.stocknogsBaseUrl,
    detectedBaseUrl: baseUrl,
    inflightCommand: runtimeState.inflightCommand,
    heartbeatStarted: runtimeState.heartbeatStarted,
    lastHeartbeatAt: runtimeState.lastHeartbeatAt || null,
    pollIntervalMs: POLL_INTERVAL_MS,
  };
}

chrome.runtime.onInstalled.addListener(async () => {
  await setSettings(DEFAULT_SETTINGS);
  setBadge("ON", "#2563eb");
});

chrome.runtime.onStartup.addListener(() => {
  setBadge("ON", "#2563eb");
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    switch (message?.type) {
      case "bridge-poll":
        sendResponse(await handlePoll(message.pageContext || {}, sender));
        break;
      case "bridge-report-payload":
        sendResponse(await handlePayloadReport(message));
        break;
      case "bridge-report-debug":
        sendResponse(await handleDebugReport(message));
        break;
      case "bridge-command-failed":
        sendResponse(await handleCommandFailure(message));
        break;
      case "bridge-get-state":
        sendResponse(await bridgeStatePayload());
        break;
      case "bridge-save-settings":
        await setSettings({
          enabled: message.enabled,
          stocknogsBaseUrl: message.stocknogsBaseUrl,
        });
        runtimeState.detectedBaseUrl = "";
        runtimeState.detectedAt = 0;
        sendResponse(await bridgeStatePayload());
        break;
      case "bridge-detect-base":
        runtimeState.detectedBaseUrl = "";
        runtimeState.detectedAt = 0;
        sendResponse(await bridgeStatePayload());
        break;
      default:
        sendResponse({ ok: false, error: "Unknown bridge message." });
        break;
    }
  })().catch((error) => {
    console.error("[stocknogs bridge] background failure", error);
    sendResponse({ ok: false, error: error?.message || String(error) });
  });
  return true;
});
