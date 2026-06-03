const app = document.getElementById("app");
const monitor = {
  socket: null,
  jobs: new Map(),
  counts: { running: 0, queued: 0, failed: 0, stopped: 0 },
  events: [],
};
const companiesState = {
  page: 1,
  pageSize: 50,
  status: "",
  search: "",
  importBatchId: "",
  dateMode: "created",
  dateFrom: "",
  dateTo: "",
  selected: new Set(),
};

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

let _quotaTimer = null;
const updateQuota = () => {
  clearTimeout(_quotaTimer);
  _quotaTimer = setTimeout(async () => {
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
  }, 1000);
};

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

function companyQueryParams({ includePaging = true } = {}) {
  const params = new URLSearchParams();
  if (includePaging) {
    params.set("page", companiesState.page);
    params.set("page_size", companiesState.pageSize);
  }
  if (companiesState.status) params.set("status", companiesState.status);
  if (companiesState.search) params.set("search", companiesState.search);
  if (companiesState.importBatchId) params.set("import_batch_id", companiesState.importBatchId);
  if (companiesState.dateFrom) params.set(`${companiesState.dateMode}_from`, companiesState.dateFrom);
  if (companiesState.dateTo) params.set(`${companiesState.dateMode}_to`, companiesState.dateTo);
  return params;
}

