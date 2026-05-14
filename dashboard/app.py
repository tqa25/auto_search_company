"""
Pipeline Dashboard v2 — Pipeline Control Center
FastAPI application with Jinja2 templates, WebSocket, and full API.
"""

import os
import sys
import json
import csv
import io
import asyncio
import threading
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import set_key, load_dotenv

# Ensure project root on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from src.database import DatabaseManager
from src.health_monitor import HealthMonitor
from src.logger import PipelineLogger
from src.config import Config
from src.pipeline import Pipeline

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

VN_TZ = timezone(timedelta(hours=7))

app = FastAPI(title="Pipeline Control Center")

# ---------------------------------------------------------------------------
# Static files & Templates
# ---------------------------------------------------------------------------
_DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_DASHBOARD_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_DASHBOARD_DIR, "templates"))

# ---------------------------------------------------------------------------
# Paths & Helpers
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(_PROJECT_ROOT, os.getenv("DB_PATH", "data/company_data.db"))
DOTENV_PATH = os.path.join(_PROJECT_ROOT, ".env")
LOG_DIR = os.path.join(_PROJECT_ROOT, "output", "logs")


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


# ---------------------------------------------------------------------------
# WebSocket connections
# ---------------------------------------------------------------------------
ws_clients: list[WebSocket] = []


async def broadcast_log(message: str):
    """Send a message to all connected WebSocket clients."""
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


# ---------------------------------------------------------------------------
# PAGE: Monitor (/)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def monitor_page(request: Request):
    db = _db()
    cfg = _cfg()

    # Basic stats
    total = db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]
    done = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='done'")["cnt"]
    failed = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status IN ('failed','permanently_failed')")["cnt"]
    pending = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='pending'")["cnt"]
    pct = round(done / max(total, 1) * 100, 1)

    # Phone/email coverage
    phone_row = db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE phone IS NOT NULL AND phone != ''")
    email_row = db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE email IS NOT NULL AND email != ''")
    phone_count = phone_row["cnt"] if phone_row else 0
    email_count = email_row["cnt"] if email_row else 0

    # Pipeline step stats
    gemini_sufficient = db.fetch_one("SELECT COUNT(*) as cnt FROM gemini_quick_results WHERE is_sufficient=1")
    total_processed = max(done, 1)
    gemini_pct = round((gemini_sufficient["cnt"] if gemini_sufficient else 0) / total_processed * 100)
    # Approximate other stats from extracted contacts source types
    maps_count = db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts WHERE source_type='google_maps'")["cnt"]
    maps_pct = round(maps_count / total_processed * 100)
    deep_pct = max(0, 100 - gemini_pct - maps_pct - 5)  # Approximation
    fb_pct = 5 if done > 10 else 0
    no_phone_row = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status='done' AND id NOT IN (SELECT DISTINCT company_id FROM extracted_contacts WHERE phone IS NOT NULL AND phone != '')")
    no_phone_pct = round((no_phone_row["cnt"] if no_phone_row else 0) / total_processed * 100)

    # Quota
    today = _today_str()
    quota_row = db.fetch_one("SELECT gemini_grounding_used, serper_used FROM daily_quota WHERE date = ?", (today,))
    gemini_used = quota_row["gemini_grounding_used"] if quota_row else 0
    serper_used = quota_row["serper_used"] if quota_row else 0

    # Token usage (from gemini_quick_results today)
    tokens = db.fetch_one("SELECT SUM(input_tokens) as tin, SUM(output_tokens) as tout FROM gemini_quick_results WHERE created_at LIKE ?", (f"{today}%",))

    return templates.TemplateResponse(request, "monitor.html", context={
        "active_page": "monitor",
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "stats": {
            "total": total, "done": done, "failed": failed, "pending": pending,
            "pct": pct,
            "phone_pct": round(phone_count / max(done, 1) * 100, 1),
            "email_pct": round(email_count / max(done, 1) * 100, 1),
        },
        "step_stats": {
            "gemini": gemini_pct, "maps": maps_pct, "deep": deep_pct,
            "facebook": fb_pct, "no_phone": no_phone_pct,
        },
        "quota": {
            "gemini_used": gemini_used, "serper_used": serper_used,
            "tokens_in": tokens["tin"] or 0 if tokens else 0,
            "tokens_out": tokens["tout"] or 0 if tokens else 0,
        },
    })


# ---------------------------------------------------------------------------
# PAGE: Companies (/companies)
# ---------------------------------------------------------------------------
@app.get("/companies", response_class=HTMLResponse)
def companies_page(request: Request, status: str = None, page: int = 1):
    db = _db()
    cfg = _cfg()
    per_page = 50

    # Count
    if status:
        total_count = db.fetch_one("SELECT COUNT(*) as cnt FROM companies WHERE status = ?", (status,))["cnt"]
    else:
        total_count = db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    # Fetch
    if status:
        rows = db.fetch_all(
            "SELECT id, original_name, status, updated_at FROM companies WHERE status = ? ORDER BY id LIMIT ? OFFSET ?",
            (status, per_page, offset)
        )
    else:
        rows = db.fetch_all(
            "SELECT id, original_name, status, updated_at FROM companies ORDER BY id LIMIT ? OFFSET ?",
            (per_page, offset)
        )

    # Check phone for each
    phone_ids = set()
    if rows:
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        phone_rows = db.fetch_all(
            f"SELECT DISTINCT company_id FROM extracted_contacts WHERE company_id IN ({placeholders}) AND phone IS NOT NULL AND phone != ''",
            tuple(ids)
        )
        phone_ids = {r["company_id"] for r in phone_rows}

    for r in rows:
        r["has_phone"] = r["id"] in phone_ids

    return templates.TemplateResponse(request, "companies.html", context={
        "active_page": "companies",
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "companies": rows,
        "status_filter": status,
        "page": page,
        "total_pages": total_pages,
    })


