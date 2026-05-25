const app = document.getElementById("app");
const monitor = {
  socket: null,
  jobs: new Map(),
  counts: { running: 0, queued: 0, failed: 0, stopped: 0 },
  events: [],
};
const companiesState = { page: 1, pageSize: 50, status: "", search: "", selected: new Set() };

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.detail || `HTTP ${response.status}`);
  return data;
}

function iconize() {
  if (window.lucide) window.lucide.createIcons();
}

function setRouteActive(route) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.route === route);
  });
}

function statusClass(status) {
  return ["gemini_quick", "searching", "scraping", "extracting"].includes(status) ? "running" : status;
}

function rowMessage(message) {
  return `<tr><td colspan="8" class="muted" style="text-align:center;padding:36px">${message}</td></tr>`;
}

function setConnection(state, label) {
  const el = document.getElementById("connectionState");
  el.className = `connection ${state}`;
  el.innerHTML = `<span></span>${label}`;
}

async function updateQuota() {
  try {
    const data = await api("/api/spa/status");
    const q = data.quota || {};
    const geminiLimit = q.gemini_limit || 1;
    const firecrawlTotal = q.firecrawl_total || 1;
    document.getElementById("quota-gemini").textContent = `${q.gemini_used || 0}/${geminiLimit}`;
    document.getElementById("quota-firecrawl").textContent = `${q.firecrawl_used || 0}/${firecrawlTotal}`;
    document.getElementById("quota-gemini-fill").style.width = `${Math.min(100, ((q.gemini_used || 0) / geminiLimit) * 100)}%`;
    document.getElementById("quota-firecrawl-fill").style.width = `${Math.min(100, ((q.firecrawl_used || 0) / firecrawlTotal) * 100)}%`;
  } catch {
    setConnection("offline", "Offline");
  }
}

async function renderDashboard() {
  setRouteActive("dashboard");
  const data = await api("/api/spa/status");
  const s = data.stats || {};
  const q = data.quota || {};
  const logs = data.logs || [];
  app.innerHTML = `
    <div class="page-title">
      <div><h1>Overview Dashboard</h1><div class="subtitle">System progress and recent activity</div></div>
    </div>
    <div class="grid stats">
      ${stat("Total Companies", s.total || 0)}
      ${stat("Done", s.done || 0, "success")}
      ${stat("Pending / Running", (s.pending || 0) + (s.running || 0), "warning")}
      ${stat("Failed", s.failed || 0, "danger-text")}
    </div>
    <div class="grid two" style="margin-top:16px">
      <div class="card">
        <h3>Completion</h3>
        <div class="progress" style="width:100%;height:14px"><div style="width:${s.progress_percent || 0}%"></div></div>
        <div class="toolbar" style="margin-top:14px">
          <span class="muted">Progress</span><strong>${s.progress_percent || 0}%</strong>
          <span class="spacer"></span>
          <span class="muted">Phone</span><strong>${s.phone_pct || 0}%</strong>
          <span class="muted">Email</span><strong>${s.email_pct || 0}%</strong>
        </div>
      </div>
      <div class="card">
        <h3>Today's Usage</h3>
        <div class="toolbar"><span class="muted">Tokens In</span><span class="spacer"></span><strong>${(q.tokens_in || 0).toLocaleString()}</strong></div>
        <div class="toolbar"><span class="muted">Tokens Out</span><span class="spacer"></span><strong>${(q.tokens_out || 0).toLocaleString()}</strong></div>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <h3>Recent Activity</h3>
      <div class="terminal">
        ${logs.length ? logs.map((l) => `<div class="terminal-line">${l.started_at || l.finished_at || ""} ${l.company_id ? `#${l.company_id}` : ""} ${l.step || "event"} ${l.status || ""} ${l.error_message || ""}</div>`).join("") : '<div class="terminal-line">No activity yet.</div>'}
      </div>
    </div>
  `;
}

function stat(label, value, className = "") {
  return `<div class="card"><div class="stat-value ${className}">${value}</div><div class="stat-label">${label}</div></div>`;
}

