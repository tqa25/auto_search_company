import sqlite3
import os
import re
import threading
import time
import uuid

from src.time_utils import vn_timestamp

class DatabaseManager:
    """Manages the SQLite database for the company data extraction pipeline."""

    def __init__(self, db_path="data/company_data.db"):
        """Initialize the DatabaseManager with the given database path."""
        self.db_path = db_path
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # Thread-local storage for connection pooling
        self._local = threading.local()

    def _get_connection(self):
        """Reuse connection per thread via thread-local storage."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
        return self._local.conn

    def close(self):
        """Close current thread's connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()

    def init_db(self):
        """Initialize the database tables and indexes."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. companies
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                original_name_key TEXT,
                vietnamese_name TEXT,
                tax_code TEXT,
                status TEXT DEFAULT 'pending',
                import_batch_id INTEGER REFERENCES company_import_batches(id),
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                updated_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                source_filename TEXT,
                total INTEGER DEFAULT 0,
                imported INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_import_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL REFERENCES company_import_batches(id),
                row_number INTEGER NOT NULL,
                input_name TEXT,
                canonical_name TEXT,
                normalized_key TEXT,
                outcome TEXT NOT NULL,
                company_id INTEGER REFERENCES companies(id),
                matched_company_id INTEGER REFERENCES companies(id),
                reason TEXT,
                match_score REAL,
                match_method TEXT,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        for sql in (
            "ALTER TABLE company_import_items ADD COLUMN match_score REAL",
            "ALTER TABLE company_import_items ADD COLUMN match_method TEXT",
            "ALTER TABLE company_import_items ADD COLUMN evidence_json TEXT",
        ):
            try:
                cursor.execute(sql)
            except Exception:
                pass

        # Safe migration: add address and vn_data_source to existing companies table
        for sql in (
            "ALTER TABLE companies ADD COLUMN original_name_key TEXT",
            "ALTER TABLE companies ADD COLUMN import_batch_id INTEGER REFERENCES company_import_batches(id)",
            "ALTER TABLE companies ADD COLUMN completed_at TIMESTAMP",
        ):
            try:
                cursor.execute(sql)
            except Exception:
                pass
        try:
            cursor.execute("ALTER TABLE companies ADD COLUMN address TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE companies ADD COLUMN vn_data_source TEXT")
        except Exception:
            pass
        for sql in (
            "ALTER TABLE companies ADD COLUMN business_status TEXT",
            "ALTER TABLE companies ADD COLUMN business_status_category TEXT",
            "ALTER TABLE companies ADD COLUMN business_status_source_url TEXT",
        ):
            try:
                cursor.execute(sql)
            except Exception:
                pass

        # 2. search_results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id),
                search_query TEXT NOT NULL,
                search_type TEXT,
                result_rank INTEGER,
                url TEXT NOT NULL,
                title TEXT,
                snippet TEXT,
                credits_used REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        # 3. filtered_links
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filtered_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_result_id INTEGER REFERENCES search_results(id),
                company_id INTEGER REFERENCES companies(id),
                url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                should_scrape BOOLEAN DEFAULT 1,
                reason TEXT,
                relevance_score REAL DEFAULT 0.0
            )
        """)

        # Safe migration: add relevance_score to existing filtered_links tables
        try:
            cursor.execute("ALTER TABLE filtered_links ADD COLUMN relevance_score REAL DEFAULT 0.0")
        except Exception:
            pass  # column already exists

        # 4. scraped_pages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraped_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filtered_link_id INTEGER REFERENCES filtered_links(id),
                company_id INTEGER REFERENCES companies(id),
                url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                markdown_content TEXT,
                content_length INTEGER,
                scrape_status TEXT,
                credits_used REAL DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        # 5. extracted_contacts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id),
                scraped_page_id INTEGER REFERENCES scraped_pages(id),
                source_type TEXT NOT NULL,
                source_url TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                fax TEXT,
                representative TEXT,
                raw_ai_response TEXT,
                confidence_score REAL,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        # 6. pipeline_logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id),
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                duration_seconds REAL,
                source_url TEXT,
                source_name TEXT,
                credits_used REAL DEFAULT 0,
                error_message TEXT,
                data_saved BOOLEAN DEFAULT 0,
                metadata_json TEXT
            )
        """)

        # 7. query_cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                query_hash TEXT PRIMARY KEY,
                query_text TEXT NOT NULL,
                company_id INTEGER REFERENCES companies(id),
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                expires_at TIMESTAMP,
                result_count INTEGER DEFAULT 0
            )
        """)

        # 8. url_cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS url_cache (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                scrape_status TEXT,
                content_hash TEXT,
                scraped_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                ttl_expires_at TIMESTAMP
            )
        """)

        # index for pipeline_logs
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_logs_company_step
            ON pipeline_logs(company_id, step)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_import_items_batch
            ON company_import_items(batch_id, row_number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_import_items_outcome
            ON company_import_items(batch_id, outcome)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_tax_code
            ON companies(tax_code)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_status_updated
            ON companies(status, updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_import_batch_status_id
            ON companies(import_batch_id, status, id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_import_batch_id
            ON companies(import_batch_id, id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_updated_at
            ON companies(updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_completed_at
            ON companies(completed_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_created_at
            ON companies(created_at)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_match_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER REFERENCES company_import_batches(id),
                import_item_id INTEGER REFERENCES company_import_items(id),
                row_number INTEGER,
                input_name TEXT,
                input_tax_code TEXT,
                candidate_company_id INTEGER REFERENCES companies(id),
                match_score REAL,
                match_method TEXT,
                decision TEXT NOT NULL,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_match_candidates_batch
            ON company_match_candidates(batch_id, row_number)
        """)

        # 9. gemini_quick_results — Bước 1 Gemini Quick Search results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gemini_quick_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id),
                core_name TEXT,
                core_name_vi TEXT,
                abbreviation TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                website TEXT,
                tax_code TEXT,
                fax TEXT,
                representative TEXT,
                confidence REAL,
                sources_json TEXT,
                grounding_sources_json TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                duration_seconds REAL,
                is_sufficient BOOLEAN,
                fallback_reason TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        # 10. daily_quota — Track daily API usage to avoid charges
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_quota (
                date TEXT PRIMARY KEY,
                gemini_grounding_used INTEGER DEFAULT 0,
                serper_used INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        # 11. pipeline_jobs — Realtime dashboard monitor state
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                company_id INTEGER PRIMARY KEY REFERENCES companies(id),
                company_name TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                current_step TEXT,
                checkpoint TEXT,
                progress INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                finished_at TIMESTAMP,
                error_message TEXT,
                removed_from_monitor BOOLEAN DEFAULT 0
            )
        """)
        for sql in (
            "ALTER TABLE pipeline_jobs ADD COLUMN run_id TEXT",
            "ALTER TABLE pipeline_jobs ADD COLUMN worker_id TEXT",
            "ALTER TABLE pipeline_jobs ADD COLUMN requested_action TEXT",
            "ALTER TABLE pipeline_jobs ADD COLUMN heartbeat_at TIMESTAMP",
            "ALTER TABLE pipeline_jobs ADD COLUMN attempt_count INTEGER DEFAULT 0",
            "ALTER TABLE pipeline_jobs ADD COLUMN last_error TEXT",
            "ALTER TABLE pipeline_jobs ADD COLUMN locked_at TIMESTAMP",
        ):
            try:
                cursor.execute(sql)
            except Exception:
                pass

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status_updated
            ON pipeline_jobs(status, updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_monitor_status_updated
            ON pipeline_jobs(removed_from_monitor, status, updated_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_queue_claim
            ON pipeline_jobs(status, removed_from_monitor, updated_at, company_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_worker_heartbeat
            ON pipeline_jobs(worker_id, heartbeat_at)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_workers (
                worker_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TIMESTAMP,
                heartbeat_at TIMESTAMP,
                last_seen_at TIMESTAMP,
                current_company_id INTEGER,
                message TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_workers_status_heartbeat
            ON pipeline_workers(status, heartbeat_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_results_company_id
            ON search_results(company_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_filtered_links_company_id
            ON filtered_links(company_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraped_pages_company_status
            ON scraped_pages(company_id, scrape_status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_extracted_contacts_company_id
            ON extracted_contacts(company_id)
        """)

        # 12. domain_stats — Track scrape success for auto-blacklisting
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domain_stats (
                domain TEXT PRIMARY KEY,
                scrape_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                is_auto_blacklisted BOOLEAN DEFAULT 0,
                updated_at TIMESTAMP DEFAULT (datetime('now', '+7 hours'))
            )
        """)

        # 13. report_runs / reported_companies — user-controlled reporting checkpoints.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS report_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                window_start TIMESTAMP,
                window_end TIMESTAMP,
                note TEXT,
                company_count INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reported_companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                report_run_id INTEGER REFERENCES report_runs(id),
                reported_at TIMESTAMP DEFAULT (datetime('now', '+7 hours')),
                reported_by TEXT,
                note TEXT,
                UNIQUE(company_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reported_companies_reported_at
            ON reported_companies(reported_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reported_companies_run
            ON reported_companies(report_run_id)
        """)

        conn.commit()
        self._ensure_company_name_keys()

        # Run pending schema migrations
        from src.migrations import run_migrations
        run_migrations(self)

    @staticmethod
    def canonicalize_company_name(name: str) -> str:
        """Create the stored company name used for duplicate checks."""
        value = re.sub(r"\s+", " ", str(name or "").strip())
        return re.sub(r"\\([\\`*_{}\[\]()#+\-.!&])", r"\1", value)

    @staticmethod
    def normalize_company_name(name: str) -> str:
        """Create a stable key for duplicate company-name checks."""
        return DatabaseManager.canonicalize_company_name(name).casefold()

    def _ensure_company_name_keys(self):
        """Backfill normalized company keys and add the unique guard."""
        rows = self.fetch_all(
            "SELECT id, original_name, original_name_key FROM companies ORDER BY id"
        )
        seen: set[str] = set()
        for row in rows:
            current_key = row.get("original_name_key")
            if current_key:
                if current_key in seen:
                    base_duplicate_key = f"{current_key}#duplicate-{row['id']}"
                    current_key = base_duplicate_key
                    suffix = 2
                    while current_key in seen:
                        current_key = f"{base_duplicate_key}-{suffix}"
                        suffix += 1
                    self.execute_query(
                        "UPDATE companies SET original_name_key = ? WHERE id = ?",
                        (current_key, row["id"]),
                    )
                seen.add(current_key)
                continue

            base_key = self.normalize_company_name(row["original_name"])
            if not base_key:
                base_key = f"company-{row['id']}"
            if base_key not in seen:
                key = base_key
            else:
                duplicate_key = f"{base_key}#duplicate-{row['id']}"
                key = duplicate_key
                suffix = 2
                while key in seen:
                    key = f"{duplicate_key}-{suffix}"
                    suffix += 1
            seen.add(key)
            self.execute_query(
                "UPDATE companies SET original_name_key = ? WHERE id = ?",
                (key, row["id"]),
            )

        self.execute_query(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_original_name_key "
            "ON companies(original_name_key)"
        )

    # Generic method for inserting/updating to avoid redundant code
    def execute_query(self, query, params=()):
        """Execute a general query that doesn't return rows (INSERT/UPDATE/DELETE)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid

    def fetch_all(self, query, params=()):
        """Execute a query and return all rows."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetch_one(self, query, params=()):
        """Execute a query and return the first row."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    # --- Pipeline job queue ---
    def enqueue_pipeline_jobs(self, company_ids: list[int], run_id: str | None = None) -> dict:
        """Queue companies for the external pipeline worker without starting work in-process."""
        run_id = run_id or uuid.uuid4().hex
        if not company_ids:
            return {"run_id": run_id, "queued": [], "skipped": []}

        now = vn_timestamp()
        queued = []
        skipped = []
        seen = set()
        for raw_id in company_ids:
            try:
                cid = int(raw_id)
            except (TypeError, ValueError):
                skipped.append({"id": raw_id, "reason": "invalid_company_id"})
                continue
            if cid in seen:
                continue
            seen.add(cid)

            company = self.get_company(cid)
            if not company:
                skipped.append({"id": cid, "reason": "not_found"})
                continue
            if company.get("status") in ("done", "permanently_failed"):
                skipped.append({"id": cid, "reason": "not_resumable", "status": company.get("status")})
                continue

            existing = self.fetch_one("SELECT * FROM pipeline_jobs WHERE company_id = ?", (cid,))
            if existing and existing.get("status") in ("queued", "running", "stopping"):
                skipped.append({"id": cid, "reason": "already_queued_or_running", "status": existing.get("status")})
                continue

            self.execute_query(
                """
                INSERT INTO pipeline_jobs (
                    company_id, company_name, status, current_step, checkpoint, progress,
                    started_at, updated_at, finished_at, error_message, removed_from_monitor,
                    run_id, worker_id, requested_action, heartbeat_at, attempt_count, last_error, locked_at
                ) VALUES (?, ?, 'queued', 'Queued', ?, 0, ?, ?, NULL, NULL, 0, ?, NULL, NULL, NULL, ?, NULL, NULL)
                ON CONFLICT(company_id) DO UPDATE SET
                    company_name=excluded.company_name,
                    status='queued',
                    current_step='Queued',
                    checkpoint=excluded.checkpoint,
                    progress=0,
                    updated_at=excluded.updated_at,
                    finished_at=NULL,
                    error_message=NULL,
                    removed_from_monitor=0,
                    run_id=excluded.run_id,
                    worker_id=NULL,
                    requested_action=NULL,
                    heartbeat_at=NULL,
                    last_error=NULL,
                    locked_at=NULL
                """,
                (
                    cid,
                    company["original_name"],
                    company.get("status") or "pending",
                    existing.get("started_at") if existing and existing.get("started_at") else now,
                    now,
                    run_id,
                    existing.get("attempt_count") if existing and existing.get("attempt_count") is not None else 0,
                ),
            )
            queued.append(cid)
        return {"run_id": run_id, "queued": queued, "skipped": skipped}

    def claim_next_pipeline_job(self, worker_id: str, max_lock_retries: int = 5) -> dict | None:
        """Atomically claim the next queued job for one worker.

        Retries transient "database is locked"/"busy" errors a few times with a
        short backoff instead of propagating them. Under multi-process contention
        (dashboard + worker writing concurrently) BEGIN IMMEDIATE can otherwise
        raise sqlite3.OperationalError, which — being called from the worker loop —
        would kill the worker. busy_timeout (see _get_connection) covers most of it;
        this loop is the last line of defence.
        """
        conn = self._get_connection()
        attempt = 0
        while True:
            now = vn_timestamp()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT j.*, c.status AS company_status
                    FROM pipeline_jobs j
                    JOIN companies c ON c.id = j.company_id
                    WHERE j.removed_from_monitor = 0
                      AND j.status = 'queued'
                      AND c.status NOT IN ('done', 'permanently_failed')
                    ORDER BY j.updated_at ASC, j.company_id ASC
                    LIMIT 1
                    """
                ).fetchone()
                if not row:
                    conn.commit()
                    return None
                company_id = row["company_id"]
                conn.execute(
                    """
                    UPDATE pipeline_jobs
                    SET status='running',
                        current_step='Running',
                        checkpoint=COALESCE(checkpoint, ?),
                        progress=CASE WHEN progress IS NULL OR progress = 0 THEN 1 ELSE progress END,
                        updated_at=?,
                        heartbeat_at=?,
                        worker_id=?,
                        locked_at=?,
                        requested_action=NULL,
                        finished_at=NULL,
                        error_message=NULL,
                        attempt_count=COALESCE(attempt_count, 0) + 1
                    WHERE company_id=?
                    """,
                    (row["company_status"], now, now, worker_id, now, company_id),
                )
                conn.commit()
                return self.fetch_one("SELECT * FROM pipeline_jobs WHERE company_id = ?", (company_id,))
            except sqlite3.OperationalError as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                message = str(exc).lower()
                if ("locked" in message or "busy" in message) and attempt < max_lock_retries:
                    attempt += 1
                    time.sleep(0.2 * attempt)
                    continue
                raise
            except Exception:
                conn.rollback()
                raise

    def update_pipeline_job(self, company_id: int, **kwargs):
        if not kwargs:
            return
        now = vn_timestamp()
        allowed = {
            "status", "current_step", "checkpoint", "progress", "finished_at",
            "error_message", "last_error", "requested_action", "heartbeat_at",
            "worker_id", "locked_at", "removed_from_monitor", "run_id",
        }
        updates = {key: value for key, value in kwargs.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = now
        set_clauses = ", ".join(f"{key} = ?" for key in updates)
        self.execute_query(
            f"UPDATE pipeline_jobs SET {set_clauses} WHERE company_id = ?",
            list(updates.values()) + [company_id],
        )

    def heartbeat_pipeline_job(self, company_id: int, worker_id: str, **kwargs):
        kwargs["heartbeat_at"] = vn_timestamp()
        kwargs["worker_id"] = worker_id
        self.update_pipeline_job(company_id, **kwargs)

    def request_stop_pipeline_jobs(self, company_ids: list[int] | None = None, stop_queued: bool = True) -> dict:
        """Ask running work to stop at the next safe point and optionally stop queued jobs."""
        now = vn_timestamp()
        params: list[object] = []
        scope_sql = ""
        if company_ids is not None:
            ids = [int(cid) for cid in dict.fromkeys(company_ids)]
            if not ids:
                return {"queued_stopped": 0, "stop_requested": 0}
            scope_sql = f" AND company_id IN ({','.join('?' for _ in ids)})"
            params.extend(ids)

        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if stop_queued:
                queued_cursor = conn.execute(
                    f"""
                    UPDATE pipeline_jobs
                    SET status='stopped',
                        current_step='Stopped',
                        checkpoint='stopped',
                        progress=0,
                        requested_action=NULL,
                        updated_at=?,
                        finished_at=?
                    WHERE removed_from_monitor=0
                      AND status='queued'
                      {scope_sql}
                    """,
                    [now, now] + params,
                )
            else:
                queued_cursor = conn.execute("SELECT 0")
            running_cursor = conn.execute(
                f"""
                UPDATE pipeline_jobs
                SET status='stopping',
                    current_step='Stopping',
                    requested_action='stop',
                    updated_at=?
                WHERE removed_from_monitor=0
                  AND status='running'
                  {scope_sql}
                """,
                [now] + params,
            )
            conn.commit()
            return {"queued_stopped": queued_cursor.rowcount, "stop_requested": running_cursor.rowcount}
        except Exception:
            conn.rollback()
            raise

    def register_pipeline_worker(self, worker_id: str, status: str = "idle", message: str | None = None):
        now = vn_timestamp()
        self.execute_query(
            """
            INSERT INTO pipeline_workers (
                worker_id, status, started_at, heartbeat_at, last_seen_at, current_company_id, message
            ) VALUES (?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                status=excluded.status,
                heartbeat_at=excluded.heartbeat_at,
                last_seen_at=excluded.last_seen_at,
                message=excluded.message
            """,
            (worker_id, status, now, now, now, message),
        )

    def heartbeat_pipeline_worker(
        self,
        worker_id: str,
        status: str = "idle",
        current_company_id: int | None = None,
        message: str | None = None,
    ):
        now = vn_timestamp()
        self.execute_query(
            """
            INSERT INTO pipeline_workers (
                worker_id, status, started_at, heartbeat_at, last_seen_at, current_company_id, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                status=excluded.status,
                heartbeat_at=excluded.heartbeat_at,
                last_seen_at=excluded.last_seen_at,
                current_company_id=excluded.current_company_id,
                message=excluded.message
            """,
            (worker_id, status, now, now, now, current_company_id, message),
        )

    def get_recent_pipeline_workers(self, since_timestamp: str | None = None) -> list[dict]:
        if since_timestamp:
            return self.fetch_all(
                "SELECT * FROM pipeline_workers WHERE heartbeat_at >= ? ORDER BY heartbeat_at DESC",
                (since_timestamp,),
            )
        return self.fetch_all("SELECT * FROM pipeline_workers ORDER BY heartbeat_at DESC")

    # --- Companies ---
    def insert_company(
        self,
        original_name,
        vietnamese_name=None,
        tax_code=None,
        status="pending",
        import_batch_id=None,
        allow_duplicate_name=False,
    ):
        """Insert a new company into the companies table."""
        canonical_name = self.canonicalize_company_name(original_name)
        name_key = self.normalize_company_name(canonical_name)
        insert_key = name_key
        now = vn_timestamp()
        completed_at = now if status == "done" else None
        if allow_duplicate_name:
            insert_key = f"{name_key}#pending-{uuid.uuid4().hex}"
        company_id = self.execute_query(
            """
            INSERT INTO companies (
                original_name, original_name_key, vietnamese_name, tax_code, status,
                import_batch_id, completed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_name,
                insert_key,
                vietnamese_name,
                tax_code,
                status,
                import_batch_id,
                completed_at,
                now,
                now,
            )
        )
        if allow_duplicate_name:
            self.execute_query(
                "UPDATE companies SET original_name_key = ? WHERE id = ?",
                (f"{name_key}#duplicate-{company_id}", company_id),
            )
        return company_id

    def get_company(self, company_id):
        """Retrieve a company by its ID."""
        return self.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))

    def get_all_companies(self):
        """Retrieve all companies."""
        return self.fetch_all("SELECT * FROM companies")

    def update_company(self, company_id, **kwargs):
        """Update fields formatting a given company entry."""
        if not kwargs: return
        now = vn_timestamp()
        if "original_name" in kwargs:
            kwargs["original_name"] = self.canonicalize_company_name(kwargs["original_name"])
        if "original_name" in kwargs and "original_name_key" not in kwargs:
            kwargs["original_name_key"] = self.normalize_company_name(kwargs["original_name"])
        if kwargs.get("status") == "done" and "completed_at" not in kwargs:
            kwargs["completed_at"] = now
        set_clauses = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE companies SET {set_clauses}, updated_at = ? WHERE id = ?"
        params = list(kwargs.values()) + [now, company_id]
        self.execute_query(query, params)

    def create_import_batch(self, source_filename=None, total=0, imported=0, skipped=0):
        """Create an import batch record and return its ID."""
        return self.execute_query(
            "INSERT INTO company_import_batches (source_filename, total, imported, skipped, created_at) VALUES (?, ?, ?, ?, ?)",
            (source_filename, total, imported, skipped, vn_timestamp()),
        )

    def update_import_batch(self, batch_id, **kwargs):
        if not kwargs:
            return
        set_clauses = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        params = list(kwargs.values()) + [batch_id]
        self.execute_query(f"UPDATE company_import_batches SET {set_clauses} WHERE id = ?", params)

    def get_import_batches(self, limit=25):
        return self.fetch_all(
            """
            SELECT b.*,
                   COALESCE(c.current_company_count, 0) as current_company_count,
                   COALESCE(i.imported_items, b.imported) as imported_items,
                   COALESCE(i.matched_by_tax_code, 0) as matched_by_tax_code,
                   COALESCE(i.matched_by_score, 0) as matched_by_score,
                   COALESCE(i.ambiguous, 0) as ambiguous,
                   COALESCE(i.no_match, 0) as no_match,
                   COALESCE(i.duplicate_existing, 0) as duplicate_existing,
                   COALESCE(i.duplicate_in_file, 0) as duplicate_in_file,
                   COALESCE(i.invalid, 0) as invalid
            FROM company_import_batches b
            LEFT JOIN (
                SELECT import_batch_id, COUNT(*) as current_company_count
                FROM companies
                GROUP BY import_batch_id
            ) c ON c.import_batch_id = b.id
            LEFT JOIN (
                SELECT batch_id,
                       SUM(CASE WHEN outcome = 'imported' THEN 1 ELSE 0 END) as imported_items,
                       SUM(CASE WHEN outcome = 'matched_by_tax_code' THEN 1 ELSE 0 END) as matched_by_tax_code,
                       SUM(CASE WHEN outcome = 'matched_by_score' THEN 1 ELSE 0 END) as matched_by_score,
                       SUM(CASE WHEN outcome = 'ambiguous' THEN 1 ELSE 0 END) as ambiguous,
                       SUM(CASE WHEN outcome = 'no_match' THEN 1 ELSE 0 END) as no_match,
                       SUM(CASE WHEN outcome = 'duplicate_existing' THEN 1 ELSE 0 END) as duplicate_existing,
                       SUM(CASE WHEN outcome = 'duplicate_in_file' THEN 1 ELSE 0 END) as duplicate_in_file,
                       SUM(CASE WHEN outcome = 'invalid' THEN 1 ELSE 0 END) as invalid
                FROM company_import_items
                GROUP BY batch_id
            ) i ON i.batch_id = b.id
            ORDER BY b.created_at DESC, b.id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def mark_companies_reported(
        self,
        company_ids: list[int],
        window_start: str | None = None,
        window_end: str | None = None,
        note: str | None = None,
        reported_by: str | None = "dashboard",
    ) -> dict:
        """Mark companies as reported via a user-controlled reporting checkpoint."""
        ids = []
        seen = set()
        for raw_id in company_ids or []:
            try:
                cid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if cid > 0 and cid not in seen:
                ids.append(cid)
                seen.add(cid)
        if not ids:
            return {"report_run_id": None, "marked": 0}

        now = vn_timestamp()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                INSERT INTO report_runs (created_at, window_start, window_end, note, company_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, window_start, window_end, note, len(ids)),
            )
            report_run_id = cursor.lastrowid
            for cid in ids:
                conn.execute(
                    """
                    INSERT INTO reported_companies (
                        company_id, report_run_id, reported_at, reported_by, note
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(company_id) DO UPDATE SET
                        report_run_id=excluded.report_run_id,
                        reported_at=excluded.reported_at,
                        reported_by=excluded.reported_by,
                        note=excluded.note
                    """,
                    (cid, report_run_id, now, reported_by, note),
                )
            conn.commit()
            return {"report_run_id": report_run_id, "marked": len(ids), "reported_at": now}
        except Exception:
            conn.rollback()
            raise

    def unmark_companies_reported(self, company_ids: list[int]) -> dict:
        ids = []
        seen = set()
        for raw_id in company_ids or []:
            try:
                cid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if cid > 0 and cid not in seen:
                ids.append(cid)
                seen.add(cid)
        if not ids:
            return {"unmarked": 0}
        placeholders = ",".join("?" * len(ids))
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM reported_companies WHERE company_id IN ({placeholders})", tuple(ids))
        conn.commit()
        return {"unmarked": cursor.rowcount}

    def get_reported_status_for_companies(self, company_ids: list[int]) -> dict[int, dict]:
        ids = []
        seen = set()
        for raw_id in company_ids or []:
            try:
                cid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if cid > 0 and cid not in seen:
                ids.append(cid)
                seen.add(cid)
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self.fetch_all(
            f"""
            SELECT company_id, report_run_id, reported_at, reported_by, note
            FROM reported_companies
            WHERE company_id IN ({placeholders})
            """,
            tuple(ids),
        )
        return {int(row["company_id"]): row for row in rows}


    def insert_import_item(
        self,
        batch_id,
        row_number,
        input_name,
        canonical_name,
        normalized_key,
        outcome,
        company_id=None,
        matched_company_id=None,
        reason=None,
        match_score=None,
        match_method=None,
        evidence_json=None,
    ):
        """Record one source row from a company import."""
        return self.execute_query(
            """
            INSERT INTO company_import_items (
                batch_id, row_number, input_name, canonical_name, normalized_key,
                outcome, company_id, matched_company_id, reason,
                match_score, match_method, evidence_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                row_number,
                input_name,
                canonical_name,
                normalized_key,
                outcome,
                company_id,
                matched_company_id,
                reason,
                match_score,
                match_method,
                evidence_json,
                vn_timestamp(),
            ),
        )

    def insert_match_candidate(
        self,
        batch_id,
        import_item_id,
        row_number,
        input_name,
        input_tax_code,
        candidate_company_id,
        match_score,
        match_method,
        decision,
        evidence_json,
    ):
        """Record resolver evidence for one candidate company."""
        return self.execute_query(
            """
            INSERT INTO company_match_candidates (
                batch_id, import_item_id, row_number, input_name, input_tax_code,
                candidate_company_id, match_score, match_method, decision, evidence_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                import_item_id,
                row_number,
                input_name,
                input_tax_code,
                candidate_company_id,
                match_score,
                match_method,
                decision,
                evidence_json,
                vn_timestamp(),
            ),
        )

    def has_import_items(self, batch_id):
        row = self.fetch_one(
            "SELECT COUNT(*) as cnt FROM company_import_items WHERE batch_id = ?",
            (batch_id,),
        )
        return bool(row and row["cnt"])

    def get_import_item_counts(self, batch_id):
        rows = self.fetch_all(
            """
            SELECT outcome, COUNT(*) as cnt
            FROM company_import_items
            WHERE batch_id = ?
            GROUP BY outcome
            """,
            (batch_id,),
        )
        return {row["outcome"]: row["cnt"] for row in rows}

    def delete_companies(self, company_ids):
        """Delete multiple companies and all their associated data across all tables."""
        if not company_ids: return
        placeholders = ",".join(["?"] * len(company_ids))
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Delete in order of dependencies (child to parent)
            cursor.execute(f"DELETE FROM extracted_contacts WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM scraped_pages WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM filtered_links WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM search_results WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM pipeline_logs WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM query_cache WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM pipeline_jobs WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM gemini_quick_results WHERE company_id IN ({placeholders})", company_ids)
            cursor.execute(f"DELETE FROM companies WHERE id IN ({placeholders})", company_ids)
            
            conn.commit()
            return cursor.rowcount  # Number of companies actually deleted
        except Exception as e:
            conn.rollback()
            raise e

    # --- Search Results ---
    def insert_search_result(self, company_id, search_query, search_type, result_rank, url, title, snippet, credits_used=0):
        """Insert a search result."""
        return self.execute_query(
            "INSERT INTO search_results (company_id, search_query, search_type, result_rank, url, title, snippet, credits_used, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, search_query, search_type, result_rank, url, title, snippet, credits_used, vn_timestamp())
        )

    def get_search_results_for_company(self, company_id):
        """Get all search results for a company."""
        return self.fetch_all("SELECT * FROM search_results WHERE company_id = ?", (company_id,))

    # --- Filtered Links ---
    def insert_filtered_link(self, search_result_id, company_id, url, source_type, should_scrape=True, reason=None):
        """Insert a filtered link, or reuse the existing row for this (company, url).

        The filter step runs on every pipeline attempt and would otherwise append a
        fresh row per URL each time, ballooning filtered_links and breaking the
        top-N scrape/completion logic. Reusing the existing row keeps a stable
        filtered_link_id (so scraped_pages linkage stays intact) and refreshes the
        classification fields.
        """
        existing = self.fetch_one(
            "SELECT id FROM filtered_links WHERE company_id = ? AND url = ? ORDER BY id LIMIT 1",
            (company_id, url),
        )
        if existing:
            self.execute_query(
                "UPDATE filtered_links SET source_type = ?, should_scrape = ?, reason = ? WHERE id = ?",
                (source_type, should_scrape, reason, existing["id"]),
            )
            return existing["id"]
        return self.execute_query(
            "INSERT INTO filtered_links (search_result_id, company_id, url, source_type, should_scrape, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (search_result_id, company_id, url, source_type, should_scrape, reason)
        )
        
    def get_filtered_links_for_company(self, company_id):
        """Get filtered links for a company."""
        return self.fetch_all("SELECT * FROM filtered_links WHERE company_id = ?", (company_id,))

    # --- Scraped Pages ---
    def insert_scraped_page(self, filtered_link_id, company_id, url, source_type, markdown_content, content_length, scrape_status, credits_used=0, error_message=None):
        """Insert a scraped page snippet."""
        return self.execute_query(
            "INSERT INTO scraped_pages (filtered_link_id, company_id, url, source_type, markdown_content, content_length, scrape_status, credits_used, error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filtered_link_id, company_id, url, source_type, markdown_content, content_length, scrape_status, credits_used, error_message, vn_timestamp())
        )

    def get_scraped_pages_for_company(self, company_id):
        """Get all scraped pages for a company."""
        return self.fetch_all("SELECT * FROM scraped_pages WHERE company_id = ? ORDER BY id", (company_id,))

    # --- Extracted Contacts ---
    def insert_extracted_contact(self, company_id, scraped_page_id, source_type, source_url, address, phone, email, website, fax, representative, raw_ai_response, confidence_score):
        """Insert an extracted contact generated by AI."""
        return self.execute_query(
            "INSERT INTO extracted_contacts (company_id, scraped_page_id, source_type, source_url, address, phone, email, website, fax, representative, raw_ai_response, confidence_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, scraped_page_id, source_type, source_url, address, phone, email, website, fax, representative, raw_ai_response, confidence_score, vn_timestamp())
        )

    def get_extracted_contacts_for_company(self, company_id):
        """Get all extracted contacts for a given company."""
        return self.fetch_all("SELECT * FROM extracted_contacts WHERE company_id = ?", (company_id,))

    # --- Pipeline Logs ---
    def insert_pipeline_log(self, company_id, step, status, started_at=None, finished_at=None, duration_seconds=None, source_url=None, source_name=None, credits_used=0, error_message=None, data_saved=False, metadata_json=None):
        """Insert a new pipeline log entry."""
        return self.execute_query(
            "INSERT INTO pipeline_logs (company_id, step, status, started_at, finished_at, duration_seconds, source_url, source_name, credits_used, error_message, data_saved, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, step, status, started_at, finished_at, duration_seconds, source_url, source_name, credits_used, error_message, data_saved, metadata_json)
        )

    def update_pipeline_log(self, log_id, **kwargs):
        """Update specific fields of an existing pipeline log."""
        if not kwargs: return
        set_clauses = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE pipeline_logs SET {set_clauses} WHERE id = ?"
        params = list(kwargs.values()) + [log_id]
        self.execute_query(query, params)

    def get_pipeline_logs_for_company(self, company_id):
        """Get pipeline logs for a company."""
        return self.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? ORDER BY started_at ASC", (company_id,))

    def get_pipeline_time_for_company(self, company_id: int) -> dict:
        """Get started_at and finished_at for a company, falling back to pipeline_logs if missing."""
        # Try pipeline_jobs first
        job = self.fetch_one("SELECT started_at, finished_at FROM pipeline_jobs WHERE company_id = ?", (company_id,))
        if job and job.get('started_at'):
            return {
                "started_at": job.get('started_at'),
                "finished_at": job.get('finished_at')
            }
        
        # Fallback to pipeline_logs
        logs = self.fetch_all("SELECT MIN(started_at) as min_start, MAX(finished_at) as max_finish FROM pipeline_logs WHERE company_id = ?", (company_id,))
        if logs and logs[0].get('min_start'):
            return {
                "started_at": logs[0].get('min_start'),
                "finished_at": logs[0].get('max_finish')
            }
            
        return {"started_at": None, "finished_at": None}

    # --- Query Cache ---
    def insert_query_cache(self, query_hash: str, query_text: str, company_id: int, expires_at: str, result_count: int = 0):
        return self.execute_query(
            "INSERT OR REPLACE INTO query_cache (query_hash, query_text, company_id, created_at, expires_at, result_count) VALUES (?, ?, ?, ?, ?, ?)",
            (query_hash, query_text, company_id, vn_timestamp(), expires_at, result_count)
        )

    def get_query_cache(self, query_hash: str):
        return self.fetch_one("SELECT * FROM query_cache WHERE query_hash = ?", (query_hash,))

    def is_query_cached(self, query_hash: str) -> bool:
        """Returns True if query is cached AND not expired."""
        row = self.fetch_one(
            "SELECT * FROM query_cache WHERE query_hash = ? AND (expires_at IS NULL OR expires_at > ?)",
            (query_hash, vn_timestamp())
        )
        return row is not None

    # --- URL Cache ---
    def insert_url_cache(self, url_hash: str, url: str, scrape_status: str, content_hash: str = None, ttl_expires_at: str = None):
        return self.execute_query(
            "INSERT OR REPLACE INTO url_cache (url_hash, url, scrape_status, content_hash, scraped_at, ttl_expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (url_hash, url, scrape_status, content_hash, vn_timestamp(), ttl_expires_at)
        )

    def get_url_cache(self, url_hash: str):
        return self.fetch_one("SELECT * FROM url_cache WHERE url_hash = ?", (url_hash,))

    def is_url_cached(self, url_hash: str) -> bool:
        """Returns True if URL was successfully scraped AND cache is not expired."""
        row = self.fetch_one(
            "SELECT * FROM url_cache WHERE url_hash = ? AND scrape_status = 'success' AND (ttl_expires_at IS NULL OR ttl_expires_at > ?)",
            (url_hash, vn_timestamp())
        )
        return row is not None

    # --- Filtered Links (update relevance_score) ---
    def update_filtered_link_score(self, filtered_link_id: int, relevance_score: float):
        self.execute_query(
            "UPDATE filtered_links SET relevance_score = ? WHERE id = ?",
            (relevance_score, filtered_link_id)
        )

    def get_top_scored_links(self, company_id: int, top_n: int = 10) -> list:
        """Get top N filtered links by relevance_score for a company (should_scrape=1 only).

        Deduplicates by URL (keeping the lowest id per URL) so the scraper spends
        its top_n budget on distinct URLs. filtered_links are re-inserted on every
        pipeline run, so without this the top_n slots fill up with duplicate copies
        of one or two high-scoring URLs and the remaining distinct links never get
        scraped. Uses the same MIN(id) keying as the completion audit so the two
        stay aligned.
        """
        return self.fetch_all(
            """
            SELECT * FROM filtered_links
            WHERE company_id = ? AND should_scrape = 1
              AND id IN (
                  SELECT MIN(id) FROM filtered_links
                  WHERE company_id = ? AND should_scrape = 1
                  GROUP BY url
              )
            ORDER BY relevance_score DESC, id
            LIMIT ?
            """,
            (company_id, company_id, top_n)
        )

    # --- Export Data Helpers ---
    def get_gemini_quick_results_for_company(self, company_id: int):
        """Get Gemini Quick Search results for a company."""
        return self.fetch_all("SELECT * FROM gemini_quick_results WHERE company_id = ?", (company_id,))

    def get_deep_scrape_export_data_for_company(self, company_id: int):
        """Get joined deep scrape data for CSV export for a company."""
        query = """
            SELECT 
                sr.created_at AS timestamp,
                sr.url AS search_url,
                sr.search_query,
                sr.result_rank,
                sr.snippet AS search_snippet,
                sr.credits_used AS search_credits,
                fl.should_scrape,
                fl.source_type AS filter_source_type,
                fl.relevance_score,
                fl.reason AS filter_reason,
                sp.source_type AS scrape_source_type,
                sp.scrape_status,
                sp.credits_used AS scrape_credits,
                sp.error_message,
                ec.source_url,
                ec.address,
                ec.phone,
                ec.email,
                ec.website,
                ec.fax,
                ec.representative,
                ec.confidence_score,
                ec.raw_ai_response
            FROM search_results sr
            LEFT JOIN filtered_links fl ON sr.id = fl.search_result_id
            LEFT JOIN scraped_pages sp ON fl.id = sp.filtered_link_id
            LEFT JOIN extracted_contacts ec ON sp.id = ec.scraped_page_id
            WHERE sr.company_id = ?
        """
        return self.fetch_all(query, (company_id,))

    # --- Domain Stats (Auto-Blacklist) ---
    def record_domain_scrape(self, domain: str, success: bool, threshold: int = 10):
        """Record a scrape attempt for a domain and auto-blacklist if it fails too many times."""
        now = vn_timestamp()
        # Insert if not exists
        self.execute_query(
            "INSERT OR IGNORE INTO domain_stats (domain, updated_at) VALUES (?, ?)",
            (domain, now)
        )
        
        # Update counts
        if success:
            self.execute_query(
                "UPDATE domain_stats SET scrape_count = scrape_count + 1, success_count = success_count + 1, updated_at = ? WHERE domain = ?",
                (now, domain)
            )
        else:
            self.execute_query(
                "UPDATE domain_stats SET scrape_count = scrape_count + 1, updated_at = ? WHERE domain = ?",
                (now, domain)
            )
            
        # Check auto-blacklist threshold
        stat = self.fetch_one("SELECT scrape_count, success_count, is_auto_blacklisted FROM domain_stats WHERE domain = ?", (domain,))
        if stat and not stat['is_auto_blacklisted'] and stat['scrape_count'] >= threshold and stat['success_count'] == 0:
            self.execute_query("UPDATE domain_stats SET is_auto_blacklisted = 1 WHERE domain = ?", (domain,))

    def get_auto_blacklisted_domains(self) -> list[str]:
        """Get list of auto-blacklisted domains."""
        rows = self.fetch_all("SELECT domain FROM domain_stats WHERE is_auto_blacklisted = 1")
        return [row['domain'] for row in rows]
        
    def get_domain_stats(self):
        """Get all domain stats for settings UI."""
        return self.fetch_all("SELECT * FROM domain_stats ORDER BY scrape_count DESC")
        
    def remove_auto_blacklist(self, domain: str):
        """Manually remove a domain from auto-blacklist and reset its counts."""
        self.execute_query(
            "UPDATE domain_stats SET is_auto_blacklisted = 0, scrape_count = 0, success_count = 0 WHERE domain = ?",
            (domain,)
        )
