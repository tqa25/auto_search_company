import sqlite3
import os
import threading

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
            conn.execute("PRAGMA busy_timeout=5000")
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
                vietnamese_name TEXT,
                tax_code TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Safe migration: add address and vn_data_source to existing companies table
        try:
            cursor.execute("ALTER TABLE companies ADD COLUMN address TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE companies ADD COLUMN vn_data_source TEXT")
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ttl_expires_at TIMESTAMP
            )
        """)

        # index for pipeline_logs
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_logs_company_step
            ON pipeline_logs(company_id, step)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 10. daily_quota — Track daily API usage to avoid charges
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_quota (
                date TEXT PRIMARY KEY,
                gemini_grounding_used INTEGER DEFAULT 0,
                serper_used INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                error_message TEXT,
                removed_from_monitor BOOLEAN DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status_updated
            ON pipeline_jobs(status, updated_at)
        """)

        conn.commit()

        # Run pending schema migrations
        from src.migrations import run_migrations
        run_migrations(self)

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

    # --- Companies ---
    def insert_company(self, original_name, vietnamese_name=None, tax_code=None, status="pending"):
        """Insert a new company into the companies table."""
        return self.execute_query(
            "INSERT INTO companies (original_name, vietnamese_name, tax_code, status) VALUES (?, ?, ?, ?)",
            (original_name, vietnamese_name, tax_code, status)
        )

    def get_company(self, company_id):
        """Retrieve a company by its ID."""
        return self.fetch_one("SELECT * FROM companies WHERE id = ?", (company_id,))

    def get_all_companies(self):
        """Retrieve all companies."""
        return self.fetch_all("SELECT * FROM companies")

    def update_company(self, company_id, **kwargs):
        """Update fields formatting a given company entry."""
        if not kwargs: return
        set_clauses = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        query = f"UPDATE companies SET {set_clauses}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        params = list(kwargs.values()) + [company_id]
        self.execute_query(query, params)

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
            "INSERT INTO search_results (company_id, search_query, search_type, result_rank, url, title, snippet, credits_used) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, search_query, search_type, result_rank, url, title, snippet, credits_used)
        )

    def get_search_results_for_company(self, company_id):
        """Get all search results for a company."""
        return self.fetch_all("SELECT * FROM search_results WHERE company_id = ?", (company_id,))

    # --- Filtered Links ---
    def insert_filtered_link(self, search_result_id, company_id, url, source_type, should_scrape=True, reason=None):
        """Insert a filtered link."""
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
            "INSERT INTO scraped_pages (filtered_link_id, company_id, url, source_type, markdown_content, content_length, scrape_status, credits_used, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (filtered_link_id, company_id, url, source_type, markdown_content, content_length, scrape_status, credits_used, error_message)
        )

    def get_scraped_pages_for_company(self, company_id):
        """Get all scraped pages for a company."""
        return self.fetch_all("SELECT * FROM scraped_pages WHERE company_id = ?", (company_id,))

    # --- Extracted Contacts ---
    def insert_extracted_contact(self, company_id, scraped_page_id, source_type, source_url, address, phone, email, website, fax, representative, raw_ai_response, confidence_score):
        """Insert an extracted contact generated by AI."""
        return self.execute_query(
            "INSERT INTO extracted_contacts (company_id, scraped_page_id, source_type, source_url, address, phone, email, website, fax, representative, raw_ai_response, confidence_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, scraped_page_id, source_type, source_url, address, phone, email, website, fax, representative, raw_ai_response, confidence_score)
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

    # --- Query Cache ---
    def insert_query_cache(self, query_hash: str, query_text: str, company_id: int, expires_at: str, result_count: int = 0):
        return self.execute_query(
            "INSERT OR REPLACE INTO query_cache (query_hash, query_text, company_id, expires_at, result_count) VALUES (?, ?, ?, ?, ?)",
            (query_hash, query_text, company_id, expires_at, result_count)
        )

    def get_query_cache(self, query_hash: str):
        return self.fetch_one("SELECT * FROM query_cache WHERE query_hash = ?", (query_hash,))

    def is_query_cached(self, query_hash: str) -> bool:
        """Returns True if query is cached AND not expired."""
        row = self.fetch_one(
            "SELECT * FROM query_cache WHERE query_hash = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            (query_hash,)
        )
        return row is not None

    # --- URL Cache ---
    def insert_url_cache(self, url_hash: str, url: str, scrape_status: str, content_hash: str = None, ttl_expires_at: str = None):
        return self.execute_query(
            "INSERT OR REPLACE INTO url_cache (url_hash, url, scrape_status, content_hash, ttl_expires_at) VALUES (?, ?, ?, ?, ?)",
            (url_hash, url, scrape_status, content_hash, ttl_expires_at)
        )

    def get_url_cache(self, url_hash: str):
        return self.fetch_one("SELECT * FROM url_cache WHERE url_hash = ?", (url_hash,))

    def is_url_cached(self, url_hash: str) -> bool:
        """Returns True if URL was successfully scraped AND cache is not expired."""
        row = self.fetch_one(
            "SELECT * FROM url_cache WHERE url_hash = ? AND scrape_status = 'success' AND (ttl_expires_at IS NULL OR ttl_expires_at > CURRENT_TIMESTAMP)",
            (url_hash,)
        )
        return row is not None

    # --- Filtered Links (update relevance_score) ---
    def update_filtered_link_score(self, filtered_link_id: int, relevance_score: float):
        self.execute_query(
            "UPDATE filtered_links SET relevance_score = ? WHERE id = ?",
            (relevance_score, filtered_link_id)
        )

    def get_top_scored_links(self, company_id: int, top_n: int = 10) -> list:
        """Get top N filtered links by relevance_score for a company (should_scrape=1 only)."""
        return self.fetch_all(
            "SELECT * FROM filtered_links WHERE company_id = ? AND should_scrape = 1 ORDER BY relevance_score DESC LIMIT ?",
            (company_id, top_n)
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
                fl.relevance_score,
                fl.reason AS filter_reason,
                sp.scrape_status,
                sp.credits_used AS scrape_credits,
                sp.error_message,
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
