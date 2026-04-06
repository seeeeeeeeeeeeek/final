async function send(message) {
  return chrome.runtime.sendMessage(message);
}

function renderState(state) {
  document.getElementById("bridge-enabled").checked = state.enabled !== false;
  document.getElementById("base-url").value = state.configuredBaseUrl || state.detectedBaseUrl || "";
  const inflight = state.inflightCommand
    ? `In-flight command: ${state.inflightCommand.symbol} (#${state.inflightCommand.id})`
    : "In-flight command: none";
  document.getElementById("status").textContent = [
    `Detected stocknogs URL: ${state.detectedBaseUrl || "not found"}`,
    inflight,
    `Heartbeat sent: ${state.heartbeatStarted ? "yes" : "not yet"}`,
  ].join("\n");
}

async function refreshState(forceDetect = false) {
  const state = await send({ type: forceDetect ? "bridge-detect-base" : "bridge-get-state" });
  renderState(state);
}

document.getElementById("detect-base").addEventListener("click", async () => {
  await refreshState(true);
});

document.getElementById("save-settings").addEventListener("click", async () => {
  const payload = await send({
    type: "bridge-save-settings",
    enabled: document.getElementById("bridge-enabled").checked,
    stocknogsBaseUrl: document.getElementById("base-url").value,
  });
  renderState(payload);
});

refreshState(false).catch((error) => {
  document.getElementById("status").textContent = String(error?.message || error);
});
