/**
 * Generic DOM executor for BrowserCommand protocol.
 * Receives commands from background, returns page_state + step_result.
 */

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function cssEscape(value) {
  if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function resolveElement(selector, index = -1) {
  if (!selector) return null;
  const nodes = document.querySelectorAll(selector);
  if (!nodes.length) return null;
  if (index >= 0 && index < nodes.length) return nodes[index];
  return nodes[0];
}

function elementSnapshot(el, idx) {
  const tag = (el.tagName || "").toLowerCase();
  let type = el.type || "";
  if (tag === "select") type = "select";
  const text = (el.innerText || el.textContent || "").trim().slice(0, 120);
  let selector = "";
  if (el.id) selector = `#${cssEscape(el.id)}`;
  else if (el.name) selector = `[name="${cssEscape(el.name)}"]`;
  return {
    index: idx,
    tag,
    type,
    text,
    id: el.id || "",
    name: el.name || "",
    selector,
  };
}

function collectInteractiveElements(limit = 80) {
  const nodes = document.querySelectorAll(
    "a, button, input, select, textarea, [role='button'], [onclick]"
  );
  const elements = [];
  for (let i = 0; i < nodes.length && elements.length < limit; i += 1) {
    const el = nodes[i];
    if (!el.offsetParent && el.tagName !== "INPUT") continue;
    elements.push(elementSnapshot(el, elements.length));
  }
  return elements;
}

function collectTables(limit = 5, rowLimit = 20) {
  const tables = [];
  document.querySelectorAll("table").forEach((table, tIdx) => {
    if (tIdx >= limit) return;
    const rows = [];
    table.querySelectorAll("tr").forEach((tr, rIdx) => {
      if (rIdx >= rowLimit) return;
      const cells = Array.from(tr.querySelectorAll("th, td")).map((c) =>
        (c.innerText || c.textContent || "").trim()
      );
      if (cells.length) rows.push(cells);
    });
    if (rows.length) tables.push({ index: tIdx, rows });
  });
  return tables;
}

function buildPageState(extracted = {}) {
  return {
    url: location.href,
    title: document.title || "",
    elements: collectInteractiveElements(),
    tables: collectTables(),
    extracted,
  };
}

function setInputValue(el, value) {
  const tag = (el.tagName || "").toLowerCase();
  if (tag === "select") {
    el.value = value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  el.focus();
  el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function extractFromPage(command) {
  const extracted = { record_type: command.record_type || "page_extract" };
  if (command.external_id) extracted.external_id = command.external_id;

  if (command.selector) {
    const el = resolveElement(command.selector, command.index);
    if (el) {
      const val = (el.innerText || el.textContent || el.value || "").trim();
      if (command.field) extracted[command.field] = val;
      else extracted.value = val;
    }
  }

  if (command.field && command.text && !(command.field in extracted)) {
    extracted[command.field] = command.text;
  }

  if (!extracted.external_id) {
    extracted.external_id = extracted.id || location.href;
  }
  return extracted;
}

async function executeCommand(command) {
  const action = command.action;
  const stepResult = { action, ok: true };

  if (action === "noop") {
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "wait") {
    await sleep(command.ms || 1000);
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "scroll") {
    window.scrollBy(0, command.ms || 400);
    await sleep(200);
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "goto") {
    stepResult.deferred_navigation = command.url;
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "snapshot") {
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "click") {
    const el = resolveElement(command.selector, command.index);
    if (!el) throw new Error(`click target not found: ${command.selector}`);
    el.click();
    await sleep(300);
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "fill") {
    const el = resolveElement(command.selector, command.index);
    if (!el) throw new Error(`fill target not found: ${command.selector}`);
    setInputValue(el, command.value ?? command.text ?? "");
    await sleep(150);
    return { page_state: buildPageState(), step_result: step_result, records: [] };
  }

  if (action === "select") {
    const el = resolveElement(command.selector, command.index);
    if (!el) throw new Error(`select target not found: ${command.selector}`);
    setInputValue(el, command.value ?? command.text ?? "");
    await sleep(150);
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  if (action === "extract") {
    const extracted = extractFromPage(command);
    const record = {
      record_type: command.record_type || extracted.record_type || "record",
      external_id: String(extracted.external_id || "unknown"),
      payload: { ...extracted },
    };
    delete record.payload.record_type;
    return {
      page_state: buildPageState(extracted),
      step_result: stepResult,
      records: [record],
    };
  }

  if (action === "finish") {
    stepResult.action = "finish";
    return { page_state: buildPageState(), step_result: stepResult, records: [] };
  }

  throw new Error(`unsupported action: ${action}`);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "EXECUTE_COMMAND") return false;
  executeCommand(message.command)
    .then((result) => sendResponse({ ok: true, ...result }))
    .catch((err) => sendResponse({ ok: false, error: String(err.message || err) }));
  return true;
});
