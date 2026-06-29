import time
import os
import json
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
            self.cfg.FORCE_REFRESH = True
            print("[FORCE REFRESH] Cache bypass enabled.")

        # Install signal handlers for graceful shutdown
        self._install_signal_handlers()

        success_count = 0
        fail_count = 0
        skip_count = 0

        def _worker_update(company_id: int, status: str, current_step: str = None,
                           checkpoint: str = None, progress: int = None):
            if job_controller is not None:
                job_controller.update(
                    company_id,
                    status=status,
                    current_step=current_step,
                    checkpoint=checkpoint,
                    progress=progress,
                )

        def _set_status(company_id: int, status: str, current_step: str = None,
                        checkpoint: str = None, progress: int = None):
            self.db.update_company(company_id, status=status)
            _worker_update(company_id, status, current_step, checkpoint, progress)

        def _finalize_strict_done(company_id: int, company_name: str) -> bool:
            audit = audit_company_completion(self.db, company_id, self.db.get_company(company_id))
            if audit.get("completion_status") == "strict_done":
                _set_status(company_id, 'done', 'Done', 'done', 100)
                return True
            resume_status = audit.get("resume_status") or 'pending'
            _set_status(
                company_id,
                resume_status,
                audit.get("current_step") or 'Waiting',
                audit.get("checkpoint") or 'pipeline_init',
                0,
            )
            self.logger.log_event("strict_completion_blocked", company_id, {
                "completion_reason": audit.get("completion_reason"),
                "resume_status": resume_status,
            })
            print(f"  -> Incomplete strict completion: {audit.get('completion_reason')} ({company_name})")
            return False

        try:
            for idx, company_id in enumerate(company_ids):
                if job_controller is not None and job_controller.should_stop(company_id):
                    self._shutdown_requested = True

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

                retry_count = 0
                max_retries = 2

                while retry_count < max_retries:
                    try:
                        # ====== BƯỚC 1: GEMINI QUICK SEARCH (no early-stop) ======
                        gemini_result = None
                        quick = None
                        filter_already_completed = False
                        if self._should_do_step(next_step, 'gemini_quick') and not replay_mode:
                            print("  -> Bước 1: Gemini Quick Search...")
                            _set_status(company_id, 'gemini_quick', 'Gemini Quick', 'gemini_quick', 20)
                            quick = self.gemini_quick.search(company_id)
                            gemini_result = quick.get("result", {})
                            self._batch_stats["gemini_tokens_in"] += quick.get("input_tokens", 0)
                            self._batch_stats["gemini_tokens_out"] += quick.get("output_tokens", 0)

                            # Record result quality but ALWAYS continue to deep search
                            if quick.get("is_sufficient"):
                                self._batch_stats["step1_success"] += 1
                                print(f"  -> Bước 1 đủ dữ liệu, tiếp tục deep search để bổ sung...")
                            elif not self._company_has_no_phone(company_id):
                                self._batch_stats["step1_success"] += 1
                                print(f"  -> Bước 1 tìm được phone (độ tin cậy thấp), tiếp tục deep search...")
                            else:
                                reason = quick.get("fallback_reason", "unknown")
                                print(f"  -> Bước 1: thiếu dữ liệu ({reason}), tiếp tục...")

                            _set_status(company_id, 'gemini_quick_done', 'Deep Search', 'deep_search', 35)

                        # ====== BƯỚC 2: DEEP SEARCH (Firecrawl + Filter + Extract) ======
                        if self._should_do_step(next_step, 'deep_search'):
                            if not replay_mode:
                                _set_status(company_id, 'searching', 'Deep Search', 'deep_search', 40)
                                print("  -> Bước 2: Deep Search...")
                                        # Build smart queries from Gemini result
                                if gemini_result:
                                    queries = self.deep_search.build_fallback_queries(gemini_result, company_name)
                                    gemini_sources = set(quick.get("grounding_sources", []) if quick else [])

                                    seen_domains = set()
                                    good_pages_total = 0
                                    all_search_results = []
                                    for q_idx, q in enumerate(queries):
                                        print(f"    - Query {q_idx+1}: {q['query']}")
                                        results = self.deep_search.search(company_id, q["query"], limit=self.cfg.SEARCH_LIMIT)
                                        
                                        # Dedup against Gemini sources
                                        deduped = FirecrawlDeepSearch.dedup_results(results, gemini_sources)
                                        self._batch_stats["urls_deduped"] += len(results) - len(deduped)
                                        
                                        # Save to search_results table and collect IDs
                                        urls_to_filter = []
                                        for rank, r in enumerate(deduped):
                                            sr_id = self.db.insert_search_result(
                                                company_id, q["query"], q["type"], rank + 1, r["url"], r["title"], r["snippet"]
                                            )
                                            urls_to_filter.append({
                                                "search_result_id": sr_id,
                                                "url": r["url"],
                                                "title": r.get("title", ""),
                                                "snippet": r.get("snippet", "")
                                            })
                                        all_search_results.extend(deduped)

                                        # Run incremental filter immediately
                                        target_tax_code = ""
                                        if isinstance(gemini_result, dict):
                                            target_tax_code = gemini_result.get("tax_code", "") or company.get("tax_code", "") or ""
                                        else:
                                            target_tax_code = company.get("tax_code", "") or ""
                                        vn_name = gemini_result.get("vietnamese_name", "") if isinstance(gemini_result, dict) else ""
                                        batch_filtered, batch_good = self.filter_module.filter_urls_incremental(
                                            company_id=company_id,
                                            urls=urls_to_filter,
                                            seen_domains=seen_domains,
                                            company_name=company_name,
                                            vn_name=vn_name,
                                            tax_code=target_tax_code
                                        )
                                        good_pages_total += batch_good

                                        if good_pages_total >= self.cfg.EARLY_STOP_COUNT:
                                            print(f"    -> Đã tìm đủ {good_pages_total} URLs chất lượng thực tế (score >= {self.cfg.EARLY_STOP_SCORE}). Dừng các query tiếp theo.")
                                            break
                                    
                                    filter_already_completed = True
                                else:
                                    # No Gemini result — use legacy search
                                    print("  -> (Legacy search fallback)")
                                    self.search_module.search_company(company_id)

                                _set_status(company_id, 'searched', 'Filter', 'filter', 55)
                                time.sleep(self.delay_seconds)
                            else:
                                print(f"  -> [REPLAY] Skipping search for company {company_id}")

                        # FILTER
                        if self._should_do_step(next_step, 'filter'):
                            if not filter_already_completed:
                                print("  -> Filtering...")
                                self.filter_module.filter_company_links(company_id)
                            else:
                                print("  -> Filtering already completed incrementally during search.")

                        # SCRAPE
                        if self._should_do_step(next_step, 'scrape'):
                            status_gate_result = self._run_business_status_gate(company_id, replay_mode=replay_mode)
                            if status_gate_result and status_gate_result.get("business_status_category") == INACTIVE_STOP:
                                done_ok = _finalize_strict_done(company_id, company_name)
                                if done_ok:
                                    self._batch_stats["status_gate_skipped"] += 1
                                    print(f"  -> Business status gate skipped scrape: {status_gate_result.get('business_status')}")
                                    success_count += 1
                                else:
                                    fail_count += 1
                                break

                            if not replay_mode:
                                _set_status(company_id, 'scraping', 'Scrape', 'scrape', 65)
                                print("  -> Scraping...")
                                self.scrape_module.scrape_company(company_id, self.delay_seconds)
                                # ★ CHECKPOINT: all scraping done → mark ai_extract_pending
                                # On resume, pipeline will skip scrape and go straight to AI extract
                                _set_status(company_id, 'ai_extract_pending', 'AI Extract', 'ai_extract', 82)
                                print("  -> ✓ Checkpoint: scraped data saved (ai_extract_pending)")
                            else:
                                print(f"  -> [REPLAY] Skipping scrape for company {company_id}")

                        # AI EXTRACT
                        if self._should_do_step(next_step, 'ai_extract'):
                            if not replay_mode and self.ai_extractor:
                                print("  -> AI Extracting...")
                                _set_status(company_id, 'extracting', 'AI Extract', 'ai_extract', 90)
                                self.ai_extractor.extract_for_company(company_id, self.delay_seconds)
                                _set_status(company_id, 'ai_done', 'Finalizing', 'done', 95)
                            elif not replay_mode:
                                print("  -> AI Extract SKIP (no API Key)")
                                _set_status(company_id, 'ai_done', 'Finalizing', 'done', 95)
                            else:
                                print(f"  -> [REPLAY] Skipping AI extract for company {company_id}")
                                _set_status(company_id, 'ai_done', 'Finalizing', 'done', 95)

                            # Early Stop Check after AI Extract
                            if not self._company_has_no_phone(company_id):
                                self._batch_stats["step2_success"] += 1
                                if _finalize_strict_done(company_id, company_name):
                                    print(f"  -> ✅ Bước 2 tìm được phone sau extract, dừng pipeline! {company_name}")
                                    success_count += 1
                                else:
                                    fail_count += 1
                                break

                        self._batch_stats["step2_success"] += 1

                        if _finalize_strict_done(company_id, company_name):
                            if self._company_has_no_phone(company_id):
                                self._batch_stats["no_phone"] += 1
                                print(f"  -> ⚠️  Hoàn tất nhưng không tìm được phone: {company_name}")
                            else:
                                print(f"  -> ✅ SUCCESS: {company_name}")
                            success_count += 1
                        else:
                            fail_count += 1
                        break  # Exit retry loop on success

                    except RetryableError as e:
                        retry_count += 1
                        error_msg = str(e)
                        print(f"  -> RETRY #{retry_count}: {error_msg}")
                        if retry_count < max_retries:
                            backoff_time = 60 * retry_count
                            print(f"     Waiting {backoff_time}s before retry...")
                            time.sleep(backoff_time)
                        else:
                            print(f"  -> FAILED: Exceeded max retries ({max_retries})")
                            _set_status(company_id, 'failed', 'Failed', 'failed', 0)
                            fail_count += 1
                            break

                    except SkippableError as e:
                        error_msg = str(e)
                        print(f"  -> SKIPPED: {error_msg}")
                        _set_status(company_id, 'failed', 'Failed', 'failed', 0)
                        fail_count += 1
                        break

                    except CriticalError as e:
                        error_msg = str(e)
                        print(f"  -> ⛔ CRITICAL: {error_msg}")
                        # If scraping was already done, preserve that checkpoint
                        current_status = self.db.get_company(company_id)
                        if current_status and current_status['status'] in ('ai_extract_pending', 'extracting'):
                            _set_status(company_id, 'ai_extract_pending', 'AI Extract', 'ai_extract', 82)
                            print(f"  -> Checkpoint bảo toàn: status='ai_extract_pending' — dữ liệu đã cào được giữ lại.")
                        print("  -> Stopping entire pipeline.")
                        self._restore_signal_handlers()
                        raise

                    except Exception as e:
                        # Unknown error — treat as skippable
                        error_msg = str(e)
                        print(f"  -> FAILED (unknown error): {error_msg}")
                        _set_status(company_id, 'failed', 'Failed', 'failed', 0)
                        fail_count += 1
                        break

        finally:
            # Always restore signal handlers
            self._restore_signal_handlers()
            if force_refresh:
                self.cfg.FORCE_REFRESH = False

        # Print detailed batch summary report
        self._batch_stats["total"] = total_to_process
        self._batch_stats["success"] = success_count
        self._batch_stats["failed"] = fail_count
        self._batch_stats["skipped"] = skip_count
        self._print_batch_summary()

        if self._shutdown_requested:
            print("⚠️  Pipeline đã dừng an toàn do nhận tín hiệu. Chạy lại với --resume để tiếp tục.")

    # ------------------------------------------------------------------
    # Batch stats & summary report
    # ------------------------------------------------------------------

    @staticmethod
    def _init_batch_stats() -> dict:
        return {
            "total": 0, "success": 0, "failed": 0, "skipped": 0,
            "step1_success": 0, "step2_success": 0,
            "optional_maps_success": 0,
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
        maps_line = f"\n  [Optional] Maps thành công:      {s['optional_maps_success']}" if s['optional_maps_success'] > 0 else ""
        print(f"""
═══════════════════════════════════════════
  BÁO CÁO PIPELINE - {today}
═══════════════════════════════════════════
  Tổng công ty xử lý:            {processed}
  Bước 1 thành công (Gemini):     {s['step1_success']} ({s['step1_success']/max(processed,1)*100:.0f}%)
  Bước 2 thành công (Deep):       {s['step2_success']}{maps_line}
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

    def _save_maps_contact(self, company_id: int, maps_result: dict, gemini_result: dict = None):
        """Save Google Maps contact to extracted_contacts and update company."""
        self.db.insert_extracted_contact(
            company_id=company_id,
            scraped_page_id=None,
            source_type="google_maps",
            source_url="serper_places_api",
            address=maps_result.get("address"),
            phone=maps_result.get("phone"),
            email=(gemini_result or {}).get("email"),
            website=maps_result.get("website"),
            fax=(gemini_result or {}).get("fax"),
            representative=(gemini_result or {}).get("representative"),
            raw_ai_response=json.dumps(maps_result, ensure_ascii=False),
            confidence_score=0.85,
        )
        # Update company table with info
        updates = {}
        if maps_result.get("address"):
            updates["address"] = maps_result["address"]
        if gemini_result:
            if gemini_result.get("core_name_vi"):
                updates["vietnamese_name"] = gemini_result["core_name_vi"]
            if gemini_result.get("tax_code"):
                updates["tax_code"] = gemini_result["tax_code"]
        if updates:
            self.db.update_company(company_id, **updates)

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
