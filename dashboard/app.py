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
import subprocess
import base64
import sqlite3
import time
import signal
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import set_key, load_dotenv

# Ensure project root on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.database import DatabaseManager
from src.company_matcher import (
    evidence_json,
    normalize_tax_code,
    resolve_company_match,
)
from src.completion_audit import audit_company_completion
from src.logger import PipelineLogger
from src.config import Config
from src.time_utils import parse_timestamp_as_vn, vn_date_str, vn_now, vn_timestamp

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

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
_WORKER_AUTO_START = os.getenv("PIPELINE_WORKER_AUTO_START", "true").strip().lower() not in {"0", "false", "no"}
_WORKER_HEARTBEAT_SECONDS = 45
# Completion/checkpoint filters have no SQL-side column, so they audit each row in
# Python. Bound how many rows we scan per request so the endpoint can't fan out to
# tens of thousands of audit queries on the full table; the response flags when the
# scan was truncated. (A persisted completion_status column is the real follow-up.)
_COMPLETION_FILTER_SCAN_CAP = 3000
_monitor_removed_ids: set[int] = set()
_monitor_stopped_ids: set[int] = set()
monitor_clients: list[WebSocket] = []
_monitor_loop: asyncio.AbstractEventLoop | None = None
_dashboard_cache: dict[str, tuple[float, object]] = {}
_DASHBOARD_CACHE_SECONDS = 10
_SLOW_QUERY_SECONDS = 0.5


DatabaseManager(DB_PATH).init_db()


def _spa_response() -> HTMLResponse:
    with open(SPA_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


def _db() -> DatabaseManager:
    return DatabaseManager(DB_PATH)


def _cache_get(key: str):
    entry = _dashboard_cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if expires_at < time.monotonic():
        _dashboard_cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value, ttl: int = _DASHBOARD_CACHE_SECONDS):
    _dashboard_cache[key] = (time.monotonic() + ttl, value)
    return value


def _invalidate_dashboard_cache():
    _dashboard_cache.clear()


def _slow_log(name: str, started_at: float):
    elapsed = time.monotonic() - started_at
    if elapsed >= _SLOW_QUERY_SECONDS:
        print(f"[dashboard:slow] {name} took {elapsed:.3f}s")


def _recent_worker_cutoff() -> str:
    return vn_timestamp(vn_now() - timedelta(seconds=_WORKER_HEARTBEAT_SECONDS))


def _normalize_path(path: str | None) -> str:
    if not path:
        return ""
    return os.path.abspath(os.path.realpath(path))


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return key
    return f"{key[:4]}...{key[-4:]}"


def _read_proc_environ(pid: int) -> dict[str, str]:
    try:
        with open(f"/proc/{pid}/environ", "rb") as handle:
            chunks = handle.read().split(b"\0")
    except OSError:
        return {}
    env: dict[str, str] = {}
    for item in chunks:
        if b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        env[key.decode("utf-8", errors="ignore")] = value.decode("utf-8", errors="ignore")
    return env


def _read_proc_cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return [part.decode("utf-8", errors="ignore") for part in handle.read().split(b"\0") if part]
    except OSError:
        return []


def _worker_script_path() -> str:
    return _normalize_path(os.path.join(_PROJECT_ROOT, "scripts", "pipeline_worker.py"))


def _worker_python_executable() -> str:
    venv_python = os.path.join(_PROJECT_ROOT, "venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def _iter_runtime_worker_processes(db_path: str | None = None) -> list[dict]:
    target_db_path = _normalize_path(db_path or DB_PATH)
    script_path = _worker_script_path()
    results: list[dict] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        cmdline = _read_proc_cmdline(pid)
        if not cmdline:
            continue
        normalized_cmd = [_normalize_path(part) if part.endswith(".py") or "/" in part else part for part in cmdline]
        if script_path not in normalized_cmd:
            continue
        worker_db_path = ""
        if "--db" in cmdline:
            try:
                worker_db_path = _normalize_path(cmdline[cmdline.index("--db") + 1])
            except (IndexError, ValueError):
                worker_db_path = ""
        if worker_db_path != target_db_path:
            continue
        environ = _read_proc_environ(pid)
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            cwd = ""
        results.append({
            "pid": pid,
            "cmdline": " ".join(cmdline),
            "cwd": cwd,
            "db_path": worker_db_path,
            "firecrawl_key_mask": _mask_key(environ.get("FIRECRAWL_API_KEY", "")),
        })
    return sorted(results, key=lambda item: item["pid"])


def _current_firecrawl_key_mask() -> str:
    return _mask_key(os.getenv("FIRECRAWL_API_KEY", ""))


def _worker_status(db: DatabaseManager) -> dict:
    workers = db.get_recent_pipeline_workers(_recent_worker_cutoff())
    runtime_processes = _iter_runtime_worker_processes()
    current_key_mask = _current_firecrawl_key_mask()
    runtime_by_pid = {proc["pid"]: proc for proc in runtime_processes}
    enriched_workers = []
    for worker in workers:
        pid = None
        worker_id = str(worker.get("worker_id") or "")
        parts = worker_id.split("-")
        if len(parts) >= 3 and parts[-2].isdigit():
            pid = int(parts[-2])
        runtime = runtime_by_pid.get(pid) if pid else None
        enriched_workers.append({
            **worker,
            "pid": pid,
            "firecrawl_key_mask": runtime.get("firecrawl_key_mask", "") if runtime else "",
            "env_mismatch": bool(runtime and runtime.get("firecrawl_key_mask") and runtime.get("firecrawl_key_mask") != current_key_mask),
            "runtime_present": bool(runtime),
        })
    return {
        "online": bool(workers),
        "workers": enriched_workers,
        "runtime_processes": runtime_processes,
        "current_firecrawl_key_mask": current_key_mask,
        "message": None if workers else "Worker offline: queued jobs will not run until scripts/pipeline_worker.py is started.",
    }


# Serializes worker spawning within this process so two concurrent requests can't
# both decide to start a worker.
_WORKER_SPAWN_LOCK = threading.Lock()


def _reap_extra_workers(processes: list[dict]) -> list[int]:
    """Keep the lowest-PID worker for this DB and terminate the rest.

    `processes` is expected to come from _iter_runtime_worker_processes (sorted by
    pid ascending). Returns the PIDs that were signalled to stop.
    """
    if len(processes) <= 1:
        return []
    return _terminate_runtime_workers(processes[1:])


def _start_worker_process() -> dict:
    """Ensure exactly one worker runs for DB_PATH; spawn only if none is alive.

    A worker busy on a long scrape can miss its DB heartbeat window and look
    "offline", but its process is still alive. Spawning again in that situation is
    what caused worker processes to pile up. So we check /proc first and only spawn
    when nothing is running, reaping any duplicates we find.
    """
    script_path = os.path.join(_PROJECT_ROOT, "scripts", "pipeline_worker.py")
    os.makedirs(LOG_DIR, exist_ok=True)
    with _WORKER_SPAWN_LOCK:
        existing = _iter_runtime_worker_processes(DB_PATH)
        if existing:
            reaped = _reap_extra_workers(existing)
            message = "Worker already running; reused existing process."
            if reaped:
                message += f" Reaped {len(reaped)} duplicate worker(s)."
            return {"pid": existing[0]["pid"], "message": message, "reused": True, "reaped": reaped}
        log_handle = open(os.path.join(LOG_DIR, "pipeline_worker.log"), "a", encoding="utf-8")
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                [_worker_python_executable(), "-u", script_path, "--db", DB_PATH, "--poll", "2"],
                cwd=_PROJECT_ROOT,
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,
                env=env,
            )
        finally:
            log_handle.close()
        return {
            "pid": process.pid,
            "message": "Worker was offline; dashboard started scripts/pipeline_worker.py.",
            "reused": False,
            "reaped": [],
        }


