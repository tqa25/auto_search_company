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

    def search_company(self, company_id: int) -> List[Dict]:
        """Execute the full 2-tier coarse+fallback search strategy for a single company.

        Strategy order:
          ① Tier 1 — Coarse search: ("{name}" OR "{abbr}") AND ("lien he" OR "contact")
          ② Tier 2a — Recruitment query (if Tier 1 didn't early-stop)
          ③ Tier 2b — Abbreviation query (if applicable and Tier 2a didn't early-stop)
          ④ Tier 2c — Facebook search (if < FB_FALLBACK_THRESHOLD high-scoring links)

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

        # Update status to 'searching'
        self.db.update_company(company_id, status="searching")

        all_results: List[Dict] = []

        # Compute abbreviation
        abbreviation = self._compute_abbreviation(company_name)

        # ------------------------------------------------------------------
        # Tier 1 — Coarse search
        # ------------------------------------------------------------------
        if abbreviation:
            tier1_query = (
                f'("{company_name}" OR "{abbreviation}") AND ("liên hệ" OR "contact")'
            )
        else:
            tier1_query = f'"{company_name}" AND ("liên hệ" OR "contact")'

        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"tier1_coarse: {company_name}",
            raw_request={"query": tier1_query, "tier": "tier1_coarse"}
        )
        try:
            start_time = time.time()
            results, cache_hit = self._search_with_dedup(
                tier1_query, company_id, limit=self.config.SEARCH_LIMIT
            )
            elapsed_ms = (time.time() - start_time) * 1000
            saved = self._save_results(company_id, tier1_query, "tier1_coarse", results)
            all_results.extend(saved)
            self.pipeline_logger.log_step_end(
                log_id,
                status="success",
                credits_used=0 if cache_hit else self.CREDITS_PER_SEARCH,
                data_saved=True,
                network_latency_ms=elapsed_ms,
                raw_response_summary={"result_count": len(saved), "status_code": 200},
                metadata={
                    "links_found": len(saved),
                    "search_type": "tier1_coarse",
                    "cache_hit": cache_hit,
                },
            )
        except CriticalError as e:
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e), error_category=e.category
            )
            raise
        except RetryableError as e:
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e), error_category=e.category
            )
            raise
        except Exception as e:
            category = e.category if isinstance(e, PipelineError) else "unknown"
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e), error_category=category
            )

        if self._check_inline_early_stop(company_id, company_name, all_results, "T1"):
            self.db.update_company(company_id, status="searched")
            return all_results

        # ------------------------------------------------------------------
        # Tier 2a — Recruitment query
        # ------------------------------------------------------------------
        tier2a_query = (
            f'"{company_name}" AND ("tuyển dụng" OR "nhân sự" OR "việc làm")'
        )

        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"tier2a_recruitment: {company_name}",
            raw_request={"query": tier2a_query, "tier": "tier2a_recruitment"}
        )
        try:
            start_time = time.time()
            results, cache_hit = self._search_with_dedup(
                tier2a_query, company_id, limit=self.config.SEARCH_LIMIT
            )
            elapsed_ms = (time.time() - start_time) * 1000
            saved = self._save_results(company_id, tier2a_query, "tier2a_recruitment", results)
            all_results.extend(saved)
            self.pipeline_logger.log_step_end(
                log_id,
                status="success",
                credits_used=0 if cache_hit else self.CREDITS_PER_SEARCH,
                data_saved=True,
                network_latency_ms=elapsed_ms,
                raw_response_summary={"result_count": len(saved), "status_code": 200},
                metadata={
                    "links_found": len(saved),
                    "search_type": "tier2a_recruitment",
                    "cache_hit": cache_hit,
                },
            )
        except CriticalError as e:
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e), error_category=e.category
            )
            raise
        except RetryableError as e:
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e), error_category=e.category
            )
            raise
        except Exception as e:
            category = e.category if isinstance(e, PipelineError) else "unknown"
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e), error_category=category
            )

        if self._check_inline_early_stop(company_id, company_name, all_results, "T2a"):
            self.db.update_company(company_id, status="searched")
            return all_results

        # ------------------------------------------------------------------
        # Tier 2b — Abbreviation query (only if abbreviation exists and differs)
        # ------------------------------------------------------------------
        if abbreviation and abbreviation.upper() != company_name.upper():
            tier2b_query = f'"{abbreviation}" AND ("liên hệ" OR "contact")'

            log_id = self.pipeline_logger.log_step_start(
                company_id, "search", source_name=f"tier2b_abbrev: {abbreviation}",
                raw_request={"query": tier2b_query, "tier": "tier2b_abbrev"}
            )
            try:
                start_time = time.time()
                results, cache_hit = self._search_with_dedup(
                    tier2b_query, company_id, limit=self.config.SEARCH_LIMIT
                )
                elapsed_ms = (time.time() - start_time) * 1000
                saved = self._save_results(
                    company_id, tier2b_query, "tier2b_abbrev", results
                )
                all_results.extend(saved)
                self.pipeline_logger.log_step_end(
                    log_id,
                    status="success",
                    credits_used=0 if cache_hit else self.CREDITS_PER_SEARCH,
                    data_saved=True,
                    network_latency_ms=elapsed_ms,
                    raw_response_summary={"result_count": len(saved), "status_code": 200},
                    metadata={
                        "links_found": len(saved),
                        "search_type": "tier2b_abbrev",
                        "cache_hit": cache_hit,
                    },
                )
            except CriticalError as e:
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e), error_category=e.category
                )
                raise
            except RetryableError as e:
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e), error_category=e.category
                )
                raise
            except Exception as e:
                category = e.category if isinstance(e, PipelineError) else "unknown"
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e), error_category=category
                )

            if self._check_inline_early_stop(company_id, company_name, all_results, "T2b"):
                self.db.update_company(company_id, status="searched")
                return all_results

        # ------------------------------------------------------------------
        # Tier 2c — Facebook search (only if below FB_FALLBACK_THRESHOLD)
        # ------------------------------------------------------------------
        good_count = self._count_good_links(company_id)
        if good_count < self.config.FB_FALLBACK_THRESHOLD:
            tier2c_query = f'site:facebook.com "{company_name}"'

            log_id = self.pipeline_logger.log_step_start(
                company_id, "search", source_name=f"tier2c_facebook: {company_name}",
                raw_request={"query": tier2c_query, "tier": "tier2c_facebook"}
            )
            try:
                start_time = time.time()
                results, cache_hit = self._search_with_dedup(
                    tier2c_query, company_id, limit=self.config.SEARCH_LIMIT
                )
                elapsed_ms = (time.time() - start_time) * 1000
                saved = self._save_results(
                    company_id, tier2c_query, "tier2c_facebook", results
                )
                all_results.extend(saved)
                self.pipeline_logger.log_step_end(
                    log_id,
                    status="success",
                    credits_used=0 if cache_hit else self.CREDITS_PER_SEARCH,
                    data_saved=True,
                    network_latency_ms=elapsed_ms,
                    raw_response_summary={"result_count": len(saved), "status_code": 200},
                    metadata={
                        "links_found": len(saved),
                        "search_type": "tier2c_facebook",
                        "cache_hit": cache_hit,
                    },
                )
            except CriticalError as e:
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e), error_category=e.category
                )
                raise
            except RetryableError as e:
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e), error_category=e.category
                )
                raise
            except Exception as e:
                category = e.category if isinstance(e, PipelineError) else "unknown"
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(e), error_category=category
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


# ------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------

class FirecrawlCreditExhausted(Exception):
    """Raised when Firecrawl returns HTTP 402 (credits exhausted)."""
    pass


class FirecrawlSearchError(Exception):
    """Raised for unrecoverable Firecrawl API errors."""
    pass
