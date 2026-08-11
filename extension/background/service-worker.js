/**
 * Poll Ontology Platform for pending browser runs and execute commands in tabs.
 */

const POLL_ALARM = "ontology-browser-poll";
const DEFAULT_POLL_SEC = 5;

async function getConfig() {
  const data = await chrome.storage.sync.get({
    platformBaseUrl: "http://127.0.0.1:8765",
    pollIntervalSec: DEFAULT_POLL_SEC,
    enabled: true,
  });
  return data;
}

async function platformFetch(path, options = {}) {
  const cfg = await getConfig();
  const base = cfg.platformBaseUrl.replace(/\/$/, "");
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const resp = await fetch(url, { ...options, headers });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${text.slice(0, 200)}`);
  }
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) return resp.json();
  return resp.text();
}

async function broadcastStatus(patch) {
  const current = await chrome.storage.local.get(["runStatus"]);
  const next = { ...(current.runStatus || {}), ...patch, updatedAt: Date.now() };
  await chrome.storage.local.set({ runStatus: next });
  chrome.runtime.sendMessage({ type: "STATUS_UPDATE", status: next }).catch(() => {});
}

async function findOrCreateTab(url) {
  if (!url) {
    const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
    return active;
  }
  const tabs = await chrome.tabs.query({});
  const existing = tabs.find((t) => t.url && t.url.startsWith(url.split("?")[0].slice(0, 24)));
  if (existing?.id) {
    await chrome.tabs.update(existing.id, { active: true });
    return existing;
  }
  return chrome.tabs.create({ url, active: true });
}

async function sendCommandToContent(tabId, command, retries = 5) {
  for (let i = 0; i < retries; i += 1) {
    try {
      const resp = await chrome.tabs.sendMessage(tabId, {
        type: "EXECUTE_COMMAND",
        command,
      });
      if (resp?.ok) return resp;
      throw new Error(resp?.error || "content script failed");
    } catch (err) {
      if (i === retries - 1) throw err;
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  return null;
}

async function executeOnTab(tabId, command) {
  if (command.action === "goto") {
    const url = command.url;
    await chrome.tabs.update(tabId, { url });
    await waitForTabLoad(tabId);
    return {
      ok: true,
      page_state: { url, title: "" },
      step_result: { action: "goto" },
      records: [],
    };
  }
  return sendCommandToContent(tabId, command);
}

function waitForTabLoad(tabId, timeoutMs = 15000) {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, timeoutMs);
    function onUpdated(id, info) {
      if (id === tabId && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        clearTimeout(timer);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

async function postStep(runId, body) {
  return platformFetch(`/api/browser/runs/${runId}/step`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function processRun(run) {
  const runId = run.id;
  await broadcastStatus({
    active: true,
    runId,
    connector: run.connector_name,
    status: run.status,
    step: `${run.step_index}/${run.step_total}`,
    message: "执行中…",
  });

  await platformFetch(`/api/browser/runs/${runId}/heartbeat`, { method: "POST", body: "{}" });

  let tab = await findOrCreateTab(run.source_url);
  if (!tab?.id) throw new Error("no tab available");

  let done = false;
  let guard = 0;
  let body = {};

  while (!done && guard < 100) {
    guard += 1;
    const stepResp = await postStep(runId, body);
    done = !!stepResp.done;
    if (done) {
      await broadcastStatus({
        active: false,
        runId,
        status: stepResp.status,
        message: stepResp.message || "已完成",
      });
      break;
    }

    const command = stepResp.command;
    if (!command) {
      await broadcastStatus({ message: "等待平台指令…" });
      break;
    }

    if (command.action === "finish") {
      await broadcastStatus({ active: false, runId, message: command.message || "脚本结束" });
      break;
    }

    await broadcastStatus({
      message: `执行: ${command.action}${command.selector ? ` ${command.selector}` : ""}`,
      step: `${run.step_index}/${run.step_total}`,
    });

    if (command.action === "goto" && command.url) {
      tab = await findOrCreateTab(command.url);
      if (!tab?.id) throw new Error("无法打开目标页面");
    }

    const exec = await executeOnTab(tab.id, command);
    if (!exec?.ok) throw new Error(exec?.error || "command failed");

    body = {
      page_state: exec.page_state,
      step_result: exec.step_result,
      records: exec.records || [],
    };

    await platformFetch(`/api/browser/runs/${runId}/heartbeat`, { method: "POST", body: "{}" });
  }
}

async function pollPendingRuns() {
  const cfg = await getConfig();
  if (!cfg.enabled) return;

  const local = await chrome.storage.local.get(["activeRunId"]);
  if (local.activeRunId) return;

  try {
    const data = await platformFetch(`/api/browser/runs/pending?limit=5`);
    const runs = data.runs || [];
    if (!runs.length) {
      await broadcastStatus({ active: false, message: "无待执行任务" });
      return;
    }

    const run = runs[0];
    await chrome.storage.local.set({ activeRunId: run.id });
    try {
      await processRun(run);
    } finally {
      await chrome.storage.local.remove("activeRunId");
    }
  } catch (err) {
    await broadcastStatus({ active: false, message: String(err.message || err) });
  }
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) pollPendingRuns();
});

let pollTimer = null;

async function configurePolling() {
  const cfg = await getConfig();
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  chrome.alarms.clear(POLL_ALARM);
  if (!cfg.enabled) return;

  const sec = Math.max(3, cfg.pollIntervalSec || DEFAULT_POLL_SEC);
  if (sec < 60) {
    pollTimer = setInterval(pollPendingRuns, sec * 1000);
  } else {
    chrome.alarms.create(POLL_ALARM, { periodInMinutes: sec / 60 });
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  await configurePolling();
  if (chrome.sidePanel?.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  if (changes.pollIntervalSec || changes.enabled || changes.platformBaseUrl) {
    configurePolling();
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "POLL_NOW") {
    pollPendingRuns().then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  if (msg?.type === "GET_STATUS") {
    chrome.storage.local.get(["runStatus"]).then((data) => sendResponse(data.runStatus || {}));
    return true;
  }
  return false;
});

pollPendingRuns();
configurePolling();