async function renderCompanies(patch = {}) {
  setRouteActive("companies");
  Object.assign(companiesState, patch);
  const params = new URLSearchParams({ page: companiesState.page, page_size: companiesState.pageSize });
  if (companiesState.status) params.set("status", companiesState.status);
  if (companiesState.search) params.set("search", companiesState.search);
  const data = await api(`/api/spa/companies?${params}`);
  const companies = data.companies || [];
  const counts = data.counts || {};
  const p = data.pagination || {};
  const allSelected = companies.length > 0 && companies.every(c => companiesState.selected.has(c.id));
  app.innerHTML = `
    <div class="page-title">
      <div><h1>Companies</h1><div class="subtitle">${p.total || 0} companies, server-side pagination</div></div>
      <div class="toolbar">
        <button class="btn" id="exportLogs"><i data-lucide="download"></i>Export Logs</button>
        <button class="btn primary" id="importBtn"><i data-lucide="upload"></i>Import</button>
        <input type="file" id="importInput" accept=".csv,.txt" hidden>
      </div>
    </div>
    <div class="toolbar">
      ${chip("All", "", counts.total)}
      ${chip("Done", "done", counts.done)}
      ${chip("Pending", "pending", counts.pending)}
      ${chip("Failed", "failed", counts.failed)}
      <span class="spacer"></span>
      <button class="btn primary" id="runSelected" ${companiesState.selected.size ? "" : "style='display:none'"}><i data-lucide="play"></i>Run Selected</button>
      <input class="input" id="search" value="${escapeHtml(companiesState.search)}" placeholder="Search companies...">
    </div>
    <div class="table-wrap fixed">
      <table>
        <thead><tr><th><input type="checkbox" id="selectPage" ${allSelected ? "checked" : ""}></th><th>ID</th><th>Name</th><th>Status</th><th>Checkpoint</th><th>Data</th><th>Updated</th><th>Actions</th></tr></thead>
        <tbody>${companies.length ? companies.map(companyRow).join("") : rowMessage("No companies found.")}</tbody>
      </table>
    </div>
    <div class="pagination">
      <button class="btn" id="prevPage" ${p.page <= 1 ? "disabled" : ""}>Previous</button>
      <span class="muted">Page ${p.page || 1} / ${p.total_pages || 1}</span>
      <button class="btn" id="nextPage" ${p.page >= p.total_pages ? "disabled" : ""}>Next</button>
    </div>
  `;
  bindCompanyEvents(companies, p);
  iconize();
}

function chip(label, status, count) {
  const active = companiesState.status === status ? "primary" : "";
  return `<button class="btn ${active}" data-status="${status}">${label} (${count || 0})</button>`;
}

function companyRow(c) {
  const selected = companiesState.selected.has(c.id);
  return `
    <tr class="${selected ? "selected" : ""}">
      <td><input type="checkbox" class="row-check" data-id="${c.id}" ${selected ? "checked" : ""}></td>
      <td class="muted">#${c.id}</td>
      <td><a href="#/company/${c.id}">${escapeHtml(c.name || "")}</a></td>
      <td><span class="badge ${statusClass(c.status)}">${c.status}</span></td>
      <td class="mono">${c.checkpoint || "pipeline_init"}</td>
      <td>${c.has_phone ? '<span class="success">phone</span>' : '<span class="muted">phone</span>'} · ${c.has_email ? '<span class="success">email</span>' : '<span class="muted">email</span>'}</td>
      <td class="muted">${c.updated_at || ""}</td>
      <td><button class="btn ghost run-one" data-id="${c.id}" title="Run"><i data-lucide="play"></i></button><button class="btn ghost" onclick="location.hash='#/company/${c.id}'" title="Open"><i data-lucide="eye"></i></button></td>
    </tr>
  `;
}

