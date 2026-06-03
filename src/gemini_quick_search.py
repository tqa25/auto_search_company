"""
Gemini Quick Search Module — Bước 1 of the 4-step pipeline.

Uses Gemini 2.5 Flash Lite with Google Search Grounding to rapidly
find company contact information in 5-10 seconds per company.

Includes:
  - Daily quota limiter to stay within free tier (1,450 requests/day)
  - Detailed logging of token usage, duration, sources for reporting
  - Structured JSON parsing with fallback
"""

import os
import json
import time
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.database import DatabaseManager
from src.logger import PipelineLogger

load_dotenv()
logger = logging.getLogger(__name__)

# Vietnam timezone (UTC+7)
VN_TZ = timezone(timedelta(hours=7))


class GeminiQuickSearch:
    """Bước 1: Fast company contact lookup via Gemini + Google Search Grounding."""

    PROMPT_TEMPLATE = """Tìm thông tin công ty "{company_name}" tại Việt Nam. 
CHỈ TRẢ VỀ JSON THUẦN TÚY (KHÔNG GIẢI THÍCH):
{{
  "core_name": "Tên thương hiệu cốt lõi (LOẠI BỎ hoàn toàn hậu tố như co.,ltd, corp, jsc, llc. VD: 'king freight int\\'l vn co.,ltd' -> 'king freight int\\'l vn')",
  "core_name_vi": "Tên tiếng Việt pháp lý",
  "abbreviation": "Viết tắt",
  "address": "Địa chỉ",
  "phone": "SĐT",
  "email": "Email",
  "website": "Website",
  "tax_code": "MST",
  "representative": "Người đại diện",
  "sources": ["url1", "url2"],
  "confidence": 0.95
}}"""

    def __init__(self, db: DatabaseManager, pipeline_logger: PipelineLogger, config=None):
        from src.config import default_config
        self.config = config or default_config
        self.db = db
        self.pipeline_logger = pipeline_logger

        api_key = self.config.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not set. Gemini Quick Search will be disabled.")
        self.client = genai.Client(api_key=api_key, http_options={'timeout': 600000}) if api_key else None

    # ------------------------------------------------------------------
    # Quota management
    # ------------------------------------------------------------------

    def _get_today_str(self) -> str:
        """Return today's date string in VN timezone (YYYY-MM-DD)."""
        return datetime.now(VN_TZ).strftime("%Y-%m-%d")

    def _get_quota_used_today(self) -> int:
        """Return the number of Gemini grounding requests used today."""
        today = self._get_today_str()
        row = self.db.fetch_one(
            "SELECT gemini_grounding_used FROM daily_quota WHERE date = ?",
            (today,)
        )
        return row["gemini_grounding_used"] if row else 0

    def _increment_quota(self):
        """Increment today's Gemini grounding request count."""
        today = self._get_today_str()
        self.db.execute_query(
            """INSERT INTO daily_quota (date, gemini_grounding_used, updated_at)
               VALUES (?, 1, CURRENT_TIMESTAMP)
               ON CONFLICT(date) DO UPDATE SET
                   gemini_grounding_used = gemini_grounding_used + 1,
                   updated_at = CURRENT_TIMESTAMP""",
            (today,)
        )

    def _check_quota(self) -> bool:
        """Return True if we can still make requests today."""
        used = self._get_quota_used_today()
        limit = self.config.GEMINI_DAILY_LIMIT
        warn_threshold = int(limit * self.config.GEMINI_DAILY_WARN_PERCENT)

        if used >= limit:
            logger.warning(f"⚠️ Gemini daily quota reached: {used}/{limit}. Falling back.")
            return False

        if used >= warn_threshold:
            logger.info(f"📊 Gemini quota warning: {used}/{limit} ({used/limit*100:.0f}%)")

        return True

    # ------------------------------------------------------------------
    # Core search
    # ------------------------------------------------------------------

    def search(self, company_id: int) -> Dict:
        """Execute Gemini Quick Search for a company.

        Returns:
            dict with keys: result (parsed data), is_sufficient (bool),
            fallback_reason (str or None), duration_seconds, token counts
        """
        company = self.db.get_company(company_id)
        if not company:
            logger.error(f"Company {company_id} not found")
            return self._empty_result("company_not_found")

        company_name = company["original_name"]

        # Feature toggle check
        if not self.config.GEMINI_QUICK_ENABLED:
            logger.info(f"[{company_id}] Gemini Quick Search disabled by config")
            return self._empty_result("feature_disabled")

        # Client check
        if not self.client:
            logger.warning(f"[{company_id}] No Gemini API key configured")
            return self._empty_result("no_api_key")

        # Quota check
        if not self._check_quota():
            return self._empty_result("quota_exceeded")

        # Log step start
        log_id = self.pipeline_logger.log_step_start(
            company_id, "gemini_quick",
            source_name=f"gemini_quick: {company_name}",
            raw_request={"company_name": company_name, "model": self.config.AI_GROUNDING_MODEL}
        )

        started_at = datetime.now(VN_TZ)
        start_time = time.time()

        try:
            # Build prompt
            prompt = self.PROMPT_TEMPLATE.format(company_name=company_name)

            # Call Gemini with Search Grounding
            try:
                response = self.client.models.generate_content(
                    model=self.config.AI_GROUNDING_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[{"google_search": {}}],
                        temperature=0.0,
                        max_output_tokens=2048
                    )
                )
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota exceeded" in error_msg.lower():
                    logger.error(f"[{company_id}] Gemini API Rate Limit/Quota Exceeded (429)! Stop processing.")
                    from src.errors import CriticalError
                    raise CriticalError("Gemini API quota exceeded or rate limit hit. Stop pipeline.")
                    
                elif "503" in error_msg or "unavailable" in error_msg.lower() or "experiencing high demand" in error_msg.lower():
                    logger.warning(f"[{company_id}] Gemini API 503/Unavailable. Attempting fallback to models/gemini-3.5-flash...")
                    try:
                        response = self.client.models.generate_content(
                            model="models/gemini-3.5-flash",
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                tools=[{"google_search": {}}],
                                temperature=0.0,
                                max_output_tokens=2048
                            )
                        )
                    except Exception as fallback_e:
                        logger.warning(f"[{company_id}] Fallback to 3.5-flash also failed: {fallback_e}")
                        from src.errors import RetryableError
                        raise RetryableError("Gemini API 503 unavailable and fallback failed.")
                else:
                    logger.warning(f"[{company_id}] Gemini grounding failed ({e}). Retrying without grounding...")
                    # Fallback without grounding
                    response = self.client.models.generate_content(
                        model=self.config.AI_GROUNDING_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            max_output_tokens=2048
                        )
                    )

            duration = time.time() - start_time
            finished_at = datetime.now(VN_TZ)

            # Increment quota
            self._increment_quota()

            # Parse token usage
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count or 0
                output_tokens = response.usage_metadata.candidates_token_count or 0
                total_tokens = response.usage_metadata.total_token_count or 0

            # Extract grounding sources
            grounding_sources = []
            try:
                if response.candidates and response.candidates[0].grounding_metadata:
                    metadata = response.candidates[0].grounding_metadata
                    if metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if chunk.web:
                                grounding_sources.append(chunk.web.uri)
            except Exception:
                pass

            # Parse JSON response
            parsed = self._parse_response(response.text)

            # Merge grounding sources with parsed sources
            parsed_sources = parsed.get("sources", []) or []
            all_sources = list(set(parsed_sources + grounding_sources))
            parsed["sources"] = all_sources

            # Evaluate sufficiency
            is_sufficient, fallback_reason = self._evaluate(parsed)

            # Save to DB
            quota_used = self._get_quota_used_today()
            self._save_result(company_id, parsed, is_sufficient, fallback_reason,
                              input_tokens, output_tokens, total_tokens, duration,
                              grounding_sources)

            # Update company table with core info
            self._update_company(company_id, parsed)

            # Save to extracted_contacts if we have useful data
            if parsed.get("phone") or parsed.get("email"):
                self._save_contact(company_id, parsed)

            # Log step end
            self.pipeline_logger.log_step_end(
                log_id, status="sufficient" if is_sufficient else "insufficient",
                credits_used=0,
                data_saved=True,
                network_latency_ms=duration * 1000,
                raw_response_summary={"model": self.config.AI_GROUNDING_MODEL},
                metadata={
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(duration, 2),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "grounding_sources_count": len(grounding_sources),
                    "has_phone": bool(parsed.get("phone")),
                    "confidence": parsed.get("confidence", 0),
                    "fallback_needed": not is_sufficient,
                    "quota_used_today": quota_used,
                }
            )

            logger.info(
                f"[{company_id}] Gemini Quick: {'✅ sufficient' if is_sufficient else '⚡ fallback needed'} "
                f"| phone={'yes' if parsed.get('phone') else 'no'} "
                f"| conf={parsed.get('confidence', 0)} "
                f"| {duration:.1f}s "
                f"| tokens={total_tokens}"
            )

            return {
                "result": parsed,
                "is_sufficient": is_sufficient,
                "fallback_reason": fallback_reason,
                "duration_seconds": round(duration, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "grounding_sources": grounding_sources,
            }

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "quota exceeded" in error_msg.lower():
                logger.error(f"[{company_id}] Gemini API Rate Limit/Quota Exceeded (429)! Stop processing.")
                self.pipeline_logger.log_step_end(
                    log_id, status="error", error_message="Rate Limit/Quota Exceeded",
                    metadata={"error_category": "critical"}
                )
                from src.errors import CriticalError
                raise CriticalError("Gemini API quota exceeded or rate limit hit. Stop pipeline.")
                
            if "503" in error_msg or "unavailable" in error_msg.lower() or "experiencing high demand" in error_msg.lower():
                logger.error(f"[{company_id}] Gemini API transient error (503) caught in quick search!")
                self.pipeline_logger.log_step_end(
                    log_id, status="error", error_message="Service Unavailable (503)",
                    metadata={"error_category": "retryable"}
                )
                from src.errors import RetryableError
                raise RetryableError("Gemini API 503 unavailable during quick search.")
                
            duration = time.time() - start_time
            logger.error(f"[{company_id}] Gemini Quick Search error: {e}")
            self.pipeline_logger.log_step_end(
                log_id, status="error", error_message=error_msg,
                network_latency_ms=duration * 1000,
                metadata={"duration_seconds": round(duration, 2)}
            )
            return self._empty_result("error")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_response(self, text: str) -> dict:
        """Parse Gemini response text as JSON. Handles markdown code blocks and noise."""
        if not text:
            return {}
            
        # Try to find JSON block { ... } if it's mixed with other text
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            text = match.group(1)
            
        cleaned = text.strip()
        # Remove markdown markers
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Gemini response as JSON: {text[:200]}")
            # Try one more fallback: if it's cut off, maybe we can at least get some fields?
            # But usually it's better to return {} and retry if needed.
            return {}

    def _evaluate(self, parsed: dict) -> tuple:
        """Evaluate if the result is sufficient to skip fallback.

        Returns:
            (is_sufficient: bool, fallback_reason: str or None)
        """
        phone = parsed.get("phone")
        confidence = parsed.get("confidence", 0)
        sources = parsed.get("sources", [])
        threshold = self.config.GEMINI_QUICK_CONFIDENCE_THRESHOLD

        if not phone or not str(phone).strip():
            return False, "no_phone"
        if confidence < threshold:
            return False, "low_confidence"
        if not sources:
            return False, "no_sources"
        return True, None

    def _save_result(self, company_id, parsed, is_sufficient, fallback_reason,
                     input_tokens, output_tokens, total_tokens, duration, grounding_sources):
        """Save result to gemini_quick_results table."""
        self.db.execute_query(
            """INSERT INTO gemini_quick_results
               (company_id, core_name, core_name_vi, abbreviation, address, phone, email,
                website, tax_code, fax, representative, confidence, sources_json,
                grounding_sources_json, input_tokens, output_tokens, total_tokens,
                duration_seconds, is_sufficient, fallback_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company_id,
             parsed.get("core_name"), parsed.get("core_name_vi"),
             parsed.get("abbreviation"), parsed.get("address"),
             parsed.get("phone"), parsed.get("email"),
             parsed.get("website"), parsed.get("tax_code"),
             parsed.get("fax"), parsed.get("representative"),
             parsed.get("confidence", 0),
             json.dumps(parsed.get("sources", []), ensure_ascii=False),
             json.dumps(grounding_sources, ensure_ascii=False),
             input_tokens, output_tokens, total_tokens,
             round(duration, 2), is_sufficient, fallback_reason)
        )

    def _update_company(self, company_id, parsed):
        """Update companies table with info from Gemini Quick Search."""
        updates = {}
        if parsed.get("core_name_vi"):
            updates["vietnamese_name"] = parsed["core_name_vi"]
        if parsed.get("tax_code"):
            updates["tax_code"] = parsed["tax_code"]
        if parsed.get("address"):
            updates["address"] = parsed["address"]
        if updates:
            self.db.update_company(company_id, **updates)

    def _save_contact(self, company_id, parsed):
        """Save extracted contact to extracted_contacts table. One record per source URL."""
        sources = parsed.get("sources", [])
        if not sources:
            sources = ["unknown"]
        else:
            sources = sources[:3] # keep max 3 to avoid spam
            
        for source_url in sources:
            self.db.execute_query(
                """INSERT INTO extracted_contacts
                   (company_id, source_type, source_url, address, phone, email, website,
                    fax, representative, raw_ai_response, confidence_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (company_id, "gemini_grounding",
                 source_url,
                 parsed.get("address"), parsed.get("phone"),
                 parsed.get("email"), parsed.get("website"),
                 parsed.get("fax"), parsed.get("representative"),
                 json.dumps(parsed, ensure_ascii=False),
                 parsed.get("confidence", 0))
            )

    def _empty_result(self, reason: str) -> Dict:
        """Return an empty result dict with a fallback reason."""
        return {
            "result": {},
            "is_sufficient": False,
            "fallback_reason": reason,
            "duration_seconds": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "grounding_sources": [],
        }
