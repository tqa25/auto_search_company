import { parseCompanyImportText } from "./companyImportParser.js";

const app = document.getElementById("app");
const monitor = {
  socket: null,
  jobs: new Map(),
  counts: { running: 0, queued: 0, failed: 0, stopped: 0, stale: 0 },
  worker: { online: false, workers: [], message: "Worker status unknown" },
  runtimeHealth: null,
  events: [],
  showStaleOnly: false,
};
const companiesState = {
  page: 1,
  pageSize: 50,
  status: "",
  search: "",
  importBatchId: "",
  importOutcome: "",
  completion: "",
  checkpoint: "",
  reportState: "",
  reportWindow: "",
  showNormalizedNames: false,
  dateMode: "created",
  dateFrom: "",
  dateTo: "",
  selected: new Set(),
};
const scoringDomainsState = {
  activeTab: "scores",
};
const SCORING_DOMAIN_TABS = [
  { id: "scores", label: "Scores" },
  { id: "known", label: "Known Sources" },
  { id: "skip", label: "Skip Domains" },
  { id: "blacklist", label: "Blacklist" },
];
const VN_TIMEZONE = "Asia/Ho_Chi_Minh";
const VN_DATE_PARTS = new Intl.DateTimeFormat("en-CA", {
  timeZone: VN_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const VN_DATETIME_FORMATTER = new Intl.DateTimeFormat("sv-SE", {
  timeZone: VN_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const VN_TIME_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  timeZone: VN_TIMEZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const PIPELINE_CONFIG_DEFAULTS = {
  FIRECRAWL_BATCH_SCRAPE_ENABLED: false,
  FIRECRAWL_MAX_CONCURRENCY: 10,
  FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS: 2.0,
  FIRECRAWL_BATCH_TIMEOUT_SECONDS: 300.0,
  BUSINESS_STATUS_GATE_ENABLED: true,
  REPORT_CUTOFF_TIME: "17:00",
};

const STATUS_FILTER_OPTIONS = [
  ["", "All statuses"],
  ["pending", "Pending"],
  ["gemini_quick", "Gemini Quick"],
  ["gemini_quick_done", "Gemini Quick Done"],
  ["searching", "Searching"],
  ["searched", "Searched"],
  ["scraping", "Scraping"],
  ["scraped", "Scraped"],
  ["ai_extract_pending", "AI Extract Pending"],
  ["extracting", "Extracting"],
  ["ai_done", "AI Done"],
  ["done", "Done"],
  ["failed", "Failed"],
  ["permanently_failed", "Permanently Failed"],
];


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
  return ["gemini_quick", "searching", "scraping", "extracting", "running", "stopping"].includes(status) ? "running" : status;
}

function rowMessage(message, colspan = 8) {
  return `<tr><td colspan="${colspan}" class="muted" style="text-align:center;padding:36px">${message}</td></tr>`;
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
        ${logs.length ? logs.map((l) => `<div class="terminal-line">${formatDashboardTimestamp(l.started_at || l.finished_at || "")} ${l.company_id ? `#${l.company_id}` : ""} ${l.step || "event"} ${l.status || ""} ${l.error_message || ""}</div>`).join("") : '<div class="terminal-line">No activity yet.</div>'}
      </div>
    </div>
  `;
}

function stat(label, value, className = "") {
  return `<div class="card"><div class="stat-value ${className}">${value}</div><div class="stat-label">${label}</div></div>`;
}


export function isValidDomain(value) {
  const domain = String(value || "").trim().toLowerCase();
  return /^(?!-)(?:[a-z0-9-]{1,63}\.)+[a-z]{2,63}$/.test(domain)
    && domain.split(".").every((part) => !part.endsWith("-"));
}

function toFormValue(value) {
  return value || value === 0 ? String(value) : "";
}

function numberValue(id, label) {
  const input = document.getElementById(id);
  const value = Number(input.value);
  if (input.value.trim() === "" || !Number.isFinite(value)) throw new Error(`${label} must be a number.`);
  return value;
}

export function parseScoreRows(rows, label) {
  const result = {};
  rows.forEach((row, index) => {
    const key = String(row.key || "").trim();
    const score = Number(row.score);
    if (!key) throw new Error(`${label} row ${index + 1} needs a category or keyword.`);
    if (!Number.isFinite(score)) throw new Error(`${label} row ${index + 1} needs a numeric score.`);
    result[key] = score;
  });
  return result;
}

export function parseKnownSourceRows(rows) {
  const result = {};
  rows.forEach((row, index) => {
    const domain = String(row.domain || "").trim().toLowerCase();
    const sourceType = String(row.sourceType || "").trim();
    const scoreCategory = String(row.scoreCategory || "").trim();
    if (!isValidDomain(domain)) throw new Error(`Known Sources row ${index + 1} has an invalid domain.`);
    if (!sourceType) throw new Error(`Known Sources row ${index + 1} needs a source type.`);
    if (!scoreCategory) throw new Error(`Known Sources row ${index + 1} needs a score category.`);
    result[domain] = [sourceType, scoreCategory];
  });
  return result;
}

export function parseDomainList(values, label) {
  const result = [];
  values.forEach((value, index) => {
    const domain = String(value || "").trim().toLowerCase();
    if (!domain) return;
    if (!isValidDomain(domain)) throw new Error(`${label} item ${index + 1} is not a valid domain.`);
    if (!result.includes(domain)) result.push(domain);
  });
  return result;
}

function readRows(containerId, mapper) {
  return [...document.querySelectorAll(`#${containerId} [data-row]`)].map(mapper);
}

export function collectScoringDomainsConfigFromDocument() {
  return {
    DOMAIN_SCORES: parseScoreRows(readRows("domainScoreRows", (row) => ({
      key: row.querySelector('[data-field="key"]').value,
      score: row.querySelector('[data-field="score"]').value,
    })), "Domain Scores"),
    KEYWORD_SCORES: parseScoreRows(readRows("keywordScoreRows", (row) => ({
      key: row.querySelector('[data-field="key"]').value,
      score: row.querySelector('[data-field="score"]').value,
    })), "Keyword Scores"),
    KNOWN_DOMAINS: parseKnownSourceRows(readRows("knownSourceRows", (row) => ({
      domain: row.querySelector('[data-field="domain"]').value,
      sourceType: row.querySelector('[data-field="sourceType"]').value,
      scoreCategory: row.querySelector('[data-field="scoreCategory"]').value,
    }))),
    SKIP_DOMAINS: parseDomainList(readRows("skipDomainRows", (row) => row.dataset.value), "Skip Domains"),
    BLACKLISTED_DOMAINS: parseDomainList(readRows("blacklistDomainRows", (row) => row.dataset.value), "Blacklist"),
  };
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
  if (companiesState.importOutcome) params.set("import_outcome", companiesState.importOutcome);
  if (companiesState.completion) params.set("completion", companiesState.completion);
  if (companiesState.checkpoint) params.set("checkpoint", companiesState.checkpoint);
  if (companiesState.reportState) params.set("report_state", companiesState.reportState);
  if (companiesState.reportWindow) params.set("report_window", companiesState.reportWindow);
  if (companiesState.dateFrom) params.set(`${companiesState.dateMode}_from`, companiesState.dateFrom);
  if (companiesState.dateTo) params.set(`${companiesState.dateMode}_to`, companiesState.dateTo);
  return params;
}

function datePartsMap(formatter, value) {
  return formatter.formatToParts(value).reduce((acc, part) => {
    if (part.type !== "literal") acc[part.type] = part.value;
    return acc;
  }, {});
}

export function localDate(offsetDays = 0) {
  const parts = datePartsMap(VN_DATE_PARTS, new Date());
  const date = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)));
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

function parseDashboardTimestamp(value) {
  if (!value) return null;
  const text = String(value).trim();
  const normalized = text.includes("T")
    ? text
    : `${text.replace(" ", "T")}+07:00`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDashboardTimestamp(value) {
  const parsed = parseDashboardTimestamp(value);
  return parsed ? VN_DATETIME_FORMATTER.format(parsed).replace(",", "") : (value || "");
}

function formatVnTime(value = new Date()) {
  return VN_TIME_FORMATTER.format(value);
}

function batchOptions(batches) {
  const selected = String(companiesState.importBatchId || "");
  const options = batches.map((batch) => {
    const reviewCount = (batch.ambiguous || 0) + (batch.duplicate_in_file || 0);
    const suffix = reviewCount ? `, review ${reviewCount}` : "";
    const label = `#${batch.id} ${batch.source_filename || "Import"} (${batch.imported}/${batch.total}${suffix})`;
    return `<option value="${batch.id}" ${selected === String(batch.id) ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  return `<option value="">All imports</option><option value="latest">Latest import</option>${options}`;
}

function checkpointOptions() {
  const options = [
    ["", "All checkpoints"],
    ["pipeline_init", "Waiting"],
    ["gemini_quick", "Gemini Quick"],
    ["deep_search", "Deep Search"],
    ["filter", "Filter"],
    ["scrape", "Scrape"],
    ["ai_extract", "AI Extract"],
    ["done", "Done"],
    ["failed", "Failed"],
    ["permanently_failed", "Permanently Failed"],
  ];
  return options.map(([value, label]) => `<option value="${value}" ${companiesState.checkpoint === value ? "selected" : ""}>${label}</option>`).join("");
}

function statusFilterOptions(counts = {}) {
  const byStatus = counts.by_status || {};
  const known = new Set(STATUS_FILTER_OPTIONS.map(([value]) => value).filter(Boolean));
  const extra = Object.keys(byStatus)
    .filter((status) => status && !known.has(status))
    .sort()
    .map((status) => [status, status]);
  return [...STATUS_FILTER_OPTIONS, ...extra].map(([value, label]) => {
    const countLabel = value ? ` (${byStatus[value] || 0})` : "";
    return `<option value="${value}" ${companiesState.status === value ? "selected" : ""}>${label}${countLabel}</option>`;
  }).join("");
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
  const importSummary = data.import_summary || null;
  const isBatchView = Boolean(companiesState.importBatchId && importSummary);
  const showNormalized = Boolean(companiesState.showNormalizedNames);
  const selectableCompanies = companies.filter(c => c.id);
  const allSelected = selectableCompanies.length > 0 && selectableCompanies.every(c => companiesState.selected.has(c.id));
  const selectedStaleIds = companies.filter(c => c.id && c.can_reset_resume && companiesState.selected.has(c.id)).map(c => c.id);
  const selectedIncompleteIds = companies.filter(c => c.id && c.can_resume_incomplete && companiesState.selected.has(c.id)).map(c => c.id);
  const tableColspan = 8 + (isBatchView ? 1 : 0) + (showNormalized ? 1 : 0);
  const normalizedHeader = showNormalized ? "<th>Normalized</th>" : "";
  const importHeader = isBatchView ? "<th>Import Status</th>" : "";
  const statusHeader = isBatchView ? "Pipeline Status" : "Status";
  const importFilters = isBatchView ? `
    <div class="toolbar import-outcome-toolbar">
      ${importChip("All import rows", "", importSummary.total_items || 0)}
      ${importChip("Imported", "imported", importSummary.imported || 0)}
      ${importChip("MST match", "matched_by_tax_code", importSummary.matched_by_tax_code || 0)}
      ${importChip("Score match", "matched_by_score", importSummary.matched_by_score || 0)}
      ${importChip("Review", "ambiguous", importSummary.ambiguous || 0)}
      ${importChip("Duplicate in file", "duplicate_in_file", importSummary.duplicate_in_file || 0)}
      ${importChip("Invalid", "invalid", importSummary.invalid || 0)}
      <span class="spacer"></span>
      <label class="inline-check"><input type="checkbox" id="showNormalizedNames" ${showNormalized ? "checked" : ""}> Show normalized names</label>
    </div>` : `
    <div class="toolbar import-outcome-toolbar">
      <span class="spacer"></span>
      <label class="inline-check"><input type="checkbox" id="showNormalizedNames" ${showNormalized ? "checked" : ""}> Show normalized names</label>
    </div>`;
  app.innerHTML = `
    <div class="page-title">
      <div><h1>Companies</h1><div class="subtitle">${p.total || 0} ${isBatchView ? "import rows" : "companies"}, server-side pagination</div></div>
      <div class="toolbar">
        <button class="btn success" id="exportExcelBtn"><i data-lucide="file-spreadsheet"></i>Export Excel</button>
        <button class="btn" id="exportLogs"><i data-lucide="download"></i>Export Logs</button>
        <button class="btn primary" id="importBtn"><i data-lucide="upload"></i>Import</button>
        <input type="file" id="importInput" accept=".csv,.txt,.md" hidden>
      </div>
    </div>
    <div class="toolbar">
      ${chip("All", "", counts.total)}
      ${chip("Done", "done", counts.done)}
      ${chip("Pending", "pending", counts.pending)}
      ${chip("Failed", "failed", counts.failed)}
      <span class="selection-summary">${p.total || 0} shown · ${companiesState.selected.size} selected</span>
      <span class="spacer"></span>
      <button class="btn" id="smartResetSelected" ${selectedStaleIds.length ? "" : "style='display:none'"}><i data-lucide="rotate-ccw"></i>Smart Reset Selected</button>
      <button class="btn primary" id="resumeSelectedStale" ${selectedStaleIds.length ? "" : "style='display:none'"}><i data-lucide="play"></i>Reset & Resume Selected</button>
      <button class="btn primary" id="resumeSelectedIncomplete" ${selectedIncompleteIds.length ? "" : "style='display:none'"}><i data-lucide="play"></i>Resume Incomplete Selected</button>
      <button class="btn" id="markReportedSelected" ${companiesState.selected.size ? "" : "style='display:none'"}><i data-lucide="check-check"></i>Mark reported</button>
      <button class="btn" id="unmarkReportedSelected" ${companiesState.selected.size ? "" : "style='display:none'"}><i data-lucide="undo-2"></i>Unmark reported</button>
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
      <select class="select" id="statusFilter">${statusFilterOptions(counts)}</select>
      <select class="select" id="completionFilter">
        <option value="" ${companiesState.completion === "" ? "selected" : ""}>All completion</option>
        <option value="incomplete" ${companiesState.completion === "incomplete" ? "selected" : ""}>Incomplete</option>
        <option value="strict_done" ${companiesState.completion === "strict_done" ? "selected" : ""}>Strict done</option>
      </select>
      <select class="select" id="checkpointFilter">${checkpointOptions()}</select>
      <select class="select" id="reportStateFilter">
        <option value="" ${companiesState.reportState === "" ? "selected" : ""}>All report states</option>
        <option value="unreported" ${companiesState.reportState === "unreported" ? "selected" : ""}>Unreported</option>
        <option value="reported" ${companiesState.reportState === "reported" ? "selected" : ""}>Reported</option>
      </select>
      <button class="btn ${companiesState.reportWindow === "today" ? "primary" : ""}" id="todayReportWindow"><i data-lucide="clock"></i>Today report window</button>
      <button class="btn" id="clearFilters"><i data-lucide="x"></i>Clear filters</button>
      <button class="btn" id="selectAllFiltered"><i data-lucide="list-checks"></i>Select all ${p.total || 0} filtered</button>
      <button class="btn primary" id="runAllFiltered"><i data-lucide="play"></i>Run all filtered</button>
      <button class="btn" id="selectInverseFiltered"><i data-lucide="list-x"></i>Select inverse</button>
    </div>
    ${importFilters}
    <div id="selectAllBanner" class="alert info" style="display: none; text-align: center; margin-bottom: 10px; background: var(--blue-light, #e0f2fe); color: var(--blue, #0284c7); padding: 8px; border-radius: 4px;">
      All <b id="bannerCurrentCount">0</b> companies on this page are selected.
      <a href="#" id="bannerSelectAllLink" style="font-weight: bold; cursor: pointer; text-decoration: underline;">Select all <span id="bannerTotalCount">0</span> companies matching this filter</a>
    </div>
    <div class="table-wrap fixed">
      <table>
        <thead><tr><th><input type="checkbox" id="selectPage" title="Select current page only" ${allSelected ? "checked" : ""}></th><th>ID</th><th>Name</th>${normalizedHeader}${importHeader}<th>${statusHeader}</th><th>Checkpoint</th><th>Data</th><th>Updated</th><th>Actions</th></tr></thead>
        <tbody>${companies.length ? companies.map(companyRow).join("") : rowMessage("No companies found.", tableColspan)}</tbody>
      </table>
    </div>
    <div class="pagination">
      <button class="btn" id="prevPage" ${p.page <= 1 ? "disabled" : ""}>Previous</button>
      <span class="muted">Page</span>
      <input class="input page-input" type="number" id="pageInput" min="1" max="${p.total_pages || 1}" value="${p.page || 1}">
      <span class="muted">/ ${p.total_pages || 1}</span>
      <button class="btn" id="goPage">Go</button>
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

function importChip(label, outcome, count) {
  const active = companiesState.importOutcome === outcome ? "primary" : "";
  return `<button class="btn ${active}" data-import-outcome="${outcome}">${label} (${count || 0})</button>`;
}

function companyRow(c) {
  const isBatchView = Boolean(companiesState.importBatchId && c.is_import_item);
  const showNormalized = Boolean(companiesState.showNormalizedNames);
  const selected = c.id ? companiesState.selected.has(c.id) : false;
  const checkbox = c.id
    ? `<input type="checkbox" class="row-check" data-id="${c.id}" ${selected ? "checked" : ""}>`
    : "";
  const idCell = c.id ? `#${c.id}` : "—";
  const nameCell = c.id
    ? `<a href="#/company/${c.id}">${escapeHtml(c.name || "")}</a>`
    : `<span>${escapeHtml(c.name || "")}</span>`;
  const normalizedCell = showNormalized ? `<td class="mono muted normalized-cell">${escapeHtml(c.normalized_key || "")}</td>` : "";
  const importStatusCell = isBatchView ? `<td><span class="badge import-${escapeHtml(c.outcome || "")}">${escapeHtml(c.display_status || c.outcome || "")}</span></td>` : "";
  const pipelineStatus = c.pipeline_status || c.status || "";
  const staleBadge = c.is_stale ? `<span class="badge stale" title="${escapeHtml(c.stale_reason || "")}">Stale</span>` : "";
  const completionBadge = c.completion_status === "incomplete"
    ? `<span class="badge failed" title="${escapeHtml(c.completion_reason || "")}">Incomplete</span>`
    : (c.completion_status === "strict_done" ? `<span class="badge success">Strict Done</span>` : "");
  const reportedBadge = c.is_reported
    ? `<span class="badge success" title="Reported at ${escapeHtml(formatDashboardTimestamp(c.reported_at || ""))}">Reported</span>`
    : "";
  const checkpoint = c.is_stale && c.suggested_status
    ? `${c.checkpoint || "pipeline_init"} → ${c.suggested_status}`
    : c.checkpoint || "pipeline_init";
  const lastActivity = c.last_activity_step ? `<div class="muted small-text">Last: ${escapeHtml(c.last_activity_step)}</div>` : "";
  const staleActions = c.can_reset_resume
    ? `<button class="btn ghost smart-reset-company" data-id="${c.id}" title="Smart Reset"><i data-lucide="rotate-ccw"></i></button><button class="btn ghost primary resume-stale-company" data-id="${c.id}" title="Reset & Resume"><i data-lucide="play"></i></button>`
    : "";
  const incompleteActions = c.can_resume_incomplete
    ? `<button class="btn ghost primary resume-incomplete-company" data-id="${c.id}" title="Resume Incomplete"><i data-lucide="play"></i></button>`
    : "";
  const actions = c.id
    ? `${staleActions}${incompleteActions}<button class="btn ghost run-one" data-id="${c.id}" title="Run"><i data-lucide="play"></i></button><button class="btn ghost" onclick="location.hash='#/company/${c.id}'" title="Open"><i data-lucide="eye"></i></button><button class="btn ghost danger-text delete-one" data-id="${c.id}" title="Delete"><i data-lucide="trash-2"></i></button>`
    : `<span class="muted">No company</span>`;
  return `
    <tr class="company-row ${selected ? "selected" : ""}" ${c.id ? `data-id="${c.id}"` : ""}>
      <td>${checkbox}</td>
      <td class="muted">${idCell}</td>
      <td>${nameCell}${isBatchView && c.input_name && c.input_name !== c.canonical_name ? `<div class="muted small-text">Input: ${escapeHtml(c.input_name)}</div>` : ""}</td>
      ${normalizedCell}
      ${importStatusCell}
      <td><span class="badge ${statusClass(pipelineStatus)}">${escapeHtml(pipelineStatus)}</span> ${staleBadge} ${completionBadge} ${reportedBadge}</td>
      <td class="mono">${escapeHtml(checkpoint)}${lastActivity}</td>
      <td>${c.has_phone ? '<span class="success">phone</span>' : '<span class="muted">phone</span>'} · ${c.has_email ? '<span class="success">email</span>' : '<span class="muted">email</span>'}</td>
      <td class="muted">${formatDashboardTimestamp(c.updated_at || c.import_item_created_at || "")}</td>
      <td>${actions}</td>
    </tr>
  `;
}

function bindCompanyEvents(companies, pagination) {
  const selectedStaleIds = () => companies
    .filter(c => c.id && c.can_reset_resume && companiesState.selected.has(c.id))
    .map(c => c.id);
  const selectedIncompleteIds = () => companies
    .filter(c => c.id && c.can_resume_incomplete && companiesState.selected.has(c.id))
    .map(c => c.id);

  const syncPageCheckbox = () => {
    const selectPage = document.getElementById("selectPage");
    if (selectPage) {
      const checks = [...document.querySelectorAll(".row-check")];
      selectPage.checked = checks.length > 0 && checks.every((check) => check.checked);
    }
  };
  const setRowSelected = (check, isSelected) => {
    check.checked = isSelected;
    const id = Number(check.dataset.id);
    isSelected ? companiesState.selected.add(id) : companiesState.selected.delete(id);
    check.closest("tr").classList.toggle("selected", isSelected);
    syncPageCheckbox();
    updateSelectedUI();
  };
  const isRowActionTarget = (target) => Boolean(target.closest("a, button, input, label, select, textarea"));

  const fetchFilteredCompanyIds = async (extraParams = {}) => {
    const params = companyQueryParams({ includePaging: false });
    Object.entries(extraParams).forEach(([key, value]) => params.set(key, value));
    const result = await api(`/api/spa/companies/ids?${params}`);
    return result.company_ids || [];
  };

  document.querySelectorAll("[data-status]").forEach((btn) => btn.addEventListener("click", () => {
    companiesState.selected.clear();
    renderCompanies({ status: btn.dataset.status, page: 1 });
  }));
  document.querySelectorAll("[data-import-outcome]").forEach((btn) => btn.addEventListener("click", () => {
    companiesState.selected.clear();
    renderCompanies({ importOutcome: btn.dataset.importOutcome, page: 1 });
  }));
  const normalizedToggle = document.getElementById("showNormalizedNames");
  if (normalizedToggle) {
    normalizedToggle.addEventListener("change", (event) => {
      renderCompanies({ showNormalizedNames: event.target.checked, page: companiesState.page });
    });
  }
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
      return renderCompanies({ importBatchId: latest ? String(latest.id) : "", importOutcome: "", page: 1 });
    }
    renderCompanies({ importBatchId: value, importOutcome: "", page: 1 });
  });
  document.getElementById("statusFilter").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ status: event.target.value, page: 1 });
  });
  document.getElementById("completionFilter").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ completion: event.target.value, page: 1 });
  });
  document.getElementById("checkpointFilter").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ checkpoint: event.target.value, page: 1 });
  });
  document.getElementById("reportStateFilter").addEventListener("change", (event) => {
    companiesState.selected.clear();
    renderCompanies({ reportState: event.target.value, page: 1 });
  });
  document.getElementById("todayReportWindow").addEventListener("click", () => {
    companiesState.selected.clear();
    const nextWindow = companiesState.reportWindow === "today" ? "" : "today";
    renderCompanies({ reportWindow: nextWindow, page: 1 });
  });
  document.getElementById("clearFilters").addEventListener("click", () => {
    companiesState.selected.clear();
    renderCompanies({ status: "", search: "", importBatchId: "", importOutcome: "", completion: "", checkpoint: "", reportState: "", reportWindow: "", dateMode: "created", dateFrom: "", dateTo: "", page: 1 });
  });
  const updateSelectedUI = () => {
    const runBtn = document.getElementById("runSelected");
    const delBtn = document.getElementById("deleteSelected");
    const markReportedBtn = document.getElementById("markReportedSelected");
    const unmarkReportedBtn = document.getElementById("unmarkReportedSelected");
    const smartResetBtn = document.getElementById("smartResetSelected");
    const resumeStaleBtn = document.getElementById("resumeSelectedStale");
    const resumeIncompleteBtn = document.getElementById("resumeSelectedIncomplete");
    const show = companiesState.selected.size ? "" : "none";
    if (runBtn) runBtn.style.display = show;
    if (delBtn) delBtn.style.display = show;
    if (markReportedBtn) markReportedBtn.style.display = show;
    if (unmarkReportedBtn) unmarkReportedBtn.style.display = show;
    const staleShow = selectedStaleIds().length ? "" : "none";
    const incompleteShow = selectedIncompleteIds().length ? "" : "none";
    if (smartResetBtn) smartResetBtn.style.display = staleShow;
    if (resumeStaleBtn) resumeStaleBtn.style.display = staleShow;
    if (resumeIncompleteBtn) resumeIncompleteBtn.style.display = incompleteShow;

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
          const ids = await fetchFilteredCompanyIds();
          companiesState.selected = new Set(ids);
          renderCompanies();
      });
  }

  document.getElementById("selectPage").addEventListener("change", (event) => {
    const isChecked = event.target.checked;
    document.querySelectorAll(".row-check").forEach((check) => {
      check.checked = isChecked;
      const id = Number(check.dataset.id);
      isChecked ? companiesState.selected.add(id) : companiesState.selected.delete(id);
      check.closest("tr").classList.toggle("selected", isChecked);
    });
    updateSelectedUI();
  });
  document.querySelectorAll(".row-check").forEach((check) => check.addEventListener("change", () => {
    setRowSelected(check, check.checked);
  }));
  document.querySelectorAll(".company-row[data-id]").forEach((row) => row.addEventListener("click", (event) => {
    if (isRowActionTarget(event.target)) return;
    const check = row.querySelector(".row-check");
    if (check) setRowSelected(check, !check.checked);
  }));
  document.getElementById("selectAllFiltered").addEventListener("click", async () => {
    const ids = await fetchFilteredCompanyIds();
    companiesState.selected = new Set(ids);
    renderCompanies();
  });
  document.getElementById("runAllFiltered").addEventListener("click", async () => {
    const ids = await fetchFilteredCompanyIds();
    await runCompanies(ids);
  });
  document.getElementById("selectInverseFiltered").addEventListener("click", async () => {
    const ids = await fetchFilteredCompanyIds({ complement: "true" });
    companiesState.selected = new Set(ids);
    renderCompanies();
  });
  document.querySelectorAll(".run-one").forEach((button) => button.addEventListener("click", () => runCompanies([Number(button.dataset.id)])));
  document.querySelectorAll(".smart-reset-company").forEach((button) => button.addEventListener("click", async () => {
    await resetCompanyStatus([Number(button.dataset.id)], "smart_resume");
    await renderCompanies({ page: companiesState.page });
  }));
  document.querySelectorAll(".resume-stale-company").forEach((button) => button.addEventListener("click", () => runCompanies([Number(button.dataset.id)], { resumeStale: true })));
  document.querySelectorAll(".resume-incomplete-company").forEach((button) => button.addEventListener("click", () => runCompanies([Number(button.dataset.id)], { resumeIncomplete: true })));
  document.querySelectorAll(".delete-one").forEach((button) => button.addEventListener("click", () => deleteCompanies([Number(button.dataset.id)])));
  document.getElementById("markReportedSelected").addEventListener("click", () => setReportedStatus([...companiesState.selected], "mark"));
  document.getElementById("unmarkReportedSelected").addEventListener("click", () => setReportedStatus([...companiesState.selected], "unmark"));
  document.getElementById("runSelected").addEventListener("click", () => runCompanies([...companiesState.selected]));
  document.getElementById("smartResetSelected").addEventListener("click", async () => {
    const ids = selectedStaleIds();
    if (!ids.length) return alert("No stale selected companies on this page.");
    await resetCompanyStatus(ids, "smart_resume");
    companiesState.selected.clear();
    await renderCompanies({ page: companiesState.page });
  });
  document.getElementById("resumeSelectedStale").addEventListener("click", async () => {
    const ids = selectedStaleIds();
    if (!ids.length) return alert("No stale selected companies on this page.");
    await runCompanies(ids, { resumeStale: true });
  });
  document.getElementById("resumeSelectedIncomplete").addEventListener("click", async () => {
    const ids = selectedIncompleteIds();
    if (!ids.length) return alert("No incomplete selected companies on this page.");
    await runCompanies(ids, { resumeIncomplete: true });
  });
  document.getElementById("deleteSelected").addEventListener("click", () => deleteCompanies([...companiesState.selected]));
  const goToPage = () => {
    const totalPages = pagination.total_pages || 1;
    const value = Number(document.getElementById("pageInput").value);
    const page = Number.isFinite(value) ? Math.min(totalPages, Math.max(1, Math.trunc(value))) : companiesState.page;
    renderCompanies({ page });
  };
  document.getElementById("prevPage").addEventListener("click", () => renderCompanies({ page: Math.max(1, companiesState.page - 1) }));
  document.getElementById("nextPage").addEventListener("click", () => renderCompanies({ page: Math.min(pagination.total_pages || 1, companiesState.page + 1) }));
  document.getElementById("goPage").addEventListener("click", goToPage);
  document.getElementById("pageInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") goToPage();
  });
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