function bindCompanyEvents(companies, pagination) {
  document.querySelectorAll("[data-status]").forEach((btn) => btn.addEventListener("click", () => {
    companiesState.selected.clear();
    renderCompanies({ status: btn.dataset.status, page: 1 });
  }));
  let searchTimer;
  document.getElementById("search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      companiesState.selected.clear();
      renderCompanies({ search: event.target.value.trim(), page: 1 });
    }, 250);
  });
  const updateSelectedUI = () => {
    const runBtn = document.getElementById("runSelected");
    if (runBtn) runBtn.style.display = companiesState.selected.size ? "" : "none";
  };
  document.getElementById("selectPage").addEventListener("change", (event) => {
    const isChecked = event.target.checked;
    document.querySelectorAll(".row-check").forEach((check) => {
      check.checked = isChecked;
      const id = Number(check.dataset.id);
      isChecked ? companiesState.selected.add(id) : companiesState.selected.delete(id);
      check.closest("tr").className = isChecked ? "selected" : "";
    });
    updateSelectedUI();
  });
  document.querySelectorAll(".row-check").forEach((check) => check.addEventListener("change", () => {
    const id = Number(check.dataset.id);
    check.checked ? companiesState.selected.add(id) : companiesState.selected.delete(id);
    check.closest("tr").className = check.checked ? "selected" : "";
    document.getElementById("selectPage").checked = document.querySelectorAll(".row-check:not(:checked)").length === 0;
    updateSelectedUI();
  }));
  document.querySelectorAll(".run-one").forEach((button) => button.addEventListener("click", () => runCompanies([Number(button.dataset.id)])));
  document.getElementById("runSelected").addEventListener("click", () => runCompanies([...companiesState.selected]));
  document.getElementById("prevPage").addEventListener("click", () => renderCompanies({ page: Math.max(1, companiesState.page - 1) }));
  document.getElementById("nextPage").addEventListener("click", () => renderCompanies({ page: Math.min(pagination.total_pages || 1, companiesState.page + 1) }));
  document.getElementById("exportLogs").addEventListener("click", () => window.open("/api/export/logs?format=csv", "_blank"));
  document.getElementById("importBtn").addEventListener("click", () => document.getElementById("importInput").click());
  document.getElementById("importInput").addEventListener("change", (event) => importCompanies(event.target.files[0]));
}

async function runCompanies(ids) {
  if (!ids.length) return;
  const result = await api("/api/spa/runner/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_ids: ids }),
  });
  companiesState.selected.clear();
  alert(`Started: ${result.started.length}. Skipped: ${result.skipped.length}.`);
  location.hash = "#/monitor";
}

async function importCompanies(file) {
  if (!file) return;
  const text = await file.text();
  const names = text.split(/\r?\n/).map((line) => line.split(",")[0].trim()).filter(Boolean);
  if (!names.length) return alert("No company names found.");
  const result = await api("/api/companies/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names }),
  });
  alert(`Imported ${result.imported}; skipped ${result.skipped}.`);
  renderCompanies({ page: 1 });
}