function localDate(offsetDays = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function batchOptions(batches) {
  const selected = String(companiesState.importBatchId || "");
  const options = batches.map((batch) => {
    const label = `#${batch.id} ${batch.source_filename || "Import"} (${batch.imported}/${batch.total})`;
    return `<option value="${batch.id}" ${selected === String(batch.id) ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  return `<option value="">All imports</option><option value="latest">Latest import</option>${options}`;
}

async function renderCompanies(patch = {}) {
  setRouteActive("companies");
  Object.assign(companiesState, patch);
  const [data, batchesData] = await Promise.all([
    api(`/api/spa/companies?${companyQueryParams()}`),
    api("/api/spa/import-batches"),
  ]);
  const companies = data.companies || [];
  const batches = batchesData.batches || [];
  const counts = data.counts || {};
  const p = data.pagination || {};
  const allSelected = companies.length > 0 && companies.every(c => companiesState.selected.has(c.id));
  app.innerHTML = `
    <div class="page-title">
      <div><h1>Companies</h1><div class="subtitle">${p.total || 0} companies, server-side pagination</div></div>
      <div class="toolbar">
        <button class="btn success" id="exportExcelBtn"><i data-lucide="file-spreadsheet"></i>Export Excel</button>
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
      <span class="selection-summary">${p.total || 0} shown · ${companiesState.selected.size} selected</span>
      <span class="spacer"></span>
      <button class="btn primary" id="runSelected" ${companiesState.selected.size ? "" : "style='display:none'"}><i data-lucide="play"></i>Run Selected</button>
      <button class="btn danger" id="deleteSelected" ${companiesState.selected.size ? "" : "style='display:none'"}><i data-lucide="trash-2"></i>Delete Selected</button>
      <input class="input" id="search" value="${escapeHtml(companiesState.search)}" placeholder="Search companies...">
    </div>
    <div class="toolbar filter-toolbar">
      <select class="select" id="dateMode">
        <option value="created" ${companiesState.dateMode === "created" ? "selected" : ""}>Imported date</option>
        <option value="completed" ${companiesState.dateMode === "completed" ? "selected" : ""}>Completed date</option>
      </select>
      <button class="btn" data-quick-date="today">Today</button>
      <button class="btn" data-quick-date="yesterday">Yesterday</button>
      <button class="btn" data-quick-date="last7">Last 7 days</button>
      <input class="input date-input" type="date" id="dateFrom" value="${escapeHtml(companiesState.dateFrom)}">
      <input class="input date-input" type="date" id="dateTo" value="${escapeHtml(companiesState.dateTo)}">
      <select class="select import-batch-select" id="importBatch">${batchOptions(batches)}</select>
      <button class="btn" id="clearFilters"><i data-lucide="x"></i>Clear filters</button>
      <button class="btn" id="selectAllFiltered"><i data-lucide="list-checks"></i>Select all filtered</button>
    </div>
    <div id="selectAllBanner" class="alert info" style="display: none; text-align: center; margin-bottom: 10px; background: var(--blue-light, #e0f2fe); color: var(--blue, #0284c7); padding: 8px; border-radius: 4px;">
      All <b id="bannerCurrentCount">0</b> companies on this page are selected. 
      <a href="#" id="bannerSelectAllLink" style="font-weight: bold; cursor: pointer; text-decoration: underline;">Select all <span id="bannerTotalCount">0</span> companies matching this filter</a>
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
      <td><button class="btn ghost run-one" data-id="${c.id}" title="Run"><i data-lucide="play"></i></button><button class="btn ghost" onclick="location.hash='#/company/${c.id}'" title="Open"><i data-lucide="eye"></i></button><button class="btn ghost danger-text delete-one" data-id="${c.id}" title="Delete"><i data-lucide="trash-2"></i></button></td>
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
  document.getElementById("dateMode").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ dateMode: event.target.value, page: 1 });
  });
  document.querySelectorAll("[data-quick-date]").forEach((button) => button.addEventListener("click", () => {
    const value = button.dataset.quickDate;
    const today = localDate(0);
    const yesterday = localDate(-1);
    const patch = value === "today"
      ? { dateFrom: today, dateTo: today }
      : value === "yesterday"
        ? { dateFrom: yesterday, dateTo: yesterday }
        : { dateFrom: localDate(-6), dateTo: today };
    companiesState.selected.clear();
    renderCompanies({ ...patch, page: 1 });
  }));
  document.getElementById("dateFrom").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ dateFrom: event.target.value, page: 1 });
  });
  document.getElementById("dateTo").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ dateTo: event.target.value, page: 1 });
  });
  document.getElementById("importBatch").addEventListener("change", async (event) => {
    const value = event.target.value;
    companiesState.selected.clear();
    if (value === "latest") {
      const data = await api("/api/spa/import-batches?limit=1");
      const latest = (data.batches || [])[0];
      return renderCompanies({ importBatchId: latest ? String(latest.id) : "", page: 1 });
    }
    renderCompanies({ importBatchId: value, page: 1 });
  });
  document.getElementById("clearFilters").addEventListener("click", () => {
    companiesState.selected.clear();
    renderCompanies({ status: "", search: "", importBatchId: "", dateMode: "created", dateFrom: "", dateTo: "", page: 1 });
  });
  const updateSelectedUI = () => {
    const runBtn = document.getElementById("runSelected");
    const delBtn = document.getElementById("deleteSelected");
    const show = companiesState.selected.size ? "" : "none";
    if (runBtn) runBtn.style.display = show;
    if (delBtn) delBtn.style.display = show;
    
    // Update banner
    const selectPageChecked = document.getElementById("selectPage").checked;
    const banner = document.getElementById("selectAllBanner");
    const totalCurrentPage = document.querySelectorAll(".row-check").length;
    
    if (selectPageChecked && totalCurrentPage > 0 && pagination.total > totalCurrentPage) {
        if (companiesState.selected.size < pagination.total) {
            banner.style.display = "block";
            document.getElementById("bannerCurrentCount").textContent = totalCurrentPage;
            document.getElementById("bannerTotalCount").textContent = pagination.total;
        } else {
            // Already selected all across pages
            banner.style.display = "block";
            banner.innerHTML = `All <b>${pagination.total}</b> companies matching this filter are selected. <a href="#" id="bannerClearSelection" style="font-weight: bold; cursor: pointer; text-decoration: underline;">Clear selection</a>`;
            document.getElementById("bannerClearSelection").addEventListener("click", (e) => {
                e.preventDefault();
                companiesState.selected.clear();
                renderCompanies({ page: companiesState.page });
            });
        }
    } else {
        banner.style.display = "none";
    }
  };
  
  if (document.getElementById("bannerSelectAllLink")) {
      document.getElementById("bannerSelectAllLink").addEventListener("click", async (e) => {
          e.preventDefault();
          const result = await api(`/api/spa/companies/ids?${companyQueryParams({ includePaging: false })}`);
          companiesState.selected = new Set(result.company_ids || []);
          renderCompanies();
      });
  }

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
  document.getElementById("selectAllFiltered").addEventListener("click", async () => {
    const result = await api(`/api/spa/companies/ids?${companyQueryParams({ includePaging: false })}`);
    companiesState.selected = new Set(result.company_ids || []);
    renderCompanies();
  });
  document.querySelectorAll(".run-one").forEach((button) => button.addEventListener("click", () => runCompanies([Number(button.dataset.id)])));
  document.querySelectorAll(".delete-one").forEach((button) => button.addEventListener("click", () => deleteCompanies([Number(button.dataset.id)])));
  document.getElementById("runSelected").addEventListener("click", () => runCompanies([...companiesState.selected]));
  document.getElementById("deleteSelected").addEventListener("click", () => deleteCompanies([...companiesState.selected]));
  document.getElementById("prevPage").addEventListener("click", () => renderCompanies({ page: Math.max(1, companiesState.page - 1) }));
  document.getElementById("nextPage").addEventListener("click", () => renderCompanies({ page: Math.min(pagination.total_pages || 1, companiesState.page + 1) }));
  document.getElementById("exportExcelBtn").addEventListener("click", () => {
    if (companiesState.selected.size === 0) {
      alert("Please select at least one company to export.");
      return;
    }
    const ids = Array.from(companiesState.selected);
    const btn = document.getElementById("exportExcelBtn");
    const oldText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="loader-2" class="spin"></i> Exporting...`;
    btn.disabled = true;
    
    fetch("/api/export-excel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: ids })
    })
    .then(async res => {
      if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Export failed");
      }
      return res.blob();
    })
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `final_results_export.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    })
    .catch(err => {
      alert("Error exporting: " + err.message);
    })
    .finally(() => {
      btn.innerHTML = oldText;
      btn.disabled = false;
      iconize();
    });
  });
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