# ---------------------------------------------------------------------------
# PAGE: Company Detail (/companies/{id})
# ---------------------------------------------------------------------------
@app.get("/companies/{company_id}", response_class=HTMLResponse)
def company_detail_page(request: Request, company_id: int):
    db = _db()
    cfg = _cfg()
    company = db.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    contacts = db.fetch_all(
        "SELECT * FROM extracted_contacts WHERE company_id = ? ORDER BY confidence_score DESC",
        (company_id,)
    )

    logs = db.fetch_all(
        "SELECT * FROM pipeline_logs WHERE company_id = ? ORDER BY id DESC",
        (company_id,)
    )

    links = db.fetch_all(
        "SELECT url, source_type, relevance_score, should_scrape, reason FROM filtered_links WHERE company_id = ? ORDER BY relevance_score DESC",
        (company_id,)
    )

    search_results = db.fetch_all(
        "SELECT * FROM search_results WHERE company_id = ? ORDER BY search_type, result_rank",
        (company_id,)
    )

    scraped_pages = db.fetch_all(
        "SELECT id, url, source_type, content_length, scrape_status, credits_used, error_message, created_at FROM scraped_pages WHERE company_id = ? ORDER BY id",
        (company_id,)
    )

    gemini_result = db.fetch_one(
        "SELECT * FROM gemini_quick_results WHERE company_id = ? ORDER BY id DESC LIMIT 1",
        (company_id,)
    )
    gemini_grounding = []
    if gemini_result and gemini_result.get("grounding_sources_json"):
        import json
        try:
            gemini_grounding = json.loads(gemini_result["grounding_sources_json"])
        except json.JSONDecodeError:
            pass

    return templates.TemplateResponse(request, "company_detail.html", context={
        "active_page": "companies",
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "company": company,
        "contacts": contacts,
        "logs": logs,
        "links": links,
        "search_results": search_results,
        "scraped_pages": scraped_pages,
        "gemini_result": gemini_result,
        "gemini_grounding": gemini_grounding,
    })


# POST rerun
@app.post("/companies/{company_id}/rerun")
def company_rerun(company_id: int):
    db = _db()
    db.update_company(company_id, status="pending")
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)


# ---------------------------------------------------------------------------
# PAGE: Runner (/runner)
# ---------------------------------------------------------------------------
@app.get("/runner", response_class=HTMLResponse)
def runner_page(request: Request):
    db = _db()
    cfg = _cfg()
    companies = db.fetch_all("SELECT id, original_name FROM companies ORDER BY id")
    return templates.TemplateResponse(request, "runner.html", context={
        "active_page": "runner",
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "companies": companies,
    })


# ---------------------------------------------------------------------------
# PAGE: Settings (/settings)
# ---------------------------------------------------------------------------
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, saved: str = None):
    cfg = _cfg()
    return templates.TemplateResponse(request, "settings.html", context={
        "active_page": "settings",
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "cfg": cfg,
        "saved": saved == "1",
    })


@app.post("/settings")
async def settings_save(request: Request):
    form = await request.form()
    for key in form:
        val = form.get(key)
        if val is not None:
            set_key(DOTENV_PATH, key, str(val))
    # Reload environment to reflect changes immediately
    load_dotenv(DOTENV_PATH, override=True)
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# ---------------------------------------------------------------------------
# PAGE: Raw Logs (/logs)
# ---------------------------------------------------------------------------
@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    cfg = _cfg()
    today = _today_str()
    log_file = os.path.join(LOG_DIR, f"pipeline_{today}.jsonl")

    log_lines = []
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()[-200:]

        for line in reversed(raw_lines):
            try:
                obj = json.loads(line)
                status = obj.get("status", "")
                css = "log-success" if status == "success" else ("log-failed" if status in ("failed", "error") else "log-muted")
                log_lines.append({"text": json.dumps(obj, ensure_ascii=False), "css": css})
            except (json.JSONDecodeError, ValueError):
                log_lines.append({"text": line.strip(), "css": "log-muted"})

    return templates.TemplateResponse(request, "logs.html", context={
        "active_page": "logs",
        "gemini_limit": cfg.GEMINI_DAILY_LIMIT,
        "today": today,
        "log_count": len(log_lines),
        "log_lines": log_lines,
    })


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
async def api_runner_step(request: Request):
    data = await request.json()
    company_id = data.get("company_id")
    step = data.get("step")

    from starlette.concurrency import run_in_threadpool

    if not company_id or not step:
        return JSONResponse({"error": "Missing company_id or step"}, status_code=400)

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
            # Run full pipeline in background
            def run_pipeline():
                p = Pipeline(_pipeline_config())
                db_inner = _db()
                db_inner.update_company(company_id, status="pending")
                p.run(resume=False, company_ids=[company_id])

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

    def run_batch():
        db_inner = _db()
        for cid in company_ids:
            db_inner.update_company(cid, status="pending")
        p = Pipeline(_pipeline_config())
        p.run(resume=False, company_ids=company_ids)

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
        query = "SELECT * FROM pipeline_logs"
        params = ()
        if company_id:
            query += " WHERE company_id = ?"
            params = (company_id,)
        query += " ORDER BY started_at ASC"

        rows = db.fetch_all(query, params)
        if not rows:
            return JSONResponse({"error": "No logs found"}, status_code=404)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
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
