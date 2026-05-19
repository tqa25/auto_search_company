"""
Serper Search Module — Used in Bước 2 (Google Maps) and Bước 3 (Deep Search).

Provides:
  - Google Maps Places API lookup (structured phone/address/website)
  - Google Search API (organic results with titles/snippets/URLs)
  - URL deduplication against Gemini grounding sources
  - Daily quota tracking for Serper credits
"""

import os
import time
import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from typing import List, Dict, Optional, Set

import requests
from dotenv import load_dotenv

from src.database import DatabaseManager
from src.logger import PipelineLogger

load_dotenv()
logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))


class SerperSearch:
    """Serper API client for Google Search and Google Maps Places lookups."""

    SEARCH_URL = "https://google.serper.dev/search"
    PLACES_URL = "https://google.serper.dev/places"

    def __init__(self, db: DatabaseManager, pipeline_logger: PipelineLogger, config=None):
        from src.config import default_config
        self.config = config or default_config
        self.db = db
        self.pipeline_logger = pipeline_logger
        self.api_key = os.getenv("SERPER_API_KEY", "")
        if not self.api_key:
            logger.warning("SERPER_API_KEY not set. Serper features will be disabled.")

    # ------------------------------------------------------------------
    # Quota tracking
    # ------------------------------------------------------------------

    def _get_today_str(self) -> str:
        return datetime.now(VN_TZ).strftime("%Y-%m-%d")

    def _increment_serper_quota(self, count: int = 1):
        """Increment today's Serper usage count."""
        today = self._get_today_str()
        self.db.execute_query(
            """INSERT INTO daily_quota (date, serper_used, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(date) DO UPDATE SET
                   serper_used = serper_used + ?,
                   updated_at = CURRENT_TIMESTAMP""",
            (today, count, count)
        )

    # ------------------------------------------------------------------
    # URL normalization for dedup
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize a URL for dedup comparison."""
        if not url:
            return ""
        parsed = urlparse(url.lower().rstrip("/"))
        host = parsed.netloc
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{parsed.path}"

    @staticmethod
    def dedup_results(results: List[Dict], existing_urls: Set[str]) -> List[Dict]:
        """Remove results whose URLs overlap with existing_urls.

        Args:
            results: list of dicts with 'url' key
            existing_urls: set of normalized URLs to exclude

        Returns:
            filtered list
        """
        normalized_existing = {SerperSearch.normalize_url(u) for u in existing_urls}
        deduped = []
        for r in results:
            if SerperSearch.normalize_url(r.get("url", "")) not in normalized_existing:
                deduped.append(r)
        return deduped

    # ------------------------------------------------------------------
    # Bước 2: Google Maps Places lookup
    # ------------------------------------------------------------------

    def search_places(self, company_id: int, query: str) -> Dict:
        """Search Google Maps via Serper Places API.

        Returns:
            dict with keys: phone, address, website, title, rating, results_count,
            duration_seconds, serper_credits_used
        """
        if not self.api_key or not self.config.SERPER_ENABLED:
            return {"phone": None, "address": None, "website": None, "results_count": 0,
                    "duration_seconds": 0, "serper_credits_used": 0}

        log_id = self.pipeline_logger.log_step_start(
            company_id, "google_maps",
            source_name=f"serper_places: {query[:60]}",
            raw_request={"query": query, "endpoint": "places"}
        )

        started_at = datetime.now(VN_TZ)
        start_time = time.time()

        try:
            resp = requests.post(
                self.PLACES_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "gl": "vn", "hl": "vi"},
                timeout=10
            )
            duration = time.time() - start_time
            finished_at = datetime.now(VN_TZ)

            self._increment_serper_quota(1)

            if resp.status_code != 200:
                logger.warning(f"[{company_id}] Serper Places error: HTTP {resp.status_code}")
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=f"HTTP {resp.status_code}",
                    network_latency_ms=duration * 1000,
                    metadata={"started_at": started_at.isoformat(),
                              "finished_at": finished_at.isoformat()}
                )
                return {"phone": None, "address": None, "website": None, "results_count": 0,
                        "duration_seconds": round(duration, 2), "serper_credits_used": 1}

            data = resp.json()
            places = data.get("places", [])

            result = {
                "phone": None, "address": None, "website": None,
                "title": None, "rating": None,
                "results_count": len(places),
                "duration_seconds": round(duration, 2),
                "serper_credits_used": 1,
                "all_places": places,
                "raw_response": data,
            }

            # Take the first/best result
            if places:
                best = places[0]
                result["phone"] = best.get("phoneNumber")
                result["address"] = best.get("address")
                result["website"] = best.get("website")
                result["title"] = best.get("title")
                result["rating"] = best.get("rating")

            self.pipeline_logger.log_step_end(
                log_id, status="success",
                credits_used=0,
                data_saved=bool(result["phone"]),
                network_latency_ms=duration * 1000,
                metadata={
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(duration, 2),
                    "serper_credits_used": 1,
                    "results_count": len(places),
                    "has_phone": bool(result["phone"]),
                    "raw_response": data,
                }
            )

            logger.info(
                f"[{company_id}] Google Maps: {'✅ phone found' if result['phone'] else '❌ no phone'} "
                f"| {len(places)} results | {duration:.1f}s"
            )

            return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{company_id}] Serper Places error: {e}")
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e),
                network_latency_ms=duration * 1000,
                metadata={"started_at": started_at.isoformat() if 'started_at' in dir() else None,
                          "finished_at": datetime.now(VN_TZ).isoformat()}
            )
            return {"phone": None, "address": None, "website": None, "results_count": 0,
                    "duration_seconds": round(duration, 2), "serper_credits_used": 0}

    # ------------------------------------------------------------------
    # Bước 3: Google Search (organic results)
    # ------------------------------------------------------------------

    def search(self, company_id: int, query: str, num_results: int = None) -> List[Dict]:
        """Execute a Google Search via Serper API.

        Returns:
            list of dicts: [{url, title, snippet}, ...]
        """
        if not self.api_key or not self.config.SERPER_ENABLED:
            return []

        num = num_results or self.config.SERPER_NUM_RESULTS
        # 2 credits for >10 results
        credits = 2 if num > 10 else 1

        log_id = self.pipeline_logger.log_step_start(
            company_id, "serper_search",
            source_name=f"serper_search: {query[:60]}",
            raw_request={"query": query, "num": num}
        )

        started_at = datetime.now(VN_TZ)
        start_time = time.time()

        try:
            resp = requests.post(
                self.SEARCH_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "gl": "vn", "hl": "vi", "num": num},
                timeout=10
            )
            duration = time.time() - start_time
            finished_at = datetime.now(VN_TZ)

            self._increment_serper_quota(credits)

            if resp.status_code != 200:
                logger.warning(f"[{company_id}] Serper Search error: HTTP {resp.status_code}")
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=f"HTTP {resp.status_code}",
                    network_latency_ms=duration * 1000,
                    metadata={"started_at": started_at.isoformat(),
                              "finished_at": finished_at.isoformat(),
                              "serper_credits_used": credits}
                )
                return []

            data = resp.json()
            organic = data.get("organic", [])

            results = []
            for item in organic:
                results.append({
                    "url": item.get("link", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                })

            self.pipeline_logger.log_step_end(
                log_id, status="success",
                credits_used=0,
                data_saved=bool(results),
                network_latency_ms=duration * 1000,
                metadata={
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(duration, 2),
                    "serper_credits_used": credits,
                    "results_count": len(results),
                }
            )

            logger.info(f"[{company_id}] Serper Search: {len(results)} results | {duration:.1f}s")
            return results

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{company_id}] Serper Search error: {e}")
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e),
                network_latency_ms=duration * 1000
            )
            return []

    # ------------------------------------------------------------------
    # Bước 3: Build smart fallback queries
    # ------------------------------------------------------------------

    def build_fallback_queries(self, gemini_result: dict) -> List[Dict]:
        """Build complementary queries based on Gemini Quick Search results.

        Returns list of {query: str, type: str, required: bool}
        """
        queries = []
        core_name = gemini_result.get("core_name", "")
        core_name_vi = gemini_result.get("core_name_vi", "")
        tax_code = gemini_result.get("tax_code", "")

        name_vi = core_name_vi if core_name_vi else core_name
        name_en = core_name if core_name else core_name_vi

        # Query 1: "{core_name}" ("số điện thoại" OR "liên hệ" OR "contact" OR "Zalo")
        if name_en:
            queries.append({
                "query": f'"{name_en}" ("số điện thoại" OR "liên hệ" OR "contact" OR "Zalo")',
                "type": "contact_search",
                "required": True,
            })

        # Query 2: "{core_name}" tuyển dụng
        if name_en:
            queries.append({
                "query": f'"{name_en}" tuyển dụng',
                "type": "recruitment_search",
                "required": False,
            })

        # Query 3: "{tax_code}"
        if tax_code:
            queries.append({
                "query": f'"{tax_code}"',
                "type": "tax_code_search",
                "required": False,
            })

        # Query 4: "{core_name}"
        if name_en:
            queries.append({
                "query": f'"{name_en}"',
                "type": "general_search",
                "required": False,
            })

        return queries
