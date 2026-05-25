"""
Pipeline Dashboard v2 — Pipeline Control Center
FastAPI application serving the SPA dashboard and JSON APIs.
"""

import os
import sys
import json
import csv
import io
import asyncio
import threading
import base64
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import set_key, load_dotenv

# Ensure project root on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.config import Config

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

VN_TZ = timezone(timedelta(hours=7))

app = FastAPI(title="Pipeline Control Center")

# ---------------------------------------------------------------------------
# Auth & Locking
# ---------------------------------------------------------------------------
_pipeline_lock = threading.Lock()
_pipeline_running = False
_active_pipeline = None

from dashboard.reparse_api import reparse_router
app.include_router(reparse_router)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    user = os.getenv("DASHBOARD_USER", "admin")
    password = os.getenv("DASHBOARD_PASS")
    if password:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return Response("Unauthorized", status_code=401, headers={"WWW-Authenticate": "Basic"})
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            u, p = decoded.split(":", 1)
            if u != user or p != password:
                return Response("Unauthorized", status_code=401, headers={"WWW-Authenticate": "Basic"})
        except Exception:
            return Response("Unauthorized", status_code=401, headers={"WWW-Authenticate": "Basic"})
    return await call_next(request)

# ---------------------------------------------------------------------------
# SPA shell
# ---------------------------------------------------------------------------
_DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(_DASHBOARD_DIR, "frontend")
SPA_PATH = os.path.join(FRONTEND_DIR, "index.html")
app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

# ---------------------------------------------------------------------------
# Paths & Helpers
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(_PROJECT_ROOT, os.getenv("DB_PATH", "data/company_data.db"))
DOTENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
LOG_DIR = os.path.join(_PROJECT_ROOT, "output", "logs")
_monitor_removed_ids: set[int] = set()
_monitor_stopped_ids: set[int] = set()
monitor_clients: list[WebSocket] = []
_monitor_loop: asyncio.AbstractEventLoop | None = None


DatabaseManager(DB_PATH).init_db()


def _spa_response() -> HTMLResponse:
    with open(SPA_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


def _db() -> DatabaseManager:
    return DatabaseManager(DB_PATH)


def _cfg() -> Config:
    return Config()


def _pipeline_config() -> dict:
    return {
        "firecrawl_api_key": os.getenv("FIRECRAWL_API_KEY"),
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "serper_api_key": os.getenv("SERPER_API_KEY"),
        "input_excel_path": None,
        "output_dir": "output"
    }


def _today_str():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def _now_iso():
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def _job_from_status(status: str) -> tuple[str, str, int]:
    return _STEP_BY_STATUS.get(status or "pending", ("Waiting", status or "pending", 0))


def _upsert_job(db: DatabaseManager, company_id: int, status: str, current_step: str = None,
                checkpoint: str = None, progress: int = None, error_message: str = None,
                removed_from_monitor: int = 0) -> dict | None:
    company = db.get_company(company_id)
    if not company:
        return None

    inferred_step, inferred_checkpoint, inferred_progress = _job_from_status(status)
    current_step = current_step or inferred_step
    checkpoint = checkpoint or inferred_checkpoint
    progress = inferred_progress if progress is None else progress
    now = _now_iso()
    finished_at = now if status in ("done", "failed", "stopped", "permanently_failed") else None

    db.execute_query(
        """
        INSERT INTO pipeline_jobs (
            company_id, company_name, status, current_step, checkpoint, progress,
            started_at, updated_at, finished_at, error_message, removed_from_monitor
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            company_name=excluded.company_name,
            status=excluded.status,
            current_step=excluded.current_step,
            checkpoint=excluded.checkpoint,
            progress=excluded.progress,
            updated_at=excluded.updated_at,
            finished_at=excluded.finished_at,
            error_message=excluded.error_message,
            removed_from_monitor=excluded.removed_from_monitor
        """,
        (
            company_id, company["original_name"], status, current_step, checkpoint,
            progress, now, now, finished_at, error_message, removed_from_monitor,
        ),
    )
    return _get_job(db, company_id)


def _get_job(db: DatabaseManager, company_id: int) -> dict | None:
    return db.fetch_one(
        """
        SELECT company_id as id, company_name as name, status, current_step as step,
               checkpoint, progress, started_at as started, updated_at, finished_at,
               error_message, removed_from_monitor
        FROM pipeline_jobs
        WHERE company_id = ?
        """,
        (company_id,),
    )


def _monitor_counts(jobs: list[dict]) -> dict:
    return {
        "running": sum(1 for j in jobs if j["status"] in _RUNNING_STATUSES),
        "queued": sum(1 for j in jobs if j["status"] == "queued"),
        "failed": sum(1 for j in jobs if j["status"] == "failed"),
        "stopped": sum(1 for j in jobs if j["status"] == "stopped"),
    }


def _monitor_snapshot(db: DatabaseManager) -> dict:
    rows = db.fetch_all(
        """
        SELECT company_id as id, company_name as name, status, current_step as step,
               checkpoint, progress, started_at as started, updated_at, finished_at,
               error_message
        FROM pipeline_jobs
        WHERE removed_from_monitor = 0
          AND status IN ('queued','pending','gemini_quick','searching','scraping','extracting','failed','stopped')
        ORDER BY updated_at DESC, company_id
        LIMIT 500
        """
    )
    return {"jobs": rows, "counts": _monitor_counts(rows)}


_broadcast_lock: asyncio.Lock | None = None

async def _broadcast_monitor(payload: dict):
    global _broadcast_lock
    if _broadcast_lock is None:
        _broadcast_lock = asyncio.Lock()
        
    dead = []
    text = json.dumps(payload, ensure_ascii=False)
    
    async with _broadcast_lock:
        for ws in monitor_clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in monitor_clients:
                monitor_clients.remove(ws)


def _emit_monitor(payload: dict):
    global _monitor_loop
    if not monitor_clients:
        return
    try:
        loop = _monitor_loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast_monitor(payload), loop)
    except RuntimeError:
        pass