def _ensure_worker_started(db: DatabaseManager) -> dict:
    status = _worker_status(db)
    runtime_processes = _iter_runtime_worker_processes(DB_PATH)
    # Treat a live process as "online" even if the DB heartbeat is stale (long
    # scrapes lag the 45s window). Only auto-start when nothing is actually running.
    if status["online"] or runtime_processes or not _WORKER_AUTO_START:
        status["auto_started"] = False
        reaped = _reap_extra_workers(runtime_processes)
        if reaped:
            status["message"] = f"Reaped {len(reaped)} duplicate worker(s)."
        return status

    try:
        started = _start_worker_process()
        status["pid"] = started["pid"]
        status["auto_started"] = not started.get("reused", False)
        status["message"] = started["message"]
    except Exception as exc:
        status["auto_started"] = False
        status["message"] = f"Worker offline and auto-start failed: {exc}"
    return status


def _runtime_health_payload(db: DatabaseManager) -> dict:
    worker_status = _worker_status(db)
    current_key_mask = worker_status.get("current_firecrawl_key_mask", "")
    runtime_processes = worker_status.get("runtime_processes", [])
    db_workers = worker_status.get("workers", [])
    runtime_pids = {proc["pid"] for proc in runtime_processes}
    db_pids = {worker["pid"] for worker in db_workers if worker.get("pid")}
    return {
        "db_path": _normalize_path(DB_PATH),
        "current_firecrawl_key_mask": current_key_mask,
        "worker_online": worker_status.get("online", False),
        "message": worker_status.get("message"),
        "db_workers": db_workers,
        "runtime_processes": [
            {
                **proc,
                "env_mismatch": bool(proc.get("firecrawl_key_mask") and proc.get("firecrawl_key_mask") != current_key_mask),
                "orphaned": proc["pid"] not in db_pids,
            }
            for proc in runtime_processes
        ],
        "orphaned_db_workers": [worker for worker in db_workers if worker.get("pid") and worker["pid"] not in runtime_pids],
        "has_env_mismatch": any(worker.get("env_mismatch") for worker in db_workers) or any(proc.get("firecrawl_key_mask") and proc.get("firecrawl_key_mask") != current_key_mask for proc in runtime_processes),
    }


def _terminate_runtime_workers(processes: list[dict], sig: int = signal.SIGTERM) -> list[int]:
    stopped = []
    for process in processes:
        pid = process.get("pid")
        if not pid:
            continue
        try:
            os.kill(int(pid), sig)
            stopped.append(int(pid))
        except ProcessLookupError:
            continue
    return stopped


def _has_active_pipeline_jobs(db: DatabaseManager, company_ids: list[int] | None = None) -> bool:
    params: list[object] = []
    scope_sql = ""
    if company_ids:
        ids = [int(cid) for cid in dict.fromkeys(company_ids)]
        scope_sql = f" AND company_id IN ({','.join('?' for _ in ids)})"
        params.extend(ids)
    row = db.fetch_one(
        f"""
        SELECT COUNT(*) AS cnt
        FROM pipeline_jobs
        WHERE removed_from_monitor = 0
          AND status IN ('queued', 'running', 'stopping')
          {scope_sql}
        """,
        tuple(params),
    )
    return bool(row and row["cnt"])


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
    return vn_date_str()


def _now_iso():
    return vn_timestamp()


def _date_start(value: str | None) -> str | None:
    if not value:
        return None
    return f"{value[:10]} 00:00:00"


def _date_end(value: str | None) -> str | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value[:10], "%Y-%m-%d") + timedelta(days=1)
        return day.strftime("%Y-%m-%d 00:00:00")
    except ValueError:
        return value

def _valid_cutoff_time(value: str | None) -> str:
    value = str(value or "17:00").strip()
    try:
        datetime.strptime(value, "%H:%M")
        return value
    except ValueError:
        return "17:00"


def _report_window_bounds(report_window: str | None = None) -> tuple[str | None, str | None]:
    if report_window != "today":
        return None, None
    cutoff = _valid_cutoff_time(getattr(_cfg(), "REPORT_CUTOFF_TIME", "17:00"))
    hour, minute = [int(part) for part in cutoff.split(":")]
    now = vn_now()
    end = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    start = end - timedelta(days=1)
    return vn_timestamp(start), vn_timestamp(end)


def _apply_report_filters(
    filters: list[str],
    params: list[object],
    company_id_expr: str,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
):
    reported_clauses = [f"rc.company_id = {company_id_expr}"]
    reported_params: list[object] = []
    if reported_from:
        reported_clauses.append("rc.reported_at >= ?")
        reported_params.append(reported_from)
    if reported_to:
        reported_clauses.append("rc.reported_at < ?")
        reported_params.append(reported_to)
    exists_sql = f"EXISTS (SELECT 1 FROM reported_companies rc WHERE {' AND '.join(reported_clauses)})"

    if report_state == "reported":
        filters.append(exists_sql)
        params.extend(reported_params)
    elif report_state == "unreported":
        filters.append(f"NOT {exists_sql}")
        params.extend(reported_params)
    elif reported_from or reported_to:
        filters.append(exists_sql)
        params.extend(reported_params)


def _company_filter_sql(
    status: str = None,
    search: str = None,
    import_batch_id: int = None,
    created_from: str = None,
    created_to: str = None,
    completed_from: str = None,
    completed_to: str = None,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
) -> tuple[str, list[object]]:
    filters = []
    params: list[object] = []
    if status:
        filters.append("status = ?")
        params.append(status)
    if search:
        filters.append("LOWER(original_name) LIKE ?")
        params.append(f"%{search.lower()}%")
    if import_batch_id:
        filters.append("import_batch_id = ?")
        params.append(import_batch_id)
    if created_from:
        filters.append("created_at >= ?")
        params.append(_date_start(created_from))
    if created_to:
        filters.append("created_at < ?")
        params.append(_date_end(created_to))
    if completed_from:
        filters.append("completed_at >= ?")
        params.append(_date_start(completed_from))
    if completed_to:
        filters.append("completed_at < ?")
        params.append(_date_end(completed_to))
    _apply_report_filters(filters, params, "companies.id", report_state, reported_from, reported_to)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return where, params


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
    _invalidate_dashboard_cache()
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
        "running": sum(1 for j in jobs if j["status"] in _JOB_RUNNING_STATUSES and not j.get("stale")),
        "queued": sum(1 for j in jobs if j["status"] == "queued"),
        "failed": sum(1 for j in jobs if j["status"] == "failed"),
        "stopped": sum(1 for j in jobs if j["status"] == "stopped"),
        "stale": sum(1 for j in jobs if j.get("stale")),
    }


def _monitor_status_counts(db: DatabaseManager, stale_count: int = 0) -> dict:
    rows = db.fetch_all(
        """
        SELECT status, COUNT(*) as cnt
        FROM pipeline_jobs
        WHERE removed_from_monitor = 0
        GROUP BY status
        """
    )
    by_status = {r["status"]: r["cnt"] for r in rows}
    running_count = sum(by_status.get(status, 0) for status in _JOB_RUNNING_STATUSES)
    return {
        "running": max(0, running_count - stale_count),
        "queued": by_status.get("queued", 0),
        "failed": by_status.get("failed", 0),
        "stopped": by_status.get("stopped", 0),
        "stale": stale_count,
    }


def _light_job_payload(row: dict, *, stale: bool = False) -> dict:
    payload = {
        "id": row["id"],
        "name": row.get("name"),
        "status": row.get("status"),
        "step": row.get("step"),
        "checkpoint": row.get("checkpoint"),
        "progress": row.get("progress"),
        "started": row.get("started"),
        "updated_at": row.get("updated_at"),
        "finished_at": row.get("finished_at"),
        "error_message": row.get("error_message"),
        "stale": stale,
    }
    if not stale:
        payload.update({
            "suggested_status": None,
            "stale_reason": None,
            "data_counts": None,
        })
    return payload


def _pipeline_job_rows(db: DatabaseManager, statuses: tuple[str, ...], limit: int | None = None) -> list[dict]:
    placeholders = ",".join("?" * len(statuses))
    limit_sql = "LIMIT ?" if limit else ""
    params: list[object] = list(statuses)
    if limit:
        params.append(limit)
    return db.fetch_all(
        f"""
        SELECT company_id as id, company_name as name, status, current_step as step,
               checkpoint, progress, started_at as started, updated_at, finished_at,
               error_message
        FROM pipeline_jobs
        WHERE removed_from_monitor = 0
          AND status IN ({placeholders})
        ORDER BY updated_at DESC, company_id
        {limit_sql}
        """,
        tuple(params),
    )


