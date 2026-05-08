"""
Pipeline Dashboard — FastAPI web application for managing the Vietnamese
company contact-data extraction pipeline.

Serves read-only monitoring pages, a config editor, and a company re-run
action.  Does NOT start any background threads or run the pipeline itself.
"""

import os
import sys
import json
import asyncio
from datetime import datetime

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from dotenv import set_key, load_dotenv

# Ensure the project root (parent of dashboard/) is on sys.path so that
# `from src.xxx import ...` works regardless of cwd.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.database import DatabaseManager
from src.health_monitor import HealthMonitor
from src.logger import PipelineLogger
from src.config import Config
from src.pipeline import Pipeline

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

app = FastAPI(title="Pipeline Dashboard")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(
    _PROJECT_ROOT,
    os.getenv("DB_PATH", "data/company_data.db"),
)
DOTENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
LOG_DIR = os.path.join(_PROJECT_ROOT, "output", "logs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db() -> DatabaseManager:
    """Return a DatabaseManager pointed at the absolute DB path."""
    return DatabaseManager(DB_PATH)


def _get_monitor() -> HealthMonitor:
    db = _get_db()
    # PipelineLogger writes to disk — keep log_dir absolute.
    logger = PipelineLogger(db, log_dir=LOG_DIR)
    return HealthMonitor(db, logger)


# ---------------------------------------------------------------------------
# Shared HTML fragments
# ---------------------------------------------------------------------------

_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #1a1a2e; color: #eee;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  nav {
    background: #16213e; padding: 12px 24px;
    border-bottom: 2px solid #0f3460;
    display: flex; gap: 24px; align-items: center;
  }
  nav a {
    color: #a8dadc; text-decoration: none; font-weight: 600;
    padding: 4px 10px; border-radius: 4px;
    transition: background 0.15s;
  }
  nav a:hover { background: #0f3460; color: #fff; }
  nav .brand { color: #e94560; font-size: 16px; font-weight: 700; margin-right: 12px; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 20px; margin-bottom: 18px; color: #a8dadc; }
  h2 { font-size: 16px; margin: 18px 0 10px; color: #a8dadc; }
  .card {
    background: #16213e; border: 1px solid #0f3460;
    border-radius: 8px; padding: 18px; margin-bottom: 18px;
  }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
  .stat {
    background: #0f3460; border-radius: 6px; padding: 14px;
    text-align: center;
  }
  .stat .value { font-size: 26px; font-weight: 700; }
  .stat .label { font-size: 11px; color: #a0a0b0; margin-top: 4px; text-transform: uppercase; }
  /* Progress bar */
  .progress-wrap { background: #0f3460; border-radius: 6px; height: 22px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 6px; transition: width 0.3s; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #fff; }
  /* Table */
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid #0f3460; }
  th { background: #0f3460; color: #a8dadc; font-size: 12px; text-transform: uppercase; position: sticky; top: 0; }
  tr:hover td { background: #1e2a4a; }
  tr:nth-child(even) td { background: #182040; }
  tr:nth-child(even):hover td { background: #1e2a4a; }
  /* Badges */
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
  }
  .badge-done     { background: #1a7a4a; color: #aef3c7; }
  .badge-failed, .badge-permanently_failed { background: #7a1a1a; color: #f3aeae; }
  .badge-pending  { background: #3a3a4a; color: #b0b0c0; }
  .badge-searching, .badge-scraping, .badge-extracting,
  .badge-in_progress, .badge-contact_discovering { background: #5a4a10; color: #f3e0ae; }
  /* Buttons / forms */
  .btn {
    display: inline-block; padding: 5px 12px; border-radius: 4px; border: none;
    cursor: pointer; font-size: 12px; font-weight: 600; text-decoration: none;
  }
  .btn-rerun   { background: #0f3460; color: #a8dadc; }
  .btn-rerun:hover { background: #1a5090; }
  .btn-save    { background: #1a7a4a; color: #fff; padding: 8px 20px; font-size: 14px; }
  .btn-save:hover { background: #22a060; }
  /* Filter bar */
  .filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .filters a {
    padding: 4px 12px; border-radius: 14px; border: 1px solid #0f3460;
    color: #a8dadc; text-decoration: none; font-size: 12px;
  }
  .filters a.active, .filters a:hover { background: #0f3460; color: #fff; }
  /* Log lines */
  .log-success { color: #5cffa0; }
  .log-failed  { color: #ff6060; }
  .log-dedup   { color: #ffe04a; }
  .log-earlystop { color: #60b0ff; }
  .log-default { color: #c0c0d0; }
  pre { font-size: 11px; white-space: pre-wrap; word-break: break-all; margin: 0; }
  /* Form inputs */
  input[type=text], input[type=number] {
    background: #0f1e3a; border: 1px solid #0f3460; color: #eee;
    border-radius: 4px; padding: 5px 8px; width: 100%;
  }
  input[type=text]:focus, input[type=number]:focus {
    outline: none; border-color: #a8dadc;
  }
  .config-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  .config-row label { width: 220px; font-size: 12px; color: #a0a0b0; flex-shrink: 0; }
  .config-row .config-val { flex: 1; }
  .flash { padding: 10px 16px; border-radius: 6px; margin-bottom: 16px; }
  .flash-ok { background: #1a4a2a; color: #aef3c7; border: 1px solid #2a7a4a; }
  .flash-err { background: #4a1a1a; color: #f3aeae; border: 1px solid #7a2a2a; }
  a.view-link { color: #60b0ff; text-decoration: none; font-size: 12px; }
  a.view-link:hover { text-decoration: underline; }
</style>
"""

_NAV = """
<nav>
  <span class="brand">Pipeline Dashboard</span>
  <a href="/">Dashboard</a>
  <a href="/companies">Companies</a>
  <a href="/config">Config</a>
  <a href="/logs">Logs</a>
</nav>
"""


def _page(title: str, body: str) -> str:
    """Wrap body in a full HTML page."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Pipeline Dashboard</title>
  {_CSS}
</head>
<body>
{_NAV}
<div class="container">
{body}
</div>
</body>
</html>"""


def _badge(status: str) -> str:
    cls = f"badge-{status}"
    return f'<span class="badge {cls}">{status}</span>'


def _progress_bar(pct: float) -> str:
    color = "#1a7a4a" if pct >= 75 else ("#b07800" if pct >= 25 else "#7a1a1a")
    return (
        f'<div class="progress-wrap">'
        f'<div class="progress-fill" style="width:{pct:.1f}%;background:{color};">'
        f'{pct:.1f}%</div></div>'
    )


# ---------------------------------------------------------------------------
# GET /  — Main dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard():
    try:
        monitor = _get_monitor()
        status = monitor.get_system_status()
        credits = monitor.check_credits_remaining()
    except Exception as exc:
        return HTMLResponse(_page("Dashboard", f'<div class="card flash flash-err">DB error: {exc}</div>'))

    total = status["total_companies"]
    done = status["completed"]
    failed = status["failed"]
    perm_failed = status["permanently_failed"]
    in_prog = status["in_progress"]
    pending = status["pending"]
    pct = status["progress_percent"]

    # Phone / email coverage
    db = _get_db()
    phone_row = db.fetch_one(
        "SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE phone IS NOT NULL AND phone != ''"
    )
    email_row = db.fetch_one(
        "SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE email IS NOT NULL AND email != ''"
    )
    phone_count = phone_row["cnt"] if phone_row else 0
    email_count = email_row["cnt"] if email_row else 0
    phone_pct = round(phone_count / done * 100, 1) if done > 0 else 0.0
    email_pct = round(email_count / done * 100, 1) if done > 0 else 0.0

    body = f"""
<h1>Pipeline Overview</h1>

<div class="card">
  <h2>Progress</h2>
  {_progress_bar(pct)}
  <p style="margin-top:8px;font-size:13px;color:#a0a0b0;">{done} / {total} companies completed</p>
</div>

<div class="card">
  <div class="grid">
    <div class="stat">
      <div class="value" style="color:#5cffa0;">{done}</div>
      <div class="label">Done</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#ff6060;">{failed}</div>
      <div class="label">Failed</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#ff4040;">{perm_failed}</div>
      <div class="label">Perm. Failed</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#ffe04a;">{in_prog}</div>
      <div class="label">In Progress</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#a0a0b0;">{pending}</div>
      <div class="label">Pending</div>
    </div>
    <div class="stat">
      <div class="value">{total}</div>
      <div class="label">Total</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="grid">
    <div class="stat">
      <div class="value" style="color:#60b0ff;">{credits['total_credits_used']:.0f}</div>
      <div class="label">Credits Used</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#a8dadc;">{credits['search_credits_used']:.0f}</div>
      <div class="label">Search Credits</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#a8dadc;">{credits['scrape_credits_used']:.0f}</div>
      <div class="label">Scrape Credits</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#5cffa0;">{credits['credits_remaining']:.0f}</div>
      <div class="label">Credits Remaining</div>
    </div>
    <div class="stat">
      <div class="value">~{status['estimated_hours_remaining']:.1f}h</div>
      <div class="label">Est. Hours Left</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#5cffa0;">{phone_pct:.1f}%</div>
      <div class="label">Phone Coverage</div>
    </div>
    <div class="stat">
      <div class="value" style="color:#5cffa0;">{email_pct:.1f}%</div>
      <div class="label">Email Coverage</div>
    </div>
  </div>
</div>

<div class="card">
  <h2>Quick Links</h2>
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;">
    <a href="/companies" class="btn btn-rerun">All Companies</a>
    <a href="/companies?status=failed" class="btn btn-rerun">Failed Companies</a>
    <a href="/companies?status=pending" class="btn btn-rerun">Pending Companies</a>
    <a href="/config" class="btn btn-rerun">Edit Config</a>
    <a href="/logs" class="btn btn-rerun">View Logs</a>
    <a href="/api/status" class="btn btn-rerun">JSON Status</a>
  </div>
</div>
"""
    return HTMLResponse(_page("Dashboard", body))


# ---------------------------------------------------------------------------
# GET /companies  — Company list
# ---------------------------------------------------------------------------

@app.get("/companies", response_class=HTMLResponse)
def companies_list(status: str = None):
    db = _get_db()

    valid_statuses = {"done", "failed", "pending", "searched", "scraped",
                      "searching", "scraping", "extracting", "permanently_failed",
                      "ai_done", "contact_discovering"}

    if status and status in valid_statuses:
        rows = db.fetch_all(
            "SELECT id, original_name, tax_code, status, updated_at FROM companies WHERE status = ? ORDER BY id",
            (status,)
        )
    else:
        rows = db.fetch_all(
            "SELECT id, original_name, tax_code, status, updated_at FROM companies ORDER BY id"
        )
        status = None

    filter_links = "".join(
        f'<a href="/companies?status={s}" class="{"active" if status == s else ""}">{s}</a>'
        for s in ["done", "failed", "permanently_failed", "pending", "searching", "scraping", "extracting"]
    )
    filter_html = f"""
<div class="filters">
  <a href="/companies" class="{"active" if status is None else ""}">All</a>
  {filter_links}
</div>"""

    rows_html = ""
    for r in rows:
        rows_html += f"""
<tr>
  <td>{r['id']}</td>
  <td>{r['original_name'] or ''}</td>
  <td>{r['tax_code'] or ''}</td>
  <td>{_badge(r['status'])}</td>
  <td>{r['updated_at'] or ''}</td>
  <td>
    <form method="post" action="/companies/{r['id']}/rerun" style="display:inline;">
      <button type="submit" class="btn btn-rerun">Re-run</button>
    </form>
    &nbsp;
    <a href="/companies/{r['id']}/logs" class="view-link">View logs</a>
  </td>
</tr>"""

    body = f"""
<h1>Companies ({len(rows)} shown)</h1>
{filter_html}
<div class="card" style="overflow-x:auto;">
  <table>
    <thead>
      <tr>
        <th>ID</th><th>Name</th><th>Tax Code</th><th>Status</th>
        <th>Last Updated</th><th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>"""
    return HTMLResponse(_page("Companies", body))


# ---------------------------------------------------------------------------
# POST /companies/{company_id}/rerun
# ---------------------------------------------------------------------------

@app.post("/companies/{company_id}/rerun")
def company_rerun(company_id: int):
    db = _get_db()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    db.update_company(company_id, status="pending")
    return RedirectResponse(url="/companies", status_code=303)


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/logs
# ---------------------------------------------------------------------------

@app.get("/companies/{company_id}/logs", response_class=HTMLResponse)
def company_logs(company_id: int):
    db = _get_db()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    logs = db.get_pipeline_logs_for_company(company_id)
    contacts = db.get_extracted_contacts_for_company(company_id)

    # Build logs table
    log_rows = ""
    for lg in logs:
        status_color = ""
        if lg.get("status") == "success":
            status_color = "color:#5cffa0;"
        elif lg.get("status") in ("failed", "error"):
            status_color = "color:#ff6060;"
        elif lg.get("status") == "started":
            status_color = "color:#ffe04a;"

        err = lg.get("error_message") or ""
        if len(err) > 80:
            err = err[:80] + "…"

        log_rows += f"""
<tr>
  <td>{lg.get('id','')}</td>
  <td>{lg.get('step','')}</td>
  <td style="{status_color}">{lg.get('status','')}</td>
  <td>{lg.get('started_at','') or ''}</td>
  <td>{lg.get('finished_at','') or ''}</td>
  <td>{lg.get('duration_seconds') or ''}</td>
  <td>{lg.get('credits_used') or 0}</td>
  <td>{err}</td>
</tr>"""

    # Build contacts table
    contact_rows = ""
    for c in contacts:
        contact_rows += f"""
<tr>
  <td>{c.get('id','')}</td>
  <td>{c.get('source_type','')}</td>
  <td>{c.get('phone') or ''}</td>
  <td>{c.get('email') or ''}</td>
  <td>{c.get('address') or ''}</td>
  <td>{c.get('website') or ''}</td>
  <td>{c.get('confidence_score') or ''}</td>
</tr>"""

    contacts_section = ""
    if contacts:
        contacts_section = f"""
<h2>Extracted Contacts ({len(contacts)})</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr>
      <th>ID</th><th>Source Type</th><th>Phone</th><th>Email</th>
      <th>Address</th><th>Website</th><th>Confidence</th>
    </tr></thead>
    <tbody>{contact_rows}</tbody>
  </table>
</div>"""
    else:
        contacts_section = '<div class="card"><p style="color:#a0a0b0;">No extracted contacts yet.</p></div>'

    body = f"""
<h1>Logs: {company.get('original_name','Company')} (ID {company_id})</h1>
<div class="card" style="margin-bottom:8px;">
  <strong>Status:</strong> {_badge(company.get('status',''))}
  &nbsp;&nbsp;
  <strong>Tax code:</strong> {company.get('tax_code') or 'N/A'}
  &nbsp;&nbsp;
  <a href="/companies" class="view-link">← Back to Companies</a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="/companies/{company_id}/scores" class="view-link">View Scores</a>
</div>

<div class="card">
  <h2 style="margin-top:0;">Run Pipeline Step</h2>
  <form method="post" action="/companies/{company_id}/run-step" style="display:flex;gap:8px;align-items:center;">
    <select name="step" style="padding:5px 8px;background:#0f1e3a;border:1px solid #0f3460;color:#eee;border-radius:4px;">
      <option value="search">Search</option>
      <option value="filter">Filter</option>
      <option value="scrape">Scrape</option>
      <option value="extract">Extract</option>
    </select>
    <button type="submit" class="btn btn-rerun">Run Step</button>
  </form>
</div>

<h2>Pipeline Logs ({len(logs)} entries)</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr>
      <th>ID</th><th>Step</th><th>Status</th><th>Started</th>
      <th>Finished</th><th>Duration (s)</th><th>Credits</th><th>Error</th>
    </tr></thead>
    <tbody>{log_rows or '<tr><td colspan="8" style="color:#a0a0b0;">No logs yet.</td></tr>'}</tbody>
  </table>
</div>

{contacts_section}
"""
    return HTMLResponse(_page(f"Logs: Company {company_id}", body))


# ---------------------------------------------------------------------------
# GET /config  — Config viewer / editor
# ---------------------------------------------------------------------------

_CONFIG_FIELDS = [
    # (env_key, label, type_hint)
    ("SEARCH_LIMIT",             "Search Limit",             "int"),
    ("EARLY_STOP_COUNT",         "Early Stop Count",          "int"),
    ("EARLY_STOP_SCORE",         "Early Stop Score",          "int"),
    ("FB_FALLBACK_THRESHOLD",    "FB Fallback Threshold",     "int"),
    ("DOMAIN_SCORES",            "Domain Scores (JSON)",      "str"),
    ("KEYWORD_SCORES",           "Keyword Scores (JSON)",     "str"),
    ("TOP_N",                    "Top N Links",               "int"),
    ("CONTACT_DISCOVERY_ENABLED","Contact Discovery Enabled", "bool"),
    ("CONTACT_PATHS",            "Contact Paths (comma-sep)", "str"),
    ("ENABLE_QUERY_DEDUP",       "Enable Query Dedup",        "bool"),
    ("ENABLE_URL_DEDUP",         "Enable URL Dedup",          "bool"),
    ("ENABLE_GLOBAL_CACHE",      "Enable Global Cache",       "bool"),
    ("CACHE_TTL_DAYS",           "Cache TTL (days)",          "int"),
    ("FORCE_REFRESH",            "Force Refresh",             "bool"),
    ("DELAY_SECONDS",            "Delay Between Requests (s)","float"),
    ("MAX_RETRIES",              "Max Retries",               "int"),
    ("EXECUTION_MODE",           "Execution Mode",            "str"),
    ("BATCH_SIZE",               "Batch Size",                "int"),
]


def _config_value_str(cfg: Config, key: str) -> str:
    """Return the current config value as a display string."""
    val = getattr(cfg, key, "")
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, saved: str = None):
    cfg = Config()

    flash = ""
    if saved == "1":
        flash = '<div class="flash flash-ok">Configuration saved successfully.</div>'
    elif saved == "error":
        flash = '<div class="flash flash-err">Error saving configuration.</div>'

    rows_html = ""
    for env_key, label, _ in _CONFIG_FIELDS:
        current = _config_value_str(cfg, env_key)
        rows_html += f"""
<div class="config-row">
  <label for="field_{env_key}">{label}<br><small style="color:#606070;">{env_key}</small></label>
  <div class="config-val">
    <input type="text" id="field_{env_key}" name="{env_key}" value="{current}">
  </div>
</div>"""

    body = f"""
<h1>Configuration</h1>
{flash}
<div class="card">
  <p style="color:#a0a0b0;margin-bottom:16px;font-size:12px;">
    Values are written to <code>.env</code> in the project root.
    Restart the pipeline process to apply changes.
  </p>
  <form method="post" action="/config">
    {rows_html}
    <div style="margin-top:18px;">
      <button type="submit" class="btn btn-save">Save Configuration</button>
    </div>
  </form>
</div>"""
    return HTMLResponse(_page("Config", body))


# ---------------------------------------------------------------------------
# POST /config  — Save config to .env
# ---------------------------------------------------------------------------

@app.post("/config")
async def config_save(request: Request):
    form = await request.form()
    try:
        for env_key, _, _ in _CONFIG_FIELDS:
            value = form.get(env_key)
            if value is not None:
                set_key(DOTENV_PATH, env_key, str(value))
        return RedirectResponse(url="/config?saved=1", status_code=303)
    except Exception:
        return RedirectResponse(url="/config?saved=error", status_code=303)


# ---------------------------------------------------------------------------
# GET /logs  — Log stream page
# ---------------------------------------------------------------------------

@app.get("/logs", response_class=HTMLResponse)
def logs_page(company_id: int = None):
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"pipeline_{today}.jsonl")

    lines_raw = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines_raw = f.readlines()
        except OSError:
            lines_raw = []

    # Filter by company_id if requested
    if company_id is not None:
        filtered = []
        for line in lines_raw:
            try:
                obj = json.loads(line)
                if str(obj.get("company_id", "")) == str(company_id):
                    filtered.append(line)
            except (json.JSONDecodeError, ValueError):
                pass
        lines_raw = filtered

    # Take last 200
    lines_raw = lines_raw[-200:]

    def _classify(line: str) -> str:
        """Return CSS class for this log line."""
        try:
            obj = json.loads(line)
            event = obj.get("event", "")
            status = obj.get("status", "")
            if event == "step_end" and status == "success":
                return "log-success"
            if event == "step_end" and status in ("failed", "error"):
                return "log-failed"
            if event.startswith("dedup_"):
                return "log-dedup"
            if event.startswith("early_stop_"):
                return "log-earlystop"
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass
        return "log-default"

    log_items = ""
    for line in reversed(lines_raw):
        css = _classify(line)
        # Pretty-print JSON when possible, else show raw
        try:
            obj = json.loads(line)
            display = json.dumps(obj, ensure_ascii=False, indent=None)
        except (json.JSONDecodeError, ValueError):
            display = line.rstrip()
        log_items += f'<div class="{css}"><pre>{display}</pre></div>\n'

    filter_note = f"  &nbsp;·&nbsp; Filtering by company_id={company_id}" if company_id else ""
    no_file_note = "" if os.path.exists(log_file) else f'<div class="flash flash-err">Log file not found: {log_file}</div>'

    body = f"""
<h1>Log Stream — {today}{filter_note}</h1>
{no_file_note}
<div class="card" style="margin-bottom:12px;">
  <span style="font-size:12px;color:#a0a0b0;">
    Showing last {len(lines_raw)} lines (newest first) from
    <code>output/logs/pipeline_{today}.jsonl</code>
  </span>
  &nbsp;&nbsp;
  <span style="font-size:11px;">
    <span class="badge" style="background:#1a4a2a;color:#5cffa0;">green=success</span>
    &nbsp;
    <span class="badge" style="background:#4a1a1a;color:#ff6060;">red=failed</span>
    &nbsp;
    <span class="badge" style="background:#4a3800;color:#ffe04a;">yellow=dedup</span>
    &nbsp;
    <span class="badge" style="background:#1a2a4a;color:#60b0ff;">blue=early_stop</span>
  </span>
</div>
<div class="card" style="max-height:70vh;overflow-y:auto;">
  {log_items or '<p style="color:#a0a0b0;">No log entries for today.</p>'}
</div>"""
    return HTMLResponse(_page("Logs", body))


# ---------------------------------------------------------------------------
# GET /api/status  — JSON status
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    try:
        monitor = _get_monitor()
        return JSONResponse(monitor.get_system_status())
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# GET /api/companies  — JSON company list
# ---------------------------------------------------------------------------

@app.get("/api/companies")
def api_companies():
    try:
        db = _get_db()
        rows = db.get_all_companies()
        return JSONResponse(rows)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Sub-task A: GET /companies/{company_id}/scores  — Scoring breakdown view
# ---------------------------------------------------------------------------

@app.get("/companies/{company_id}/scores", response_class=HTMLResponse)
def company_scores(company_id: int):
    db = _get_db()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    # Query filtered_links ordered by relevance_score DESC
    filtered_links = db.fetch_all(
        "SELECT url, source_type, relevance_score, should_scrape, reason "
        "FROM filtered_links WHERE company_id = ? ORDER BY relevance_score DESC",
        (company_id,)
    )

    # Build table rows
    rows_html = ""
    for link in filtered_links:
        rows_html += f"""
<tr>
  <td style="word-break:break-all;max-width:400px;"><a href="{link['url']}" target="_blank" style="color:#60b0ff;">{link['url']}</a></td>
  <td>{link['source_type'] or ''}</td>
  <td>{link['relevance_score'] or ''}</td>
  <td>{link['should_scrape'] or 'N/A'}</td>
  <td>{link['reason'] or ''}</td>
</tr>"""

    body = f"""
<h1>Scoring Breakdown: {company.get('original_name','')} (ID {company_id})</h1>
<div class="card" style="margin-bottom:8px;">
  <strong>Tax code:</strong> {company.get('tax_code') or 'N/A'}
  &nbsp;&nbsp;
  <a href="/companies/{company_id}/logs" class="view-link">← Back to logs</a>
</div>

<h2>Filtered Links ({len(filtered_links)} total)</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr>
      <th>URL</th><th>Source Type</th><th>Score</th><th>Should Scrape</th><th>Reason</th>
    </tr></thead>
    <tbody>{rows_html or '<tr><td colspan="5" style="color:#a0a0b0;">No filtered links yet.</td></tr>'}</tbody>
  </table>
</div>
"""
    return HTMLResponse(_page(f"Scores: Company {company_id}", body))


# ---------------------------------------------------------------------------
# Sub-task B: POST /companies/{company_id}/run-step  — Step-level execution
# ---------------------------------------------------------------------------

@app.post("/companies/{company_id}/run-step")
async def company_run_step(company_id: int, request: Request):
    form = await request.form()
    step = form.get("step")

    if not step or step not in ("search", "filter", "scrape", "extract"):
        raise HTTPException(status_code=400, detail="Invalid or missing step parameter")

    db = _get_db()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    try:
        # Map form step names to pipeline step names
        step_map = {
            "search": "search",
            "filter": "filter",
            "scrape": "scrape",
            "extract": "ai_extract"
        }
        pipeline_step = step_map.get(step, step)

        # Instantiate Pipeline with minimal config
        config = {
            "firecrawl_api_key": os.getenv("FIRECRAWL_API_KEY"),
            "gemini_api_key": os.getenv("GEMINI_API_KEY"),
            "input_excel_path": None,
            "output_dir": "output"
        }
        pipeline = Pipeline(config)
        pipeline.run_step(pipeline_step, company_id)

        return RedirectResponse(url=f"/companies/{company_id}/logs", status_code=303)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error running step: {str(exc)}")


# ---------------------------------------------------------------------------
# Sub-task C: GET /api/logs/stream  — SSE real-time logs
# ---------------------------------------------------------------------------

async def log_generator():
    """Generate log lines as Server-Sent Events from the JSONL file."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"pipeline_{today}.jsonl")

    # Check if file exists
    if not os.path.exists(log_file):
        yield f"data: {json.dumps({'event': 'error', 'message': 'Log file not found'})}\n\n"
        return

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Seek to end of file
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    # Yield as SSE format
                    yield f"data: {line.strip()}\n\n"
                else:
                    # No new data, sleep briefly before checking again
                    await asyncio.sleep(1)
    except Exception as exc:
        yield f"data: {json.dumps({'event': 'error', 'message': str(exc)})}\n\n"


@app.get("/api/logs/stream")
async def logs_stream():
    """Server-Sent Events endpoint for real-time log streaming."""
    return StreamingResponse(log_generator(), media_type="text/event-stream")