async function deleteCompanies(ids) {
  if (!ids.length) return;
  const msg = ids.length === 1
    ? `Bạn có chắc chắn muốn xóa công ty #${ids[0]}?\nToàn bộ dữ liệu liên quan sẽ bị xóa vĩnh viễn.`
    : `Bạn có chắc chắn muốn xóa ${ids.length} công ty?\nToàn bộ dữ liệu liên quan sẽ bị xóa vĩnh viễn.`;
  if (!confirm(msg)) return;
  try {
    const result = await api("/api/spa/companies/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: ids }),
    });
    companiesState.selected.clear();
    alert(`Đã xóa ${result.deleted} công ty thành công.`);
    renderCompanies();
  } catch (err) {
    alert("Lỗi khi xóa: " + err.message);
  }
}

async function importCompanies(file) {
  if (!file) return;
  const text = await file.text();
  const names = text.split(/\r?\n/).map((line) => line.split(",")[0].trim()).filter(Boolean);
  if (!names.length) return alert("No company names found.");
  const result = await api("/api/companies/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names, source_filename: file.name }),
  });
  alert(`Imported ${result.imported}; skipped ${result.skipped}.`);
  companiesState.selected.clear();
  renderCompanies({ importBatchId: String(result.batch_id || ""), page: 1 });
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
    const [settingsRes, pipelineRes, modelsRes] = await Promise.all([
      fetch("/api/spa/settings", { cache: "no-store" }),
      fetch("/api/spa/pipeline-config", { cache: "no-store" }),
      fetch("/api/spa/gemini-models", { cache: "no-store" })
    ]);
    
    const settings = await settingsRes.json();
    const pipelineConfig = await pipelineRes.json();
    
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
    
    const buildInput = (id, label, value, placeholder="Leave unchanged to keep current key", type="text") => `
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display:block; margin-bottom: 5px; font-weight: 500; color: var(--muted);">${label}</label>
            <input type="${type}" id="${id}" class="form-input" value="${value || (type==='number' ? 0 : '')}" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid var(--border); background: var(--surface); color: var(--text);" placeholder="${placeholder}">
        </div>`;

    const buildTextarea = (id, label, value, hint="") => `
        <div class="form-group" style="margin-bottom: 15px;">
            <label style="display:block; margin-bottom: 5px; font-weight: 500; color: var(--muted);">${label}</label>
            <textarea id="${id}" class="form-input" rows="3" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font-family: monospace; font-size: 13px;">${(typeof value === 'string' ? value : JSON.stringify(value, null, 2)) || ''}</textarea>
            ${hint ? `<small style="color: var(--muted);">${hint}</small>` : ''}
        </div>`;
        
    const buildCheckbox = (id, label, checked) => `
        <div class="form-group" style="margin-bottom: 15px; display: flex; align-items: center; gap: 10px;">
            <input type="checkbox" id="${id}" ${checked ? 'checked' : ''} style="width: 16px; height: 16px; cursor: pointer;">
            <label for="${id}" style="font-weight: 500; color: var(--text); cursor: pointer; margin: 0;">${label}</label>
        </div>`;
    
    app.innerHTML = `
      <div class="page-title"><div><h1>Settings</h1><div class="subtitle">API Keys and Pipeline Configuration</div></div></div>
      <div style="display: flex; gap: 20px; flex-wrap: wrap;">
          <div class="card" style="flex: 1; min-width: 300px; max-width: 500px;">
            <h2 style="margin-bottom: 15px; font-size: 1.2rem;">API & Models</h2>
            <form id="settings-form" onsubmit="saveSettings(event)">
                ${buildInput("gemini_key", "Gemini API Key", settings.GEMINI_API_KEY)}
                ${buildInput("firecrawl_key", "Firecrawl API Key", settings.FIRECRAWL_API_KEY)}
                ${buildInput("serper_key", "Serper API Key", settings.SERPER_API_KEY)}
                ${buildSelect("grounding_model", "AI Grounding Model", settings.AI_GROUNDING_MODEL)}
                ${buildSelect("extractor_model", "AI Extractor Model", settings.AI_EXTRACTOR_MODEL)}
                <button type="submit" class="btn" style="background: var(--blue); color: white; margin-top: 10px; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;">Save API Keys</button>
            </form>
          </div>
          
          <div class="card" style="flex: 2; min-width: 300px;">
            <h2 style="margin-bottom: 15px; font-size: 1.2rem;">Pipeline Logic</h2>
            <form id="pipeline-form" onsubmit="savePipelineConfig(event)">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                    <!-- Section A: Scrape/Search Control -->
                    <div>
                        <h3 style="margin-bottom: 10px; font-size: 1rem; color: var(--blue);">Scrape & Search Control</h3>
                        ${buildInput("TOP_N", "Top N Pages to Scrape", pipelineConfig.TOP_N, "", "number")}
                        ${buildInput("SEARCH_LIMIT", "Serper Search Limit", pipelineConfig.SEARCH_LIMIT, "", "number")}
                        ${buildInput("SERPER_NUM_RESULTS", "Results per Serper request", pipelineConfig.SERPER_NUM_RESULTS, "", "number")}
                        ${buildInput("INFER_MAX_SCRAPE", "Max Scrapes for Inference", pipelineConfig.INFER_MAX_SCRAPE, "", "number")}
                    </div>
                    
                    <!-- Section C: Pipeline Behavior -->
                    <div>
                        <h3 style="margin-bottom: 10px; font-size: 1rem; color: var(--blue);">Pipeline Behavior</h3>
                        ${buildInput("EARLY_STOP_COUNT", "Early Stop Count", pipelineConfig.EARLY_STOP_COUNT, "", "number")}
                        ${buildInput("EARLY_STOP_SCORE", "Early Stop Score", pipelineConfig.EARLY_STOP_SCORE, "", "number")}
                        ${buildInput("DELAY_SECONDS", "Delay Seconds", pipelineConfig.DELAY_SECONDS, "", "number")}
                        ${buildInput("MAX_RETRIES", "Max Retries", pipelineConfig.MAX_RETRIES, "", "number")}
                        ${buildInput("BATCH_SIZE", "Batch Size", pipelineConfig.BATCH_SIZE, "", "number")}
                        ${buildInput("MIN_CONFIDENCE_THRESHOLD", "Min Confidence", pipelineConfig.MIN_CONFIDENCE_THRESHOLD, "", "number")}
                        ${buildInput("MIN_SCRAPE_SCORE", "Min Scrape Score", pipelineConfig.MIN_SCRAPE_SCORE, "", "number")}
                    </div>
                    
                    <!-- Section D: Feature Toggles -->
                    <div>
                        <h3 style="margin-bottom: 10px; font-size: 1rem; color: var(--blue);">Feature Toggles</h3>
                        ${buildCheckbox("GEMINI_QUICK_ENABLED", "Enable Gemini Quick Search", pipelineConfig.GEMINI_QUICK_ENABLED)}
                        ${buildCheckbox("SERPER_ENABLED", "Enable Serper Search", pipelineConfig.SERPER_ENABLED)}
                        ${buildCheckbox("GOOGLE_MAPS_ENABLED", "Enable Google Maps Lookup", pipelineConfig.GOOGLE_MAPS_ENABLED)}
                        ${buildCheckbox("SCRAPE_LINKEDIN_ENABLED", "Enable LinkedIn Scrape", pipelineConfig.SCRAPE_LINKEDIN_ENABLED)}
                        ${buildCheckbox("ENABLE_QUERY_DEDUP", "Enable Query Dedup", pipelineConfig.ENABLE_QUERY_DEDUP)}
                        ${buildCheckbox("ENABLE_URL_DEDUP", "Enable URL Dedup", pipelineConfig.ENABLE_URL_DEDUP)}
                        ${buildCheckbox("ENABLE_GLOBAL_CACHE", "Enable Global Cache", pipelineConfig.ENABLE_GLOBAL_CACHE)}
                        ${buildInput("CACHE_TTL_DAYS", "Cache TTL (Days)", pipelineConfig.CACHE_TTL_DAYS, "", "number")}
                    </div>
                </div>
                
                <!-- Section B: Scoring and Domains -->
                <div style="margin-top: 20px;">
                    <h3 style="margin-bottom: 10px; font-size: 1rem; color: var(--blue);">Scoring & Domains (JSON Format)</h3>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                        ${buildTextarea("DOMAIN_SCORES", "Domain Scores (JSON)", pipelineConfig.DOMAIN_SCORES, "JSON object mapping categories to scores")}
                        ${buildTextarea("KEYWORD_SCORES", "Keyword Scores (JSON)", pipelineConfig.KEYWORD_SCORES, "JSON object mapping keywords to scores")}
                        ${buildTextarea("BLACKLISTED_DOMAINS", "Blacklist Domains (JSON array)", pipelineConfig.BLACKLISTED_DOMAINS, "JSON array of strings")}
                        ${buildTextarea("SKIP_DOMAINS", "Skip Domains (JSON array)", pipelineConfig.SKIP_DOMAINS, "JSON array of strings")}
                    </div>
                </div>
                
                <button type="submit" class="btn" style="background: var(--blue); color: white; margin-top: 20px; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; width: 100%;">Save Pipeline Config</button>
            </form>
          </div>
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
            btn.textContent = "Save API Keys";
            btn.disabled = false;
        }
    } catch (err) {
        alert("Error: " + err.message);
        btn.textContent = "Save API Keys";
        btn.disabled = false;
    }
}

async function savePipelineConfig(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.textContent = "Saving...";
    btn.disabled = true;
    
    let data = {};
    try {
        // Parse numbers
        const numFields = ['TOP_N', 'SEARCH_LIMIT', 'SERPER_NUM_RESULTS', 'INFER_MAX_SCRAPE', 'EARLY_STOP_COUNT', 'EARLY_STOP_SCORE', 'DELAY_SECONDS', 'MAX_RETRIES', 'BATCH_SIZE', 'MIN_CONFIDENCE_THRESHOLD', 'MIN_SCRAPE_SCORE', 'CACHE_TTL_DAYS'];
        for (const f of numFields) {
            const val = parseFloat(document.getElementById(f).value);
            if (isNaN(val)) throw new Error(`Invalid number for ${f}`);
            data[f] = val;
        }
        
        // Parse booleans
        const boolFields = ['GEMINI_QUICK_ENABLED', 'SERPER_ENABLED', 'GOOGLE_MAPS_ENABLED', 'SCRAPE_LINKEDIN_ENABLED', 'ENABLE_QUERY_DEDUP', 'ENABLE_URL_DEDUP', 'ENABLE_GLOBAL_CACHE'];
        for (const f of boolFields) {
            data[f] = document.getElementById(f).checked;
        }
        
        // Parse JSON
        const jsonFields = ['DOMAIN_SCORES', 'KEYWORD_SCORES', 'BLACKLISTED_DOMAINS', 'SKIP_DOMAINS'];
        for (const f of jsonFields) {
            try {
                data[f] = JSON.parse(document.getElementById(f).value);
            } catch (err) {
                throw new Error(`Invalid JSON format in ${f}`);
            }
        }
    } catch (err) {
        alert(err.message);
        btn.textContent = "Save Pipeline Config";
        btn.disabled = false;
        return;
    }
    // Send data to server
    
    try {
        const res = await fetch("/api/spa/pipeline-config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
        if (res.ok) {
            alert("Pipeline Config saved successfully!");
            renderSettings();
        } else {
            alert("Error saving pipeline config");
            btn.textContent = "Save Pipeline Config";
            btn.disabled = false;
        }
    } catch (err) {
        alert("Error: " + err.message);
        btn.textContent = "Save Pipeline Config";
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