def _emit_job_update(db: DatabaseManager, job: dict | None, event_type: str = "job_updated"):
    if not job:
        return
    _emit_monitor({
        "type": event_type,
        "job": job,
        "counts": _monitor_snapshot(db)["counts"],
    })


class MonitorDatabase(DatabaseManager):
    """Database wrapper that emits monitor events when company status changes."""

    def update_company(self, company_id, **kwargs):
        super().update_company(company_id, **kwargs)
        if "status" in kwargs:
            job = _upsert_job(self, int(company_id), kwargs["status"])
            _emit_job_update(self, job)


# ---------------------------------------------------------------------------
# WebSocket connections
# ---------------------------------------------------------------------------
ws_clients: list[WebSocket] = []


_log_broadcast_lock: asyncio.Lock | None = None

async def broadcast_log(message: str):
    """Send a message to all connected WebSocket clients."""
    global _log_broadcast_lock
    if _log_broadcast_lock is None:
        _log_broadcast_lock = asyncio.Lock()
        
    dead = []
    async with _log_broadcast_lock:
        for ws in ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in ws_clients:
                ws_clients.remove(ws)


# ---------------------------------------------------------------------------
# SPA Pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def spa_home():
    return _spa_response()


@app.get("/companies", response_class=HTMLResponse)
def spa_companies():
    return RedirectResponse(url="/#/companies", status_code=303)


@app.get("/companies/{company_id}", response_class=HTMLResponse)
def spa_company_detail(company_id: int):
    return RedirectResponse(url=f"/#/company/{company_id}", status_code=303)


@app.get("/runner", response_class=HTMLResponse)
def spa_runner():
    return RedirectResponse(url="/#/runner", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def spa_settings():
    return RedirectResponse(url="/#/settings", status_code=303)


@app.get("/logs", response_class=HTMLResponse)
def spa_logs():
    return RedirectResponse(url="/#/logs", status_code=303)


@app.post("/companies/{company_id}/rerun")
def company_rerun(company_id: int):
    db = _db()
    db.update_company(company_id, status="pending")
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)


@app.post("/settings")
async def settings_save(request: Request):
    form = await request.form()
    for key in form:
        val = form.get(key)
        if val is not None:
            if "***" in str(val):
                continue
            set_key(DOTENV_PATH, key, str(val))
    # Reload environment to reflect changes immediately
    load_dotenv(DOTENV_PATH, override=True)
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# ---------------------------------------------------------------------------
# API: Quota
# ---------------------------------------------------------------------------
@app.get("/api/quota")
def api_quota():
    db = _db()
    cfg = _cfg()
    today = _today_str()
    row = db.fetch_one("SELECT gemini_grounding_used, serper_used FROM daily_quota WHERE date = ?", (today,))
    return JSONResponse({
        "gemini_grounding_used": row["gemini_grounding_used"] if row else 0,
        "serper_used": row["serper_used"] if row else 0,
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "date": today,
    })


# ---------------------------------------------------------------------------
# API: Status
# ---------------------------------------------------------------------------
@app.get("/api/status")
def api_status():
    db = _db()
    total = db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]
    done = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='done'")["cnt"]
    failed = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status IN ('failed','permanently_failed')")["cnt"]
    pending = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='pending'")["cnt"]
    return JSONResponse({
        "total": total, "done": done, "failed": failed, "pending": pending,
        "progress_percent": round(done / max(total, 1) * 100, 1),
    })


