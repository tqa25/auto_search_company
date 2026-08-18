import time

from src.business_status import INACTIVE_STOP
from src.completion_audit import audit_company_completion
from src.errors import CriticalError, RetryableError, SkippableError
from src.firecrawl_deep_search import FirecrawlDeepSearch


class CompanyRun:
    """Owns execution policy for one company through the existing pipeline steps."""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def run(self, company_id: int, replay_mode: bool = False, force_refresh: bool = False, job_controller=None):
        pipeline = self.pipeline
        company = pipeline.db.get_company(company_id)
        if not company:
            print(f"Company ID {company_id} not found in DB.")
            return {"outcome": "failed", "reason": "company_not_found"}

        status = company["status"]
        company_name = company["original_name"]
        print(f"Processing company ID {company_id} - {company_name} (status: {status})...")

        if status == "done":
            print("  -> Skipping (already completed)")
            return {"outcome": "skipped", "reason": "done"}

        if status == "permanently_failed":
            print("  -> Skipping (permanently failed)")
            return {"outcome": "skipped", "reason": "permanently_failed"}

        if self._safe_stop_requested(company_id, job_controller):
            print("  -> Stop requested before next safe point. Leaving company unchanged.")
            return {"outcome": "shutdown", "reason": "stop_requested_before_start"}

        next_step = pipeline._get_next_step(status)
        if next_step != "search":
            print(f"  -> Resuming from step: {next_step} (previous status: {status})")

        if force_refresh:
            pipeline.cfg.FORCE_REFRESH = True

        try:
            return self._run_with_retries(
                company_id=company_id,
                company_name=company_name,
                next_step=next_step,
                replay_mode=replay_mode,
                job_controller=job_controller,
            )
        finally:
            if force_refresh:
                pipeline.cfg.FORCE_REFRESH = False

    def _run_with_retries(self, company_id: int, company_name: str, next_step: str, replay_mode: bool, job_controller=None):
        """
        Run a single attempt. Individual operations (search, scrape, ai_extract) now use
        RetryExecutor internally with MAX_ATTEMPTS. This method no longer retries the
        entire company — operation-level retries are handled by the unified executor.
        
        Status mapping when operations exhaust retries:
        - Search or scrape exhausted → 'failed' (re-run from start of that step)
        - AI extraction exhausted → keep 'ai_extract_pending' (preserve scraped data)
        - CriticalError → preserve current checkpoint, stop entire batch
        """
        try:
            return self._run_attempt(
                company_id=company_id,
                company_name=company_name,
                next_step=next_step,
                replay_mode=replay_mode,
                job_controller=job_controller,
            )
        except RetryableError as exc:
            # Operation exhausted retries — determine final status based on current step
            error_msg = str(exc)
            print(f"  -> Operation exhausted retries: {error_msg}")
            
            # Get current company status to determine which step failed
            company = self.pipeline.db.get_company(company_id)
            current_status = company["status"] if company else "pending"
            
            # Map status to final status per §5.4
            if current_status in ("searching", "searched", "scraping"):
                # Search or scrape exhausted → 'failed'
                final_status = "failed"
            elif current_status in ("ai_extract_pending", "extracting"):
                # AI extraction exhausted → keep 'ai_extract_pending'
                final_status = "ai_extract_pending"
            else:
                # Default
                final_status = "failed"
            
            self._set_status(company_id, final_status, "Failed", "failed", 0, job_controller)
            return {"outcome": "failed", "reason": "max_attempts_exhausted"}
        except SkippableError as exc:
            error_msg = str(exc)
            print(f"  -> SKIPPED: {error_msg}")
            # SkippableError means "skip this company, move on" (invalid data /
            # no results / non-retryable source error). But if earlier steps
            # already satisfied strict completion, finalize as done instead of
            # discarding that work as failed.
            audit = audit_company_completion(
                self.pipeline.db, company_id, self.pipeline.db.get_company(company_id)
            )
            if audit.get("completion_status") == "strict_done":
                self._set_status(company_id, "done", "Done", "done", 100, job_controller)
                return {"outcome": "success", "reason": "strict_done_before_skip"}
            self._set_status(company_id, "failed", "Failed", "failed", 0, job_controller)
            return {"outcome": "failed", "reason": "skippable_error"}
        except CriticalError as exc:
            error_msg = str(exc)
            print(f"  -> ⛔ CRITICAL: {error_msg}")
            current_status = self.pipeline.db.get_company(company_id)
            if current_status and current_status["status"] in ("ai_extract_pending", "extracting"):
                self._set_status(company_id, "ai_extract_pending", "AI Extract", "ai_extract", 82, job_controller)
                print("  -> Checkpoint bảo toàn: status='ai_extract_pending' — dữ liệu đã cào được giữ lại.")
            print("  -> Stopping entire pipeline.")
            raise
        except Exception as exc:
            error_msg = str(exc)
            print(f"  -> FAILED (unknown error): {error_msg}")
            self._set_status(company_id, "failed", "Failed", "failed", 0, job_controller)
            return {"outcome": "failed", "reason": "unknown_error"}

    def _run_attempt(self, company_id: int, company_name: str, next_step: str, replay_mode: bool, job_controller=None):
        pipeline = self.pipeline
        gemini_result = None
        quick = None
        filter_already_completed = False

        if self._safe_stop_requested(company_id, job_controller):
            print("  -> Stop requested before step execution. Leaving company unchanged.")
            return {"outcome": "shutdown", "reason": "stop_requested_before_steps"}

        if pipeline._should_do_step(next_step, "gemini_quick") and not replay_mode:
            print("  -> Bước 1: Gemini Quick Search...")
            self._set_status(company_id, "gemini_quick", "Gemini Quick", "gemini_quick", 20, job_controller)
            quick = pipeline.gemini_quick.search(company_id)
            gemini_result = quick.get("result", {})
            pipeline._batch_stats["gemini_tokens_in"] += quick.get("input_tokens", 0)
            pipeline._batch_stats["gemini_tokens_out"] += quick.get("output_tokens", 0)

            if quick.get("is_sufficient"):
                pipeline._batch_stats["step1_success"] += 1
                print("  -> Bước 1 đủ dữ liệu, tiếp tục deep search để bổ sung...")
            elif not pipeline._company_has_no_phone(company_id):
                pipeline._batch_stats["step1_success"] += 1
                print("  -> Bước 1 tìm được phone (độ tin cậy thấp), tiếp tục deep search...")
            else:
                reason = quick.get("fallback_reason", "unknown")
                print(f"  -> Bước 1: thiếu dữ liệu ({reason}), tiếp tục...")

            self._set_status(company_id, "gemini_quick_done", "Deep Search", "deep_search", 35, job_controller)

        if self._safe_stop_requested(company_id, job_controller):
            print("  -> Stop requested at safe point after Gemini Quick.")
            return {"outcome": "stopped", "reason": "after_gemini_quick"}

        if pipeline._should_do_step(next_step, "deep_search"):
            if not replay_mode:
                self._set_status(company_id, "searching", "Deep Search", "deep_search", 40, job_controller)
                print("  -> Bước 2: Deep Search...")
                if gemini_result:
                    queries = pipeline.deep_search.build_fallback_queries(gemini_result, company_name)
                    gemini_sources = set(quick.get("grounding_sources", []) if quick else [])

                    seen_domains = set()
                    good_pages_total = 0
                    for q_idx, query in enumerate(queries):
                        print(f"    - Query {q_idx+1}: {query['query']}")
                        results = pipeline.deep_search.search(company_id, query["query"], limit=pipeline.cfg.SEARCH_LIMIT)
                        deduped = FirecrawlDeepSearch.dedup_results(results, gemini_sources)
                        pipeline._batch_stats["urls_deduped"] += len(results) - len(deduped)

                        urls_to_filter = []
                        for rank, result in enumerate(deduped):
                            search_result_id = pipeline.db.insert_search_result(
                                company_id,
                                query["query"],
                                query["type"],
                                rank + 1,
                                result["url"],
                                result["title"],
                                result["snippet"],
                            )
                            urls_to_filter.append({
                                "search_result_id": search_result_id,
                                "url": result["url"],
                                "title": result.get("title", ""),
                                "snippet": result.get("snippet", ""),
                            })

                        if isinstance(gemini_result, dict):
                            target_tax_code = gemini_result.get("tax_code", "") or pipeline.db.get_company(company_id).get("tax_code", "") or ""
                            vn_name = gemini_result.get("vietnamese_name", "")
                        else:
                            target_tax_code = pipeline.db.get_company(company_id).get("tax_code", "") or ""
                            vn_name = ""
                        _, batch_good = pipeline.filter_module.filter_urls_incremental(
                            company_id=company_id,
                            urls=urls_to_filter,
                            seen_domains=seen_domains,
                            company_name=company_name,
                            vn_name=vn_name,
                            tax_code=target_tax_code,
                        )
                        good_pages_total += batch_good

                        if good_pages_total >= pipeline.cfg.EARLY_STOP_COUNT:
                            print(
                                f"    -> Đã tìm đủ {good_pages_total} URLs chất lượng thực tế "
                                f"(score >= {pipeline.cfg.EARLY_STOP_SCORE}). Dừng các query tiếp theo."
                            )
                            break

                    filter_already_completed = True
                else:
                    print("  -> (Legacy search fallback)")
                    pipeline.search_module.search_company(company_id)

                self._set_status(company_id, "searched", "Filter", "filter", 55, job_controller)
                time.sleep(pipeline.delay_seconds)
            else:
                print(f"  -> [REPLAY] Skipping search for company {company_id}")

        if self._safe_stop_requested(company_id, job_controller):
            print("  -> Stop requested at safe point after search/filter planning.")
            return {"outcome": "stopped", "reason": "after_search"}

        if pipeline._should_do_step(next_step, "filter"):
            if not filter_already_completed:
                print("  -> Filtering...")
                pipeline.filter_module.filter_company_links(company_id)
            else:
                print("  -> Filtering already completed incrementally during search.")

        if self._safe_stop_requested(company_id, job_controller):
            print("  -> Stop requested at safe point before scrape.")
            return {"outcome": "stopped", "reason": "before_scrape"}

        if pipeline._should_do_step(next_step, "scrape"):
            status_gate_result = pipeline._run_business_status_gate(company_id, replay_mode=replay_mode)
            if status_gate_result and status_gate_result.get("business_status_category") == INACTIVE_STOP:
                pipeline._batch_stats["status_gate_skipped"] += 1
                # The company is dissolved/suspended and the gate intentionally skips
                # further scraping. Finalize as a terminal 'done' (business_status
                # records the inactive reason) instead of requiring strict completion:
                # an inactive company will almost never have full contacts, and marking
                # it 'failed' resets it to 'searched' so it is re-queued and churns
                # forever. Any contacts already extracted are preserved.
                self._set_status(company_id, "done", "Done", "done", 100, job_controller)
                print(f"  -> Business status gate: company inactive ({status_gate_result.get('business_status')}); finalized as done.")
                return {"outcome": "success", "reason": "business_status_inactive"}

            if not replay_mode:
                self._set_status(company_id, "scraping", "Scrape", "scrape", 65, job_controller)
                print("  -> Scraping...")
                pipeline.scrape_module.scrape_company(company_id, pipeline.delay_seconds)
                self._set_status(company_id, "ai_extract_pending", "AI Extract", "ai_extract", 82, job_controller)
                print("  -> ✓ Checkpoint: scraped data saved (ai_extract_pending)")
            else:
                print(f"  -> [REPLAY] Skipping scrape for company {company_id}")

        if self._safe_stop_requested(company_id, job_controller):
            print("  -> Stop requested at safe point before AI extract.")
            return {"outcome": "stopped", "reason": "before_ai_extract"}

        if pipeline._should_do_step(next_step, "ai_extract"):
            if not replay_mode and pipeline.ai_extractor:
                print("  -> AI Extracting...")
                self._set_status(company_id, "extracting", "AI Extract", "ai_extract", 90, job_controller)
                pipeline.ai_extractor.extract_for_company(company_id, pipeline.delay_seconds)
                self._set_status(company_id, "ai_done", "Finalizing", "done", 95, job_controller)
            elif not replay_mode:
                print("  -> AI Extract SKIP (no API Key)")
                self._set_status(company_id, "ai_done", "Finalizing", "done", 95, job_controller)
            else:
                print(f"  -> [REPLAY] Skipping AI extract for company {company_id}")
                self._set_status(company_id, "ai_done", "Finalizing", "done", 95, job_controller)

            if not pipeline._company_has_no_phone(company_id):
                pipeline._batch_stats["step2_success"] += 1
                if self._finalize_strict_done(company_id, company_name, job_controller):
                    print(f"  -> ✅ Bước 2 tìm được phone sau extract, dừng pipeline! {company_name}")
                    return {"outcome": "success", "reason": "phone_found_after_extract"}
                return {"outcome": "failed", "reason": "strict_completion_blocked_after_ai_extract"}

        pipeline._batch_stats["step2_success"] += 1
        if self._finalize_strict_done(company_id, company_name, job_controller):
            if pipeline._company_has_no_phone(company_id):
                pipeline._batch_stats["no_phone"] += 1
                print(f"  -> ⚠️  Hoàn tất nhưng không tìm được phone: {company_name}")
            else:
                print(f"  -> ✅ SUCCESS: {company_name}")
            return {"outcome": "success", "reason": "strict_done"}
        return {"outcome": "failed", "reason": "strict_completion_blocked"}

    def _safe_stop_requested(self, company_id: int, job_controller=None) -> bool:
        if job_controller is not None and job_controller.should_stop(company_id):
            self.pipeline._shutdown_requested = True
            return True
        return False

    def _worker_update(self, company_id: int, status: str, current_step: str = None, checkpoint: str = None, progress: int = None, job_controller=None):
        if job_controller is not None:
            job_controller.update(
                company_id,
                status=status,
                current_step=current_step,
                checkpoint=checkpoint,
                progress=progress,
            )

    def _set_status(self, company_id: int, status: str, current_step: str = None, checkpoint: str = None, progress: int = None, job_controller=None):
        self.pipeline.db.update_company(company_id, status=status)
        self._worker_update(company_id, status, current_step, checkpoint, progress, job_controller)

    def _finalize_strict_done(self, company_id: int, company_name: str, job_controller=None) -> bool:
        audit = audit_company_completion(self.pipeline.db, company_id, self.pipeline.db.get_company(company_id))
        if audit.get("completion_status") == "strict_done":
            self._set_status(company_id, "done", "Done", "done", 100, job_controller)
            return True

        resume_status = audit.get("resume_status") or "pending"
        self._set_status(
            company_id,
            resume_status,
            audit.get("current_step") or "Waiting",
            audit.get("checkpoint") or "pipeline_init",
            0,
            job_controller,
        )
        self.pipeline.logger.log_event(
            "strict_completion_blocked",
            company_id,
            {
                "completion_reason": audit.get("completion_reason"),
                "resume_status": resume_status,
            },
        )
        print(f"  -> Incomplete strict completion: {audit.get('completion_reason')} ({company_name})")
        return False
