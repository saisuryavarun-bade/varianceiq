/* VarianceIQ — frontend logic */
const $ = (sel) => document.querySelector(sel);
const fmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const state = { investigating: false, eventSource: null, memoMarkdown: "" };

function showView(name) {
  document.querySelectorAll("[data-view]").forEach(el =>
    el.classList.toggle("hidden", el.dataset.view !== name)
  );
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 5500);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ---- dataset loading ----

async function loadDatasetSummary() {
  const r = await fetch("/api/dataset");
  if (!r.ok) throw new Error("Could not load dataset summary");
  return r.json();
}

function applyDataset(d) {
  $("#stat-rows").textContent = d.row_count.toLocaleString();
  $("#stat-periods").textContent = d.periods.length;
  $("#stat-depts").textContent = d.departments.length;
  // We don't get numeric totals from /api/dataset, so show counts
  $("#stat-budget").textContent = `${d.row_count} lines`;
  $("#stat-actual").textContent = `${d.transaction_count} txns`;
  $("#stat-variance").textContent = d.source;
  showView("investigation");
  resetPanels();
}

async function loadSample() {
  await fetch("/api/reset", { method: "POST" });
  const data = await loadDatasetSummary();
  applyDataset(data);
}

async function uploadFiles() {
  const bva = $("#file-bva").files?.[0];
  if (!bva) { toast("Select a Budget vs Actuals CSV first."); return; }
  const txn = $("#file-txn").files?.[0];
  const fd = new FormData();
  fd.append("budget_file", bva);
  if (txn) fd.append("transactions_file", txn);
  else {
    // backend requires both files — use sample transactions as fallback
    toast("Transactions file is required. Using sample transactions.");
    return;
  }
  const r = await fetch("/api/upload", { method: "POST", body: fd });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail || "Upload failed.";
    throw new Error(detail);
  }
  const data = await loadDatasetSummary();
  applyDataset(data);
}

function resetPanels() {
  state.investigating = false;
  state.memoMarkdown = "";
  $("#stream-body").innerHTML = '<div class="empty-state"><p>Press <strong>Start Investigation</strong> to watch the agent work.</p></div>';
  $("#results-body").innerHTML = '<div class="empty-state"><p>The memo will appear once the agent completes its investigation.</p></div>';
  $("#stream-status").textContent = "Idle";
  $("#stream-status").className = "panel__status";
  $("#results-status").textContent = "—";
  $("#results-status").className = "panel__status";
  $("#btn-start").disabled = false;
  $("#btn-start").textContent = "Start Investigation";
}

// ---- investigation ----

function startInvestigation() {
  if (state.investigating) return;
  state.investigating = true;
  if (state.eventSource) state.eventSource.close();

  $("#stream-body").innerHTML = "";
  $("#results-body").innerHTML = '<div class="empty-state"><p>Investigating…</p></div>';
  $("#stream-status").textContent = "Investigating";
  $("#stream-status").className = "panel__status is-active";
  $("#results-status").textContent = "Awaiting memo";
  $("#btn-start").disabled = true;
  $("#btn-start").textContent = "Investigating…";

  const es = new EventSource("/api/investigate?period=YTD");
  state.eventSource = es;

  // Accumulate thinking text into a single block until a tool_call arrives
  let thinkingBlock = null;

  es.addEventListener("status", e => {
    const data = JSON.parse(e.data);
    appendSystemBlock(data.message);
  });

  es.addEventListener("thinking", e => {
    const data = JSON.parse(e.data);
    if (!thinkingBlock) {
      thinkingBlock = document.createElement("div");
      thinkingBlock.className = "block block--thinking";
      thinkingBlock.innerHTML = '<div class="block__meta"><span>Reasoning</span></div><div class="block__body"></div>';
      appendToStream(thinkingBlock);
    }
    thinkingBlock.querySelector(".block__body").textContent += data.text;
    scrollStream();
  });

  es.addEventListener("tool_call", e => {
    thinkingBlock = null; // reset for next thinking chunk
    const data = JSON.parse(e.data);
    appendToolCallBlock(data);
  });

  es.addEventListener("tool_result", e => {
    const data = JSON.parse(e.data);
    updateToolResult(data);
  });

  es.addEventListener("final", e => {
    thinkingBlock = null;
    const data = JSON.parse(e.data);
    renderMemo(data.markdown);
  });

  es.addEventListener("done", () => {
    finishInvestigation();
    es.close();
  });

  es.addEventListener("error", e => {
    try {
      const data = JSON.parse(e.data);
      toast(data.message || "Investigation error.");
    } catch { /* SSE connection error */ }
    failInvestigation();
    es.close();
  });

  es.onerror = () => {
    if (state.investigating) failInvestigation();
    es.close();
  };
}