# ---------------------------------------------------------------------------
# API: SPA data
# ---------------------------------------------------------------------------
_RUNNING_STATUSES = {"gemini_quick", "searching", "scraping", "extracting"}
_RESUMABLE_STATUSES = {
    "pending", "failed", "gemini_quick", "gemini_quick_done", "searching",
    "searched", "scraping", "scraped", "ai_extract_pending", "extracting",
    "ai_done",
}
_STEP_BY_STATUS = {
    "pending": ("Waiting", "pipeline_init", 0),
    "failed": ("Failed", "failed", 0),
    "gemini_quick": ("Gemini Quick", "gemini_quick", 20),
    "gemini_quick_done": ("Deep Search", "deep_search", 35),
    "searching": ("Deep Search", "deep_search", 40),
    "searched": ("Filter", "filter", 55),
    "scraping": ("Scrape", "scrape", 65),
    "scraped": ("AI Extract", "ai_extract", 78),
    "ai_extract_pending": ("AI Extract", "ai_extract", 82),
    "extracting": ("AI Extract", "ai_extract", 90),
    "ai_done": ("Finalizing", "done", 95),
    "done": ("Done", "done", 100),
    "permanently_failed": ("Permanently Failed", "permanently_failed", 100),
}


def _counts(db: DatabaseManager) -> dict:
    total = db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]
    done = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='done'")["cnt"]
    failed = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status IN ('failed','permanently_failed')")["cnt"]
    pending = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='pending'")["cnt"]
    running = db.fetch_one(
        "SELECT COUNT(*) as cnt FROM companies WHERE status IN ('gemini_quick','searching','scraping','extracting')"
    )["cnt"]
    return {"total": total, "done": done, "failed": failed, "pending": pending, "running": running}


def _latest_logs(db: DatabaseManager, limit: int = 20) -> list[dict]:
    return db.fetch_all(
        """
        SELECT company_id, step, status, started_at, finished_at, duration_seconds,
               credits_used, error_message, metadata_json
        FROM pipeline_logs
        ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )


def _safe_json(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _company_step(status: str) -> tuple[str, str, int]:
    return _STEP_BY_STATUS.get(status or "pending", ("Unknown", status or "pending", 0))


@app.get("/api/spa/status")
def api_spa_status():
    db = _db()
    cfg = _cfg()
    counts = _counts(db)
    done = counts["done"]

    phone_count = db.fetch_one(
        "SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE phone IS NOT NULL AND phone != ''"
    )["cnt"]
    email_count = db.fetch_one(
        "SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE email IS NOT NULL AND email != ''"
    )["cnt"]

    today = _today_str()
    quota = db.fetch_one("SELECT gemini_grounding_used, serper_used FROM daily_quota WHERE date = ?", (today,))
    tokens = db.fetch_one(
        "SELECT SUM(input_tokens) as tin, SUM(output_tokens) as tout FROM gemini_quick_results WHERE created_at LIKE ?",
        (f"{today}%",),
    )
    gemini_sufficient = db.fetch_one("SELECT COUNT(*) as cnt FROM gemini_quick_results WHERE is_sufficient=1")["cnt"]
    ai_extract_contacts = db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts")["cnt"]

    return JSONResponse({
        "stats": {
            **counts,
            "progress_percent": round(done / max(counts["total"], 1) * 100, 1),
            "phone_pct": round(phone_count / max(done, 1) * 100, 1),
            "email_pct": round(email_count / max(done, 1) * 100, 1),
        },
        "quota": {
            "gemini_used": quota["gemini_grounding_used"] if quota else 0,
            "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
            "firecrawl_used": quota["serper_used"] if quota else 0,
            "firecrawl_total": 2500,
            "tokens_in": tokens["tin"] or 0 if tokens else 0,
            "tokens_out": tokens["tout"] or 0 if tokens else 0,
        },
        "sources": [
            {"label": "Step 1: Gemini Quick", "value": gemini_sufficient},
            {"label": "Step 4: AI Extract", "value": ai_extract_contacts},
        ],
        "logs": _latest_logs(db, 12),
    })


@app.get("/api/spa/companies")
def api_spa_companies(status: str = None, search: str = None, page: int = 1, page_size: int = 50):
    db = _db()
    page_size = max(1, min(page_size, 100))
    page = max(1, page)

    filters = []
    params: list[object] = []
    if status:
        filters.append("status = ?")
        params.append(status)
    if search:
        filters.append("LOWER(original_name) LIKE ?")
        params.append(f"%{search.lower()}%")

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    total = db.fetch_one(f"SELECT COUNT(*) as cnt FROM companies {where}", tuple(params))["cnt"]
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    offset = (page - 1) * page_size

    rows = db.fetch_all(
        f"""
        SELECT id, original_name, vietnamese_name, tax_code, status, updated_at, created_at
        FROM companies
        {where}
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        tuple(params + [page_size, offset]),
    )

    ids = [r["id"] for r in rows]
    contact_by_id: dict[int, dict] = {}
    latest_step_by_id: dict[int, str] = {}
    if ids:
        placeholders = ",".join("?" * len(ids))
        contacts = db.fetch_all(
            f"""
            SELECT company_id,
                   MAX(CASE WHEN phone IS NOT NULL AND phone != '' THEN 1 ELSE 0 END) as has_phone,
                   MAX(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) as has_email
            FROM extracted_contacts
            WHERE company_id IN ({placeholders})
            GROUP BY company_id
            """,
            tuple(ids),
        )
        contact_by_id = {r["company_id"]: r for r in contacts}
        latest_logs = db.fetch_all(
            f"""
            SELECT company_id, step
            FROM pipeline_logs
            WHERE id IN (
                SELECT MAX(id) FROM pipeline_logs WHERE company_id IN ({placeholders}) GROUP BY company_id
            )
            """,
            tuple(ids),
        )
        latest_step_by_id = {r["company_id"]: r["step"] for r in latest_logs}

    companies = []
    for row in rows:
        contact = contact_by_id.get(row["id"], {})
        step, checkpoint, _ = _company_step(row["status"])
        companies.append({
            **row,
            "name": row["original_name"],
            "has_phone": bool(contact.get("has_phone")),
            "has_email": bool(contact.get("has_email")),
            "checkpoint": latest_step_by_id.get(row["id"]) or checkpoint,
            "current_step": step,
        })

    return JSONResponse({
        "companies": companies,
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
        "counts": _counts(db),
    })


