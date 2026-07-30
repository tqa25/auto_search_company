from __future__ import annotations

import argparse
import os
import signal
import socket
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import timedelta

from dotenv import load_dotenv

from src.database import DatabaseManager
from src.pipeline import Pipeline
from src.time_utils import parse_timestamp_as_vn, vn_now, vn_timestamp

RUNNING_COMPANY_STATUSES = {"gemini_quick", "searching", "scraping", "extracting"}
STALE_JOB_STATUSES = {"running", "stopping"}


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


def suggest_resume_status(company: dict, counts: dict) -> tuple[str, str]:
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


@dataclass
class WorkerJobController:
    db: DatabaseManager
    worker_id: str

    def update(self, company_id: int, status: str, current_step: str | None = None,
               checkpoint: str | None = None, progress: int | None = None):
        job = self.db.fetch_one("SELECT status, requested_action FROM pipeline_jobs WHERE company_id = ?", (company_id,))
        job_status = "stopping" if job and (job.get("status") == "stopping" or job.get("requested_action") == "stop") else "running"
        self.db.heartbeat_pipeline_job(
            company_id,
            self.worker_id,
            status=job_status,
            current_step=current_step or status,
            checkpoint=checkpoint or status,
            progress=progress,
        )
        self.db.heartbeat_pipeline_worker(self.worker_id, status="running", current_company_id=company_id, message=current_step or status)

    def should_stop(self, company_id: int) -> bool:
        job = self.db.fetch_one("SELECT requested_action FROM pipeline_jobs WHERE company_id = ?", (company_id,))
        return bool(job and job.get("requested_action") == "stop")


