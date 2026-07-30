import time
import os
import signal
import sys
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.search_module import SearchModule
from src.filter_module import LinkFilter
from src.scrape_module import ScrapeModule
from src.excel_handler import ExcelReader, ExcelWriter
from src.ai_extractor import AIExtractor
from src.result_aggregator import ResultAggregator
from src.gemini_quick_search import GeminiQuickSearch
from src.firecrawl_deep_search import FirecrawlDeepSearch
from src.business_status import INACTIVE_STOP, extract_business_status
from src.time_utils import vn_date_str, vn_filename_timestamp, vn_now, vn_timestamp
from src.errors import PipelineError, RetryableError, SkippableError, CriticalError
from src.completion_audit import audit_company_completion
from src.company_run import CompanyRun


class Pipeline:
    """Pipeline orchestrator with resume, checkpoint, and graceful shutdown support."""

    # Status progression: pending → gemini_quick_done → searched → scraped → ai_extract_pending → ai_done → done
    # Failed states: failed, permanently_failed
    STATUS_FLOW = {
        'pending':              'gemini_quick',
        'gemini_quick':         'gemini_quick',     # interrupted during gemini quick
        'gemini_quick_done':    'deep_search',      # gemini done → deep search
        'searching':            'deep_search',      # interrupted during deep search
        'searched':             'filter',
        'scraping':             'filter',           # interrupted during scrape — redo filter+scrape
        'scraped':              'ai_extract',
        'ai_extract_pending':   'ai_extract',       # ★ CHECKPOINT: scraped done, AI not yet run → skip scrape on resume
        'extracting':           'ai_extract',       # interrupted during extraction
        'ai_done':              'done',
        'failed':               'gemini_quick',     # retry from beginning
    }

    def __init__(self, config: dict, pipeline_config=None):
        # existing dict-based config stays for backward compat
        self.config = config
        self.firecrawl_api_key = config.get("firecrawl_api_key") or os.getenv("FIRECRAWL_API_KEY", "")
        self.input_excel_path = config.get("input_excel_path")
        self.output_dir = config.get("output_dir", "output")
        self.delay_seconds = config.get("delay_seconds", 3.0)
        self.batch_size = config.get("batch_size", 10)

        # Ensure output dir exists
        os.makedirs(self.output_dir, exist_ok=True)

        self.db = DatabaseManager()
        self.logger = PipelineLogger(self.db)

        # New: load typed Config object
        from src.config import Config, default_config
        if pipeline_config is not None:
            self.cfg = pipeline_config
        else:
            self.cfg = default_config

        # Pass cfg to sub-modules
        self.search_module = SearchModule(self.db, self.logger, self.firecrawl_api_key, config=self.cfg)
        self.filter_module = LinkFilter(self.db, self.logger, config=self.cfg)
        self.scrape_module = ScrapeModule(self.db, self.logger, self.firecrawl_api_key, config=self.cfg)

        # New modules for 4-step pipeline
        self.gemini_quick = GeminiQuickSearch(self.db, self.logger, config=self.cfg)
        self.deep_search = FirecrawlDeepSearch(self.db, self.logger, config=self.cfg)

        self.gemini_api_key = config.get("gemini_api_key")

        # We handle AIExtractor gracefully if GEMINI_API_KEY doesn't exist yet for legacy scripts
        self.ai_extractor = None
        if self.cfg.GEMINI_API_KEY:
            self.ai_extractor = AIExtractor(self.db, self.logger, config=self.cfg)

        self.result_aggregator = ResultAggregator(self.db)

        # Batch statistics for summary report
        self._batch_stats = self._init_batch_stats()

        self.excel_reader = ExcelReader()
        self.excel_writer = ExcelWriter()

        # Graceful shutdown support
        self._shutdown_requested = False
        self._original_sigint_handler = None
        self._original_sigterm_handler = None
        self.company_run = CompanyRun(self)

    # ------------------------------------------------------------------
    # Signal handling for graceful shutdown
    # ------------------------------------------------------------------

    def _install_signal_handlers(self):
        """Install signal handlers for SIGINT and SIGTERM to enable graceful shutdown."""
        self._shutdown_requested = False
        try:
            self._original_sigint_handler = signal.getsignal(signal.SIGINT)
            self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            self._original_sigint_handler = None
            self._original_sigterm_handler = None
            print("⚠️ Running in background thread. Skipping graceful signal handling.")

    def _restore_signal_handlers(self):
        """Restore original signal handlers after pipeline run completes."""
        try:
            if self._original_sigint_handler is not None:
                signal.signal(signal.SIGINT, self._original_sigint_handler)
            if self._original_sigterm_handler is not None:
                signal.signal(signal.SIGTERM, self._original_sigterm_handler)
        except ValueError:
            pass

    def _signal_handler(self, signum, frame):
        """Handle SIGINT/SIGTERM by setting a flag to stop after current company."""
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        print(f"\n⚠️  Nhận tín hiệu {sig_name}. Đang dừng an toàn...")
        print("   Hoàn thành công ty hiện tại trước khi thoát.")
        self._shutdown_requested = True

    # ------------------------------------------------------------------
    # Helper: determine next step for a company based on its status
    # ------------------------------------------------------------------

    def _get_next_step(self, status: str) -> str:
        """Determine which pipeline step to resume from based on company status."""
        return self.STATUS_FLOW.get(status, 'search')

    def _should_do_step(self, next_step: str, target_step: str) -> bool:
        """Check if a given target_step should be executed given the next_step.

        Pipeline order: gemini_quick → deep_search → filter → scrape → ai_extract
        If next_step is 'filter', we skip gemini_quick and deep_search but do filter, scrape, etc.
        """
        if next_step == 'done':
            return False
        step_order = ['gemini_quick', 'deep_search', 'filter', 'scrape', 'ai_extract']
        if next_step not in step_order or target_step not in step_order:
            return True
        return step_order.index(target_step) >= step_order.index(next_step)

    def _company_has_no_phone(self, company_id: int) -> bool:
        """Returns True if no phone number was extracted for this company."""
        row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM extracted_contacts WHERE company_id = ? AND phone IS NOT NULL AND phone != ''",
            (company_id,)
        )
        return (row['cnt'] if row else 0) == 0

    def _status_gate_candidate_links(self, company_id: int) -> list[dict]:
        status_domains = (
            "masothue.com", "thuvienphapluat.vn", "congtydoanhnghiep.com",
            "doanhnghiep.biz", "thongtincongty.vn", "tratencongty.com",
            "yp.vn", "mytour.vn",
        )
        rows = self.db.fetch_all(
            """
            SELECT * FROM filtered_links
            WHERE company_id = ?
            ORDER BY should_scrape DESC, relevance_score DESC
            """,
            (company_id,),
        )

        def priority(row):
            url = (row.get("url") or "").lower()
            for idx, domain in enumerate(status_domains):
                if domain in url:
                    return idx
            return len(status_domains)

        candidates = [
            row for row in rows
            if priority(row) < len(status_domains)
            and "masothue_tax_mismatch" not in (row.get("reason") or "")
            and row.get("source_type") not in {"blacklisted", "social", "facebook", "linkedin"}
        ]
        candidates.sort(key=lambda row: (priority(row), -float(row.get("relevance_score") or 0)))
        return candidates[:3]

    def _run_business_status_gate(self, company_id: int, replay_mode: bool = False) -> dict | None:
        if not getattr(self.cfg, "BUSINESS_STATUS_GATE_ENABLED", True):
            return None

        candidates = self._status_gate_candidate_links(company_id)
        if not candidates:
            return None

        for link in candidates:
            if not replay_mode:
                self.scrape_module.scrape_url(link["id"])
            page = self.db.fetch_one(
                """
                SELECT * FROM scraped_pages
                WHERE filtered_link_id = ? AND scrape_status = 'success'
                ORDER BY id DESC LIMIT 1
                """,
                (link["id"],),
            )
            if not page:
                continue
            status = extract_business_status(page.get("markdown_content"))
            if not status:
                continue
            self.db.update_company(
                company_id,
                business_status=status["business_status"],
                business_status_category=status["business_status_category"],
                business_status_source_url=page.get("url"),
            )
            self.logger.log_event("business_status_detected", company_id, {
                "business_status": status["business_status"],
                "business_status_category": status["business_status_category"],
                "source_url": page.get("url"),
            })
            return status
        return None

    # ------------------------------------------------------------------
    # Core run method (upgraded with resume + checkpoint + graceful shutdown
    #                   + contact discovery + replay mode + force refresh)
    # ------------------------------------------------------------------

    def run(self, company_ids: list[int] = None, limit: int = None, offset: int = 0,
            replay_mode: bool = False, force_refresh: bool = False, job_controller=None):
        """Execute the pipeline for a list of companies with resume and checkpoint support.

        Args:
            company_ids: Specific company IDs to process. If None, fetches from DB.
            limit: Maximum number of companies to process.
            offset: Number of companies to skip from the beginning.
            replay_mode: If True, skip all API-calling steps and re-process from cached DB data.
            force_refresh: If True, temporarily bypass caches for search/scrape steps.
            job_controller: Optional worker adapter for job heartbeat, progress and stop requests.
        """
        if not company_ids:
            companies = self.db.get_all_companies()
            if offset > 0:
                companies = companies[offset:]
            if limit:
                companies = companies[:limit]
            company_ids = [c["id"] for c in companies]

        total_to_process = len(company_ids)
        print(f"Starting pipeline for {total_to_process} companies...")

        # Replay / force-refresh notices
        if replay_mode:
            print("[REPLAY MODE] Re-processing from cached DB data. No API calls.")
        if force_refresh:
            print("[FORCE REFRESH] Cache bypass enabled.")

        # Install signal handlers for graceful shutdown
        self._install_signal_handlers()

        success_count = 0
        fail_count = 0
        skip_count = 0

        try:
            for idx, company_id in enumerate(company_ids):
                if job_controller is not None and job_controller.should_stop(company_id):
                    self._shutdown_requested = True

                if self._shutdown_requested:
                    print(f"\n🛑 Dừng an toàn tại công ty {idx}/{total_to_process}. Dữ liệu đã được lưu. Dùng --resume để tiếp tục.")
                    break

                result = self.company_run.run(
                    company_id,
                    replay_mode=replay_mode,
                    force_refresh=force_refresh,
                    job_controller=job_controller,
                )
                outcome = (result or {}).get("outcome")
                if outcome == "success":
                    success_count += 1
                elif outcome == "failed":
                    fail_count += 1
                elif outcome == "skipped":
                    skip_count += 1
                elif outcome in ("shutdown", "stopped"):
                    break

        finally:
            self._restore_signal_handlers()

        self._batch_stats["total"] = total_to_process
        self._batch_stats["success"] = success_count
        self._batch_stats["failed"] = fail_count
        self._batch_stats["skipped"] = skip_count
        self._print_batch_summary()

        if self._shutdown_requested:
            print("⚠️  Pipeline đã dừng an toàn do nhận tín hiệu. Chạy lại với --resume để tiếp tục.")

    def run_company(self, company_id: int, replay_mode: bool = False, force_refresh: bool = False, job_controller=None):
        return self.company_run.run(
            company_id,
            replay_mode=replay_mode,
            force_refresh=force_refresh,
            job_controller=job_controller,
        )

    # ------------------------------------------------------------------
    # Batch stats & summary report
    # ------------------------------------------------------------------

    @staticmethod
    def _init_batch_stats() -> dict:
        return {
            "total": 0, "success": 0, "failed": 0, "skipped": 0,
            "step1_success": 0, "step2_success": 0,
            "no_phone": 0,
            "gemini_tokens_in": 0, "gemini_tokens_out": 0,
            "serper_credits": 0, "firecrawl_credits": 0,
            "urls_deduped": 0,
            "status_gate_skipped": 0,
        }

    def _print_batch_summary(self):
        s = self._batch_stats
        today = vn_date_str()

        # Get daily quota used
        quota_row = self.db.fetch_one(
            "SELECT gemini_grounding_used, serper_used FROM daily_quota WHERE date = ?",
            (today,)
        )
        gemini_used = quota_row["gemini_grounding_used"] if quota_row else 0
        serper_used = quota_row["serper_used"] if quota_row else 0

        processed = s["total"] - s["skipped"]
        print(f"""
═══════════════════════════════════════════
  BÁO CÁO PIPELINE - {today}
═══════════════════════════════════════════
  Tổng công ty xử lý:            {processed}
  Bước 1 thành công (Gemini):     {s['step1_success']} ({s['step1_success']/max(processed,1)*100:.0f}%)
  Bước 2 thành công (Deep):       {s['step2_success']}
  Không tìm được phone:           {s['no_phone']}
  Thất bại (lỗi):                 {s['failed']}
  ─────────────────────────────────────────
  Gemini Grounding requests:      {gemini_used} / {self.cfg.GEMINI_DAILY_LIMIT}
  Gemini tokens (input):          {s['gemini_tokens_in']:,}
  Gemini tokens (output):         {s['gemini_tokens_out']:,}
  Serper credits (hôm nay):       {serper_used}
  URLs trùng lặp đã loại:         {s['urls_deduped']}
  Status gate đã bỏ qua:          {s['status_gate_skipped']}
═══════════════════════════════════════════""")

    # ------------------------------------------------------------------
    # Manual step execution
    # ------------------------------------------------------------------

    def run_step(self, step: str, company_id: int, **kwargs):
        """Run a single pipeline step for one company. For manual/debug use.

        Args:
            step: One of 'search', 'filter', 'scrape', 'ai_extract'
            company_id: Company to process
            **kwargs: Step-specific overrides (e.g. delay_seconds)
        """
        delay = kwargs.get('delay_seconds', self.delay_seconds)

        if step == 'search':
            self.search_module.search_company(company_id)
            self.db.update_company(company_id, status='searched')
        elif step == 'filter':
            self.filter_module.filter_company_links(company_id)
        elif step == 'scrape':
            self.scrape_module.scrape_company(company_id, delay)
            self.db.update_company(company_id, status='scraped')
        elif step == 'ai_extract':
            if self.ai_extractor:
                self.db.update_company(company_id, status='extracting')
                self.ai_extractor.extract_for_company(company_id, delay)
                self.db.update_company(company_id, status='ai_done')
        else:
            raise ValueError(f"Unknown step: {step}. Valid: search, filter, scrape, ai_extract")

    # ------------------------------------------------------------------
    # Manual URL injection
    # ------------------------------------------------------------------

    def inject_search_results(self, company_id: int, urls: list[str]):
        """Inject custom URLs as search results for a company (bypasses Firecrawl search).

        Useful for manual testing with known URLs.

        Args:
            company_id: Target company
            urls: List of URL strings to inject
        """
        for i, url in enumerate(urls):
            self.db.insert_search_result(
                company_id=company_id,
                search_query="__manual_inject__",
                search_type="manual",
                result_rank=i + 1,
                url=url,
                title="",
                snippet="",
                credits_used=0
            )
        self.db.update_company(company_id, status='searched')
        print(f"Injected {len(urls)} URLs for company {company_id}")

    # ------------------------------------------------------------------
    # Resume method (upgraded)
    # ------------------------------------------------------------------

    def resume(self):
        """Resume pipeline from where it was interrupted.

        Finds all companies that are not 'done' or 'permanently_failed'
        and processes them in order.
        """
        resumable = self.get_resumable_companies()

        if not resumable:
            print("✅ No companies to resume. All done!")
            return

        company_ids = [c["company_id"] for c in resumable]

        print(f"Resuming pipeline for {len(company_ids)} companies...")
        for item in resumable[:5]:  # Show first 5
            print(f"  - Company ID {item['company_id']}: status={item['status']}, next_step={item['next_step']}")
        if len(resumable) > 5:
            print(f"  ... and {len(resumable) - 5} more")

        self.run(company_ids=company_ids)

    # ------------------------------------------------------------------
    # Get resumable companies
    # ------------------------------------------------------------------

    def get_resumable_companies(self) -> list[dict]:
        """Get list of companies that need processing, with their current status and next step.

        Returns:
            List of dicts: [{"company_id": int, "status": str, "next_step": str, "retry_count": int}, ...]
        """
        companies = self.db.get_all_companies()
        resumable = []

        for company in companies:
            status = company['status']

            # Skip completed or permanently failed
            if status in ('done', 'permanently_failed'):
                continue

            next_step = self._get_next_step(status)

            # Count how many times this company has failed (from pipeline_logs)
            fail_logs = self.db.fetch_all(
                "SELECT COUNT(*) as cnt FROM pipeline_logs WHERE company_id = ? AND status = 'failed'",
                (company['id'],)
            )
            retry_count = fail_logs[0]['cnt'] if fail_logs else 0

            resumable.append({
                "company_id": company['id'],
                "company_name": company['original_name'],
                "status": status,
                "next_step": next_step,
                "retry_count": retry_count
            })

        return resumable

    # ------------------------------------------------------------------
    # Retry failed companies
    # ------------------------------------------------------------------

    def retry_failed(self, max_retries: int = 2):
        """Retry all companies with status='failed'.

        Args:
            max_retries: Maximum number of retry attempts. Companies that fail
                         beyond this limit are marked as 'permanently_failed'.
        """
        failed_companies = self.db.fetch_all(
            "SELECT * FROM companies WHERE status = 'failed'"
        )

        if not failed_companies:
            print("✅ No failed companies to retry.")
            return

        print(f"Found {len(failed_companies)} failed companies to retry (max_retries={max_retries})...")

        for company in failed_companies:
            company_id = company['id']
            company_name = company['original_name']

            # Count previous failures for this company
            fail_logs = self.db.fetch_all(
                "SELECT COUNT(DISTINCT started_at) as cnt FROM pipeline_logs "
                "WHERE company_id = ? AND status = 'failed' AND step = 'search'",
                (company_id,)
            )
            retry_count = fail_logs[0]['cnt'] if fail_logs else 0

            if retry_count >= max_retries:
                print(f"  ❌ Company {company_id} ({company_name}): exceeded max_retries ({retry_count}/{max_retries}) → permanently_failed")
                self.db.update_company(company_id, status='permanently_failed')
                continue

            print(f"  🔄 Retrying company {company_id} ({company_name}): attempt {retry_count + 1}/{max_retries}...")

            # Reset status to pending so run() processes it from scratch
            self.db.update_company(company_id, status='pending')

        # Now run the pipeline for the companies we just reset
        pending_companies = self.db.fetch_all(
            "SELECT id FROM companies WHERE status = 'pending'"
        )
        if pending_companies:
            company_ids = [c['id'] for c in pending_companies]
            self.run(company_ids=company_ids)

    # ------------------------------------------------------------------
    # Report generation (kept from Phase 3)
    # ------------------------------------------------------------------

    def generate_report(self, output_path: str):
        """Generate final Excel report with aggregated data."""
        print(f"Generating report at {output_path}...")

        # Use ResultAggregator for Phase 3 logic
        aggregated_data = self.result_aggregator.aggregate_all()
        summary_stats = self.result_aggregator.generate_summary_stats(aggregated_data)

        # Check if new write_final_report is available, otherwise fallback
        if hasattr(self.excel_writer, "write_final_report"):
            self.excel_writer.write_final_report(output_path, aggregated_data, summary_stats)
            print("Final Report generated using write_final_report.")
        else:
            # Fallback backward compatibility code
            companies = self.db.get_all_companies()
            results = []

            for company in companies:
                if hasattr(self.db, "get_scraped_pages_for_company"):
                    scraped_pages = self.db.get_scraped_pages_for_company(company["id"])
                else:
                    try:
                        conn = getattr(self.db, "conn")
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM scraped_pages WHERE company_id=?", (company["id"],))
                        columns = [description[0] for description in cursor.description]
                        scraped_pages = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    except:
                        scraped_pages = []

                sources = []
                for sp in scraped_pages:
                    sources.append({
                        "source": sp.get("source_type", ""),
                        "address": sp.get("url", ""),
                        "phone": f"Length: {sp.get('content_length', 0)}",
                        "email": sp.get("scrape_status", ""),
                        "date": vn_date_str()
                    })

                results.append({
                    "name": company.get("original_name", ""),
                    "tax_code": company.get("tax_code", ""),
                    "sources": sources
                })

            self.excel_writer.write_results(output_path, results)
            print("Report generated using fallback logic.")