@app.get("/api/spa/companies/{company_id}")
def api_spa_company_detail(company_id: int):
    db = _db()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    gemini = db.fetch_one("SELECT * FROM gemini_quick_results WHERE company_id = ? ORDER BY id DESC LIMIT 1", (company_id,))
    if gemini:
        gemini["sources"] = _safe_json(gemini.get("sources_json"), [])
        gemini["grounding_sources"] = _safe_json(gemini.get("grounding_sources_json"), [])

    return JSONResponse({
        "company": company,
        "gemini_quick": gemini,
        "search_results": db.fetch_all("SELECT * FROM search_results WHERE company_id = ? ORDER BY search_type, result_rank", (company_id,)),
        "filtered_links": db.fetch_all("SELECT * FROM filtered_links WHERE company_id = ? ORDER BY relevance_score DESC", (company_id,)),
        "scraped_pages": db.fetch_all("SELECT id, url, source_type, content_length, scrape_status, credits_used, error_message, created_at FROM scraped_pages WHERE company_id = ? ORDER BY id", (company_id,)),
        "contacts": db.fetch_all("SELECT * FROM extracted_contacts WHERE company_id = ? ORDER BY confidence_score DESC", (company_id,)),
        "timeline": db.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? ORDER BY id", (company_id,)),
    })


@app.get("/api/spa/monitor")
def api_spa_monitor():
    return JSONResponse(_monitor_snapshot(_db()))


@app.post("/api/spa/runner/start")
async def api_spa_runner_start(request: Request):
    data = await request.json()
    company_ids = data.get("company_ids", [])
    if not isinstance(company_ids, list) or not company_ids:
        return JSONResponse({"error": "No company IDs provided"}, status_code=400)

    normalized_ids = []
    for cid in company_ids:
        try:
            normalized_ids.append(int(cid))
        except (TypeError, ValueError):
            return JSONResponse({"error": f"Invalid company id: {cid}"}, status_code=400)

    db = _db()
    started = []
    skipped = []
    for cid in dict.fromkeys(normalized_ids):
        company = db.get_company(cid)
        if not company:
            skipped.append({"id": cid, "reason": "not_found"})
            continue
        status = company["status"]
        if status in _RUNNING_STATUSES:
            skipped.append({"id": cid, "reason": "already_running", "status": status})
            continue
        if status in ("done", "permanently_failed"):
            skipped.append({"id": cid, "reason": "not_resumable", "status": status})
            continue
        if status not in _RESUMABLE_STATUSES:
            skipped.append({"id": cid, "reason": "unknown_status", "status": status})
            continue
        _monitor_removed_ids.discard(cid)
        _monitor_stopped_ids.discard(cid)
        job = _upsert_job(db, cid, "queued", current_step="Queued", checkpoint=status, progress=0)
        _emit_job_update(db, job, "job_queued")
        started.append(cid)

    if not started:
        return JSONResponse({"status": "skipped", "started": [], "skipped": skipped}, status_code=409)

    global _pipeline_running
    if _pipeline_running:
        return JSONResponse({"error": "Pipeline already running", "started": [], "skipped": skipped}, status_code=409)

    def run_batch():
        global _pipeline_running, _active_pipeline
        _pipeline_running = True
        try:
            with _pipeline_lock:
                from src.pipeline import Pipeline
                p = Pipeline(_pipeline_config())
                _active_pipeline = p
                monitor_db = MonitorDatabase(DB_PATH)
                p.db = monitor_db
                p.logger.db = monitor_db
                p.run(company_ids=started)
                for cid in started:
                    company = monitor_db.get_company(cid)
                    if company:
                        job = _upsert_job(monitor_db, cid, company["status"])
                        _emit_job_update(monitor_db, job)
        finally:
            _active_pipeline = None
            _pipeline_running = False

    threading.Thread(target=run_batch, daemon=True).start()
    return JSONResponse({"status": "started", "started": started, "skipped": skipped})


