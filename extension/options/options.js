const defaults = {
  bridgeUrl: "http://127.0.0.1:8080",
  platformBaseUrl: "http://127.0.0.1:8080",
  pollIntervalSec: 5,
  enabled: true,
  apiVersion: "v1",
};

async function load() {
  const data = await chrome.storage.sync.get(defaults);
  document.getElementById("bridgeUrl").value = data.bridgeUrl || data.platformBaseUrl;
  document.getElementById("apiVersion").value = data.apiVersion || "v1";
  document.getElementById("pollIntervalSec").value = data.pollIntervalSec;
  document.getElementById("enabled").checked = !!data.enabled;
}

document.getElementById("save").addEventListener("click", async () => {
  const bridgeUrl = document.getElementById("bridgeUrl").value.trim() || defaults.bridgeUrl;
  const apiVersion = document.getElementById("apiVersion").value;
  const pollIntervalSec = parseInt(document.getElementById("pollIntervalSec").value, 10) || defaults.pollIntervalSec;
  const enabled = document.getElementById("enabled").checked;
  await chrome.storage.sync.set({ bridgeUrl, platformBaseUrl: bridgeUrl, apiVersion, pollIntervalSec, enabled });
  document.getElementById("msg").textContent = "已保存";
});

load();
