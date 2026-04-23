import sqlite3
import os

class DatabaseManager:
    """Manages the SQLite database for the company data extraction pipeline."""

    def __init__(self, db_path="data/company_data.db"):
        """Initialize the DatabaseManager with the given database path."""
        self.db_path = db_path
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize the database tables and indexes."""
        with self._get_connection() as conn:
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
                    reason TEXT
                )
            """)

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

            # index for pipeline_logs
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pipeline_logs_company_step 
                ON pipeline_logs(company_id, step)
            """)

            conn.commit()

    # Generic method for inserting/updating to avoid redundant code
    def execute_query(self, query, params=()):
        """Execute a general query that doesn't return rows (INSERT/UPDATE/DELETE)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid

    def fetch_all(self, query, params=()):
        """Execute a query and return all rows."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def fetch_one(self, query, params=()):
        """Execute a query and return the first row."""
        with self._get_connection() as conn:
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

