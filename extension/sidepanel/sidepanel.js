async function loadConfig() {
  const data = await chrome.storage.sync.get({ platformBaseUrl: "http://127.0.0.1:8765" });
  document.getElementById("platform-url").textContent = data.platformBaseUrl;
}

async function renderStatus() {
  const status = await chrome.runtime.sendMessage({ type: "GET_STATUS" });
  document.getElementById("status-text").textContent = status.message || (status.active ? "运行中" : "空闲");
  document.getElementById("run-id").textContent = status.runId || "-";
  document.getElementById("connector-name").textContent = status.connector || "-";
  document.getElementById("step-info").textContent = status.step || "-";
}

document.getElementById("poll-btn").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "POLL_NOW" });
  renderStatus();
});

document.getElementById("options-btn").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "STATUS_UPDATE") renderStatus();
});

loadConfig();
renderStatus();
setInterval(renderStatus, 2000);