async function renderCompanyDetail(id) {
  setRouteActive("companies");
  const data = await api(`/api/spa/companies/${id}`);
  const company = data.company;
  const contacts = data.contacts || [];
  const logs = data.timeline || [];
  const scrapedPages = data.scraped_pages || [];
  const filteredLinks = data.filtered_links || [];
  
  // Build step status strip
  const steps = ["gemini_quick", "deep_search", "filter", "scrape", "ai_extract"];
  const stepStatus = {};
  logs.forEach(l => {
      // Latest status for the step overwrites previous
      if (l.step && l.status) {
          stepStatus[l.step] = l.status; // "SUCCESS", "FAILED", "STARTED", etc.
      }
  });
  
  const stepStripHtml = steps.map(step => {
      let st = stepStatus[step];
      let color = "var(--muted)";
      if (st === "SUCCESS") color = "var(--green)";
      else if (st === "FAILED") color = "var(--red)";
      else if (st === "STARTED" || st === "RUNNING") color = "var(--blue)";
      
      return `<div style="flex: 1; text-align: center; padding: 10px; margin: 0 5px; border-radius: 4px; background: var(--surface); border: 2px solid ${color}; font-weight: bold; color: ${color}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 0.9em;">
          ${step.replace("_", " ")}<br>
          <small>${st || "PENDING"}</small>
      </div>`;
  }).join("");

  // Scraped URLs table
  let scrapedHtml = '<p class="muted">No scraped pages.</p>';
  if (scrapedPages.length) {
      scrapedHtml = `
      <div class="table-wrap" style="max-height: 300px; overflow-y: auto;">
          <table>
              <thead><tr><th>URL</th><th>Status</th><th>Length</th></tr></thead>
              <tbody>
                  ${scrapedPages.map(p => `<tr>
                      <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${p.url}"><a href="${p.url}" target="_blank">${p.url}</a></td>
                      <td><span class="badge ${p.scrape_status === 'success' ? 'success' : 'failed'}">${p.scrape_status}</span></td>
                      <td>${p.content_length || 0}</td>
                  </tr>`).join("")}
              </tbody>
          </table>
      </div>`;
  }
  
  // Top 10 Scored URLs
  let top10Html = '<p class="muted">No filtered links.</p>';
  const top10 = filteredLinks.slice(0, 10);
  if (top10.length) {
      top10Html = `
      <div class="table-wrap">
          <table>
              <thead><tr><th>Score</th><th>URL</th></tr></thead>
              <tbody>
                  ${top10.map(l => `<tr>
                      <td><strong>${l.relevance_score || 0}</strong></td>
                      <td style="max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${l.url}"><a href="${l.url}" target="_blank">${l.url}</a></td>
                  </tr>`).join("")}
              </tbody>
          </table>
      </div>`;
  }

  app.innerHTML = `
    <div class="page-title"><div><a href="#/companies" class="muted">← Companies</a><h1>${escapeHtml(company.original_name)}</h1><div class="subtitle">#${company.id} · ${company.status}</div></div></div>
    
    <div class="card" style="margin-bottom: 16px;">
        <h3 style="margin-bottom: 10px;">Pipeline Steps</h3>
        <div style="display: flex; flex-wrap: wrap; justify-content: space-between;">
            ${stepStripHtml}
        </div>
    </div>
    
    <div class="grid two">
      <div class="card" style="display: flex; flex-direction: column;">
          <h3>Contacts Extracted</h3>
          <div style="flex: 1;">
              ${contacts.length ? contacts.map((c) => `<div style="padding: 10px; border: 1px solid var(--border); margin-bottom: 10px; border-radius: 4px;">
                  <strong>Phone:</strong> ${c.phone || "—"} <br>
                  <strong>Email:</strong> ${c.email || "—"} <br>
                  <strong>Website:</strong> <a href="${c.website || "#"}" target="_blank">${c.website || "—"}</a><br>
                  <strong>Confidence:</strong> ${c.confidence_score || 0}
              </div>`).join("") : '<p class="muted">No contacts yet.</p>'}
          </div>
      </div>
      <div class="card">
          <h3>Gemini Quick</h3>
          <pre class="terminal" style="white-space: pre-wrap; word-break: break-word;">${escapeHtml(JSON.stringify(data.gemini_quick || {}, null, 2))}</pre>
      </div>
    </div>
    
    <div class="grid two" style="margin-top: 16px;">
        <div class="card">
            <h3>Top 10 Scored URLs</h3>
            ${top10Html}
        </div>
        <div class="card">
            <h3>Scraped URLs</h3>
            ${scrapedHtml}
        </div>
    </div>
    
    <div class="card" style="margin-top:16px"><h3>Timeline</h3><div class="terminal">${logs.length ? logs.map((l) => `<div class="terminal-line">${l.started_at || ""} ${l.step} ${l.status} ${l.error_message || ""}</div>`).join("") : '<div class="terminal-line">No logs yet.</div>'}</div></div>
  `;
}

async function renderMonitor() {
  setRouteActive("monitor");
  app.innerHTML = `
    <div class="page-title">
      <div><h1>Monitor Detail</h1><div class="subtitle">Realtime workflow state from backend events</div></div>
    </div>
    <div class="toolbar">
      <button class="btn danger" id="stopAll"><i data-lucide="square"></i>Stop All</button>
      <button class="btn" id="refreshMonitor"><i data-lucide="refresh-cw"></i>Refresh Snapshot</button>
    </div>
    <div class="grid stats" id="monitorSummary"></div>
    <div class="table-wrap fixed" style="margin-top:16px">
      <table><thead><tr><th>Company</th><th>Status</th><th>Step</th><th>Checkpoint</th><th>Progress</th><th>Updated</th><th>Actions</th></tr></thead><tbody id="monitorRows">${rowMessage("Connecting to monitor...")}</tbody></table>
    </div>
    <div class="card" style="margin-top:16px"><h3>Latest Events</h3><div class="terminal" id="monitorEvents"></div></div>
  `;
  document.getElementById("stopAll").addEventListener("click", stopAll);
  document.getElementById("refreshMonitor").addEventListener("click", loadMonitorSnapshot);
  iconize();
  await loadMonitorSnapshot();
  connectMonitorSocket();
}

async function loadMonitorSnapshot() {
  const data = await api("/api/spa/monitor");
  applyMonitorSnapshot(data);
}

