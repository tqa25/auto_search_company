import time
import os
import json
import signal
import sys
from datetime import datetime
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.search_module import SearchModule
from src.filter_module import LinkFilter
from src.scrape_module import ScrapeModule
from src.scrape_module import ScrapeModule
from src.excel_handler import ExcelReader, ExcelWriter
from src.ai_extractor import AIExtractor
from src.result_aggregator import ResultAggregator

class Pipeline:
    """Pipeline orchestrator with resume, checkpoint, and graceful shutdown support."""

    # Status progression: pending → searched → scraped → done
    # Failed states: failed, permanently_failed
    STATUS_FLOW = {
        'pending': 'search',
        'searching': 'search',       # interrupted during search
        'searched': 'filter',
        'scraping': 'filter',        # interrupted during scrape — redo filter+scrape
        'scraped': 'ai_extract',
        'extracting': 'ai_extract',  # interrupted during extraction
        'failed': 'search',          # retry from beginning
    }

    def __init__(self, config: dict):
        self.config = config
        self.firecrawl_api_key = config.get("firecrawl_api_key")
        self.input_excel_path = config.get("input_excel_path")
        self.output_dir = config.get("output_dir", "output")
        self.delay_seconds = config.get("delay_seconds", 3.0)
        self.batch_size = config.get("batch_size", 10)
        
        # Ensure output dir exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.db = DatabaseManager()
        self.logger = PipelineLogger(self.db)
        self.search_module = SearchModule(self.db, self.logger, self.firecrawl_api_key)
        self.filter_module = LinkFilter(self.db, self.logger)
        self.scrape_module = ScrapeModule(self.db, self.logger, self.firecrawl_api_key)
        
        self.gemini_api_key = config.get("gemini_api_key")
        
        # We handle AIExtractor gracefully if GEMINI API KEY doesn't exist yet for legacy scripts
        self.ai_extractor = None
        if self.gemini_api_key:
            self.ai_extractor = AIExtractor(self.db, self.logger, self.gemini_api_key)
            
        self.result_aggregator = ResultAggregator(self.db)
        
        self.excel_reader = ExcelReader()
        self.excel_writer = ExcelWriter()
        
        # Graceful shutdown support
        self._shutdown_requested = False
        self._original_sigint_handler = None
        self._original_sigterm_handler = None

    # ------------------------------------------------------------------
    # Signal handling for graceful shutdown
    # ------------------------------------------------------------------

    def _install_signal_handlers(self):
        """Install signal handlers for SIGINT and SIGTERM to enable graceful shutdown."""
        self._shutdown_requested = False
        self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _restore_signal_handlers(self):
        """Restore original signal handlers after pipeline run completes."""
        if self._original_sigint_handler is not None:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
        if self._original_sigterm_handler is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)

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
        
        Pipeline order: search → filter → scrape → ai_extract
        If next_step is 'filter', we skip search but do filter, scrape, ai_extract.
        """
        step_order = ['search', 'filter', 'scrape', 'ai_extract']
        if next_step not in step_order or target_step not in step_order:
            return True
        return step_order.index(target_step) >= step_order.index(next_step)

    # ------------------------------------------------------------------
    # Core run method (upgraded with resume + checkpoint + graceful shutdown)
    # ------------------------------------------------------------------

    def run(self, company_ids: list[int] = None, limit: int = None, offset: int = 0):
        """Execute the pipeline for a list of companies with resume and checkpoint support.
        
        Args:
            company_ids: Specific company IDs to process. If None, fetches from DB.
            limit: Maximum number of companies to process.
            offset: Number of companies to skip from the beginning.
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
        
        # Install signal handlers for graceful shutdown
        self._install_signal_handlers()
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        try:
            for idx, company_id in enumerate(company_ids):
                # Check for graceful shutdown
                if self._shutdown_requested:
                    print(f"\n🛑 Dừng an toàn tại công ty {idx}/{total_to_process}. "
                          f"Dữ liệu đã được lưu. Dùng --resume để tiếp tục.")
                    break

                company = self.db.get_company(company_id)
                if not company:
                    print(f"[{idx+1}/{total_to_process}] Company ID {company_id} not found in DB.")
                    fail_count += 1
                    continue
                    
                status = company['status']
                company_name = company['original_name']
                
                print(f"[{idx+1}/{total_to_process}] Processing company ID {company_id} - {company_name} (status: {status})...")
                
                # Skip already completed companies
                if status == 'done':
                    print(f"  -> Skipping (already completed)")
                    skip_count += 1
                    continue
                
                # Skip permanently failed companies
                if status == 'permanently_failed':
                    print(f"  -> Skipping (permanently failed)")
                    skip_count += 1
                    continue
                    
                # Determine which step to resume from
                next_step = self._get_next_step(status)
                if next_step != 'search':
                    print(f"  -> Resuming from step: {next_step} (previous status: {status})")
                    
                try:
                    # 1. SEARCH (skip if already searched/scraped)
                    if self._should_do_step(next_step, 'search'):
                        print("  -> Searching...")
                        self.search_module.search_company(company_id)
                        # Checkpoint: mark as searched
                        self.db.update_company(company_id, status='searched')
                        time.sleep(self.delay_seconds)
                    
                    # 2. FILTER (idempotent, can always rerun)
                    if self._should_do_step(next_step, 'filter'):
                        print("  -> Filtering...")
                        self.filter_module.filter_company_links(company_id)
                        # Note: filter doesn't change status (fast, no credits)
                    
                    # 3. SCRAPE
                    if self._should_do_step(next_step, 'scrape'):
                        print("  -> Scraping...")
                        self.scrape_module.scrape_company(company_id, self.delay_seconds)
                        # Checkpoint: mark as scraped
                        self.db.update_company(company_id, status='scraped')
                    
                    # 4. AI EXTRACT
                    if self._should_do_step(next_step, 'ai_extract'):
                        if self.ai_extractor:
                            print("  -> AI Extracting...")
                            self.db.update_company(company_id, status='extracting')
                            self.ai_extractor.extract_for_company(company_id, self.delay_seconds)
                            # Checkpoint: mark as done
                            self.db.update_company(company_id, status='done')
                        else:
                            print("  -> AI Extract SKIP (no API Key)")
                            # If no AI key, mark as done after scrape
                            self.db.update_company(company_id, status='done')
                    
                    print(f"  -> SUCCESS: Processed {company_name}")
                    success_count += 1
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"  -> FAILED: Error processing {company_name}: {error_msg}")
                    self.db.update_company(company_id, status='failed')
                    fail_count += 1
                    
        finally:
            # Always restore signal handlers
            self._restore_signal_handlers()
                    
        print("\n=== PIPELINE EXECUTION COMPLETED ===")
        print(f"Total: {total_to_process} | Success: {success_count} | Failed: {fail_count} | Skipped: {skip_count}")
        
        if self._shutdown_requested:
            print("⚠️  Pipeline đã dừng an toàn do nhận tín hiệu. Chạy lại với --resume để tiếp tục.")

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
                        "date": datetime.now().strftime("%Y-%m-%d")
                    })
                    
                results.append({
                    "name": company.get("original_name", ""),
                    "tax_code": company.get("tax_code", ""),
                    "sources": sources
                })
                
            self.excel_writer.write_results(output_path, results)
            print("Report generated using fallback logic.")