def _stale_jobs(db: DatabaseManager, threshold_minutes: int | None = None) -> list[dict]:
    threshold_minutes = threshold_minutes or _STALE_THRESHOLD_MINUTES
    rows = db.fetch_all(
        """
        SELECT c.*
        FROM companies c
        LEFT JOIN pipeline_jobs j ON j.company_id = c.id
        WHERE c.status IN ('gemini_quick','searching','scraping','extracting')
          AND COALESCE(j.removed_from_monitor, 0) = 0
        ORDER BY COALESCE(j.updated_at, c.updated_at) ASC, c.id
        """
    )
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    jobs_by_id = {
        row["company_id"]: row
        for row in db.fetch_all(
            f"SELECT * FROM pipeline_jobs WHERE company_id IN ({placeholders})",
            tuple(ids),
        )
    }
    stale = []
    for company in rows:
        job = jobs_by_id.get(company["id"])
        if not _is_stale_running_job(company, job, threshold_minutes=threshold_minutes):
            continue
        payload = _stale_job_payload(db, company, job)
        payload["stale"] = True
        payload["stale_reason"] = payload.pop("reason", None)
        stale.append(payload)
    return stale


def _monitor_snapshot(db: DatabaseManager) -> dict:
    started_at = time.monotonic()
    stale = _stale_jobs(db)
    stale_ids = {row["id"] for row in stale}
    running_rows = [
        _light_job_payload(row)
        for row in _pipeline_job_rows(db, tuple(_JOB_RUNNING_STATUSES), limit=100)
        if row["id"] not in stale_ids
    ]
    queued_rows = [_light_job_payload(row) for row in _pipeline_job_rows(db, ("queued", "pending"), limit=200)]
    failed_rows = [_light_job_payload(row) for row in _pipeline_job_rows(db, ("failed", "stopped"), limit=50)]
    jobs = stale + running_rows + queued_rows + failed_rows
    counts = _monitor_status_counts(db, stale_count=len(stale))
    worker_status = _worker_status(db)
    _slow_log("monitor_snapshot", started_at)
    return {"jobs": jobs, "counts": counts, "worker": worker_status}


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
_JOB_RUNNING_STATUSES = {"running", "stopping"}
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
_STALE_THRESHOLD_MINUTES = 15
_RESET_TARGET_STATUSES = {
    "pending", "failed", "gemini_quick_done", "searched",
    "ai_extract_pending", "ai_done",
}


def _counts(db: DatabaseManager) -> dict:
    cached = _cache_get("company_counts")
    if cached is not None:
        return cached
    started_at = time.monotonic()
    rows = db.fetch_all("SELECT status, COUNT(*) as cnt FROM companies GROUP BY status")
    by_status = {r["status"]: r["cnt"] for r in rows}
    total = sum(by_status.values())
    counts = {
        "total": total,
        "done": by_status.get("done", 0),
        "failed": by_status.get("failed", 0) + by_status.get("permanently_failed", 0),
        "pending": by_status.get("pending", 0),
        "running": sum(by_status.get(status, 0) for status in _RUNNING_STATUSES),
        "by_status": by_status,
    }
    _slow_log("company_counts", started_at)
    return _cache_set("company_counts", counts)


def _parse_dt(value: str | None) -> datetime | None:
    return parse_timestamp_as_vn(value)


def _company_data_counts(db: DatabaseManager, company_id: int) -> dict:
    row = db.fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM gemini_quick_results WHERE company_id = ?) AS gemini_results,
            (SELECT COUNT(*) FROM search_results WHERE company_id = ?) AS search_results,
            (SELECT COUNT(*) FROM filtered_links WHERE company_id = ?) AS filtered_links,
            (SELECT COUNT(*) FROM filtered_links WHERE company_id = ? AND should_scrape = 1) AS scrape_candidates,
            (SELECT COUNT(*) FROM scraped_pages WHERE company_id = ?) AS scraped_pages,
            (SELECT COUNT(*) FROM scraped_pages WHERE company_id = ? AND scrape_status = 'success') AS scraped_success,
            (SELECT COUNT(*) FROM extracted_contacts WHERE company_id = ?) AS contacts,
            (SELECT COUNT(*) FROM extracted_contacts WHERE company_id = ? AND address IS NOT NULL AND TRIM(address) != '') AS contact_addresses
        """,
        (company_id, company_id, company_id, company_id, company_id, company_id, company_id, company_id),
    )
    return row or {
        "gemini_results": 0,
        "search_results": 0,
        "filtered_links": 0,
        "scrape_candidates": 0,
        "scraped_pages": 0,
        "scraped_success": 0,
        "contacts": 0,
        "contact_addresses": 0,
    }


def _suggest_resume_status(company: dict, counts: dict) -> tuple[str, str]:
    status = company.get("status")
    if status == "extracting" or counts.get("contacts", 0) > 0:
        return "ai_extract_pending", "has_extracted_contacts_or_extracting"
    if counts.get("scraped_success", 0) > 0:
        if status == "scraping" and counts.get("filtered_links", 0) > counts.get("scraped_success", 0):
            return "searched", "partial_scrape_can_resume_without_deep_search"
        return "ai_extract_pending", "has_successful_scraped_pages"
    if counts.get("scraped_pages", 0) > 0 and counts.get("filtered_links", 0) > 0:
        return "searched", "partial_scraped_pages_with_filtered_links"
    if counts.get("filtered_links", 0) > 0:
        return "searched", "has_filtered_links"
    if counts.get("search_results", 0) > 0:
        return "searched", "has_search_results"
    if counts.get("gemini_results", 0) > 0:
        return "gemini_quick_done", "has_gemini_quick_results"
    return "pending", "no_intermediate_data"


def _is_stale_running_job(company: dict, job: dict | None, threshold_minutes: int = _STALE_THRESHOLD_MINUTES) -> bool:
    if company.get("status") not in _RUNNING_STATUSES:
        return False
    timestamp = _parse_dt((job or {}).get("updated_at") or company.get("updated_at"))
    if not timestamp:
        return True
    age = vn_now() - timestamp
    return age.total_seconds() >= threshold_minutes * 60


def _stale_job_payload(db: DatabaseManager, company: dict, job: dict | None = None) -> dict:
    counts = _company_data_counts(db, company["id"])
    suggested_status, reason = _suggest_resume_status(company, counts)
    step, checkpoint, progress = _company_step(company.get("status"))
    stale = _is_stale_running_job(company, job)
    return {
        "id": company["id"],
        "name": company.get("original_name"),
        "status": company.get("status"),
        "step": (job or {}).get("current_step") or step,
        "checkpoint": (job or {}).get("checkpoint") or checkpoint,
        "progress": (job or {}).get("progress") or progress,
        "updated_at": (job or {}).get("updated_at") or company.get("updated_at"),
        "stale": stale,
        "suggested_status": suggested_status,
        "reason": reason,
        "data_counts": counts,
    }


def _reset_company_status(db: DatabaseManager, company_id: int, mode: str, target_status: str | None = None) -> dict:
    company = db.get_company(company_id)
    if not company:
        return {"id": company_id, "status": "skipped", "reason": "not_found"}
    counts = _company_data_counts(db, company_id)
    suggested_status, reason = _suggest_resume_status(company, counts)
    old_status = company.get("status")

    if mode == "smart_resume":
        new_status = suggested_status
    elif mode == "to_pending":
        new_status = "pending"
        reason = "manual_to_pending"
    elif mode == "mark_failed":
        new_status = "failed"
        reason = "manual_mark_failed"
    elif mode == "to_status":
        new_status = target_status or ""
        reason = "manual_to_status"
        if new_status not in _RESET_TARGET_STATUSES:
            return {"id": company_id, "status": "skipped", "reason": "invalid_target_status"}
    else:
        return {"id": company_id, "status": "skipped", "reason": "invalid_mode"}

    db.update_company(company_id, status=new_status)
    metadata = {
        "old_status": old_status,
        "new_status": new_status,
        "reset_mode": mode,
        "reason": reason,
        "data_counts": counts,
        "reset_at": _now_iso(),
    }
    db.execute_query(
        """
        INSERT INTO pipeline_logs (
            company_id, step, status, started_at, finished_at, source_name,
            data_saved, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            "status_reset",
            "SUCCESS",
            vn_timestamp(),
            vn_timestamp(),
            mode,
            True,
            json.dumps(metadata, ensure_ascii=False),
        ),
    )
    job = _upsert_job(db, company_id, new_status, checkpoint=reason)
    _emit_job_update(db, job, "status_reset")
    return {
        "id": company_id,
        "status": "reset",
        "old_status": old_status,
        "new_status": new_status,
        "reason": reason,
        "data_counts": counts,
    }


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