function connectMonitorSocket() {
  if (monitor.socket) monitor.socket.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  setConnection("connecting", "Connecting");
  monitor.socket = new WebSocket(`${proto}://${location.host}/ws/monitor`);
  monitor.socket.onopen = () => setConnection("live", "Live");
  monitor.socket.onclose = () => {
    setConnection("offline", "Offline");
    if ((location.hash || "#/dashboard") === "#/monitor") setTimeout(connectMonitorSocket, 2000);
  };
  monitor.socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "snapshot") {
        applyMonitorSnapshot(payload);
        updateQuota();
    }
    if (payload.type === "job_removed") {
      monitor.jobs.delete(payload.company_id);
      monitor.counts = payload.counts || monitor.counts;
      pushMonitorEvent(`Removed #${payload.company_id} from monitor`);
      renderMonitorState();
      updateQuota();
    }
    if (payload.job) {
      monitor.jobs.set(payload.job.id, payload.job);
      monitor.counts = payload.counts || monitor.counts;
      pushMonitorEvent(`${payload.type}: #${payload.job.id} ${payload.job.name} · ${payload.job.status} · ${payload.job.step}`);
      renderMonitorState();
      updateQuota();
    }
  };
}

function applyMonitorSnapshot(data) {
  monitor.jobs = new Map((data.jobs || []).map((job) => [job.id, job]));
  monitor.counts = data.counts || monitor.counts;
  renderMonitorState();
}

function renderMonitorState() {
  const jobs = [...monitor.jobs.values()].sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  document.getElementById("monitorSummary").innerHTML = `
    ${stat("Running", monitor.counts.running || 0, "warning")}
    ${stat("Queued", monitor.counts.queued || 0)}
    ${stat("Failed", monitor.counts.failed || 0, "danger-text")}
    ${stat("Stopped", monitor.counts.stopped || 0)}
  `;
  document.getElementById("monitorRows").innerHTML = jobs.length ? jobs.map(jobRow).join("") : rowMessage("No companies are currently in the monitor list.");
  document.getElementById("monitorEvents").innerHTML = monitor.events.length ? monitor.events.map((event) => `<div class="terminal-line">${escapeHtml(event)}</div>`).join("") : '<div class="terminal-line">Waiting for workflow events...</div>';
  document.querySelectorAll(".remove-job").forEach((button) => button.addEventListener("click", () => removeJob(Number(button.dataset.id))));
  iconize();
}

function jobRow(job) {
  return `
    <tr>
      <td><strong>${escapeHtml(job.name || "")}</strong><div class="muted">#${job.id}</div></td>
      <td><span class="badge ${statusClass(job.status)}">${job.status}</span></td>
      <td>${escapeHtml(job.step || "")}</td>
      <td class="mono">${escapeHtml(job.checkpoint || "")}</td>
      <td><div class="progress"><div style="width:${job.progress || 0}%"></div></div><div class="muted">${job.progress || 0}%</div></td>
      <td class="muted">${job.updated_at || job.started || ""}</td>
      <td><button class="btn ghost" onclick="location.hash='#/company/${job.id}'"><i data-lucide="eye"></i></button><button class="btn ghost remove-job" data-id="${job.id}"><i data-lucide="trash-2"></i></button></td>
    </tr>
  `;
}

function pushMonitorEvent(text) {
  monitor.events.unshift(`${new Date().toLocaleTimeString()} ${text}`);
  monitor.events = monitor.events.slice(0, 200);
}

async function stopAll() {
  await api("/api/spa/runner/stop-all", { method: "POST" });
}

async function removeJob(id) {
  await api("/api/spa/monitor/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_id: id }),
  });
}

async function renderLogs() {
  setRouteActive("logs");
  const data = await api("/api/spa/logs?limit=300");
  app.innerHTML = `<div class="page-title"><div><h1>Raw Logs</h1><div class="subtitle">${data.date}</div></div><button class="btn" onclick="window.open('/api/export/logs?format=jsonl','_blank')"><i data-lucide="download"></i>Download</button></div><div class="terminal">${(data.lines || []).map((line) => `<div class="terminal-line">${escapeHtml(line)}</div>`).join("") || '<div class="terminal-line">No logs for today yet.</div>'}</div>`;
  iconize();
}

