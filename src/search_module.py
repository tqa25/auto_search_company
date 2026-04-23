"""
Search Module — Bilingual Search Strategy for Company Data Extraction Pipeline.

This module implements a three-tier search strategy to find Vietnamese business
information from English company names:
  ① Tax Code search (most precise, if available)
  ② English name + Vietnamese anchor keywords (forces domestic results)
  ③ Vietnamese translated name via Gemini AI (fallback if ② misses key sources)

Dependencies:
  - src.database.DatabaseManager (existing)
  - src.logger.PipelineLogger (existing)
  - Firecrawl Search API (external)
  - Google Gemini AI (optional, for Vietnamese name translation)
  - src.rate_limiter.AdaptiveRateLimiter (optional, for adaptive pacing)
  - src.connection_pool.ConnectionManager (optional, for connection reuse)
"""

import os
import time
import json
import logging
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

from src.database import DatabaseManager
from src.logger import PipelineLogger

# Load .env file at module level
load_dotenv()

logger = logging.getLogger(__name__)


class SearchModule:
    """Search for company information using a bilingual (EN/VN) strategy via Firecrawl."""

    # Vietnamese anchor keywords to force Google into returning domestic business pages
    ANCHOR_KEYWORDS = (
        '"mã số thuế" OR "công ty TNHH" OR "công ty cổ phần" OR "giấy phép kinh doanh"'
    )

    # Key target domains whose presence means step ② was sufficient
    KEY_TARGET_DOMAINS = ["masothue.com", "thuvienphapluat.vn"]

    # Firecrawl API endpoint
    FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"

    # Credits consumed per Firecrawl search request
    CREDITS_PER_SEARCH = 2

    def __init__(
        self,
        db: DatabaseManager,
        pipeline_logger: PipelineLogger,
        firecrawl_api_key: str = None,
        gemini_api_key: str = None,
        rate_limiter=None,
        connection_manager=None,
    ):
        """Initialize the SearchModule.

        Args:
            db: DatabaseManager instance for reading/writing company and search data.
            pipeline_logger: PipelineLogger instance for structured logging.
            firecrawl_api_key: Firecrawl API key. Falls back to env var FIRECRAWL_API_KEY.
            gemini_api_key: Google Gemini API key for Vietnamese translation.
                            Falls back to env var GEMINI_API_KEY.
            rate_limiter: Optional AdaptiveRateLimiter instance. When provided,
                          replaces fixed delay with adaptive pacing.
            connection_manager: Optional ConnectionManager instance. When provided,
                                uses session-based connection pooling instead of raw requests.
        """
        self.db = db
        self.pipeline_logger = pipeline_logger
        self.firecrawl_api_key = firecrawl_api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.rate_limiter = rate_limiter
        self.connection_manager = connection_manager

        if not self.firecrawl_api_key:
            logger.warning("FIRECRAWL_API_KEY is not set. Search requests will fail.")

    # ------------------------------------------------------------------
    # Core public API
    # ------------------------------------------------------------------

    def search_company(self, company_id: int) -> List[Dict]:
        """Execute the full bilingual search strategy for a single company.

        Strategy order:
          ① If tax_code exists → search by tax code
          ② Always → search English name + Vietnamese anchor keywords
          ③ Conditional → if ② didn't hit key target domains, translate name
             to Vietnamese via Gemini and search again.

        Args:
            company_id: ID of the company in the `companies` table.

        Returns:
            List of dicts representing all search results saved to DB.
        """
        company = self.db.get_company(company_id)
        if not company:
            logger.error(f"Company with id={company_id} not found in DB.")
            return []

        company_name = company["original_name"]
        tax_code = company.get("tax_code")

        # Update status to 'searching'
        self.db.update_company(company_id, status="searching")

        all_results: List[Dict] = []

        # ① Tax Code search
        if tax_code and tax_code.strip():
            log_id = self.pipeline_logger.log_step_start(
                company_id, "search", source_name=f"tax_code: {tax_code}"
            )
            try:
                results = self._firecrawl_search(tax_code.strip())
                saved = self._save_results(
                    company_id, tax_code.strip(), "tax_code", results
                )
                all_results.extend(saved)
                self.pipeline_logger.log_step_end(
                    log_id,
                    status="success",
                    credits_used=self.CREDITS_PER_SEARCH,
                    data_saved=True,
                    metadata={"links_found": len(saved), "search_type": "tax_code"},
                )
            except FirecrawlCreditExhausted:
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message="Firecrawl credits exhausted (HTTP 402)"
                )
                raise
            except Exception as e:
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e)
                )

        # ② English name + anchor keywords (always executed)
        anchor_query = f'"{company_name}" AND ({self.ANCHOR_KEYWORDS})'
        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"english: {company_name}"
        )
        try:
            results = self._firecrawl_search(anchor_query)
            saved = self._save_results(
                company_id, anchor_query, "english", results
            )
            all_results.extend(saved)
            self.pipeline_logger.log_step_end(
                log_id,
                status="success",
                credits_used=self.CREDITS_PER_SEARCH,
                data_saved=True,
                metadata={"links_found": len(saved), "search_type": "english"},
            )
        except FirecrawlCreditExhausted:
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message="Firecrawl credits exhausted (HTTP 402)"
            )
            raise
        except Exception as e:
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e)
            )

        # ③ Vietnamese name search (conditional)
        if not self._has_key_target_hit(all_results):
            vn_name = self._translate_to_vietnamese(company_name)
            if vn_name:
                # Persist the Vietnamese name for future use
                self.db.update_company(company_id, vietnamese_name=vn_name)

                log_id = self.pipeline_logger.log_step_start(
                    company_id, "search", source_name=f"vietnamese: {vn_name}"
                )
                try:
                    results = self._firecrawl_search(vn_name)
                    saved = self._save_results(
                        company_id, vn_name, "vietnamese", results
                    )
                    all_results.extend(saved)
                    self.pipeline_logger.log_step_end(
                        log_id,
                        status="success",
                        credits_used=self.CREDITS_PER_SEARCH,
                        data_saved=True,
                        metadata={"links_found": len(saved), "search_type": "vietnamese"},
                    )
                except FirecrawlCreditExhausted:
                    self.pipeline_logger.log_step_end(
                        log_id, status="failed", error_message="Firecrawl credits exhausted (HTTP 402)"
                    )
                    raise
                except Exception as e:
                    self.pipeline_logger.log_step_end(
                        log_id, status="failed", error_message=str(e)
                    )
            else:
                logger.info(
                    f"Skipping Vietnamese search for company_id={company_id}: "
                    "translation unavailable."
                )

        # Mark company as searched
        self.db.update_company(company_id, status="searched")
        return all_results

    def search_batch(
        self, company_ids: List[int], delay_seconds: float = 2.0
    ) -> Dict:
        """Run search_company for a batch of companies with delay between each.

        Args:
            company_ids: List of company IDs to search.
            delay_seconds: Seconds to wait between companies (rate-limit safety).

        Returns:
            Summary dict with counts and stats.
        """
        total = len(company_ids)
        success_count = 0
        fail_count = 0
        total_results = 0

        for idx, cid in enumerate(company_ids, start=1):
            print(f"Đang xử lý: {idx}/{total} công ty (company_id={cid})...")
            try:
                results = self.search_company(cid)
                total_results += len(results)
                success_count += 1
            except FirecrawlCreditExhausted:
                fail_count += 1
                print("⚠️  Firecrawl credits exhausted. Stopping batch.")
                break
            except Exception as e:
                fail_count += 1
                logger.error(f"Error searching company_id={cid}: {e}")

            # Rate-limit delay (skip after last item)
            if idx < total:
                if self.rate_limiter:
                    self.rate_limiter.wait()
                else:
                    time.sleep(delay_seconds)

        summary = {
            "total_requested": total,
            "success": success_count,
            "failed": fail_count,
            "total_results_saved": total_results,
        }
        print(f"\n--- Batch Search Summary ---")
        print(f"  Requested : {total}")
        print(f"  Success   : {success_count}")
        print(f"  Failed    : {fail_count}")
        print(f"  Results   : {total_results} links saved")
        return summary

    def get_search_stats(self) -> Dict:
        """Return aggregate statistics about all search operations.

        Returns:
            Dict with keys: total_searched, total_results, avg_results_per_company,
            search_type_distribution, credits_used_total.
        """
        total_searched_row = self.db.fetch_one(
            "SELECT COUNT(DISTINCT company_id) AS cnt FROM search_results"
        )
        total_searched = total_searched_row["cnt"] if total_searched_row else 0

        total_results_row = self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM search_results"
        )
        total_results = total_results_row["cnt"] if total_results_row else 0

        avg_results = (
            total_results / total_searched if total_searched > 0 else 0.0
        )

        type_rows = self.db.fetch_all(
            "SELECT search_type, COUNT(*) AS cnt FROM search_results GROUP BY search_type"
        )
        search_type_distribution = {r["search_type"]: r["cnt"] for r in type_rows}

        credits_row = self.db.fetch_one(
            "SELECT SUM(credits_used) AS total FROM search_results"
        )
        credits_used_total = (
            credits_row["total"] if credits_row and credits_row["total"] else 0.0
        )

        return {
            "total_searched": total_searched,
            "total_results": total_results,
            "avg_results_per_company": round(avg_results, 2),
            "search_type_distribution": search_type_distribution,
            "credits_used_total": float(credits_used_total),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _firecrawl_search(
        self, query: str, limit: int = 10, max_retries: int = 3
    ) -> List[Dict]:
        """Call the Firecrawl Search API with retry logic.

        Uses ConnectionManager for connection pooling when available,
        and reports success/error to AdaptiveRateLimiter when available.

        Args:
            query: The search query string.
            limit: Max results to return (default 10).
            max_retries: Max retry attempts on rate-limit (429).

        Returns:
            List of result dicts from Firecrawl (each with url, title, snippet, etc.).

        Raises:
            FirecrawlCreditExhausted: If HTTP 402 is received.
            FirecrawlSearchError: For other unrecoverable API errors.
        """
        headers = {
            "Authorization": f"Bearer {self.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"query": query, "limit": limit}

        # Wait for rate limiter before first attempt
        if self.rate_limiter:
            self.rate_limiter.wait()

        for attempt in range(1, max_retries + 1):
            try:
                # Use ConnectionManager if available, otherwise raw requests
                if self.connection_manager:
                    resp = self.connection_manager.post(
                        self.FIRECRAWL_SEARCH_URL,
                        json=payload,
                        request_type="search",
                    )
                else:
                    resp = requests.post(
                        self.FIRECRAWL_SEARCH_URL,
                        headers=headers,
                        json=payload,
                        timeout=30,
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    # Report success to rate limiter
                    if self.rate_limiter:
                        self.rate_limiter.report_success()
                    # Firecrawl returns {"success": true, "data": [...]}
                    return data.get("data", [])

                if resp.status_code == 402:
                    if self.rate_limiter:
                        self.rate_limiter.report_error(402)
                    raise FirecrawlCreditExhausted(
                        "Firecrawl credits exhausted (HTTP 402). Stop immediately."
                    )

                if resp.status_code == 429:
                    if self.rate_limiter:
                        self.rate_limiter.report_error(429)
                    wait = 60 if attempt < max_retries else 0
                    logger.warning(
                        f"Rate-limited (429). Waiting {wait}s before retry "
                        f"({attempt}/{max_retries})…"
                    )
                    if attempt < max_retries:
                        time.sleep(wait)
                        continue
                    raise FirecrawlSearchError(
                        f"Rate-limited (429) after {max_retries} retries."
                    )

                if resp.status_code in (403, 503):
                    if self.rate_limiter:
                        self.rate_limiter.report_error(resp.status_code)

                # Other errors (5xx, etc.)
                raise FirecrawlSearchError(
                    f"Firecrawl API error: HTTP {resp.status_code} — {resp.text[:300]}"
                )

            except requests.RequestException as e:
                if self.rate_limiter:
                    self.rate_limiter.report_error(0)
                if attempt < max_retries:
                    logger.warning(f"Network error (attempt {attempt}): {e}")
                    time.sleep(5)
                    continue
                raise FirecrawlSearchError(f"Network error after {max_retries} retries: {e}")

        return []  # unreachable, but satisfies linters

    def _save_results(
        self,
        company_id: int,
        search_query: str,
        search_type: str,
        results: List[Dict],
    ) -> List[Dict]:
        """Persist Firecrawl results into the search_results table.

        Args:
            company_id: Company this search relates to.
            search_query: The actual query string sent to Firecrawl.
            search_type: One of 'tax_code', 'english', 'vietnamese'.
            results: Raw result dicts from Firecrawl.

        Returns:
            List of saved result dicts (with added 'id' and 'result_rank').
        """
        saved: List[Dict] = []
        credits_per_result = self.CREDITS_PER_SEARCH / max(len(results), 1)

        for rank, item in enumerate(results, start=1):
            url = item.get("url", "")
            title = item.get("title", "") or item.get("metadata", {}).get("title", "")
            snippet = (
                item.get("snippet", "")
                or item.get("description", "")
                or item.get("markdown", "")[:300]
                if item.get("markdown")
                else ""
            )

            row_id = self.db.insert_search_result(
                company_id=company_id,
                search_query=search_query,
                search_type=search_type,
                result_rank=rank,
                url=url,
                title=title,
                snippet=snippet,
                credits_used=credits_per_result,
            )
            saved.append(
                {
                    "id": row_id,
                    "company_id": company_id,
                    "search_query": search_query,
                    "search_type": search_type,
                    "result_rank": rank,
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                }
            )
        return saved

    def _has_key_target_hit(self, results: List[Dict]) -> bool:
        """Check whether any result URL belongs to a key target domain.

        If masothue.com or thuvienphapluat.vn already appeared, we consider
        the English search sufficient and skip the Vietnamese translation step.
        """
        for r in results:
            url = r.get("url", "").lower()
            for domain in self.KEY_TARGET_DOMAINS:
                if domain in url:
                    return True
        return False

    def _translate_to_vietnamese(self, english_name: str) -> Optional[str]:
        """Translate an English company name to its Vietnamese legal name using Gemini AI.

        Args:
            english_name: The English company name (e.g. "ABC Software Solutions Co., Ltd").

        Returns:
            Vietnamese legal name string, or None if translation fails or API key is missing.
        """
        if not self.gemini_api_key:
            logger.info("Gemini API key not set — skipping Vietnamese translation.")
            return None

        prompt = (
            "Dịch tên công ty sau sang tên pháp lý tiếng Việt. "
            "Chỉ trả về tên tiếng Việt, không giải thích gì thêm.\n\n"
            "Quy tắc:\n"
            '- "Joint Stock Company" hoặc "JSC" → "Công ty Cổ phần"\n'
            '- "Limited Liability Company" hoặc "LLC" → "Công ty TNHH"\n'
            '- "Co., Ltd" hoặc "Ltd." → "Công ty TNHH"\n'
            '- "Corporation" hoặc "Corp." → "Tập đoàn" hoặc "Công ty"\n'
            "- Giữ nguyên tên riêng (brand name) nếu không có bản dịch phổ biến.\n\n"
            f"Tên tiếng Anh: {english_name}\n"
            "Tên tiếng Việt:"
        )

        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={self.gemini_api_key}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 100,
                },
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        vn_name = parts[0].get("text", "").strip()
                        if vn_name:
                            logger.info(
                                f"Translated '{english_name}' → '{vn_name}'"
                            )
                            return vn_name
            else:
                logger.warning(
                    f"Gemini API error: HTTP {resp.status_code} — {resp.text[:200]}"
                )
        except Exception as e:
            logger.warning(f"Gemini translation failed: {e}")

        return None


# ------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------

class FirecrawlCreditExhausted(Exception):
    """Raised when Firecrawl returns HTTP 402 (credits exhausted)."""
    pass


class FirecrawlSearchError(Exception):
    """Raised for unrecoverable Firecrawl API errors."""
    pass