// ---- stream renderers ----

function appendSystemBlock(msg) {
  const div = document.createElement("div");
  div.className = "block block--system";
  div.innerHTML = `<div class="block__body">${escapeHtml(msg)}</div>`;
  appendToStream(div);
}

function appendToolCallBlock(data) {
  const div = document.createElement("div");
  div.className = "block block--tool";
  div.dataset.toolId = data.id;

  let detail = "";
  const input = data.input || {};
  if (data.name === "query_variances" || data.name === "drill_down_variance" || data.name === "summarize_vendor_spend" || data.name === "compare_period_over_period") {
    const filters = Object.entries(input).filter(([k,v]) => v != null).map(([k,v]) => `${k}=${v}`).join(", ");
    detail = filters ? `<div class="tool-purpose">${escapeHtml(filters)}</div>` : "";
  } else if (data.name === "get_dataset_overview") {
    detail = '<div class="tool-purpose">Inspecting dataset shape</div>';
  } else if (data.name === "compose_executive_summary") {
    detail = '<div class="tool-purpose">Preparing to write the memo</div>';
  }

  div.innerHTML = `
    <div class="block__meta"><span class="badge">tool call</span><span class="tool-name">${escapeHtml(data.name)}()</span></div>
    ${detail}
    <div class="tool-result-summary" data-result-slot>↳ executing…</div>`;
  appendToStream(div);
}

function updateToolResult(data) {
  const block = document.querySelector(`[data-tool-id="${data.id}"]`);
  if (!block) return;
  const slot = block.querySelector("[data-result-slot]");
  if (!slot) return;

  const result = data.result;
  if (result?.error) {
    slot.innerHTML = `↳ <span style="color:var(--negative)">${escapeHtml(result.error)}</span>`;
    return;
  }

  if (data.name === "query_variances" && result?.variances) {
    const n = result.variance_count ?? result.variances.length;
    slot.textContent = `↳ ${n} variance${n === 1 ? "" : "s"} found`;
    if (result.variances.length > 0) {
      const cols = ["period","department","account","variance","variance_pct","direction"];
      slot.innerHTML += renderTable(cols, result.variances.slice(0, 10).map(v => cols.map(c => v[c])));
    }
    return;
  }

  if (data.name === "drill_down_variance" && result?.transactions) {
    const shown = Math.min(result.transactions.length, 8);
    const matching = result.matching_transaction_count ?? result.transaction_count;
    const reconciliation = result.reconciliation?.status?.replaceAll("_", " ") ?? "not checked";
    slot.textContent = `↳ Showing ${shown} of ${matching} matching transactions. Full ledger total: ${result.total_amount_exact ?? result.total_amount}. Reconciliation: ${reconciliation}.`;
    if (result.transactions.length > 0) {
      const cols = ["source_row","vendor","amount_exact","memo"];
      slot.innerHTML += renderTable(cols, result.transactions.slice(0, 8).map(t => cols.map(c => t[c])));
    }
    return;
  }

  if (data.name === "summarize_vendor_spend" && result?.vendors) {
    slot.textContent = `↳ ${result.vendor_count} vendors`;
    if (result.vendors.length > 0) {
      const cols = ["vendor","total_spend","transaction_count"];
      slot.innerHTML += renderTable(cols, result.vendors.map(v => cols.map(c => v[c])));
    }
    return;
  }

  if (data.name === "compare_period_over_period") {
    slot.textContent = `↳ ${result.period_a}: ${result.actual_a} → ${result.period_b}: ${result.actual_b} (Δ ${result.delta}, ${result.delta_pct})`;
    return;
  }

  if (data.name === "get_dataset_overview") {
    slot.textContent = `↳ ${result.row_count} rows, ${result.periods?.length || "?"} periods, ${result.departments?.length || "?"} depts · Budget: ${result.total_budget} · Variance: ${result.total_variance}`;
    // Update ribbon with real numbers
    if (result.total_budget) $("#stat-budget").textContent = result.total_budget;
    if (result.total_actual) $("#stat-actual").textContent = result.total_actual;
    if (result.total_variance) { $("#stat-variance").textContent = result.total_variance; }
    return;
  }

  if (data.name === "compose_executive_summary") {
    slot.textContent = "↳ checklist received — writing memo";
    return;
  }

  slot.textContent = "↳ done";
}