async function runCompanies(ids, options = {}) {
  if (!ids.length) return;
  const result = await api("/api/spa/runner/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_ids: ids, resume_stale: Boolean(options.resumeStale), resume_incomplete: Boolean(options.resumeIncomplete) }),
  });
  companiesState.selected.clear();
  const worker = result.worker || {};
  const workerText = worker.online
    ? "Worker online"
    : (worker.auto_started ? "Worker auto-start requested" : (worker.message || "Worker offline"));
  alert(`Requested: ${ids.length}. Queued: ${(result.started || []).length}. Skipped: ${(result.skipped || []).length}. ${workerText}.`);
  location.hash = "#/monitor";
}

async function setReportedStatus(ids, action) {
  if (!ids.length) return;
  const label = action === "mark" ? "mark selected companies as reported" : "unmark selected companies as reported";
  if (!confirm(`Confirm ${label}?`)) return;
  try {
    const result = await api("/api/spa/companies/report-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_ids: ids, action, report_window: "today" }),
    });
    companiesState.selected.clear();
    const count = action === "mark" ? (result.marked || 0) : (result.unmarked || 0);
    alert(`${action === "mark" ? "Marked" : "Unmarked"} ${count} companies.`);
    renderCompanies({ page: companiesState.page });
  } catch (err) {
    alert("Error updating reported status: " + err.message);
  }
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
  const names = parseCompanyImportText(text, file.name);
  if (!names.length) return alert("No company names found.");
  const result = await api("/api/companies/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ companies: names, source_filename: file.name }),
  });
  const summary = result.summary || {};
  alert(`Imported ${result.imported}; MST match ${summary.matched_by_tax_code || 0}; review ${summary.ambiguous || 0}; duplicate in file ${summary.duplicate_in_file || 0}; invalid ${summary.invalid || 0}.`);
  companiesState.selected.clear();
  renderCompanies({ importBatchId: String(result.batch_id || ""), importOutcome: "", page: 1 });
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

  // Scraped URLs table (deduped by latest row per URL)
  let scrapedHtml = '<p class="muted">No scraped pages.</p>';
  if (scrapedPages.length) {
      scrapedHtml = `
      <div class="table-wrap" style="max-height: 300px; overflow-y: auto;">
          <table>
              <thead><tr><th>URL</th><th>Status</th><th>Attempts</th><th>Length</th></tr></thead>
              <tbody>
                  ${scrapedPages.map(p => {
                      const normalizedStatus = String(p.scrape_status || '').toLowerCase();
                      const label = normalizedStatus === 'success'
                        ? 'Success'
                        : normalizedStatus === 'timeout'
                          ? 'Timeout (Complete)'
                          : normalizedStatus === 'unsupported'
                            ? 'Unsupported (Complete)'
                            : normalizedStatus === 'skipped'
                              ? 'Skipped (Complete)'
                              : normalizedStatus === 'failed'
                                ? 'Failed'
                                : (p.scrape_status || 'Unknown');
                      const badgeClass = normalizedStatus === 'success'
                        ? 'success'
                        : (normalizedStatus === 'timeout' || normalizedStatus === 'skipped' || normalizedStatus === 'unsupported' ? 'warning' : 'failed');
                      return `<tr>
                      <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${p.url}"><a href="${p.url}" target="_blank">${p.url}</a></td>
                      <td><span class="badge ${badgeClass}">${label}</span></td>
                      <td>${p.attempt_count || 1}</td>
                      <td>${p.content_length || 0}</td>
                  </tr>`;
                  }).join("")}
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

    <div class="card" style="margin-top:16px"><h3>Timeline</h3><div class="terminal">${logs.length ? logs.map((l) => `<div class="terminal-line">${formatDashboardTimestamp(l.started_at || l.finished_at || "")} ${l.step} ${l.status} ${l.error_message || ""}</div>`).join("") : '<div class="terminal-line">No logs yet.</div>'}</div></div>
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
      <button class="btn" id="smartResetStale"><i data-lucide="rotate-ccw"></i>Smart Reset Stale</button>
      <button class="btn primary" id="resumeStale"><i data-lucide="play"></i>Reset & Resume Stale</button>
      <button class="btn danger" id="hardResetStale"><i data-lucide="rotate-cw"></i>Hard Reset to Pending</button>
      <button class="btn" id="toggleStaleOnly"><i data-lucide="filter"></i>Show stale only</button>
      <button class="btn" id="refreshMonitor"><i data-lucide="refresh-cw"></i>Refresh Snapshot</button>
    </div>
    <div class="grid stats" id="monitorSummary"></div>
    <div class="card" style="margin-top:16px">
      <div class="settings-section-heading"><div><h3>Worker Runtime</h3><p class="muted">Inspect live worker processes, DB heartbeat, and Firecrawl key mismatch.</p></div><div class="runtime-actions"><button class="btn" id="testFirecrawl"><i data-lucide="activity"></i>Test Firecrawl</button><button class="btn primary" id="restartWorker"><i data-lucide="refresh-cw"></i>Restart Worker</button></div></div>
      <div id="monitorRuntimeHealth" class="muted">Loading runtime health...</div>
    </div>
    <div class="table-wrap fixed" style="margin-top:16px">
      <table><thead><tr><th>Company</th><th>Status</th><th>Step</th><th>Checkpoint</th><th>Progress</th><th>Updated</th><th>Actions</th></tr></thead><tbody id="monitorRows">${rowMessage("Connecting to monitor...")}</tbody></table>
    </div>
    <div class="card" style="margin-top:16px"><h3>Latest Events</h3><div class="terminal" id="monitorEvents"></div></div>
  `;
  document.getElementById("stopAll").addEventListener("click", stopAll);
  document.getElementById("smartResetStale").addEventListener("click", () => resetStaleJobs(false));
  document.getElementById("resumeStale").addEventListener("click", () => resetStaleJobs(true));
  document.getElementById("hardResetStale").addEventListener("click", () => hardResetStaleJobs());
  document.getElementById("toggleStaleOnly").addEventListener("click", () => {
    monitor.showStaleOnly = !monitor.showStaleOnly;
    renderMonitorState();
  });
  document.getElementById("refreshMonitor").addEventListener("click", loadMonitorSnapshot);
  document.getElementById("testFirecrawl").addEventListener("click", async () => {
    await testFirecrawlHealth();
    await loadMonitorSnapshot();
  });
  document.getElementById("restartWorker").addEventListener("click", async () => {
    await restartWorker();
    await loadMonitorSnapshot();
  });
  iconize();
  await loadMonitorSnapshot();
  connectMonitorSocket();
}