@app.post("/api/spa/runner/stop-all")
def api_spa_runner_stop_all():
    if _active_pipeline is not None:
        _active_pipeline._shutdown_requested = True
    db = _db()
    rows = db.fetch_all(
        """
        SELECT company_id as id
        FROM pipeline_jobs
        WHERE removed_from_monitor = 0
          AND status IN ('queued','pending','gemini_quick','searching','scraping','extracting','failed')
        """
    )
    ids = [r["id"] for r in rows]
    for cid in ids:
        job = _upsert_job(db, cid, "stopped", current_step="Stopped", checkpoint="stopped", progress=0)
        _emit_job_update(db, job, "job_stopped")
    return JSONResponse({"status": "stop_requested", "stopped": ids, "count": len(ids)})


@app.post("/api/spa/monitor/remove")
async def api_spa_monitor_remove(request: Request):
    data = await request.json()
    company_id = data.get("company_id")
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return JSONResponse({"error": "Invalid company_id"}, status_code=400)
    db = _db()
    db.execute_query(
        "UPDATE pipeline_jobs SET removed_from_monitor = 1, updated_at = CURRENT_TIMESTAMP WHERE company_id = ?",
        (company_id,),
    )
    _emit_monitor({"type": "job_removed", "company_id": company_id, "counts": _monitor_snapshot(db)["counts"]})
    return JSONResponse({"status": "removed", "company_id": company_id})


@app.get("/api/spa/logs")
def api_spa_logs(limit: int = 200):
    limit = max(1, min(limit, 500))
    today = _today_str()
    log_file = os.path.join(LOG_DIR, f"pipeline_{today}.jsonl")
    lines = []
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()[-limit:] if line.strip()]
    return JSONResponse({"date": today, "lines": list(reversed(lines))})


@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    global _monitor_loop
    await websocket.accept()
    _monitor_loop = asyncio.get_running_loop()
    monitor_clients.append(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "snapshot",
            **_monitor_snapshot(_db()),
        }, ensure_ascii=False))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in monitor_clients:
            monitor_clients.remove(websocket)


import requests

# ---------------------------------------------------------------------------
# API: Settings
# ---------------------------------------------------------------------------
@app.get("/api/spa/settings")
def api_spa_settings():
    return JSONResponse({
        "GEMINI_API_KEY": _mask_key(os.getenv("GEMINI_API_KEY", "")),
        "FIRECRAWL_API_KEY": _mask_key(os.getenv("FIRECRAWL_API_KEY", "")),
        "SERPER_API_KEY": _mask_key(os.getenv("SERPER_API_KEY", "")),
        "AI_GROUNDING_MODEL": os.getenv("AI_GROUNDING_MODEL", "models/gemini-2.5-flash-lite"),
        "AI_EXTRACTOR_MODEL": os.getenv("AI_EXTRACTOR_MODEL", "models/gemini-2.5-flash-lite")
    })

def _mask_key(key: str) -> str:
    if not key or len(key) < 8: return key
    return f"{key[:4]}...{key[-4:]}"

@app.post("/api/spa/settings")
async def api_spa_settings_update(req: Request):
    data = await req.json()
    
    # Update only if a new value is provided and it doesn't contain the mask '...'
    updated = False
    for k in ["GEMINI_API_KEY", "FIRECRAWL_API_KEY", "SERPER_API_KEY"]:
        if k in data and data[k] and "..." not in data[k]:
            set_key(DOTENV_PATH, k, data[k])
            os.environ[k] = data[k]
            updated = True
            
    for k in ["AI_GROUNDING_MODEL", "AI_EXTRACTOR_MODEL"]:
        if k in data and data[k]:
            set_key(DOTENV_PATH, k, data[k])
            os.environ[k] = data[k]
            updated = True
            
    if updated:
        load_dotenv(DOTENV_PATH, override=True)
        
    return JSONResponse({"status": "ok", "message": "Settings updated"})