function renderTable(columns, rows) {
  const head = columns.map(c => `<th>${escapeHtml(c)}</th>`).join("");
  const body = rows.map(row => `<tr>${row.map(v => `<td>${escapeHtml(v)}</td>`).join("")}</tr>`).join("");
  return `<table class="tool-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function appendToStream(el) {
  const body = $("#stream-body");
  body.appendChild(el);
  scrollStream();
}

function scrollStream() {
  const body = $("#stream-body");
  body.scrollTop = body.scrollHeight;
}

// ---- memo ----

function renderMemo(markdown) {
  state.memoMarkdown = markdown;
  const body = $("#results-body");
  body.innerHTML = "";

  const div = document.createElement("div");
  div.className = "memo";

  // Simple markdown → HTML (handles headers, bold, lists, paragraphs)
  const html = markdownToHtml(markdown);

  div.innerHTML = `
    <p class="memo__eyebrow">Executive Memorandum</p>
    <div class="memo__content">${html}</div>
    <div class="memo__cta">
      <button class="btn btn--secondary btn--small" id="btn-copy">Copy to Clipboard</button>
      <button class="btn btn--secondary btn--small" id="btn-download">Download .md</button>
    </div>`;
  body.appendChild(div);
  body.scrollTop = 0;

  $("#results-status").textContent = "Memo ready";
  $("#results-status").className = "panel__status is-done";

  div.querySelector("#btn-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(markdown); toast("Copied!"); } catch { toast("Copy failed."); }
  });
  div.querySelector("#btn-download").addEventListener("click", () => {
    const blob = new Blob([markdown], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "variance_memo.md";
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

function markdownToHtml(md) {
  // Minimal markdown parser — good enough for the agent's output
  return md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^\- (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, match => `<ul>${match}</ul>`)
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(.)/gm, (m, c) => {
      if (c === '<') return c;
      return c;
    });
}

function finishInvestigation() {
  state.investigating = false;
  $("#stream-status").textContent = "Done";
  $("#stream-status").className = "panel__status is-done";
  $("#btn-start").disabled = false;
  $("#btn-start").textContent = "Re-run Investigation";
}

function failInvestigation() {
  state.investigating = false;
  if (!state.memoMarkdown) toast("Investigation failed or disconnected.");
  $("#stream-status").textContent = "Failed";
  $("#stream-status").className = "panel__status";
  $("#btn-start").disabled = false;
  $("#btn-start").textContent = "Retry Investigation";
}

// ---- bootstrap ----

async function bootstrap() {
  try {
    const h = await fetch("/api/health").then(r => r.json());
    $("#model-badge").textContent = `Model · ${h.model}`;
  } catch {}

  $("#btn-sample").addEventListener("click", async () => {
    $("#btn-sample").disabled = true;
    try { await loadSample(); } catch (e) { toast(e.message); }
    finally { $("#btn-sample").disabled = false; }
  });

  // Upload flow: require both files via the existing API
  $("#file-bva").addEventListener("change", async () => {
    if ($("#file-bva").files?.[0] && $("#file-txn").files?.[0]) {
      try { await uploadFiles(); } catch (e) { toast(e.message); }
    }
  });
  $("#file-txn").addEventListener("change", async () => {
    if ($("#file-bva").files?.[0] && $("#file-txn").files?.[0]) {
      try { await uploadFiles(); } catch (e) { toast(e.message); }
    }
  });

  $("#btn-start").addEventListener("click", startInvestigation);
  $("#btn-reset").addEventListener("click", () => {
    if (state.eventSource) state.eventSource.close();
    state.investigating = false;
    showView("landing");
  });
}

document.addEventListener("DOMContentLoaded", bootstrap);
