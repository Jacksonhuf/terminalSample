/**
 * Browser Action Adapter — background service worker.
 * Supports generic /v1/browser API with legacy /api/browser fallback.
 */

const POLL_ALARM = "browser-adapter-poll";
const DEFAULT_POLL_SEC = 5;

async function getConfig() {
  const data = await chrome.storage.sync.get({
    bridgeUrl: "",
    platformBaseUrl: "http://127.0.0.1:8080",
    pollIntervalSec: DEFAULT_POLL_SEC,
    enabled: true,
    apiVersion: "v1",
  });
  const bridgeUrl = data.bridgeUrl || data.platformBaseUrl;
  return { ...data, bridgeUrl };
}

async function bridgeFetch(path, options = {}) {
  const cfg = await getConfig();
  const base = cfg.bridgeUrl.replace(/\/$/, "");
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const resp = await fetch(url, { ...options, headers });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${text.slice(0, 200)}`);
  }
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) return resp.json();
  return resp.text;
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
  const prefix = url.split("?")[0].replace(/\/$/, "");
  const existing = tabs.find((t) => {
    if (!t.url) return false;
    const tabUrl = t.url.split("?")[0].replace(/\/$/, "");
    return tabUrl === prefix || tabUrl.startsWith(prefix);
  });
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

function sessionStartUrl(session) {
  return session.start_url || session.source_url || "";
}

function sessionLabel(session) {
  return session.metadata?.connector_name || session.connector_name || session.id?.slice(0, 8) || "-";
}

async function postStepV1(sessionId, body) {
  return bridgeFetch(`/v1/browser/sessions/${sessionId}/steps`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function postStepLegacy(runId, body) {
  return bridgeFetch(`/api/browser/runs/${runId}/step`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function postStep(cfg, sessionId, body) {
  if (cfg.apiVersion === "v1") {
    return postStepV1(sessionId, body);
  }
  return postStepLegacy(sessionId, body);
}

async function heartbeat(cfg, sessionId) {
  const path =
    cfg.apiVersion === "v1"
      ? `/v1/browser/sessions/${sessionId}/heartbeat`
      : `/api/browser/runs/${sessionId}/heartbeat`;
  await bridgeFetch(path, { method: "POST", body: "{}" });
}

async function processSession(session) {
  const cfg = await getConfig();
  const sessionId = session.id;
  const startUrl = sessionStartUrl(session);

  await broadcastStatus({
    active: true,
    runId: sessionId,
    connector: sessionLabel(session),
    status: session.status,
    step: `${session.step_index || 0}/${session.step_total || 0}`,
    message: "执行中…",
  });

  await heartbeat(cfg, sessionId);

  let tab = await findOrCreateTab(startUrl);
  if (!tab?.id) throw new Error("no tab available");

  let done = false;
  let guard = 0;
  let body = {};

  while (!done && guard < 100) {
    guard += 1;
    const stepResp = await postStep(cfg, sessionId, body);
    done = !!stepResp.done;
    if (done) {
      await broadcastStatus({
        active: false,
        runId: sessionId,
        status: stepResp.status,
        message: stepResp.message || "已完成",
      });
      break;
    }

    const command = stepResp.command;
    if (!command) {
      await broadcastStatus({ message: "等待指令…" });
      break;
    }

    if (command.action === "finish") {
      const exec = await executeOnTab(tab.id, command);
      body = {
        page_state: exec.page_state,
        step_result: { action: "finish" },
        records: exec.records || [],
      };
      const final = await postStep(cfg, sessionId, body);
      await broadcastStatus({
        active: false,
        runId: sessionId,
        status: final.status || "completed",
        message: final.message || command.message || "脚本结束",
      });
      break;
    }

    await broadcastStatus({
      message: `执行: ${command.action}${command.selector ? ` ${command.selector}` : ""}`,
      step: `${session.step_index || 0}/${session.step_total || 0}`,
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
      data: exec.records || [],
    };

    await heartbeat(cfg, sessionId);
  }
}

async function fetchPending(cfg) {
  if (cfg.apiVersion === "v1") {
    const data = await bridgeFetch(`/v1/browser/sessions/pending?limit=5`);
    return data.sessions || [];
  }
  const data = await bridgeFetch(`/api/browser/runs/pending?limit=5`);
  return data.runs || [];
}

async function pollPendingRuns() {
  const cfg = await getConfig();
  if (!cfg.enabled) return;

  const local = await chrome.storage.local.get(["activeSessionId"]);
  if (local.activeSessionId) return;

  try {
    const sessions = await fetchPending(cfg);
    if (!sessions.length) {
      await broadcastStatus({ active: false, message: "无待执行任务" });
      return;
    }

    const session = sessions[0];
    await chrome.storage.local.set({ activeSessionId: session.id });
    try {
      await processSession(session);
    } finally {
      await chrome.storage.local.remove("activeSessionId");
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
  if (
    changes.pollIntervalSec ||
    changes.enabled ||
    changes.bridgeUrl ||
    changes.platformBaseUrl ||
    changes.apiVersion
  ) {
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