class PipelineWorker:
    def __init__(self, db_path: str = "data/company_data.db", worker_id: str | None = None, poll_seconds: float = 2.0, stale_minutes: int = 15):
        self.db_path = db_path
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.poll_seconds = poll_seconds
        self.stale_minutes = stale_minutes
        self.db = DatabaseManager(db_path)
        self.db.init_db()
        self._stop_requested = False

    def enqueue(self, company_ids: list[int]) -> dict:
        return self.db.enqueue_pipeline_jobs(company_ids)

    def request_stop(self, company_ids: list[int] | None = None) -> dict:
        return self.db.request_stop_pipeline_jobs(company_ids)

    def heartbeat(self, status: str = "idle", current_company_id: int | None = None, message: str | None = None):
        self.db.heartbeat_pipeline_worker(self.worker_id, status=status, current_company_id=current_company_id, message=message)

    def recover_stale_jobs(self) -> list[dict]:
        threshold = vn_now() - timedelta(minutes=self.stale_minutes)
        recovered = []
        jobs = self.db.fetch_all(
            """
            SELECT j.*, c.status AS company_status
            FROM pipeline_jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.status IN ('running', 'stopping')
              AND COALESCE(j.removed_from_monitor, 0) = 0
            """
        )
        for job in jobs:
            heartbeat = parse_timestamp_as_vn(job.get("heartbeat_at") or job.get("updated_at"))
            if heartbeat and heartbeat > threshold:
                continue
            company = self.db.get_company(job["company_id"])
            if not company or company.get("status") in ("done", "permanently_failed"):
                final_status = company.get("status") if company else "failed"
                self.db.update_pipeline_job(
                    job["company_id"],
                    status="done" if final_status == "done" else "failed",
                    current_step="Done" if final_status == "done" else "Failed",
                    checkpoint=final_status,
                    progress=100 if final_status == "done" else 0,
                    finished_at=vn_timestamp(),
                )
                continue
            counts = _company_data_counts(self.db, job["company_id"])
            resume_status, reason = suggest_resume_status(company, counts)
            self.db.update_company(job["company_id"], status=resume_status)
            self.db.update_pipeline_job(
                job["company_id"],
                status="queued",
                current_step="Queued",
                checkpoint=reason,
                progress=0,
                worker_id=None,
                requested_action=None,
                heartbeat_at=None,
                locked_at=None,
                last_error=f"Recovered stale job from {job.get('status')} via {reason}",
            )
            recovered.append({"company_id": job["company_id"], "resume_status": resume_status, "reason": reason})
        return recovered

    def run_once(self) -> bool:
        job = self.db.claim_next_pipeline_job(self.worker_id)
        if not job:
            self.heartbeat(status="idle", message="no queued jobs")
            return False

        company_id = int(job["company_id"])
        controller = WorkerJobController(self.db, self.worker_id)
        self.heartbeat(status="running", current_company_id=company_id, message="claimed job")
        try:
            pipeline = Pipeline({
                "firecrawl_api_key": os.getenv("FIRECRAWL_API_KEY"),
                "gemini_api_key": os.getenv("GEMINI_API_KEY"),
                "serper_api_key": os.getenv("SERPER_API_KEY"),
                "input_excel_path": None,
                "output_dir": "output",
            })
            pipeline.db = self.db
            pipeline.logger.db = self.db
            for module_name in ("search_module", "filter_module", "scrape_module", "gemini_quick", "deep_search", "ai_extractor", "result_aggregator"):
                module = getattr(pipeline, module_name, None)
                if module is not None and hasattr(module, "db"):
                    module.db = self.db
                if module is not None and hasattr(module, "logger"):
                    module.logger.db = self.db
            pipeline.run(company_ids=[company_id], job_controller=controller)
            company = self.db.get_company(company_id)
            job_after_run = self.db.fetch_one("SELECT status, requested_action FROM pipeline_jobs WHERE company_id = ?", (company_id,))
            final_status = company.get("status") if company else "failed"
            stop_requested = bool(job_after_run and (job_after_run.get("status") == "stopping" or job_after_run.get("requested_action") == "stop"))
            if stop_requested and final_status not in ("done", "failed", "permanently_failed"):
                self.db.update_pipeline_job(company_id, status="stopped", current_step="Stopped", checkpoint="stopped", progress=0, finished_at=vn_timestamp(), requested_action=None)
            elif final_status == "done":
                self.db.update_pipeline_job(company_id, status="done", current_step="Done", checkpoint="done", progress=100, finished_at=vn_timestamp(), requested_action=None)
            elif final_status in ("failed", "permanently_failed"):
                self.db.update_pipeline_job(company_id, status="failed", current_step="Failed", checkpoint=final_status, progress=0, finished_at=vn_timestamp(), requested_action=None)
            else:
                self.db.update_pipeline_job(
                    company_id,
                    status="failed",
                    current_step="Incomplete",
                    checkpoint=final_status,
                    progress=0,
                    finished_at=vn_timestamp(),
                    last_error=f"Strict completion not reached; resume from {final_status}",
                    requested_action=None,
                )
        except Exception as exc:
            self.db.update_pipeline_job(
                company_id,
                status="failed",
                current_step="Failed",
                checkpoint="failed",
                progress=0,
                finished_at=vn_timestamp(),
                error_message=str(exc),
                last_error=str(exc),
                requested_action=None,
            )
            company = self.db.get_company(company_id)
            if company and company.get("status") not in ("done", "permanently_failed"):
                self.db.update_company(company_id, status="failed")
        finally:
            self.heartbeat(status="idle", current_company_id=None, message="job finished")
        return True

    def run_loop(self, auto_recover: bool = True):
        if auto_recover:
            try:
                self.recover_stale_jobs()
            except Exception as exc:
                traceback.print_exc()
                print(f"[worker] recover_stale_jobs failed at startup, continuing: {exc}")
        self.db.register_pipeline_worker(self.worker_id, status="idle", message="worker started")
        while not self._stop_requested:
            try:
                did_work = self.run_once()
            except Exception as exc:
                # A failure while claiming a job or recovering (e.g. a transient
                # sqlite "database is locked") must not kill the whole worker.
                # Log it, back off, and keep polling.
                traceback.print_exc()
                print(f"[worker] run_once raised, continuing: {exc}")
                did_work = False
                try:
                    self.heartbeat(status="idle", message=f"run_once error: {exc}")
                except Exception:
                    pass
            if not did_work:
                time.sleep(self.poll_seconds)
        self.heartbeat(status="stopped", message="worker stopped")

    def stop(self, signum=None, frame=None):
        self._stop_requested = True


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Run the SQLite-backed pipeline worker.")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/company_data.db"))
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--stale-minutes", type=int, default=15)
    parser.add_argument("--no-auto-recover", action="store_true")
    args = parser.parse_args(argv)

    worker = PipelineWorker(
        db_path=args.db,
        worker_id=args.worker_id,
        poll_seconds=args.poll,
        stale_minutes=args.stale_minutes,
    )
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    worker.run_loop(auto_recover=not args.no_auto_recover)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