async function renderSettings() {
  setRouteActive("settings");
  app.innerHTML = `<div class="page-title"><div><h1>Settings</h1><div class="subtitle">Configuration editing</div></div></div><div class="card"><p>Loading settings...</p></div>`;
  
  try {
    const [settingsRes, modelsRes] = await Promise.all([
      fetch("/api/spa/settings", { cache: "no-store" }),
      fetch("/api/spa/gemini-models", { cache: "no-store" })
    ]);
    
    const settings = await settingsRes.json();
    let modelsHTML = "";
    if (modelsRes.ok) {
        const modelsData = await modelsRes.json();
        modelsHTML = (modelsData.models || []).map(m => `<option value="${m.name}">${m.displayName || m.name}</option>`).join("");
    } else {
        modelsHTML = `<option value="models/gemini-2.5-flash-lite">gemini-2.5-flash-lite (Failed to load dynamic list)</option>`;
    }
    
    const buildSelect = (id, label, value) => {
        let selectHtml = `<select id="${id}" class="form-select" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid var(--border); background: var(--surface); color: var(--text);">${modelsHTML}</select>`;
        if (value) {
            selectHtml = selectHtml.replace(`value="${value}"`, `value="${value}" selected`);
        }
        return `
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display:block; margin-bottom: 5px; font-weight: 500; color: var(--muted);">${label}</label>
            ${selectHtml}
        </div>`;
    };
    
    const buildInput = (id, label, value) => `
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display:block; margin-bottom: 5px; font-weight: 500; color: var(--muted);">${label}</label>
            <input type="text" id="${id}" class="form-input" value="${value || ''}" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid var(--border); background: var(--surface); color: var(--text);" placeholder="Leave unchanged to keep current key">
        </div>`;
    
    app.innerHTML = `
      <div class="page-title"><div><h1>Settings</h1><div class="subtitle">API Keys and Model Configuration</div></div></div>
      <div class="card" style="max-width: 600px;">
        <form id="settings-form" onsubmit="saveSettings(event)">
            ${buildInput("gemini_key", "Gemini API Key", settings.GEMINI_API_KEY)}
            ${buildInput("firecrawl_key", "Firecrawl API Key", settings.FIRECRAWL_API_KEY)}
            ${buildInput("serper_key", "Serper API Key", settings.SERPER_API_KEY)}
            ${buildSelect("grounding_model", "AI Grounding Model", settings.AI_GROUNDING_MODEL)}
            ${buildSelect("extractor_model", "AI Extractor Model", settings.AI_EXTRACTOR_MODEL)}
            <button type="submit" class="btn" style="background: var(--blue); color: white; margin-top: 10px; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;">Save Settings</button>
        </form>
      </div>
    `;
  } catch (err) {
      app.innerHTML = `<div class="card" style="color:red;">Error loading settings: ${err.message}</div>`;
  }
}

async function saveSettings(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.textContent = "Saving...";
    btn.disabled = true;
    
    const data = {
        GEMINI_API_KEY: document.getElementById("gemini_key").value,
        FIRECRAWL_API_KEY: document.getElementById("firecrawl_key").value,
        SERPER_API_KEY: document.getElementById("serper_key").value,
        AI_GROUNDING_MODEL: document.getElementById("grounding_model").value,
        AI_EXTRACTOR_MODEL: document.getElementById("extractor_model").value,
    };
    
    try {
        const res = await fetch("/api/spa/settings", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
        if (res.ok) {
            alert("Settings saved successfully!");
            renderSettings();
        } else {
            alert("Error saving settings");
            btn.textContent = "Save Settings";
            btn.disabled = false;
        }
    } catch (err) {
        alert("Error: " + err.message);
        btn.textContent = "Save Settings";
        btn.disabled = false;
    }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

async function router() {
  if (monitor.socket && !(location.hash || "#/dashboard").startsWith("#/monitor")) {
    monitor.socket.close();
    monitor.socket = null;
  }
  try {
    const hash = location.hash || "#/dashboard";
    if (hash.startsWith("#/company/")) return renderCompanyDetail(hash.split("/")[2]);
    if (hash === "#/companies") return renderCompanies();
    if (hash === "#/monitor" || hash === "#/runner") return renderMonitor();
    if (hash === "#/logs") return renderLogs();
    if (hash === "#/settings") return renderSettings();
    return renderDashboard();
  } catch (error) {
    app.innerHTML = `<div class="card"><h1 class="danger-text">Request failed</h1><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.getElementById("themeToggle").addEventListener("click", () => {
  document.body.dataset.theme = document.body.dataset.theme === "dark" ? "light" : "dark";
});

window.addEventListener("hashchange", router);
updateQuota();
setInterval(updateQuota, 30000);
router();

// Mobile Menu Toggle
function toggleMobileMenu() {
    document.querySelector('.sidebar').classList.toggle('active');
}

iconize();
