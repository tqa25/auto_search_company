import os
import time
import requests
import logging
from typing import List, Dict, Set
from urllib.parse import urlparse
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
VN_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

class FirecrawlDeepSearch:
    """Firecrawl Search engine for deep search step in pipeline."""
    
    FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
    
    def __init__(self, db, pipeline_logger, config=None):
        if config is None:
            from src.config import default_config
            self.config = default_config
        else:
            self.config = config
            
        self.db = db
        self.pipeline_logger = pipeline_logger
        self.api_key = os.getenv("FIRECRAWL_API_KEY", "")
        if not self.api_key:
            logger.warning("FIRECRAWL_API_KEY not set.")

    def search(self, company_id: int, query: str, limit: int = 100) -> List[Dict]:
        """Execute a Search via Firecrawl /v2/search API.
        
        Returns:
            list of dicts: [{url, title, snippet}, ...]
        """
        if not self.api_key:
            return []

        log_id = self.pipeline_logger.log_step_start(
            company_id, "firecrawl_search",
            source_name=f"firecrawl_search: {query[:60]}",
            raw_request={"query": query, "limit": limit}
        )

        started_at = datetime.now(VN_TZ)
        start_time = time.time()
        
        credits_used = 2 # Firecrawl search always uses 2 credits

        try:
            resp = requests.post(
                self.FIRECRAWL_SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}", 
                    "Content-Type": "application/json"
                },
                json={
                    "query": query, 
                    "limit": limit,
                    "lang": "vi",
                    "country": "vn"
                },
                timeout=30
            )
            duration = time.time() - start_time
            finished_at = datetime.now(VN_TZ)

            if resp.status_code == 429:
                logger.warning(f"[{company_id}] Firecrawl Search rate limited (429).")
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message="429 Too Many Requests",
                    network_latency_ms=duration * 1000,
                    metadata={"started_at": started_at.isoformat(),
                              "finished_at": finished_at.isoformat(),
                              "credits_used": credits_used}
                )
                return []
                
            if resp.status_code != 200:
                logger.warning(f"[{company_id}] Firecrawl Search error: HTTP {resp.status_code} - {resp.text}")
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=f"HTTP {resp.status_code}",
                    network_latency_ms=duration * 1000,
                    metadata={"started_at": started_at.isoformat(),
                              "finished_at": finished_at.isoformat(),
                              "credits_used": credits_used}
                )
                return []

            data = resp.json()
            if not data.get("success"):
                logger.warning(f"[{company_id}] Firecrawl Search API returned success=false: {data.get('error')}")
                self.pipeline_logger.log_step_end(
                    log_id, status="failed", error_message=str(data.get('error', 'Unknown Error')),
                    network_latency_ms=duration * 1000,
                    metadata={"started_at": started_at.isoformat(),
                              "finished_at": finished_at.isoformat(),
                              "credits_used": credits_used}
                )
                return []
                
            raw_data = data.get("data", {})
            # Firecrawl v2 returns {data: {web: [...]}}
            if isinstance(raw_data, dict):
                firecrawl_results = raw_data.get("web", []) or []
            elif isinstance(raw_data, list):
                firecrawl_results = raw_data
            else:
                firecrawl_results = []

            results = []
            for item in firecrawl_results:
                if isinstance(item, dict):
                    results.append({
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "snippet": item.get("description", ""),
                    })

            self.pipeline_logger.log_step_end(
                log_id, status="success",
                credits_used=credits_used,
                data_saved=bool(results),
                network_latency_ms=duration * 1000,
                metadata={
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(duration, 2),
                    "firecrawl_credits_used": credits_used,
                    "results_count": len(results),
                }
            )

            logger.info(f"[{company_id}] Firecrawl Search: {len(results)} results | {duration:.1f}s")
            return results

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{company_id}] Firecrawl Search error: {e}")
            self.pipeline_logger.log_step_end(
                log_id, status="failed", error_message=str(e),
                network_latency_ms=duration * 1000
            )
            return []

    def build_fallback_queries(self, gemini_result: dict, company_name: str = "") -> List[Dict]:
        """Build complementary queries based on Gemini Quick Search results.

        Returns list of {query: str, type: str, required: bool}
        """
        queries = []
        core_name = gemini_result.get("core_name", "")
        core_name_vi = gemini_result.get("core_name_vi", "")
        tax_code = gemini_result.get("tax_code", "")

        name_vi = core_name_vi if core_name_vi else core_name
        name_en = core_name if core_name else core_name_vi
        
        if not name_en and company_name:
            name_en = company_name

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

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize a URL for dedup comparison."""
        from src.utils import normalize_url as utils_normalize
        return utils_normalize(url)

    @staticmethod
    def dedup_results(results: List[Dict], existing_urls: Set[str]) -> List[Dict]:
        """Remove results whose URLs overlap with existing_urls.

        Args:
            results: list of dicts with 'url' key
            existing_urls: set of normalized URLs to exclude

        Returns:
            filtered list
        """
        normalized_existing = {FirecrawlDeepSearch.normalize_url(u) for u in existing_urls}
        deduped = []
        for r in results:
            if FirecrawlDeepSearch.normalize_url(r.get("url", "")) not in normalized_existing:
                deduped.append(r)
        return deduped