def _scraped_url_rows(db: DatabaseManager, company_id: int) -> list[dict]:
    return db.fetch_all(
        """
        SELECT latest.id, latest.url, latest.source_type, latest.content_length,
               latest.scrape_status, latest.credits_used, latest.error_message,
               latest.created_at, counts.attempt_count
        FROM scraped_pages latest
        INNER JOIN (
            SELECT url, MAX(id) AS latest_id, COUNT(*) AS attempt_count
            FROM scraped_pages
            WHERE company_id = ?
            GROUP BY url
        ) counts ON counts.latest_id = latest.id
        WHERE latest.company_id = ?
        ORDER BY latest.id
        """,
        (company_id, company_id),
    )


def _company_step(status: str) -> tuple[str, str, int]:
    return _STEP_BY_STATUS.get(status or "pending", ("Unknown", status or "pending", 0))


_IMPORT_OUTCOME_LABELS = {
    "imported": "Imported",
    "matched_by_tax_code": "Matched by MST",
    "matched_by_score": "Matched by score",
    "ambiguous": "Cần kiểm tra",
    "no_match": "No match",
    "duplicate_existing": "Đã có trong DB",
    "duplicate_in_file": "Trùng trong file",
    "invalid": "Invalid",
}


def _import_record(raw) -> dict:
    if isinstance(raw, dict):
        name = raw.get("name") or raw.get("company_name") or raw.get("original_name") or ""
        return {
            "name": str(name or ""),
            "tax_code": normalize_tax_code(raw.get("tax_code") or raw.get("mst")),
            "address": str(raw.get("address") or ""),
            "province": str(raw.get("province") or ""),
            "website": str(raw.get("website") or ""),
            "email": str(raw.get("email") or ""),
            "phone": str(raw.get("phone") or ""),
        }
    return {
        "name": str(raw or ""),
        "tax_code": "",
        "address": "",
        "province": "",
        "website": "",
        "email": "",
        "phone": "",
    }