async function loadMonitorSnapshot() {
  const [data, runtimeHealth] = await Promise.all([api("/api/spa/monitor"), loadRuntimeHealth()]);
  applyMonitorSnapshot({ ...data, runtimeHealth });
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
  monitor.worker = data.worker || monitor.worker;
  monitor.runtimeHealth = data.runtimeHealth || monitor.runtimeHealth;
  renderMonitorState();
}

function renderMonitorState() {
  const allJobs = [...monitor.jobs.values()].sort((a, b) => {
    if (Boolean(a.stale) !== Boolean(b.stale)) return a.stale ? -1 : 1;
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
  const jobs = monitor.showStaleOnly ? allJobs.filter((job) => job.stale) : allJobs;
  const workerOnline = Boolean(monitor.worker && monitor.worker.online);
  const workerLabel = workerOnline ? `Online (${(monitor.worker.workers || []).length})` : "Offline";
  document.getElementById("monitorSummary").innerHTML = `
    ${stat("Worker", workerLabel, workerOnline ? "success" : "danger-text")}
    ${stat("Running", monitor.counts.running || 0, "warning")}
    ${stat("Queued", monitor.counts.queued || 0)}
    ${stat("Failed", monitor.counts.failed || 0, "danger-text")}
    ${stat("Stopped", monitor.counts.stopped || 0)}
    ${stat("Stale", monitor.counts.stale || allJobs.filter((job) => job.stale).length, "warning")}
  `;
  const toggle = document.getElementById("toggleStaleOnly");
  if (toggle) toggle.classList.toggle("primary", monitor.showStaleOnly);
  document.getElementById("monitorRows").innerHTML = jobs.length ? jobs.map(jobRow).join("") : rowMessage("No companies are currently in the monitor list.");
  document.getElementById("monitorEvents").innerHTML = monitor.events.length ? monitor.events.map((event) => `<div class="terminal-line">${escapeHtml(event)}</div>`).join("") : '<div class="terminal-line">Waiting for workflow events...</div>';
  const runtimeEl = document.getElementById("monitorRuntimeHealth");
  if (runtimeEl) runtimeEl.innerHTML = renderRuntimeHealth(monitor.runtimeHealth, { compact: true });
  document.querySelectorAll(".remove-job").forEach((button) => button.addEventListener("click", () => removeJob(Number(button.dataset.id))));
  document.querySelectorAll(".smart-reset-job").forEach((button) => button.addEventListener("click", () => resetCompanyStatus([Number(button.dataset.id)], "smart_resume")));
  document.querySelectorAll(".resume-stale-job").forEach((button) => button.addEventListener("click", () => runCompanies([Number(button.dataset.id)], { resumeStale: true })));
  document.querySelectorAll(".hard-reset-job").forEach((button) => button.addEventListener("click", () => resetCompanyStatus([Number(button.dataset.id)], "to_pending")));
  iconize();
}

function jobRow(job) {
  const staleBadge = job.stale ? `<span class="badge stale">Stale</span>` : "";
  const checkpoint = job.stale && job.suggested_status
    ? `${job.checkpoint || ""} → ${job.suggested_status}`
    : job.checkpoint || "";
  const resetActions = job.stale
    ? `<button class="btn ghost smart-reset-job" data-id="${job.id}" title="Smart Reset"><i data-lucide="rotate-ccw"></i></button><button class="btn ghost primary resume-stale-job" data-id="${job.id}" title="Reset & Resume"><i data-lucide="play"></i></button><button class="btn ghost danger-text hard-reset-job" data-id="${job.id}" title="Hard Reset to Pending"><i data-lucide="rotate-cw"></i></button>`
    : "";
  return `
    <tr>
      <td><strong>${escapeHtml(job.name || "")}</strong><div class="muted">#${job.id}</div></td>
      <td><span class="badge ${statusClass(job.status)}">${job.status}</span> ${staleBadge}</td>
      <td>${escapeHtml(job.step || "")}</td>
      <td class="mono">${escapeHtml(checkpoint)}</td>
      <td><div class="progress"><div style="width:${job.progress || 0}%"></div></div><div class="muted">${job.progress || 0}%</div></td>
      <td class="muted">${formatDashboardTimestamp(job.updated_at || job.started || "")}</td>
      <td>${resetActions}<button class="btn ghost" onclick="location.hash='#/company/${job.id}'"><i data-lucide="eye"></i></button><button class="btn ghost remove-job" data-id="${job.id}"><i data-lucide="trash-2"></i></button></td>
    </tr>
  `;
}

function renderRuntimeHealth(runtime, { compact = false } = {}) {
  if (!runtime) return '<div class="muted">Runtime health unavailable.</div>';
  const processRows = (runtime.runtime_processes || []).map((proc) => `
    <div class="runtime-process-card">
      <div class="runtime-health-row"><strong>PID ${proc.pid}</strong><span class="mono">${escapeHtml(proc.firecrawl_key_mask || 'n/a')}</span></div>
      <div class="muted small-text">${escapeHtml(proc.db_path || '')}</div>
      <div class="muted small-text">${escapeHtml(proc.cmdline || '')}</div>
      ${proc.env_mismatch ? '<div class="danger-text small-text">Worker key differs from current .env</div>' : ''}
      ${proc.orphaned ? '<div class="warning small-text">Runtime process not linked to current DB worker heartbeat.</div>' : ''}
    </div>`).join('');
  const dbRows = (runtime.db_workers || []).map((worker) => `
    <div class="runtime-process-card">
      <div class="runtime-health-row"><strong>${escapeHtml(worker.worker_id || 'worker')}</strong><span>${worker.runtime_present ? 'runtime' : 'heartbeat only'}</span></div>
      <div class="muted small-text">PID ${worker.pid || 'n/a'} · ${escapeHtml(worker.status || '')}</div>
      <div class="muted small-text">Last heartbeat: ${formatDashboardTimestamp(worker.heartbeat_at || worker.last_seen_at || '')}</div>
      ${worker.firecrawl_key_mask ? `<div class="mono small-text">${escapeHtml(worker.firecrawl_key_mask)}</div>` : ''}
      ${worker.env_mismatch ? '<div class="danger-text small-text">Worker key differs from current .env</div>' : ''}
    </div>`).join('');
  const summaryClass = runtime.has_env_mismatch ? 'danger-text' : 'success';
  return `
    <div class="runtime-health-grid ${compact ? 'compact' : ''}">
      <div class="runtime-health-panel">
        <div class="runtime-health-row"><strong>Current key</strong><span class="mono">${escapeHtml(runtime.current_firecrawl_key_mask || 'n/a')}</span></div>
        <div class="runtime-health-row"><strong>Worker state</strong><span class="${summaryClass}">${runtime.worker_online ? 'online' : 'offline'}</span></div>
        ${runtime.message ? `<div class="muted small-text">${escapeHtml(runtime.message)}</div>` : ''}
        ${runtime.has_env_mismatch ? '<div class="danger-text small-text">At least one worker is using a different Firecrawl key.</div>' : ''}
      </div>
      <div>
        <h3>Runtime Processes</h3>
        <div class="runtime-list">${processRows || '<div class="muted">No runtime worker process found.</div>'}</div>
      </div>
      <div>
        <h3>DB Workers</h3>
        <div class="runtime-list">${dbRows || '<div class="muted">No recent DB worker heartbeat.</div>'}</div>
      </div>
    </div>`;
}

async function loadRuntimeHealth() {
  return api('/api/spa/runtime-health');
}

async function testFirecrawlHealth() {
  const result = await api('/api/spa/runtime-health/firecrawl-test', { method: 'POST' });
  alert(`Firecrawl test: ${result.ok ? 'OK' : 'FAILED'}${result.status_code ? ` · HTTP ${result.status_code}` : ''}${result.credits_used != null ? ` · credits ${result.credits_used}` : ''}`);
  return result;
}

async function restartWorker() {
  const result = await api('/api/spa/runner/restart-worker', { method: 'POST' });
  pushMonitorEvent(`worker_restart: stopped ${result.stopped_pids.length} · started ${result.started_pid || 'none'}`);
  return result;
}

function pushMonitorEvent(text) {
  monitor.events.unshift(`${formatVnTime()} ${text}`);
  monitor.events = monitor.events.slice(0, 200);
}

async function stopAll() {
  await api("/api/spa/runner/stop-all", { method: "POST" });
}

async function resetCompanyStatus(ids, mode = "smart_resume") {
  if (!ids.length) return;
  const result = await api("/api/spa/runner/reset-status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_ids: ids, mode }),
  });
  pushMonitorEvent(`status_reset: ${result.reset || 0} companies`);
  if ((location.hash || "#/dashboard") === "#/monitor") {
    await loadMonitorSnapshot();
  }
  return result;
}

async function resetStaleJobs(resume = false) {
  const staleIds = [...monitor.jobs.values()].filter((job) => job.stale).map((job) => job.id);
  if (!staleIds.length) {
    alert("No stale jobs found.");
    return;
  }
  if (resume) {
    await runCompanies(staleIds, { resumeStale: true });
  } else {
    await resetCompanyStatus(staleIds, "smart_resume");
  }
}

async function hardResetStaleJobs() {
  const staleIds = [...monitor.jobs.values()].filter((job) => job.stale).map((job) => job.id);
  if (!staleIds.length) {
    alert("No stale jobs found.");
    return;
  }
  if (!confirm(`Hard reset ${staleIds.length} stale jobs to pending? This can rerun search/scrape steps.`)) return;
  await resetCompanyStatus(staleIds, "to_pending");
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


function formField(id, label, value, { type = "text", placeholder = "", min = "", step = "any" } = {}) {
  return `
    <div class="form-group">
      <label for="${id}">${escapeHtml(label)}</label>
      <input type="${type}" id="${id}" class="input setting-input" value="${escapeHtml(toFormValue(value))}" placeholder="${escapeHtml(placeholder)}" ${min !== "" ? `min="${min}"` : ""} ${type === "number" ? `step="${step}"` : ""}>
    </div>`;
}

function checkboxField(id, label, checked) {
  return `
    <label class="setting-check">
      <input type="checkbox" id="${id}" ${checked ? "checked" : ""}>
      <span>${escapeHtml(label)}</span>
    </label>`;
}

function scoreRows(id, values, keyLabel) {
  return Object.entries(values || {}).map(([key, score]) => `
    <div class="settings-row score-row" data-row>
      <input class="input setting-input" data-field="key" value="${escapeHtml(key)}" placeholder="${escapeHtml(keyLabel)}">
      <input class="input setting-input compact-number" data-field="score" type="number" step="any" value="${escapeHtml(score)}" placeholder="Score">
      <button type="button" class="btn ghost danger-text" data-remove-row title="Remove"><i data-lucide="trash-2"></i></button>
    </div>`).join("") || `<div class="muted empty-state">No rows yet.</div>`;
}

function knownSourceRows(values) {
  return Object.entries(values || {}).map(([domain, source]) => `
    <div class="settings-row known-source-row" data-row>
      <input class="input setting-input" data-field="domain" value="${escapeHtml(domain)}" placeholder="example.com">
      <input class="input setting-input" data-field="sourceType" value="${escapeHtml((source || [])[0] || "")}" placeholder="source type">
      <input class="input setting-input" data-field="scoreCategory" value="${escapeHtml((source || [])[1] || "")}" placeholder="score category">
      <button type="button" class="btn ghost danger-text" data-remove-row title="Remove"><i data-lucide="trash-2"></i></button>
    </div>`).join("") || `<div class="muted empty-state">No known sources yet.</div>`;
}

function domainListRows(id, values) {
  return (values || []).map((domain) => `
    <div class="domain-pill-row" data-row data-value="${escapeHtml(domain)}">
      <span class="mono">${escapeHtml(domain)}</span>
      <button type="button" class="btn ghost danger-text" data-remove-row>Remove</button>
    </div>`).join("") || `<div class="muted empty-state">No domains yet.</div>`;
}

function scoringDomainsTabs(activeTab) {
  return SCORING_DOMAIN_TABS.map((tab) => `
    <button type="button" class="settings-tab ${activeTab === tab.id ? "active" : ""}" data-scoring-tab="${tab.id}">${tab.label}</button>`).join("");
}

function scoringDomainsPane(pipelineConfig) {
  const activeTab = scoringDomainsState.activeTab;
  return `
    <div class="card settings-scoring-card">
      <div class="settings-section-heading">
        <div>
          <h2>Scoring & Domains</h2>
          <p class="muted">Structured editors for URL scoring, known source hints, and domain exclusion lists.</p>
        </div>
        <button type="button" class="btn primary" id="saveScoringDomains">Save Scoring & Domains</button>
      </div>
      <div class="settings-tabs" role="tablist">${scoringDomainsTabs(activeTab)}</div>
      <div class="settings-tab-panel ${activeTab === "scores" ? "active" : ""}" data-tab-panel="scores">
        <div class="settings-split">
          <div>
            <div class="settings-table-heading"><h3>Domain Scores</h3><button type="button" class="btn" data-add-score="domainScoreRows">Add score</button></div>
            <div id="domainScoreRows" class="settings-row-list">${scoreRows("domainScoreRows", pipelineConfig.DOMAIN_SCORES, "category")}</div>
          </div>
          <div>
            <div class="settings-table-heading"><h3>Keyword Scores</h3><button type="button" class="btn" data-add-score="keywordScoreRows">Add keyword</button></div>
            <div id="keywordScoreRows" class="settings-row-list">${scoreRows("keywordScoreRows", pipelineConfig.KEYWORD_SCORES, "keyword")}</div>
          </div>
        </div>
      </div>
      <div class="settings-tab-panel ${activeTab === "known" ? "active" : ""}" data-tab-panel="known">
        <div class="settings-table-heading"><h3>Known Sources</h3><button type="button" class="btn" id="addKnownSource">Add source</button></div>
        <div class="settings-row header-row"><span>Domain</span><span>Source type</span><span>Score category</span><span></span></div>
        <div id="knownSourceRows" class="settings-row-list">${knownSourceRows(pipelineConfig.KNOWN_DOMAINS)}</div>
      </div>
      <div class="settings-tab-panel ${activeTab === "skip" ? "active" : ""}" data-tab-panel="skip">
        <div class="list-editor-add"><input class="input setting-input" id="skipDomainInput" placeholder="domain.com"><button type="button" class="btn" data-add-domain="skipDomainRows" data-input="skipDomainInput">Add domain</button></div>
        <div id="skipDomainRows" class="domain-list">${domainListRows("skipDomainRows", pipelineConfig.SKIP_DOMAINS)}</div>
      </div>
      <div class="settings-tab-panel ${activeTab === "blacklist" ? "active" : ""}" data-tab-panel="blacklist">
        <div class="list-editor-add"><input class="input setting-input" id="blacklistDomainInput" placeholder="domain.com"><button type="button" class="btn" data-add-domain="blacklistDomainRows" data-input="blacklistDomainInput">Add domain</button></div>
        <div id="blacklistDomainRows" class="domain-list">${domainListRows("blacklistDomainRows", pipelineConfig.BLACKLISTED_DOMAINS)}</div>
      </div>
    </div>`;
}

async function renderSettings() {
  setRouteActive("settings");
  app.innerHTML = `<div class="page-title"><div><h1>Settings</h1><div class="subtitle">Configuration editing</div></div></div><div class="card"><p>Loading settings...</p></div>`;

  try {
    const [settingsRes, pipelineRes, modelsRes, runtimeHealth] = await Promise.all([
      fetch("/api/spa/settings", { cache: "no-store" }),
      fetch("/api/spa/pipeline-config", { cache: "no-store" }),
      fetch("/api/spa/gemini-models", { cache: "no-store" }),
      loadRuntimeHealth(),
    ]);

    const settings = await settingsRes.json();
    const pipelineConfig = await pipelineRes.json();

    let modelsHTML = "";
    if (modelsRes.ok) {
      const modelsData = await modelsRes.json();
      modelsHTML = (modelsData.models || []).map((m) => `<option value="${escapeHtml(m.name)}">${escapeHtml(m.displayName || m.name)}</option>`).join("");
    } else {
      modelsHTML = `<option value="models/gemini-2.5-flash-lite">gemini-2.5-flash-lite (Failed to load dynamic list)</option>`;
    }

    const buildSelect = (id, label, value) => {
      const options = modelsHTML.replace(`value="${escapeHtml(value)}"`, `value="${escapeHtml(value)}" selected`);
      return `
        <div class="form-group">
          <label for="${id}">${escapeHtml(label)}</label>
          <select id="${id}" class="select setting-input">${options}</select>
        </div>`;
    };

    app.innerHTML = `
      <div class="page-title"><div><h1>Settings</h1><div class="subtitle">API keys and pipeline configuration</div></div></div>
      <div class="settings-layout">
        <div class="card settings-card settings-narrow-card">
          <h2>API & Models</h2>
          <form id="settings-form">
            ${formField("gemini_key", "Gemini API Key", settings.GEMINI_API_KEY, { placeholder: "Leave unchanged to keep current key" })}
            ${formField("firecrawl_key", "Firecrawl API Key", settings.FIRECRAWL_API_KEY, { placeholder: "Leave unchanged to keep current key" })}
            ${formField("serper_key", "Serper API Key", settings.SERPER_API_KEY, { placeholder: "Leave unchanged to keep current key" })}
            ${buildSelect("grounding_model", "AI Grounding Model", settings.AI_GROUNDING_MODEL)}
            ${buildSelect("extractor_model", "AI Extractor Model", settings.AI_EXTRACTOR_MODEL)}
            <button type="submit" class="btn primary">Save API Keys</button>
          </form>
        </div>

        <div class="settings-wide-column">
          <div class="card settings-card">
            <div class="settings-section-heading"><div><h2>Firecrawl Health</h2><p class="muted">Verify current key health and restart stale workers after changing credentials.</p></div><div class="runtime-actions"><button type="button" class="btn" id="testFirecrawlSettings"><i data-lucide="activity"></i>Test Firecrawl</button><button type="button" class="btn primary" id="restartWorkerSettings"><i data-lucide="refresh-cw"></i>Restart Worker</button></div></div>
            <div id="settingsRuntimeHealth">${renderRuntimeHealth(runtimeHealth)}</div>
          </div>
          <div class="card settings-card">
            <div class="settings-section-heading"><div><h2>Pipeline Behavior</h2><p class="muted">Search, scrape, batch, and feature controls.</p></div></div>
            <form id="pipeline-form">
              <div class="settings-grid">
                <section>
                  <h3>Scrape & Search</h3>
                  ${formField("TOP_N", "Top N Pages to Scrape", pipelineConfig.TOP_N, { type: "number" })}
                  ${formField("SEARCH_LIMIT", "Serper Search Limit", pipelineConfig.SEARCH_LIMIT, { type: "number" })}
                  ${formField("SERPER_NUM_RESULTS", "Results per Serper request", pipelineConfig.SERPER_NUM_RESULTS, { type: "number" })}
                  ${formField("INFER_MAX_SCRAPE", "Max Scrapes for Inference", pipelineConfig.INFER_MAX_SCRAPE, { type: "number" })}
                </section>
                <section>
                  <h3>Pipeline</h3>
                  ${formField("EARLY_STOP_COUNT", "Early Stop Count", pipelineConfig.EARLY_STOP_COUNT, { type: "number" })}
                  ${formField("EARLY_STOP_SCORE", "Early Stop Score", pipelineConfig.EARLY_STOP_SCORE, { type: "number" })}
                  ${formField("DELAY_SECONDS", "Delay Seconds", pipelineConfig.DELAY_SECONDS, { type: "number" })}
                  ${formField("MAX_RETRIES", "Max Retries", pipelineConfig.MAX_RETRIES, { type: "number" })}
                  ${formField("BATCH_SIZE", "Batch Size", pipelineConfig.BATCH_SIZE, { type: "number" })}
                  ${formField("MIN_CONFIDENCE_THRESHOLD", "Min Confidence", pipelineConfig.MIN_CONFIDENCE_THRESHOLD, { type: "number" })}
                  ${formField("MIN_SCRAPE_SCORE", "Min Scrape Score", pipelineConfig.MIN_SCRAPE_SCORE, { type: "number" })}
                  ${formField("REPORT_CUTOFF_TIME", "Report Cutoff Time", pipelineConfig.REPORT_CUTOFF_TIME ?? PIPELINE_CONFIG_DEFAULTS.REPORT_CUTOFF_TIME, { type: "time" })}
                </section>
                <section>
                  <h3>Firecrawl Batch</h3>
                  ${checkboxField("FIRECRAWL_BATCH_SCRAPE_ENABLED", "Enable batch scrape", pipelineConfig.FIRECRAWL_BATCH_SCRAPE_ENABLED ?? PIPELINE_CONFIG_DEFAULTS.FIRECRAWL_BATCH_SCRAPE_ENABLED)}
                  ${formField("FIRECRAWL_MAX_CONCURRENCY", "Max Concurrency", pipelineConfig.FIRECRAWL_MAX_CONCURRENCY ?? PIPELINE_CONFIG_DEFAULTS.FIRECRAWL_MAX_CONCURRENCY, { type: "number", min: "1", step: "1" })}
                  ${formField("FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS", "Poll Interval Seconds", pipelineConfig.FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS ?? PIPELINE_CONFIG_DEFAULTS.FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS, { type: "number" })}
                  ${formField("FIRECRAWL_BATCH_TIMEOUT_SECONDS", "Timeout Seconds", pipelineConfig.FIRECRAWL_BATCH_TIMEOUT_SECONDS ?? PIPELINE_CONFIG_DEFAULTS.FIRECRAWL_BATCH_TIMEOUT_SECONDS, { type: "number" })}
                </section>
                <section>
                  <h3>Feature Toggles</h3>
                  ${checkboxField("GEMINI_QUICK_ENABLED", "Enable Gemini Quick Search", pipelineConfig.GEMINI_QUICK_ENABLED)}
                  ${checkboxField("SERPER_ENABLED", "Enable Serper Search", pipelineConfig.SERPER_ENABLED)}
                  ${checkboxField("SCRAPE_LINKEDIN_ENABLED", "Enable LinkedIn Scrape", pipelineConfig.SCRAPE_LINKEDIN_ENABLED)}
                  ${checkboxField("BUSINESS_STATUS_GATE_ENABLED", "Enable Business Status Gate", pipelineConfig.BUSINESS_STATUS_GATE_ENABLED ?? PIPELINE_CONFIG_DEFAULTS.BUSINESS_STATUS_GATE_ENABLED)}
                  ${checkboxField("ENABLE_QUERY_DEDUP", "Enable Query Dedup", pipelineConfig.ENABLE_QUERY_DEDUP)}
                  ${checkboxField("ENABLE_URL_DEDUP", "Enable URL Dedup", pipelineConfig.ENABLE_URL_DEDUP)}
                  ${checkboxField("ENABLE_GLOBAL_CACHE", "Enable Global Cache", pipelineConfig.ENABLE_GLOBAL_CACHE)}
                  ${formField("CACHE_TTL_DAYS", "Cache TTL (Days)", pipelineConfig.CACHE_TTL_DAYS, { type: "number" })}
                </section>
              </div>
              <button type="submit" class="btn primary settings-save-wide">Save Pipeline Behavior</button>
            </form>
          </div>
          ${scoringDomainsPane(pipelineConfig)}
        </div>
      </div>
    `;
    bindSettingsEvents();
    iconize();
  } catch (err) {
    app.innerHTML = `<div class="card danger-text">Error loading settings: ${escapeHtml(err.message)}</div>`;
  }
}

function clearEmptyState(container) {
  container.querySelectorAll(".empty-state").forEach((item) => item.remove());
}

function appendScoreRow(containerId) {
  const container = document.getElementById(containerId);
  clearEmptyState(container);
  container.insertAdjacentHTML("beforeend", `
    <div class="settings-row score-row" data-row>
      <input class="input setting-input" data-field="key" placeholder="${containerId === "domainScoreRows" ? "category" : "keyword"}">
      <input class="input setting-input compact-number" data-field="score" type="number" step="any" placeholder="Score">
      <button type="button" class="btn ghost danger-text" data-remove-row title="Remove"><i data-lucide="trash-2"></i></button>
    </div>`);
  iconize();
}

function appendKnownSourceRow() {
  const container = document.getElementById("knownSourceRows");
  clearEmptyState(container);
  container.insertAdjacentHTML("beforeend", `
    <div class="settings-row known-source-row" data-row>
      <input class="input setting-input" data-field="domain" placeholder="example.com">
      <input class="input setting-input" data-field="sourceType" placeholder="source type">
      <input class="input setting-input" data-field="scoreCategory" placeholder="score category">
      <button type="button" class="btn ghost danger-text" data-remove-row title="Remove"><i data-lucide="trash-2"></i></button>
    </div>`);
  iconize();
}

function appendDomainListItem(containerId, inputId) {
  const input = document.getElementById(inputId);
  const domain = input.value.trim().toLowerCase();
  try {
    parseDomainList([domain], containerId === "skipDomainRows" ? "Skip Domains" : "Blacklist");
  } catch (err) {
    alert(err.message);
    return;
  }
  const container = document.getElementById(containerId);
  const exists = [...container.querySelectorAll("[data-row]")].some((row) => row.dataset.value === domain);
  if (exists) {
    alert(`${domain} is already in this list.`);
    return;
  }
  clearEmptyState(container);
  container.insertAdjacentHTML("beforeend", `
    <div class="domain-pill-row" data-row data-value="${escapeHtml(domain)}">
      <span class="mono">${escapeHtml(domain)}</span>
      <button type="button" class="btn ghost danger-text" data-remove-row>Remove</button>
    </div>`);
  input.value = "";
}

function bindSettingsEvents() {
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("pipeline-form").addEventListener("submit", savePipelineConfig);
  const testSettingsBtn = document.getElementById("testFirecrawlSettings");
  if (testSettingsBtn) testSettingsBtn.addEventListener("click", async () => {
    await testFirecrawlHealth();
    await renderSettings();
  });
  const restartSettingsBtn = document.getElementById("restartWorkerSettings");
  if (restartSettingsBtn) restartSettingsBtn.addEventListener("click", async () => {
    await restartWorker();
    await renderSettings();
  });
  document.getElementById("saveScoringDomains").addEventListener("click", saveScoringDomainsConfig);
  document.querySelectorAll("[data-scoring-tab]").forEach((button) => button.addEventListener("click", () => {
    scoringDomainsState.activeTab = button.dataset.scoringTab;
    document.querySelectorAll("[data-scoring-tab]").forEach((tab) => tab.classList.toggle("active", tab === button));
    document.querySelectorAll("[data-tab-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.tabPanel === scoringDomainsState.activeTab));
  }));
  document.querySelectorAll("[data-add-score]").forEach((button) => button.addEventListener("click", () => appendScoreRow(button.dataset.addScore)));
  document.getElementById("addKnownSource").addEventListener("click", appendKnownSourceRow);
  document.querySelectorAll("[data-add-domain]").forEach((button) => button.addEventListener("click", () => appendDomainListItem(button.dataset.addDomain, button.dataset.input)));
  document.querySelectorAll(".settings-scoring-card").forEach((card) => card.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-row]");
    if (!remove) return;
    remove.closest("[data-row]").remove();
  }));
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
            const runtime = await loadRuntimeHealth();
            if (runtime.has_env_mismatch) {
                alert("Worker is still using a different Firecrawl key. Restart worker from Settings or Monitor.");
            }
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
    const btn = e.target.querySelector('button[type="submit"]');
    btn.textContent = "Saving...";
    btn.disabled = true;

    let data = {};
    try {
        const numFields = [
            ["TOP_N", "Top N Pages to Scrape"],
            ["SEARCH_LIMIT", "Serper Search Limit"],
            ["SERPER_NUM_RESULTS", "Results per Serper request"],
            ["INFER_MAX_SCRAPE", "Max Scrapes for Inference"],
            ["EARLY_STOP_COUNT", "Early Stop Count"],
            ["EARLY_STOP_SCORE", "Early Stop Score"],
            ["DELAY_SECONDS", "Delay Seconds"],
            ["MAX_RETRIES", "Max Retries"],
            ["BATCH_SIZE", "Batch Size"],
            ["MIN_CONFIDENCE_THRESHOLD", "Min Confidence"],
            ["MIN_SCRAPE_SCORE", "Min Scrape Score"],
            ["FIRECRAWL_MAX_CONCURRENCY", "Firecrawl Max Concurrency"],
            ["FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS", "Firecrawl Batch Poll Interval"],
            ["FIRECRAWL_BATCH_TIMEOUT_SECONDS", "Firecrawl Batch Timeout"],
            ["CACHE_TTL_DAYS", "Cache TTL Days"],
        ];
        for (const [id, label] of numFields) data[id] = numberValue(id, label);
        data.REPORT_CUTOFF_TIME = document.getElementById("REPORT_CUTOFF_TIME").value || "17:00";
        if (!/^\d{2}:\d{2}$/.test(data.REPORT_CUTOFF_TIME)) throw new Error("Report Cutoff Time must use HH:MM format.");
        if (data.FIRECRAWL_MAX_CONCURRENCY < 1) throw new Error("Firecrawl Max Concurrency must be at least 1.");

        const boolFields = [
            "GEMINI_QUICK_ENABLED",
            "SERPER_ENABLED",
            "SCRAPE_LINKEDIN_ENABLED",
            "BUSINESS_STATUS_GATE_ENABLED",
            "ENABLE_QUERY_DEDUP",
            "ENABLE_URL_DEDUP",
            "ENABLE_GLOBAL_CACHE",
            "FIRECRAWL_BATCH_SCRAPE_ENABLED",
        ];
        for (const f of boolFields) data[f] = document.getElementById(f).checked;
    } catch (err) {
        alert(err.message);
        btn.textContent = "Save Pipeline Behavior";
        btn.disabled = false;
        return;
    }

    try {
        const res = await fetch("/api/spa/pipeline-config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
        if (res.ok) {
            alert("Pipeline behavior saved successfully!");
            renderSettings();
        } else {
            const payload = await res.json().catch(() => ({}));
            alert(payload.error || "Error saving pipeline behavior");
            btn.textContent = "Save Pipeline Behavior";
            btn.disabled = false;
        }
    } catch (err) {
        alert("Error: " + err.message);
        btn.textContent = "Save Pipeline Behavior";
        btn.disabled = false;
    }
}

async function saveScoringDomainsConfig() {
    const btn = document.getElementById("saveScoringDomains");
    btn.textContent = "Saving...";
    btn.disabled = true;

    let data;
    try {
        data = collectScoringDomainsConfigFromDocument();
    } catch (err) {
        alert(err.message);
        btn.textContent = "Save Scoring & Domains";
        btn.disabled = false;
        return;
    }

    try {
        const res = await fetch("/api/spa/pipeline-config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(data)
        });
        if (res.ok) {
            alert("Scoring & Domains saved successfully!");
            renderSettings();
        } else {
            const payload = await res.json().catch(() => ({}));
            alert(payload.error || "Error saving scoring and domains");
            btn.textContent = "Save Scoring & Domains";
            btn.disabled = false;
        }
    } catch (err) {
        alert("Error: " + err.message);
        btn.textContent = "Save Scoring & Domains";
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
    if (hash.startsWith("#/company/")) return await renderCompanyDetail(hash.split("/")[2]);
    if (hash === "#/companies") return await renderCompanies();
    if (hash === "#/monitor" || hash === "#/runner") return await renderMonitor();
    if (hash === "#/logs") return await renderLogs();
    if (hash === "#/settings") return await renderSettings();
    return await renderDashboard();
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
