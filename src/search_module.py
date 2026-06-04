"""
Search Module — 2-Tier Coarse+Fallback Search Strategy for Company Data Extraction Pipeline.

This module implements a two-tier search strategy to find Vietnamese business
information from English company names:
  ① Tier 1 — Coarse search: English name + contact keywords (broad, with early-stop check)
  ② Tier 2 — Fallback (only if Tier 1 didn't trigger early-stop):
      2a. Recruitment query
      2b. Abbreviation query (if applicable)
      2c. Facebook search (if below FB_FALLBACK_THRESHOLD good links)

All search queries are deduplicated via a query_cache table before hitting the API.

Dependencies:
  - src.database.DatabaseManager (existing)
  - src.logger.PipelineLogger (existing)
  - src.config.Config (new)
  - Firecrawl Search API (external)
  - src.rate_limiter.AdaptiveRateLimiter (optional, for adaptive pacing)
  - src.connection_pool.ConnectionManager (optional, for connection reuse)
"""

import hashlib
import os
import time
import json
import logging
import requests
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import RetryableError, CriticalError, PipelineError
from src.schemas import validate_search_result

# Load .env file at module level
load_dotenv()

logger = logging.getLogger(__name__)


class SearchModule:
    """Search for company information using a 2-tier coarse+fallback strategy via Firecrawl."""

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
        config=None,
        filter_module=None,
    ):
        """Initialize the SearchModule.

        Args:
            db: DatabaseManager instance for reading/writing company and search data.
            pipeline_logger: PipelineLogger instance for structured logging.
            firecrawl_api_key: Firecrawl API key. Falls back to env var FIRECRAWL_API_KEY.
            gemini_api_key: Google Gemini API key (kept for backward compatibility, unused).
                            Falls back to env var GEMINI_API_KEY.
            rate_limiter: Optional AdaptiveRateLimiter instance. When provided,
                          replaces fixed delay with adaptive pacing.
            connection_manager: Optional ConnectionManager instance. When provided,
                                uses session-based connection pooling instead of raw requests.
            config: Optional Config instance. Falls back to default_config.
        """
        from src.config import default_config

        self.config = config or default_config
        self.db = db
        self.pipeline_logger = pipeline_logger
        self.firecrawl_api_key = firecrawl_api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.rate_limiter = rate_limiter
        self.connection_manager = connection_manager

        if filter_module is None:
            from src.filter_module import LinkFilter
            self.filter_module = LinkFilter(db, pipeline_logger, config=self.config)
        else:
            self.filter_module = filter_module

        if not self.firecrawl_api_key:
            logger.warning("FIRECRAWL_API_KEY is not set. Search requests will fail.")

    # ------------------------------------------------------------------
    # Core public API
    # ------------------------------------------------------------------

    VN_COMPANY_PATTERNS = [
        r"(?:Công ty|CÔNG TY)\s+(?:TNHH|CP|CỔ PHẦN|HỢP DANH|MTV|MỘT THÀNH VIÊN)\s+([\w\s&.,-]+?)(?:\s+tại\s+|-|Mã số thuế|Địa chỉ|\n|$)",
        r"(?:Tập đoàn|TẬP ĐOÀN)\s+([\w\s&.,-]+?)(?:\s+tại\s+|-|Mã số thuế|Địa chỉ|\n|$)",
        r"(?:Tổng công ty|TỔNG CÔNG TY)\s+([\w\s&.,-]+?)(?:\s+tại\s+|-|Mã số thuế|Địa chỉ|\n|$)"
    ]

    def search_company(self, company_id: int, vn_name: str = None, tax_code: str = None) -> List[Dict]:
        """Execute the 4-step search strategy."""
        company = self.db.get_company(company_id)
        if not company:
            logger.error(f"Company with id={company_id} not found in DB.")
            return []

        company_name = company["original_name"]
        self.db.update_company(company_id, status="searching")
        
        # Override with DB values if available and not passed
        if not vn_name:
            vn_name = company.get("vietnamese_name")
        if not tax_code:
            tax_code = company.get("tax_code")

        all_results = []

        # Step 1: Contact Query (EN + VN)
        step1_results = self._step1_contact_query(company_id, company_name, vn_name)
        all_results.extend(step1_results)
        if self._count_qualified(company_name, vn_name, all_results) >= self.config.EARLY_STOP_COUNT:
            self.db.update_company(company_id, status="searched")
            return all_results

        # Step 2: Infer VN Name & Data (Skip if we already have both from Gemini)
        if not (vn_name and tax_code):
            vn_data = self._step2_infer_vn_data(company_id, step1_results)
            vn_name = vn_name or vn_data.get("vn_name")
            tax_code = tax_code or vn_data.get("tax_code")

        # Step 3: Tax Code Query
        if tax_code:
            step3_results = self._step3_tax_query(company_id, tax_code)
            all_results.extend(step3_results)
            if self._count_qualified(company_name, vn_name, all_results) >= self.config.EARLY_STOP_COUNT:
                self.db.update_company(company_id, status="searched")
                return all_results
        else:
            logger.info(f"[{company_id}] No tax code found. Skipping step 3.")
            self.db.execute_query(
                "UPDATE companies SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (company_id,)
            )

        # Step 4: Bare Query
        step4_results = self._step4_bare_query(company_id, company_name, vn_name)
        all_results.extend(step4_results)

        self.db.update_company(company_id, status="searched")
        return all_results

    def _step1_contact_query(self, company_id: int, en_name: str, vn_name: str) -> List[Dict]:
        if vn_name:
            query = f'("{en_name}" OR "{vn_name}") AND ("liên hệ" OR "contact")'
        else:
            query = f'"{en_name}" AND ("liên hệ" OR "contact")'
            
        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"step1_contact: {en_name}",
            raw_request={"query": query, "tier": "step1_contact"}
        )
        return self._execute_search_query(company_id, query, "step1_contact", log_id)

    def _step2_infer_vn_data(self, company_id: int, anchor_results: List[Dict]) -> dict:
        legal_results = [r for r in anchor_results if self._is_legal_domain(r.get("url", ""))]
        
        # 2a. Extract from snippets
        for result in legal_results:
            data = self._extract_vn_data_from_snippet(result.get("snippet", ""), result.get("url", ""))
            if data.get("vn_name"):
                self._update_company_vn_data(company_id, data)
                return data

        # 2b. Scrape fallback
        max_scrape = getattr(self.config, 'INFER_MAX_SCRAPE', 2)
        if max_scrape > 0 and legal_results:
            for result in legal_results[:max_scrape]:
                data = self._scrape_and_extract_vn_data(result.get("url", ""))
                if data.get("vn_name"):
                    self._update_company_vn_data(company_id, data)
                    return data
        return {}

    def _step4_bare_query(self, company_id: int, en_name: str, vn_name: str) -> List[Dict]:
        if vn_name:
            query = f'("{en_name}" OR "{vn_name}")'
        else:
            query = f'"{en_name}"'
            
        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"step4_bare: {en_name}",
            raw_request={"query": query, "tier": "step4_bare"}
        )
        return self._execute_search_query(company_id, query, "step4_bare", log_id)

    def _step3_tax_query(self, company_id: int, tax_code: str) -> List[Dict]:
        query = f'"{tax_code}"'
        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"step3_tax: {tax_code}",
            raw_request={"query": query, "tier": "step3_tax"}
        )
        return self._execute_search_query(company_id, query, "step3_tax", log_id)

    def _execute_search_query(self, company_id: int, query: str, search_type: str, log_id: int) -> List[Dict]:
        try:
            start_time = time.time()
            results, cache_hit = self._search_with_dedup(query, company_id, limit=self.config.SEARCH_LIMIT)
            elapsed_ms = (time.time() - start_time) * 1000
            saved = self._save_results(company_id, query, search_type, results)
            self.pipeline_logger.log_step_end(
                log_id,
                status="success",
                credits_used=0 if cache_hit else self.CREDITS_PER_SEARCH,
                data_saved=bool(saved),
                network_latency_ms=elapsed_ms,
                raw_response_summary={"result_count": len(saved), "status_code": 200},
                metadata={"links_found": len(saved), "search_type": search_type, "cache_hit": cache_hit},
            )
            return saved
        except Exception as e:
            category = getattr(e, 'category', 'unknown')
            self.pipeline_logger.log_step_end(log_id, status="failed", error_message=str(e), error_category=category)
            if isinstance(e, (CriticalError, RetryableError)):
                raise
            return []

    def _is_legal_domain(self, url: str) -> bool:
        if not url: return False
        domain = urllib.parse.urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain.endswith(d) or domain == d for d in self.config.VN_LEGAL_DOMAINS)

    def _extract_vn_data_from_snippet(self, snippet: str, url: str) -> dict:
        data = {"vn_name": None, "tax_code": None, "address": None, "source": f"snippet:{urllib.parse.urlparse(url).netloc}"}
        if not snippet: return data
        
        # Name
        for pattern in self.VN_COMPANY_PATTERNS:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                name = match.group(0).strip()
                name = re.sub(r'(?i)\s+tại\s+.*$', '', name)
                name = re.sub(r'(?i)\s*-\s*.*$', '', name)
                name = re.sub(r'(?i)\s+Mã số thuế.*$', '', name)
                name = re.sub(r'(?i)\s+Địa chỉ.*$', '', name)
                if len(name) > 10:
                    data["vn_name"] = name.strip(',.- ')
                    break

        # MST
        mst_match = re.search(r'\b\d{10}(?:-\d{3})?\b', snippet)
        if mst_match:
            data["tax_code"] = mst_match.group(0)

        return data

    def _scrape_and_extract_vn_data(self, url: str) -> dict:
        data = {"vn_name": None, "tax_code": None, "address": None, "source": f"scrape:{urllib.parse.urlparse(url).netloc}"}
        try:
            headers = {"Authorization": f"Bearer {self.firecrawl_api_key}", "Content-Type": "application/json"}
            body = {"url": url, "formats": ["markdown"], "timeout": 30000}
            if self.rate_limiter:
                self.rate_limiter.wait()
            if self.connection_manager:
                resp = self.connection_manager.post("https://api.firecrawl.dev/v1/scrape", json=body, request_type="scrape")
            else:
                resp = requests.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=body, timeout=35)
            
            if resp.status_code == 200:
                if self.rate_limiter:
                    self.rate_limiter.report_success()
                res_json = resp.json()
                if res_json.get("success"):
                    md = res_json.get("data", {}).get("markdown", "")
                    data_ext = self._extract_vn_data_from_snippet(md[:2000], url)
                    data["vn_name"] = data_ext.get("vn_name")
                    data["tax_code"] = data_ext.get("tax_code")
                    data["address"] = data_ext.get("address")
            elif resp.status_code == 429 and self.rate_limiter:
                self.rate_limiter.report_error(429)
        except Exception as e:
            logger.warning(f"Failed to scrape legal URL {url}: {e}")
        return data

    def _update_company_vn_data(self, company_id: int, data: dict):
        updates = {}
        if data.get("vn_name"): updates["vietnamese_name"] = data["vn_name"]
        if data.get("tax_code"): updates["tax_code"] = data["tax_code"]
        if data.get("address"): updates["address"] = data["address"]
        if data.get("source"): updates["vn_data_source"] = data["source"]
        if updates:
            self.db.update_company(company_id, **updates)

    def _count_qualified(self, company_name: str, vn_name: str, results: List[Dict]) -> int:
        if not self.config.EARLY_STOP_COUNT:
            return 0
        scored = self.filter_module.score_urls_batch(results, company_name, vn_name=vn_name)
        return sum(1 for item in scored if item["relevance_score"] >= self.config.EARLY_STOP_SCORE)

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
            except CriticalError:
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

    def _compute_abbreviation(self, company_name: str) -> Optional[str]:
        """Compute an abbreviation from an English company name.

        Rules:
        1. Split company_name into words.
        2. Check if first word is already an abbreviation (≥3 consecutive uppercase letters).
           If yes, return it directly.
        3. Filter out stop words (case-insensitive).
        4. Filter out words with trailing dots.
        5. Take first letter of remaining words and combine into abbreviation.
        6. If abbreviation < 2 characters, return None.

        Examples:
            "ABC Software Co., Ltd"          -> "ABC" (detect ABC as existing abbreviation)
            "FPT Software"                   -> "FPT" (detect FPT as existing abbreviation)
            "Vietnam Development Corp"       -> None (only "D" left after filtering)
            "Hòa Phát Group Joint Stock"    -> "HPG"
        """
        name = company_name.strip()
        words = name.split()

        if not words:
            return None

        # Check if first word is already an abbreviation (≥3 consecutive uppercase letters)
        first_word = words[0]
        if len(first_word) >= 3 and first_word.isupper():
            return first_word

        # Build list of stop words (case-insensitive)
        stop_words_lower = [w.lower() for w in self.config.ABBREVIATION_STOP_WORDS]

        # Filter out stop words and words with trailing dots
        filtered_words = [
            w for w in words
            if w.lower() not in stop_words_lower and not w.endswith(".")
        ]

        # Take first letter of each remaining word
        initials = [w[0] for w in filtered_words if w]

        # Join initials; return None if < 2 characters
        abbreviation = "".join(initials)
        return abbreviation if len(abbreviation) >= 2 else None

    def _normalize_and_hash(self, query: str) -> str:
        """Normalize query: lowercase, strip extra whitespace, then SHA-256."""
        normalized = " ".join(query.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _search_with_dedup(
        self, query: str, company_id: int, limit: int = 20
    ) -> tuple:
        """Check query cache before calling Firecrawl; populate cache after.

        Args:
            query: The search query string.
            company_id: Company ID (for cache insertion and logging).
            limit: Max results to request from Firecrawl.

        Returns:
            Tuple of (results: List[Dict], cache_hit: bool).
            On a cache hit, results are loaded from the search_results table.
        """
        query_hash = self._normalize_and_hash(query)

        # Dedup check (honoured only if ENABLE_QUERY_DEDUP is True)
        if self.config.ENABLE_QUERY_DEDUP and not self.config.FORCE_REFRESH:
            if self.db.is_query_cached(query_hash):
                self.pipeline_logger.log_event(
                    "dedup_query_cache_hit",
                    company_id,
                    {"query": query, "hash": query_hash},
                )
                # Retrieve previously saved results for this query
                cached_results = self.db.fetch_all(
                    "SELECT * FROM search_results WHERE search_query = ? AND company_id = ?",
                    (query, company_id),
                )
                return cached_results, True

        # Live API call
        results = self._firecrawl_search(query, limit=limit)

        # Populate query cache
        expires_at = (
            datetime.utcnow() + timedelta(days=self.config.CACHE_TTL_DAYS)
        ).strftime("%Y-%m-%d %H:%M:%S")
        self.db.insert_query_cache(
            query_hash=query_hash,
            query_text=query,
            company_id=company_id,
            expires_at=expires_at,
            result_count=len(results),
        )

        return results, False

    def _check_early_stop(self, company_id: int) -> bool:
        """Returns True if enough high-scoring filtered_links exist for this company."""
        if not self.config.EARLY_STOP_COUNT:
            return False
        links = self.db.fetch_all(
            "SELECT COUNT(*) as cnt FROM filtered_links WHERE company_id = ? AND relevance_score >= ? AND should_scrape = 1",
            (company_id, self.config.EARLY_STOP_SCORE),
        )
        count = links[0]["cnt"] if links else 0
        return count >= self.config.EARLY_STOP_COUNT

    def _check_inline_early_stop(self, company_id: int, company_name: str, all_results: List[Dict], tier: str) -> bool:
        """Inline early stop check: score results directly without DB read."""
        if not self.config.EARLY_STOP_COUNT:
            return False
            
        scored = self.filter_module.score_urls_batch(all_results, company_name)
        qualified_count = sum(1 for item in scored if item["relevance_score"] >= self.config.EARLY_STOP_SCORE)
        
        if qualified_count >= self.config.EARLY_STOP_COUNT:
            self.pipeline_logger.log_event(
                "early_stop_triggered",
                company_id,
                {
                    "tier": tier,
                    "qualified_count": qualified_count,
                    "threshold": self.config.EARLY_STOP_COUNT
                }
            )
            return True
        return False

    def _count_good_links(self, company_id: int) -> int:
        """Return the count of high-scoring filtered_links for this company."""
        links = self.db.fetch_all(
            "SELECT COUNT(*) as cnt FROM filtered_links WHERE company_id = ? AND relevance_score >= ? AND should_scrape = 1",
            (company_id, self.config.EARLY_STOP_SCORE),
        )
        return links[0]["cnt"] if links else 0

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
                    raw_results = data.get("data", [])
                    # Validate each result
                    validated_results = []
                    for result in raw_results:
                        try:
                            validated = validate_search_result(result)
                            validated_results.append(result)  # Return original dict, validation passed
                        except ValueError as e:
                            logger.warning(f"Skipping invalid search result: {e}")
                            continue
                    return validated_results

                if resp.status_code == 402:
                    if self.rate_limiter:
                        self.rate_limiter.report_error(402)
                    raise CriticalError(
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
                    raise RetryableError(
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
            search_type: One of 'tier1_coarse', 'tier2a_recruitment',
                         'tier2b_abbrev', 'tier2c_facebook'.
            results: Raw result dicts from Firecrawl (or cached DB rows).

        Returns:
            List of saved result dicts (with added 'id' and 'result_rank').
        """
        saved: List[Dict] = []
        credits_per_result = self.CREDITS_PER_SEARCH / max(len(results), 1)

        from src.utils import normalize_url
        for rank, item in enumerate(results, start=1):
            url = normalize_url(item.get("url", ""))
            title = item.get("title", "") or item.get("metadata", {}).get("title", "")
            snippet = item.get("snippet", "") or item.get("description", "")
            if not snippet and item.get("markdown"):
                snippet = item.get("markdown", "")[:300]

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


# ------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------

class FirecrawlCreditExhausted(Exception):
    """Raised when Firecrawl returns HTTP 402 (credits exhausted)."""
    pass


class FirecrawlSearchError(Exception):
    """Raised for unrecoverable Firecrawl API errors."""
    pass
