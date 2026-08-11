const defaults = {
  platformBaseUrl: "http://127.0.0.1:8765",
  pollIntervalSec: 5,
  enabled: true,
};

async function load() {
  const data = await chrome.storage.sync.get(defaults);
  document.getElementById("platformBaseUrl").value = data.platformBaseUrl;
  document.getElementById("pollIntervalSec").value = data.pollIntervalSec;
  document.getElementById("enabled").checked = !!data.enabled;
}

document.getElementById("save").addEventListener("click", async () => {
  const platformBaseUrl = document.getElementById("platformBaseUrl").value.trim() || defaults.platformBaseUrl;
  const pollIntervalSec = parseInt(document.getElementById("pollIntervalSec").value, 10) || defaults.pollIntervalSec;
  const enabled = document.getElementById("enabled").checked;
  await chrome.storage.sync.set({ platformBaseUrl, pollIntervalSec, enabled });
  document.getElementById("msg").textContent = "已保存";
});

load();