def _company_contact_flags(db: DatabaseManager, ids: list[int]) -> dict[int, dict]:
    ids = [int(cid) for cid in ids if cid]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = db.fetch_all(
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
    return {r["company_id"]: r for r in rows}


def _latest_steps(db: DatabaseManager, ids: list[int]) -> dict[int, str]:
    ids = [int(cid) for cid in ids if cid]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = db.fetch_all(
        f"""
        SELECT company_id, step
        FROM pipeline_logs
        WHERE id IN (
            SELECT MAX(id) FROM pipeline_logs WHERE company_id IN ({placeholders}) GROUP BY company_id
        )
        """,
        tuple(ids),
    )
    return {r["company_id"]: r["step"] for r in rows}


def _completion_matches(audit: dict, completion: str | None) -> bool:
    if not completion:
        return True
    return audit.get("completion_status") == completion


def _effective_checkpoint(row: dict, audit: dict) -> str:
    pipeline_status = row.get("pipeline_status") or row.get("status") or "pending"
    _, fallback_checkpoint, _ = _company_step(pipeline_status)
    audit_checkpoint = str(audit.get("checkpoint") or "").strip()
    if pipeline_status in {"done", "ai_done"}:
        return audit_checkpoint or fallback_checkpoint or ""
    return fallback_checkpoint or audit_checkpoint or ""


def _effective_current_step(row: dict, audit: dict) -> str:
    pipeline_status = row.get("pipeline_status") or row.get("status") or "pending"
    fallback_step, _, _ = _company_step(pipeline_status)
    audit_step = str(audit.get("current_step") or "").strip()
    if pipeline_status in {"done", "ai_done"}:
        return audit_step or fallback_step or ""
    return fallback_step or audit_step or ""


def _checkpoint_matches(row: dict, audit: dict, checkpoint: str | None) -> bool:
    if not checkpoint:
        return True
    return _effective_checkpoint(row, audit) == checkpoint


def _audit_map(db: DatabaseManager, rows: list[dict], id_key: str = "id") -> dict[int, dict]:
    audits = {}
    for row in rows:
        company_id = row.get(id_key)
        if not company_id:
            continue
        audits[int(company_id)] = audit_company_completion(db, int(company_id), row)
    return audits


def _company_stale_fields(db: DatabaseManager, rows: list[dict]) -> dict[int, dict]:
    ids = [int(r["id"]) for r in rows if r.get("id") and r.get("status") in _RUNNING_STATUSES]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    jobs_by_id = {
        row["company_id"]: row
        for row in db.fetch_all(
            f"SELECT * FROM pipeline_jobs WHERE company_id IN ({placeholders})",
            tuple(ids),
        )
    }
    result = {}
    for row in rows:
        company_id = row.get("id")
        if not company_id or row.get("status") not in _RUNNING_STATUSES:
            continue
        job = jobs_by_id.get(company_id)
        is_stale = _is_stale_running_job(row, job)
        suggested_status = None
        stale_reason = None
        if is_stale:
            counts = _company_data_counts(db, company_id)
            suggested_status, stale_reason = _suggest_resume_status(row, counts)
        result[company_id] = {
            "is_stale": is_stale,
            "suggested_status": suggested_status,
            "stale_reason": stale_reason,
            "can_reset_resume": is_stale,
        }
    return result


def _import_item_filter_sql(
    search: str = None,
    import_outcome: str = None,
    pipeline_status: str = None,
    created_from: str = None,
    created_to: str = None,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
) -> tuple[str, list[object]]:
    filters = ["i.batch_id = ?"]
    params: list[object] = []
    if import_outcome:
        filters.append("i.outcome = ?")
        params.append(import_outcome)
    if pipeline_status:
        filters.append("c.status = ?")
        params.append(pipeline_status)
    if search:
        like = f"%{search.lower()}%"
        filters.append("(LOWER(i.input_name) LIKE ? OR LOWER(i.canonical_name) LIKE ? OR LOWER(c.original_name) LIKE ?)")
        params.extend([like, like, like])
    if created_from:
        filters.append("i.created_at >= ?")
        params.append(_date_start(created_from))
    if created_to:
        filters.append("i.created_at < ?")
        params.append(_date_end(created_to))
    _apply_report_filters(filters, params, "c.id", report_state, reported_from, reported_to)
    return f"WHERE {' AND '.join(filters)}", params


def _import_batch_items_payload(
    db: DatabaseManager,
    batch_id: int,
    search: str = None,
    import_outcome: str = None,
    completion: str = None,
    checkpoint: str = None,
    pipeline_status: str = None,
    created_from: str = None,
    created_to: str = None,
    page: int = 1,
    page_size: int = 50,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
) -> dict:
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    where, params_without_batch = _import_item_filter_sql(
        search, import_outcome, pipeline_status, created_from, created_to,
        report_state=report_state, reported_from=reported_from, reported_to=reported_to,
    )
    params = [batch_id] + params_without_batch
    if not completion and not checkpoint:
        total_row = db.fetch_one(
            f"""
            SELECT COUNT(*) AS cnt
            FROM company_import_items i
            LEFT JOIN companies c ON c.id = COALESCE(i.company_id, i.matched_company_id)
            {where}
            """,
            tuple(params),
        ) or {}
        total = int(total_row.get("cnt", 0) or 0)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = db.fetch_all(
            f"""
            SELECT i.id as import_item_id, i.row_number, i.input_name, i.canonical_name,
                   i.normalized_key, i.outcome, i.company_id, i.matched_company_id, i.reason,
                   i.match_score, i.match_method, i.evidence_json, i.created_at as import_item_created_at,
                   c.id as resolved_company_id, c.original_name, c.vietnamese_name, c.tax_code,
                   c.status as pipeline_status, c.updated_at, c.created_at, c.import_batch_id, c.completed_at
            FROM company_import_items i
            LEFT JOIN companies c ON c.id = COALESCE(i.company_id, i.matched_company_id)
            {where}
            ORDER BY i.row_number, i.id
            LIMIT ? OFFSET ?
            """,
            tuple([*params, page_size, offset]),
        )
        audit_by_id = _audit_map(db, rows, id_key="resolved_company_id")
    else:
        rows = db.fetch_all(
            f"""
            SELECT i.id as import_item_id, i.row_number, i.input_name, i.canonical_name,
                   i.normalized_key, i.outcome, i.company_id, i.matched_company_id, i.reason,
                   i.match_score, i.match_method, i.evidence_json, i.created_at as import_item_created_at,
                   c.id as resolved_company_id, c.original_name, c.vietnamese_name, c.tax_code,
                   c.status as pipeline_status, c.updated_at, c.created_at, c.import_batch_id, c.completed_at
            FROM company_import_items i
            LEFT JOIN companies c ON c.id = COALESCE(i.company_id, i.matched_company_id)
            {where}
            ORDER BY i.row_number, i.id
            """,
            tuple(params),
        )
        audit_by_id = _audit_map(db, rows, id_key="resolved_company_id")
        rows = [
            row for row in rows
            if row.get("resolved_company_id")
            and _completion_matches(audit_by_id.get(int(row["resolved_company_id"]), {}), completion)
            and _checkpoint_matches(row, audit_by_id.get(int(row["resolved_company_id"]), {}), checkpoint)
        ]
        total = len(rows)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = rows[offset:offset + page_size]
    company_ids = [r["resolved_company_id"] for r in rows if r.get("resolved_company_id")]
    contacts = _company_contact_flags(db, company_ids)
    reported_by_id = db.get_reported_status_for_companies(company_ids)
    stale_input = [
        {
            "id": r["resolved_company_id"],
            "status": r.get("pipeline_status"),
            "updated_at": r.get("updated_at"),
            "original_name": r.get("original_name"),
        }
        for r in rows
        if r.get("resolved_company_id")
    ]
    stale_fields = _company_stale_fields(db, stale_input)
    items = []
    for row in rows:
        company_id = row.get("resolved_company_id")
        pipeline_status = row.get("pipeline_status") or "not_created"
        step, checkpoint, _ = _company_step(pipeline_status)
        contact = contacts.get(company_id, {}) if company_id else {}
        display_status = _IMPORT_OUTCOME_LABELS.get(row["outcome"], row["outcome"])
        audit = audit_by_id.get(int(company_id), {}) if company_id else {}
        row_stale_fields = stale_fields.get(company_id, {
            "is_stale": False,
            "suggested_status": None,
            "stale_reason": None,
            "can_reset_resume": False,
        })
        reported = reported_by_id.get(int(company_id), {}) if company_id else {}
        items.append({
            **row,
            "id": company_id,
            "name": row.get("original_name") or row.get("canonical_name") or row.get("input_name"),
            "status": display_status,
            "display_status": display_status,
            "pipeline_status": pipeline_status,
            "has_phone": bool(contact.get("has_phone")),
            "has_email": bool(contact.get("has_email")),
            "checkpoint": _effective_checkpoint(row, audit),
            "current_step": _effective_current_step(row, audit),
            "last_activity_step": audit.get("last_activity_step"),
            "completion_status": audit.get("completion_status"),
            "completion_reason": audit.get("completion_reason"),
            "resume_status": audit.get("resume_status"),
            "can_resume_incomplete": bool(company_id and audit.get("completion_status") == "incomplete"),
            "is_reported": bool(reported),
            "reported_at": reported.get("reported_at"),
            "report_run_id": reported.get("report_run_id"),
            "is_import_item": True,
            **row_stale_fields,
        })
    counts = db.get_import_item_counts(batch_id)
    return {
        "companies": items,
        "items": items,
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
        "import_summary": {
            "imported": counts.get("imported", 0),
            "matched_by_tax_code": counts.get("matched_by_tax_code", 0),
            "matched_by_score": counts.get("matched_by_score", 0),
            "ambiguous": counts.get("ambiguous", 0),
            "no_match": counts.get("no_match", 0),
            "duplicate_existing": counts.get("duplicate_existing", 0),
            "duplicate_in_file": counts.get("duplicate_in_file", 0),
            "invalid": counts.get("invalid", 0),
            "total_items": sum(counts.values()),
        },
        "counts": _counts(db),
    }


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
    quota = db.fetch_one("SELECT gemini_grounding_used FROM daily_quota WHERE date = ?", (today,))
    tokens = db.fetch_one(
        "SELECT SUM(input_tokens) as tin, SUM(output_tokens) as tout FROM gemini_quick_results WHERE created_at LIKE ?",
        (f"{today}%",),
    )
    fc_scrape = db.fetch_one("SELECT SUM(credits_used) as total FROM scraped_pages WHERE created_at LIKE ?", (f"{today}%",))
    fc_search = db.fetch_one("SELECT SUM(credits_used) as total FROM search_results WHERE search_type LIKE '%firecrawl%' AND created_at LIKE ?", (f"{today}%",))
    firecrawl_used = (fc_scrape["total"] or 0) + (fc_search["total"] or 0)
    
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
            "firecrawl_used": firecrawl_used,
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
def api_spa_companies(
    status: str = None,
    search: str = None,
    import_batch_id: int = None,
    import_outcome: str = None,
    completion: str = None,
    checkpoint: str = None,
    created_from: str = None,
    created_to: str = None,
    completed_from: str = None,
    completed_to: str = None,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
    report_window: str = None,
    page: int = 1,
    page_size: int = 50,
):
    db = _db()
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    window_start, window_end = _report_window_bounds(report_window)
    reported_from = reported_from or window_start
    reported_to = reported_to or window_end

    if import_batch_id and db.has_import_items(import_batch_id):
        payload = _import_batch_items_payload(
            db,
            import_batch_id,
            search=search,
            import_outcome=import_outcome,
            completion=completion,
            checkpoint=checkpoint,
            pipeline_status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
            report_state=report_state,
            reported_from=reported_from,
            reported_to=reported_to,
        )
        return JSONResponse(payload)

    where, params = _company_filter_sql(
        status=status,
        search=search,
        import_batch_id=import_batch_id,
        created_from=created_from,
        created_to=created_to,
        completed_from=completed_from,
        completed_to=completed_to,
        report_state=report_state,
        reported_from=reported_from,
        reported_to=reported_to,
    )
    scan_truncated = False
    if not completion and not checkpoint:
        total_row = db.fetch_one(
            f"SELECT COUNT(*) AS cnt FROM companies {where}",
            tuple(params),
        ) or {}
        total = int(total_row.get("cnt", 0) or 0)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = db.fetch_all(
            f"""
            SELECT id, original_name, original_name_key, vietnamese_name, tax_code, status, updated_at, created_at,
                   import_batch_id, completed_at
            FROM companies
            {where}
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            tuple([*params, page_size, offset]),
        )
        # Audit only the page we return (not the whole table).
        audit_by_id = _audit_map(db, rows)
    else:
        # Completion/checkpoint filters must audit rows in Python; bound the scan so
        # a filter over the full table can't trigger tens of thousands of queries.
        rows = db.fetch_all(
            f"""
            SELECT id, original_name, original_name_key, vietnamese_name, tax_code, status, updated_at, created_at,
                   import_batch_id, completed_at
            FROM companies
            {where}
            ORDER BY id
            LIMIT ?
            """,
            tuple([*params, _COMPLETION_FILTER_SCAN_CAP + 1]),
        )
        scan_truncated = len(rows) > _COMPLETION_FILTER_SCAN_CAP
        if scan_truncated:
            rows = rows[:_COMPLETION_FILTER_SCAN_CAP]

        audit_by_id = _audit_map(db, rows)
        rows = [
            row for row in rows
            if _completion_matches(audit_by_id.get(int(row["id"]), {}), completion)
            and _checkpoint_matches(row, audit_by_id.get(int(row["id"]), {}), checkpoint)
        ]
        total = len(rows)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = rows[offset:offset + page_size]

    ids = [r["id"] for r in rows]
    contact_by_id = _company_contact_flags(db, ids)
    reported_by_id = db.get_reported_status_for_companies(ids)
    stale_by_id = _company_stale_fields(db, rows)

    companies = []
    for row in rows:
        contact = contact_by_id.get(row["id"], {})
        step, checkpoint, _ = _company_step(row["status"])
        audit = audit_by_id.get(int(row["id"]), {})
        stale_fields = stale_by_id.get(row["id"], {
            "is_stale": False,
            "suggested_status": None,
            "stale_reason": None,
            "can_reset_resume": False,
        })
        reported = reported_by_id.get(int(row["id"]), {})
        companies.append({
            **row,
            "name": row["original_name"],
            "display_status": row["status"],
            "pipeline_status": row["status"],
            "normalized_key": row.get("original_name_key"),
            "has_phone": bool(contact.get("has_phone")),
            "has_email": bool(contact.get("has_email")),
            "checkpoint": _effective_checkpoint(row, audit),
            "current_step": _effective_current_step(row, audit),
            "last_activity_step": audit.get("last_activity_step"),
            "completion_status": audit.get("completion_status"),
            "completion_reason": audit.get("completion_reason"),
            "resume_status": audit.get("resume_status"),
            "can_resume_incomplete": audit.get("completion_status") == "incomplete",
            "is_reported": bool(reported),
            "reported_at": reported.get("reported_at"),
            "report_run_id": reported.get("report_run_id"),
            "is_import_item": False,
            **stale_fields,
        })

    return JSONResponse({
        "companies": companies,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "truncated": scan_truncated,
            "scan_cap": _COMPLETION_FILTER_SCAN_CAP if scan_truncated else None,
        },
        "counts": _counts(db),
    })


@app.get("/api/spa/companies/ids")
def api_spa_company_ids(
    status: str = None,
    search: str = None,
    import_batch_id: int = None,
    import_outcome: str = None,
    completion: str = None,
    checkpoint: str = None,
    created_from: str = None,
    created_to: str = None,
    completed_from: str = None,
    completed_to: str = None,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
    report_window: str = None,
    complement: bool = False,
):
    db = _db()
    window_start, window_end = _report_window_bounds(report_window)
    reported_from = reported_from or window_start
    reported_to = reported_to or window_end
    def complement_ids(rows: list[dict]) -> list[int]:
        excluded = {int(r["id"]) for r in rows if r.get("id")}
        all_rows = db.fetch_all("SELECT id FROM companies ORDER BY id")
        return [int(r["id"]) for r in all_rows if int(r["id"]) not in excluded]

    if import_batch_id and db.has_import_items(import_batch_id):
        where, params_without_batch = _import_item_filter_sql(
            search, import_outcome, status, created_from, created_to,
            report_state=report_state, reported_from=reported_from, reported_to=reported_to,
        )
        params = [import_batch_id] + params_without_batch
        rows = db.fetch_all(
            f"""
            SELECT DISTINCT COALESCE(i.company_id, i.matched_company_id) as id
            FROM company_import_items i
            LEFT JOIN companies c ON c.id = COALESCE(i.company_id, i.matched_company_id)
            {where}
              AND COALESCE(i.company_id, i.matched_company_id) IS NOT NULL
            ORDER BY id
            """,
            tuple(params),
        )
        if completion or checkpoint:
            filtered_rows = []
            for row in rows:
                company = db.get_company(int(row["id"]))
                audit = audit_company_completion(db, int(row["id"]), company)
                checkpoint_row = {"id": row["id"], "status": company.get("status") if company else "pending"}
                if _completion_matches(audit, completion) and _checkpoint_matches(checkpoint_row, audit, checkpoint):
                    filtered_rows.append(row)
            rows = filtered_rows
        company_ids = complement_ids(rows) if complement else [r["id"] for r in rows]
        return JSONResponse({"company_ids": company_ids, "count": len(company_ids)})

    where, params = _company_filter_sql(
        status=status,
        search=search,
        import_batch_id=import_batch_id,
        created_from=created_from,
        created_to=created_to,
        completed_from=completed_from,
        completed_to=completed_to,
        report_state=report_state,
        reported_from=reported_from,
        reported_to=reported_to,
    )
    rows = db.fetch_all(f"SELECT id FROM companies {where} ORDER BY id", tuple(params))
    if completion or checkpoint:
        filtered_rows = []
        for row in rows:
            company = db.get_company(int(row["id"]))
            audit = audit_company_completion(db, int(row["id"]), company)
            checkpoint_row = {"id": row["id"], "status": company.get("status") if company else "pending"}
            if _completion_matches(audit, completion) and _checkpoint_matches(checkpoint_row, audit, checkpoint):
                filtered_rows.append(row)
        rows = filtered_rows
    company_ids = complement_ids(rows) if complement else [r["id"] for r in rows]
    return JSONResponse({"company_ids": company_ids, "count": len(company_ids)})


@app.get("/api/spa/import-batches")
def api_spa_import_batches(limit: int = 25):
    db = _db()
    limit = max(1, min(limit, 100))
    cache_key = f"import_batches:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return JSONResponse({"batches": cached})
    started_at = time.monotonic()
    batches = db.get_import_batches(limit)
    _slow_log("import_batches", started_at)
    return JSONResponse({"batches": _cache_set(cache_key, batches)})


@app.get("/api/spa/import-batches/{batch_id}/items")
def api_spa_import_batch_items(
    batch_id: int,
    search: str = None,
    import_outcome: str = None,
    completion: str = None,
    checkpoint: str = None,
    created_from: str = None,
    created_to: str = None,
    report_state: str = None,
    reported_from: str = None,
    reported_to: str = None,
    report_window: str = None,
    page: int = 1,
    page_size: int = 50,
):
    db = _db()
    window_start, window_end = _report_window_bounds(report_window)
    reported_from = reported_from or window_start
    reported_to = reported_to or window_end
    return JSONResponse(_import_batch_items_payload(
        db,
        batch_id,
        search=search,
        import_outcome=import_outcome,
        completion=completion,
        checkpoint=checkpoint,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
        report_state=report_state,
        reported_from=reported_from,
        reported_to=reported_to,
    ))


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
        "scraped_pages": _scraped_url_rows(db, company_id),
        "contacts": db.fetch_all("SELECT * FROM extracted_contacts WHERE company_id = ? ORDER BY confidence_score DESC", (company_id,)),
        "timeline": db.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? ORDER BY id", (company_id,)),
    })


@app.get("/api/spa/monitor")
def api_spa_monitor():
    return JSONResponse(_monitor_snapshot(_db()))


@app.get("/api/spa/runner/stale-jobs")
def api_spa_runner_stale_jobs(threshold_minutes: int = _STALE_THRESHOLD_MINUTES):
    threshold_minutes = max(1, min(int(threshold_minutes or _STALE_THRESHOLD_MINUTES), 1440))
    db = _db()
    stale = _stale_jobs(db, threshold_minutes=threshold_minutes)
    running_rows = db.fetch_all(
        """
        SELECT c.id, c.original_name, c.status, c.updated_at,
               j.current_step, j.checkpoint, j.progress, j.updated_at as job_updated_at
        FROM companies c
        LEFT JOIN pipeline_jobs j ON j.company_id = c.id
        WHERE c.status IN ('gemini_quick','searching','scraping','extracting')
          AND COALESCE(j.removed_from_monitor, 0) = 0
        ORDER BY COALESCE(j.updated_at, c.updated_at) DESC, c.id
        """
    )
    running = []
    stale_ids = {row["id"] for row in stale}
    for row in running_rows:
        if row["id"] in stale_ids:
            continue
        step, checkpoint, progress = _company_step(row["status"])
        running.append({
            "id": row["id"],
            "name": row["original_name"],
            "status": row["status"],
            "step": row.get("current_step") or step,
            "checkpoint": row.get("checkpoint") or checkpoint,
            "progress": row.get("progress") or progress,
            "updated_at": row.get("job_updated_at") or row.get("updated_at"),
            "stale": False,
            "suggested_status": None,
            "stale_reason": None,
            "data_counts": None,
        })
    return JSONResponse({
        "threshold_minutes": threshold_minutes,
        "stale": stale,
        "running": running,
        "counts": {"stale": len(stale), "running": len(running)},
    })


@app.post("/api/spa/runner/reset-status")
async def api_spa_runner_reset_status(request: Request):
    data = await request.json()
    company_ids = data.get("company_ids", [])
    mode = data.get("mode", "smart_resume")
    target_status = data.get("target_status")
    if not isinstance(company_ids, list) or not company_ids:
        return JSONResponse({"error": "No company IDs provided"}, status_code=400)

    db = _db()
    results = []
    for raw_id in dict.fromkeys(company_ids):
        try:
            company_id = int(raw_id)
        except (TypeError, ValueError):
            results.append({"id": raw_id, "status": "skipped", "reason": "invalid_company_id"})
            continue
        results.append(_reset_company_status(db, company_id, mode, target_status=target_status))

    reset_count = sum(1 for row in results if row["status"] == "reset")
    return JSONResponse({"status": "ok", "reset": reset_count, "results": results})


@app.post("/api/spa/runner/start")
async def api_spa_runner_start(request: Request):
    data = await request.json()
    company_ids = data.get("company_ids", [])
    resume_stale = bool(data.get("resume_stale", False))
    resume_incomplete = bool(data.get("resume_incomplete", False))
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
            job = _get_job(db, cid)
            if resume_stale and _is_stale_running_job(company, job):
                reset_result = _reset_company_status(db, cid, "smart_resume")
                if reset_result.get("status") != "reset":
                    skipped.append({"id": cid, "reason": reset_result.get("reason", "reset_failed"), "status": status})
                    continue
                company = db.get_company(cid)
                status = company["status"] if company else status
            else:
                skipped.append({"id": cid, "reason": "already_running", "status": status})
                continue
        if status == "done" and resume_incomplete:
            audit = audit_company_completion(db, cid, company)
            if audit.get("completion_status") == "incomplete":
                resume_status = audit.get("resume_status") or "pending"
                db.update_company(cid, status=resume_status, completed_at=None)
                _upsert_job(
                    db,
                    cid,
                    resume_status,
                    current_step=audit.get("current_step"),
                    checkpoint=audit.get("checkpoint"),
                    progress=0,
                )
                company = db.get_company(cid)
                status = company["status"] if company else resume_status
            else:
                skipped.append({"id": cid, "reason": "already_strict_done", "status": status})
                continue
        if status in ("done", "permanently_failed"):
            skipped.append({"id": cid, "reason": "not_resumable", "status": status})
            continue
        if status not in _RESUMABLE_STATUSES:
            skipped.append({"id": cid, "reason": "unknown_status", "status": status})
            continue
        _monitor_removed_ids.discard(cid)
        _monitor_stopped_ids.discard(cid)
        started.append(cid)

    if not started:
        has_active_jobs = _has_active_pipeline_jobs(db, normalized_ids)
        worker_status = _ensure_worker_started(db) if has_active_jobs else _worker_status(db)
        status_code = 200 if has_active_jobs else 409
        return JSONResponse({"status": "skipped", "started": [], "skipped": skipped, "worker": worker_status}, status_code=status_code)

    enqueue_result = db.enqueue_pipeline_jobs(started)
    for cid in enqueue_result["queued"]:
        job = _get_job(db, cid)
        _emit_job_update(db, job, "job_queued")
    skipped.extend(enqueue_result["skipped"])
    if not enqueue_result["queued"]:
        has_active_jobs = _has_active_pipeline_jobs(db, started)
        worker_status = _ensure_worker_started(db) if has_active_jobs else _worker_status(db)
        status_code = 200 if has_active_jobs else 409
        return JSONResponse({"status": "skipped", "started": [], "skipped": skipped, "worker": worker_status}, status_code=status_code)
    worker_status = _ensure_worker_started(db)
    return JSONResponse({
        "status": "queued",
        "run_id": enqueue_result["run_id"],
        "started": enqueue_result["queued"],
        "skipped": skipped,
        "worker": worker_status,
    })


@app.post("/api/spa/runner/stop-all")
def api_spa_runner_stop_all():
    db = _db()
    result = db.request_stop_pipeline_jobs()
    return JSONResponse({
        "status": "stop_requested",
        "queued_stopped": result["queued_stopped"],
        "running_stop_requested": result["stop_requested"],
        "count": result["queued_stopped"] + result["stop_requested"],
    })


@app.get("/api/spa/runtime-health")
def api_spa_runtime_health():
    return JSONResponse(_runtime_health_payload(_db()))


@app.post("/api/spa/runtime-health/firecrawl-test")
def api_spa_runtime_health_firecrawl_test():
    key = os.getenv("FIRECRAWL_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"query": "test", "limit": 1, "lang": "vi", "country": "vn"}
    try:
        response = requests.post("https://api.firecrawl.dev/v2/search", headers=headers, json=body, timeout=30)
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return JSONResponse({
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "credits_used": payload.get("creditsUsed"),
            "key_mask": _current_firecrawl_key_mask(),
            "message": payload.get("error") or payload.get("message") or response.text[:200],
        })
    except Exception as exc:
        return JSONResponse({
            "ok": False,
            "status_code": None,
            "credits_used": None,
            "key_mask": _current_firecrawl_key_mask(),
            "message": str(exc),
        }, status_code=502)


def _request_graceful_worker_restart(db: DatabaseManager) -> dict:
    stop_result = db.request_stop_pipeline_jobs(stop_queued=False)
    before = _runtime_health_payload(db)
    runtime_processes = before.get("runtime_processes", [])
    signaled_pids = _terminate_runtime_workers(runtime_processes)
    time.sleep(1.0)
    remaining = _iter_runtime_worker_processes()
    started_pid = None
    started_message = None
    start_error = None
    if not remaining:
        try:
            started = _start_worker_process()
            started_pid = started["pid"]
            started_message = started["message"]
        except Exception as exc:
            start_error = str(exc)
    after = _runtime_health_payload(db)
    if start_error:
        status_label = "start_failed"
    elif started_pid:
        status_label = "restarted"
    else:
        status_label = "stop_pending"
    return {
        "status": status_label,
        "stop_requested": stop_result,
        "signaled_pids": signaled_pids,
        "remaining_pids": [proc["pid"] for proc in remaining],
        "started_pid": started_pid,
        "message": started_message or start_error,
        "runtime_health": after,
    }


@app.post("/api/spa/runner/restart-worker")
def api_spa_runner_restart_worker():
    payload = _request_graceful_worker_restart(_db())
    return JSONResponse(payload, status_code=500 if payload["status"] == "start_failed" else 200)


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
        "UPDATE pipeline_jobs SET removed_from_monitor = 1, updated_at = ? WHERE company_id = ?",
        (vn_timestamp(), company_id),
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

@app.get("/api/spa/pipeline-config")
def api_spa_pipeline_config_get():
    config_file = "pipeline_config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                return JSONResponse(json.load(f))
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({})

@app.post("/api/spa/pipeline-config")
async def api_spa_pipeline_config_update(req: Request):
    data = await req.json()
    config_file = "pipeline_config.json"
    
    # Merge with existing
    current_config = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                current_config = json.load(f)
        except Exception:
            pass
            
    current_config.update(data)
    
    try:
        with open(config_file, "w") as f:
            json.dump(current_config, f, indent=2)
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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
# API: Reported checkpoint
# ---------------------------------------------------------------------------
@app.post("/api/spa/companies/report-status")
async def api_spa_companies_report_status(req: Request):
    data = await req.json()
    company_ids = data.get("company_ids") or []
    action = str(data.get("action") or "").strip().lower()
    note = data.get("note")
    db = _db()

    if not company_ids:
        return JSONResponse({"error": "No company IDs provided"}, status_code=400)
    if action not in {"mark", "unmark"}:
        return JSONResponse({"error": "Invalid action"}, status_code=400)

    if action == "unmark":
        result = db.unmark_companies_reported(company_ids)
        _invalidate_dashboard_cache()
        return JSONResponse({"status": "ok", **result})

    window_start = data.get("window_start")
    window_end = data.get("window_end")
    if not window_start and not window_end:
        window_start, window_end = _report_window_bounds(data.get("report_window") or "today")
    result = db.mark_companies_reported(
        company_ids,
        window_start=window_start,
        window_end=window_end,
        note=note,
        reported_by=os.getenv("DASHBOARD_USER", "dashboard"),
    )
    _invalidate_dashboard_cache()
    return JSONResponse({"status": "ok", **result, "window_start": window_start, "window_end": window_end})


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
    raw_items = data.get("companies") or data.get("records") or data.get("items") or data.get("names", [])
    if not raw_items:
        return JSONResponse({"error": "No names provided"}, status_code=400)

    db = _db()
    batch_id = db.create_import_batch(
        source_filename=data.get("source_filename"),
        total=len(raw_items),
        imported=0,
        skipped=0,
    )
    imported = 0
    skipped = 0
    outcome_counts = {
        "imported": 0,
        "matched_by_tax_code": 0,
        "matched_by_score": 0,
        "ambiguous": 0,
        "no_match": 0,
        "duplicate_existing": 0,
        "duplicate_in_file": 0,
        "invalid": 0,
    }
    seen_keys: dict[str, int] = {}
    duplicate_names = []
    duplicate_items = []

    for row_number, raw in enumerate(raw_items, 1):
        record = _import_record(raw)
        input_name = record["name"]
        canonical_name = db.canonicalize_company_name(input_name)
        name_key = db.normalize_company_name(canonical_name)
        record["name"] = canonical_name
        tax_code = record.get("tax_code", "")
        if not canonical_name or not name_key:
            skipped += 1
            outcome_counts["invalid"] += 1
            db.insert_import_item(
                batch_id, row_number, input_name, canonical_name, name_key,
                "invalid", reason="empty_name"
            )
            continue

        import_identity_key = f"tax:{tax_code}" if tax_code else f"name:{name_key}"
        if import_identity_key in seen_keys:
            skipped += 1
            outcome_counts["duplicate_in_file"] += 1
            duplicate_names.append(canonical_name)
            duplicate_items.append({"name": canonical_name, "row_number": row_number, "reason": "duplicate_in_file"})
            db.insert_import_item(
                batch_id, row_number, input_name, canonical_name, name_key,
                "duplicate_in_file", reason=f"duplicate_of_row_{seen_keys[import_identity_key]}"
            )
            continue
        seen_keys[import_identity_key] = row_number

        decision = resolve_company_match(db, record)
        top = decision.candidate
        if decision.decision in ("matched_by_tax_code", "matched_by_score") and top:
            skipped += 1
            outcome_counts[decision.decision] += 1
            matched_company_id = top.company["id"]
            import_item_id = db.insert_import_item(
                batch_id,
                row_number,
                input_name,
                canonical_name,
                name_key,
                decision.decision,
                matched_company_id=matched_company_id,
                reason=decision.reason,
                match_score=top.score,
                match_method=top.method,
                evidence_json=evidence_json(top, decision),
            )
            for candidate in decision.candidates[:5]:
                db.insert_match_candidate(
                    batch_id,
                    import_item_id,
                    row_number,
                    canonical_name,
                    tax_code,
                    candidate.company["id"],
                    candidate.score,
                    candidate.method,
                    decision.decision,
                    evidence_json(candidate, decision),
                )
            continue

        if decision.decision == "ambiguous":
            skipped += 1
            outcome_counts["ambiguous"] += 1
            duplicate_names.append(canonical_name)
            duplicate_items.append({
                "name": canonical_name,
                "row_number": row_number,
                "reason": decision.reason,
                "candidate_count": len(decision.candidates),
                "top_candidate_id": top.company["id"] if top else None,
                "match_score": top.score if top else None,
            })
            import_item_id = db.insert_import_item(
                batch_id,
                row_number,
                input_name,
                canonical_name,
                name_key,
                "ambiguous",
                reason=decision.reason,
                match_score=top.score if top else None,
                match_method=top.method if top else None,
                evidence_json=evidence_json(top, decision),
            )
            for candidate in decision.candidates[:5]:
                db.insert_match_candidate(
                    batch_id,
                    import_item_id,
                    row_number,
                    canonical_name,
                    tax_code,
                    candidate.company["id"],
                    candidate.score,
                    candidate.method,
                    "ambiguous",
                    evidence_json(candidate, decision),
                )
            continue

        try:
            name_collision = bool(db.fetch_one(
                "SELECT id FROM companies WHERE original_name_key = ? OR original_name_key LIKE ? LIMIT 1",
                (name_key, f"{name_key}#duplicate-%"),
            ))
            company_id = db.insert_company(
                canonical_name,
                tax_code=tax_code or None,
                import_batch_id=batch_id,
                allow_duplicate_name=name_collision,
            )
            imported += 1
            outcome_counts["imported"] += 1
            db.insert_import_item(
                batch_id, row_number, input_name, canonical_name, name_key,
                "imported", company_id=company_id, reason=decision.reason
            )
        except sqlite3.IntegrityError:
            skipped += 1
            outcome_counts["ambiguous"] += 1
            duplicate_names.append(canonical_name)
            duplicate_items.append({
                "name": canonical_name,
                "row_number": row_number,
                "reason": "integrity_duplicate",
            })
            db.insert_import_item(
                batch_id, row_number, input_name, canonical_name, name_key,
                "ambiguous", reason="integrity_duplicate"
            )

    db.update_import_batch(batch_id, imported=imported, skipped=skipped)
    return JSONResponse({
        "batch_id": batch_id,
        "imported": imported,
        "skipped": skipped,
        "total": len(raw_items),
        "items_count": sum(outcome_counts.values()),
        "summary": outcome_counts,
        "duplicates": duplicate_items,
        "duplicate_names": duplicate_names,
    })


# ---------------------------------------------------------------------------
# API: Runner — Step execution
# ---------------------------------------------------------------------------
@app.post("/api/runner/step")
async def run_step_api(request: Request):
    data = await request.json()
    company_id = data.get("company_id")
    step = data.get("step")

    VALID_STEPS = {"gemini_quick", "serper_search", "filter", "scrape", "ai_extract", "facebook", "full"}
    
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
            db_inner = _db()
            db_inner.update_company(company_id, status="pending")
            result = db_inner.enqueue_pipeline_jobs([company_id])
            worker_status = _ensure_worker_started(db_inner) if result["queued"] else _worker_status(db_inner)
            return JSONResponse({
                "status": "queued",
                "run_id": result["run_id"],
                "message": f"Pipeline queued for company {company_id}",
                "skipped": result["skipped"],
                "worker": worker_status,
            })

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

    db_inner = _db()
    for cid in company_ids:
        db_inner.update_company(int(cid), status="pending")
    result = db_inner.enqueue_pipeline_jobs([int(cid) for cid in company_ids])
    worker_status = _ensure_worker_started(db_inner) if result["queued"] else _worker_status(db_inner)
    return JSONResponse({"status": "queued", "run_id": result["run_id"], "count": len(result["queued"]), "skipped": result["skipped"], "worker": worker_status})


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


@app.post("/api/export-excel")
def api_export_excel(payload: dict):
    from src.excel_handler import ExcelWriter
    from fastapi.responses import FileResponse
    import tempfile
    import logging
    
    local_logger = logging.getLogger("dashboard")
    
    company_ids = payload.get("company_ids", [])
    if not company_ids:
        raise HTTPException(status_code=400, detail="No company IDs provided")
        
    db = _db()
    today = _today_str()
    
    # Create a temporary file path
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"final_results_{today}.xlsx")
    
    try:
        writer = ExcelWriter()
        writer.write_consolidated_report(db, output_path, company_ids=company_ids)
        
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

# Triggering uvicorn reload for src/ updates