@app.get("/api/spa/gemini-models")
def api_spa_gemini_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return JSONResponse({"error": "No GEMINI_API_KEY configured"}, status_code=400)
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        models = []
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                models.append({
                    "name": m.get("name"),
                    "displayName": m.get("displayName")
                })
        return JSONResponse({"models": models})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# API: Delete Companies
# ---------------------------------------------------------------------------
@app.post("/api/spa/companies/delete")
async def api_spa_companies_delete(req: Request):
    data = await req.json()
    company_ids = data.get("company_ids", [])
    if not company_ids:
        return JSONResponse({"error": "No company_ids provided"}, status_code=400)
    db = _db()
    try:
        db.delete_companies(company_ids)
        return JSONResponse({"status": "ok", "deleted": len(company_ids)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# API: Companies mapping
# ---------------------------------------------------------------------------
@app.get("/api/companies/names")
def api_company_names():
    db = _db()
    rows = db.fetch_all("SELECT id, original_name FROM companies")
    return JSONResponse({str(r["id"]): r["original_name"] for r in rows})


# ---------------------------------------------------------------------------
# API: Import Companies
# ---------------------------------------------------------------------------
@app.post("/api/companies/import")
async def api_import(request: Request):
    data = await request.json()
    names = data.get("names", [])
    if not names:
        return JSONResponse({"error": "No names provided"}, status_code=400)

    db = _db()
    imported = 0
    skipped = 0

    for name in names:
        name = str(name).strip()
        if not name:
            continue
        # Check duplicate
        existing = db.fetch_one("SELECT id FROM companies WHERE original_name = ?", (name,))
        if existing:
            skipped += 1
            continue
        db.insert_company(name)
        imported += 1

    return JSONResponse({"imported": imported, "skipped": skipped, "total": len(names)})


# ---------------------------------------------------------------------------
# API: Runner — Step execution
# ---------------------------------------------------------------------------
@app.post("/api/runner/step")
async def run_step_api(request: Request):
    data = await request.json()
    company_id = data.get("company_id")
    step = data.get("step")

    VALID_STEPS = {"gemini_quick", "google_maps", "serper_search", "filter", "scrape", "ai_extract", "facebook", "full"}
    
    if not isinstance(company_id, int) or company_id <= 0:
        return JSONResponse({"error": "Invalid company_id"}, status_code=400)
    if step not in VALID_STEPS:
        return JSONResponse({"error": f"Invalid step: {step}. Valid: {VALID_STEPS}"}, status_code=400)

    from starlette.concurrency import run_in_threadpool

    def _sync_logic():
        db = _db()
        company = db.get_company(company_id)
        if not company:
            return JSONResponse({"error": "Company not found"}, status_code=404)
        
        cfg = _cfg()
        logger = PipelineLogger(db, log_dir=LOG_DIR)

        if step == "gemini_quick":
            from src.gemini_quick_search import GeminiQuickSearch
            gqs = GeminiQuickSearch(db, logger, config=cfg)
            result = gqs.search(company_id)
            return JSONResponse({
                "status": "success",
                "step": step,
                "phone": (result.get("result") or {}).get("phone"),
                "confidence": (result.get("result") or {}).get("confidence"),
                "is_sufficient": result.get("is_sufficient"),
                "tokens_used": {
                    "input": result.get("input_tokens", 0),
                    "output": result.get("output_tokens", 0),
                },
                "grounding_sources": result.get("grounding_sources", []),
                "result": result.get("result"),
            })

        elif step == "google_maps":
            from src.serper_search import SerperSearch
            serper = SerperSearch(db, logger, config=cfg)
            # Try to get query from gemini result
            gr = db.fetch_one("SELECT result_json FROM gemini_quick_results WHERE company_id = ? ORDER BY id DESC LIMIT 1", (company_id,))
            query = company["original_name"]
            if gr and gr.get("result_json"):
                try:
                    parsed = json.loads(gr["result_json"])
                    query = parsed.get("core_name_vi") or parsed.get("core_name") or query
                except json.JSONDecodeError:
                    pass

            result = serper.search_places(company_id, query)
            return JSONResponse({
                "status": "success",
                "step": step,
                "phone": result.get("phone"),
                "address": result.get("address"),
                "website": result.get("website"),
                "title": result.get("title"),
                "credits_used": result.get("serper_credits_used", 0),
            })

        elif step == "serper_search":
            from src.serper_search import SerperSearch
            serper = SerperSearch(db, logger, config=cfg)
            results = serper.search(company_id, company["original_name"])
            return JSONResponse({
                "status": "success",
                "step": step,
                "urls_found": len(results),
                "results": results[:10],
            })

        elif step in ("scrape", "filter", "ai_extract"):
            from src.pipeline import Pipeline
            pipeline = Pipeline(_pipeline_config())
            step_map = {"scrape": "scrape", "filter": "filter", "ai_extract": "ai_extract"}
            pipeline.run_step(step_map[step], company_id)
            return JSONResponse({"status": "success", "step": step})

        elif step == "facebook":
            # Check for FB urls
            fb_links = db.fetch_all(
                "SELECT url FROM search_results WHERE company_id = ? AND url LIKE '%facebook.com%'",
                (company_id,)
            )
            return JSONResponse({
                "status": "success",
                "step": step,
                "facebook_urls": [f["url"] for f in fb_links],
                "urls_found": len(fb_links),
            })

        elif step == "full":
            global _pipeline_running
            if _pipeline_running:
                return JSONResponse({"error": "Pipeline already running"}, status_code=409)

            def run_pipeline():
                global _pipeline_running, _active_pipeline
                _pipeline_running = True
                try:
                    with _pipeline_lock:
                        from src.pipeline import Pipeline
                        p = Pipeline(_pipeline_config())
                        _active_pipeline = p
                        db_inner = _db()
                        db_inner.update_company(company_id, status="pending")
                        p.run(company_ids=[company_id])
                finally:
                    _active_pipeline = None
                    _pipeline_running = False

            thread = threading.Thread(target=run_pipeline, daemon=True)
            thread.start()
            return JSONResponse({"status": "started", "message": f"Pipeline started for company {company_id}"})

        else:
            return JSONResponse({"error": f"Unknown step: {step}"}, status_code=400)

    try:
        return await run_in_threadpool(_sync_logic)
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API: Runner — Batch start
# ---------------------------------------------------------------------------
@app.post("/api/runner/start")
async def api_runner_start(request: Request):
    data = await request.json()
    company_ids = data.get("company_ids", [])

    if not company_ids:
        return JSONResponse({"error": "No company IDs provided"}, status_code=400)

    global _pipeline_running
    if _pipeline_running:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)

    def run_batch():
        global _pipeline_running, _active_pipeline
        _pipeline_running = True
        try:
            with _pipeline_lock:
                db_inner = _db()
                for cid in company_ids:
                    db_inner.update_company(cid, status="pending")
                from src.pipeline import Pipeline
                p = Pipeline(_pipeline_config())
                _active_pipeline = p
                p.run(company_ids=company_ids)
        finally:
            _active_pipeline = None
            _pipeline_running = False

    thread = threading.Thread(target=run_batch, daemon=True)
    thread.start()

    return JSONResponse({"status": "started", "count": len(company_ids)})


# ---------------------------------------------------------------------------
# API: Export Logs
# ---------------------------------------------------------------------------
@app.get("/api/export/logs")
def api_export_logs(format: str = "jsonl", company_id: int = None):
    db = _db()
    today = _today_str()

    if format == "jsonl":
        log_file = os.path.join(LOG_DIR, f"pipeline_{today}.jsonl")
        if not os.path.exists(log_file):
            return JSONResponse({"error": "No log file for today"}, status_code=404)
        return StreamingResponse(
            open(log_file, "r", encoding="utf-8"),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f"attachment; filename=pipeline_{today}.jsonl"}
        )

    elif format == "csv":
        query = """
            SELECT 
                pl.id, 
                pl.company_id, 
                c.original_name AS company_name,
                pl.step, 
                pl.status, 
                pl.started_at, 
                pl.finished_at, 
                pl.duration_seconds, 
                pl.source_url, 
                pl.source_name, 
                pl.credits_used, 
                pl.error_message, 
                pl.data_saved,
                COALESCE(ec.phone, gqr.phone) AS phone,
                COALESCE(ec.email, gqr.email) AS email,
                COALESCE(ec.address, gqr.address) AS address,
                COALESCE(ec.website, gqr.website) AS website,
                COALESCE(ec.representative, gqr.representative) AS representative,
                ROUND(fl.relevance_score, 1) AS relevance_score,
                fl.reason AS score_reason,
                sr.search_query,
                sr.snippet AS search_snippet,
                pl.metadata_json
            FROM pipeline_logs pl
            LEFT JOIN companies c ON pl.company_id = c.id
            LEFT JOIN scraped_pages sp ON sp.url = pl.source_url AND sp.company_id = pl.company_id
            LEFT JOIN extracted_contacts ec ON ec.scraped_page_id = sp.id
            LEFT JOIN filtered_links fl ON fl.url = pl.source_url AND fl.company_id = pl.company_id
            LEFT JOIN search_results sr ON sr.id = fl.search_result_id
            LEFT JOIN gemini_quick_results gqr ON gqr.company_id = pl.company_id AND pl.step LIKE '%gemini_quick%'
        """
        params = ()
        if company_id:
            query += " WHERE pl.company_id = ?"
            params = (company_id,)
        query += " ORDER BY pl.started_at ASC"

        rows = db.fetch_all(query, params)
        if not rows:
            return JSONResponse({"error": "No logs found"}, status_code=404)

        fieldnames = list(rows[0].keys())

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=pipeline_logs_{today}.csv"}
        )

    elif format == "markdown":
        # Build markdown summary
        total = db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]
        done = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='done'")["cnt"]
        failed = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status IN ('failed','permanently_failed')")["cnt"]
        phone_count = db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE phone IS NOT NULL AND phone != ''")["cnt"]

        # Gemini stats
        gemini_suff = db.fetch_one("SELECT COUNT(*) as cnt FROM gemini_quick_results WHERE is_sufficient=1")["cnt"]

        # Quota
        quota = db.fetch_one("SELECT gemini_grounding_used, serper_used FROM daily_quota WHERE date = ?", (today,))
        gemini_calls = quota["gemini_grounding_used"] if quota else 0
        serper_calls = quota["serper_used"] if quota else 0

        # Tokens
        tokens = db.fetch_one("SELECT SUM(input_tokens) as tin, SUM(output_tokens) as tout FROM gemini_quick_results")
        tin = tokens["tin"] or 0 if tokens else 0
        tout = tokens["tout"] or 0 if tokens else 0

        # Top errors
        errors = db.fetch_all(
            "SELECT error_message, COUNT(*) as count FROM pipeline_logs WHERE error_message IS NOT NULL AND error_message != '' AND status='failed' GROUP BY error_message ORDER BY count DESC LIMIT 5"
        )

        md = f"""# Pipeline Report — {today}

## Tổng quan
| Metric | Value |
|--------|-------|
| Tổng công ty | {total} |
| Hoàn tất | {done} |
| Thất bại | {failed} |
| Có phone | {phone_count} ({round(phone_count/max(done,1)*100,1)}%) |

## Chi tiết theo bước
| Bước | Thành công |
|------|------------|
| Gemini Quick (đủ dữ liệu) | {gemini_suff} |
| Google Maps | — |
| Deep Search | — |

## API Usage
| Resource | Used |
|----------|------|
| Gemini Grounding calls | {gemini_calls} |
| Serper credits | {serper_calls} |
| Gemini tokens (input) | {tin:,} |
| Gemini tokens (output) | {tout:,} |
| Gemini tokens (total) | {tin+tout:,} |

## Lỗi thường gặp
"""
        for err in errors:
            md += f"- `{err['error_message'][:80]}` — {err['count']} lần\n"

        if not errors:
            md += "- Không có lỗi.\n"

        return Response(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=pipeline_report_{today}.md"}
        )

    return JSONResponse({"error": "Invalid format. Use: jsonl, csv, markdown"}, status_code=400)


@app.get("/api/export/final-excel")
def api_export_final_excel():
    from src.excel_handler import ExcelWriter
    from fastapi.responses import FileResponse
    import tempfile
    import logging
    
    local_logger = logging.getLogger("dashboard")
    
    db = _db()
    today = _today_str()
    
    # Create a temporary file path
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"final_results_{today}.xlsx")
    
    try:
        writer = ExcelWriter()
        writer.write_consolidated_report(db, output_path)
        
        return FileResponse(
            path=output_path,
            filename=f"final_results_{today}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        local_logger.error(f"Failed to export final excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export Excel report: {str(e)}")


# ---------------------------------------------------------------------------
# WebSocket: Live Logs
# ---------------------------------------------------------------------------
@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)

    today = _today_str()
    log_file = os.path.join(LOG_DIR, f"pipeline_{today}.jsonl")

    try:
        # Tail the log file
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                # Send last 20 lines as initial context
                lines = f.readlines()
                for line in lines[-20:]:
                    await websocket.send_text(line.strip())

                # Then tail for new lines
                f.seek(0, 2)  # Seek to end
                while True:
                    line = f.readline()
                    if line:
                        await websocket.send_text(line.strip())
                    else:
                        await asyncio.sleep(1)
                        # Check for date rollover
                        new_today = _today_str()
                        if new_today != today:
                            break
        else:
            # Wait for file to be created
            while True:
                await asyncio.sleep(2)
                if os.path.exists(log_file):
                    break
                await websocket.send_text(json.dumps({"event_type": "waiting", "message": "Waiting for log file..."}))

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)
