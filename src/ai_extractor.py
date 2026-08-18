import os
import json
import time
import re
import requests
from urllib.parse import urlparse
from google import genai
from google.genai import types
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import RetryableError, CriticalError, SkippableError, PipelineError
from src.config import Config
from src.v2.runtime.retry import RetryExecutor, classify_error, create_retry_executor

def _normalize_tax_code(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value).strip()).replace("–", "-").replace("—", "-")


def _is_masothue_source(source_type: str | None, source_url: str | None) -> bool:
    if source_type == "masothue":
        return True
    parsed = urlparse(source_url or "")
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain == "masothue.com" or domain.endswith(".masothue.com")


def _extract_masothue_tax_code_from_url(source_url: str | None) -> str:
    if not source_url:
        return ""
    parsed = urlparse(source_url)
    path = parsed.path
    match = re.search(r"/(\d{10,14})(?:/|$)", path)
    if match:
        return match.group(1)
    return ""


def _extract_tax_code_from_text(text: str | None) -> str:
    if not text:
        return ""
    match = re.search(r"Mã số thuế[:：]\s*(\d{10,14})", text)
    if match:
        return match.group(1)
    match = re.search(r"Tax code[:：]\s*(\d{10,14})", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{10,14})\b", text)
    if match:
        return match.group(1)
    return ""


class AIExtractor:
    """Extracts contact information from scraped pages using Gemini AI."""

    EXTRACTION_PROMPT_TEMPLATE = """You are an expert at extracting Vietnamese company contact information from web page content.

Given the company name "{company_name}" and the following webpage content, extract the contact information.

Webpage content:
{markdown_content}

Return ONLY a JSON object with these fields (use null if not found):
{
  "address": "Full address of the company",
  "phone": "Phone number(s) with country code if available",
  "email": "Email address",
  "website": "Official website URL",
  "fax": "Fax number",
  "representative": "Legal representative name",
  "confidence": 0.95
}

Rules:
- Only extract information that is clearly present in the content
- For phone, prefer Vietnamese formats (+84, 0xxx, etc.)
- For address, include province/city if available
- Confidence should reflect how certain you are (0.0 to 1.0)
- If the page is not about the target company, return all null with confidence 0.0
"""

    def __init__(self, db: DatabaseManager, pipeline_logger: PipelineLogger, config: Config = None):
        from src.config import default_config
        self.config = config or default_config
        self.db = db
        self.logger = pipeline_logger

        api_key = self.config.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        self.client = genai.Client(api_key=api_key, http_options={'timeout': 600000})

    def _has_contact_signals(self, markdown_content: str) -> bool:
        """Check if markdown content has any contact-related signals."""
        if not markdown_content:
            return False
        content_lower = markdown_content.lower()
        signals = [
            "địa chỉ", "address", "số điện thoại", "phone", "điện thoại",
            "email", "hotline", "liên hệ", "contact", "fax", "website",
            "người đại diện", "representative", "giám đốc", "director"
        ]
        # Also check for email pattern
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        phone_pattern = r'(\+84|0)[0-9]{8,10}'
        
        return any(signal in content_lower for signal in signals) or \
               bool(re.search(email_pattern, content_lower)) or \
               bool(re.search(phone_pattern, content_lower))

    def _filter_values_to_page_markdown(self, values: dict, markdown_content: str, company_id: int, source_url: str) -> dict:
        """Filter extracted values to only keep those supported by the page markdown."""
        if not markdown_content:
            return {k: None for k in values}
        content_lower = markdown_content.lower()
        filtered = {}
        for field, val in values.items():
            if not val:
                filtered[field] = None
                continue
            val_str = str(val).lower()
            if val_str in content_lower:
                filtered[field] = val
            else:
                self.logger.log_event(
                    "extraction_filtered",
                    company_id,
                    {"field": field, "source_url": source_url, "reason": "not_in_page_markdown"},
                )
                filtered[field] = None
        return filtered

    def _masothue_phone_allowed(self, company_record: dict, source_type: str, source_url: str, markdown_content: str) -> tuple[bool, str]:
        """Check if phone from masothue.com is allowed (matches company tax code)."""
        if source_type != "masothue":
            return True, ""
        tax_code = company_record.get("tax_code") if company_record else ""
        if not tax_code:
            return True, ""
        page_tax_code = _extract_tax_code_from_text(markdown_content)
        if page_tax_code and page_tax_code == tax_code:
            return True, ""
        return False, f"tax_code_mismatch (page: {page_tax_code}, company: {tax_code})"

    def extract_from_page(self, scraped_page_id: int) -> dict:
        """Extracts contact info from a single scraped page using Gemini AI."""
        scraped_page = self.db.fetch_one("SELECT * FROM scraped_pages WHERE id = ?", (scraped_page_id,))
        if not scraped_page:
            return {"status": "skipped", "reason": "scraped_page_not_found"}

        # Idempotency check: Have we processed this page?
        existing = self.db.fetch_one("SELECT id, confidence_score FROM extracted_contacts WHERE scraped_page_id = ?", (scraped_page_id,))
        if existing:
            self.logger.logger.info(f"Page ID {scraped_page_id} already extracted, skipping AI call.")
            return {"status": "skipped", "reason": "already_extracted", "confidence": existing["confidence_score"]}

        company_id = scraped_page['company_id']
        source_type = scraped_page['source_type']
        source_url = scraped_page['url']
        markdown_content = scraped_page['markdown_content'] or ""

        company_record = self.db.get_company(company_id)
        company_name = company_record['original_name'] if company_record else "Unknown Company"

        # Sub-task A: Pre-filter content for contact signals
        if not self._has_contact_signals(markdown_content):
            self.logger.logger.info(f"Page ID {scraped_page_id} has no contact signals, skipping AI call.")
            log_id = self.logger.log_step_start(company_id, "AI_EXT", source_url=source_url, source_name=source_type)
            self.logger.log_step_end(log_id, "SKIPPED", metadata={"reason": "no_contact_signals", "event": "ai_skipped"})
            return {"status": "skipped", "reason": "no_contact_signals"}

        # Long content safeguard
        if len(markdown_content) > 15000:
            self.logger.logger.warning(f"Markdown content too long for scraped_page_id {scraped_page_id}, truncating to 15,000 chars.")
            markdown_content = markdown_content[:15000]

        prompt = self.EXTRACTION_PROMPT_TEMPLATE.replace(
            "{company_name}", company_name
        ).replace(
            "{markdown_content}", markdown_content
        )

        log_id = self.logger.log_step_start(company_id, "AI_EXT", source_url=source_url, source_name=source_type)

        retry_executor = create_retry_executor(self.config)

        def _do_extract(model_name: str):
            self.logger.logger.info(f"Calling Gemini API ({model_name}) for page ID {scraped_page_id}...")

            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
            raw_response = response.text

            # Parse JSON
            try:
                data = json.loads(raw_response)
            except json.JSONDecodeError:
                # Fallback cleanup just in case there are code block backticks
                clean_text = raw_response.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]

                try:
                    data = json.loads(clean_text)
                except json.JSONDecodeError:
                    self.logger.logger.warning(f"Failed to parse JSON for scraped_page_id {scraped_page_id}")
                    self.db.insert_extracted_contact(
                        company_id=company_id,
                        scraped_page_id=scraped_page_id,
                        source_type=source_type,
                        source_url=source_url,
                        address=None, phone=None, email=None, website=None, fax=None, representative=None,
                        raw_ai_response=raw_response,
                        confidence_score=0.0
                    )
                    self._record_domain_stat(source_url, False)
                    self.logger.log_step_end(log_id, "FAILED", error_message="json_parse_error", error_category="skippable")
                    raise SkippableError("json_parse_error")

            # Successfully parsed
            address = data.get("address")
            phone = data.get("phone")
            email = data.get("email")
            website = data.get("website")
            fax = data.get("fax")
            representative = data.get("representative")
            try:
                confidence = float(data.get("confidence", 0.0))
            except (ValueError, TypeError):
                confidence = 0.0

            # Check low confidence threshold
            if confidence < self.config.MIN_CONFIDENCE_THRESHOLD:
                self.logger.logger.warning(f"Low confidence extraction for page {scraped_page_id}: confidence={confidence} < threshold={self.config.MIN_CONFIDENCE_THRESHOLD}")
                low_conf_data = {
                    "page_id": scraped_page_id,
                    "source_type": source_type,
                    "confidence": confidence,
                    "threshold": self.config.MIN_CONFIDENCE_THRESHOLD
                }
                self.logger.log_event("low_confidence_extraction", company_id, low_conf_data)

            # Default "null" string normalization
            for var, val in [("address", address), ("phone", phone), ("email", email),
                             ("website", website), ("fax", fax), ("representative", representative)]:
                if str(val).lower() == "null" or str(val).lower() == "none" or val == "":
                    if var == "address": address = None
                    elif var == "phone": phone = None
                    elif var == "email": email = None
                    elif var == "website": website = None
                    elif var == "fax": fax = None
                    elif var == "representative": representative = None

            supported_values = self._filter_values_to_page_markdown(
                {
                    "address": address,
                    "phone": phone,
                    "email": email,
                    "website": website,
                    "fax": fax,
                    "representative": representative,
                },
                markdown_content,
                company_id,
                source_url,
            )
            address = supported_values["address"]
            phone = supported_values["phone"]
            email = supported_values["email"]
            website = supported_values["website"]
            fax = supported_values["fax"]
            representative = supported_values["representative"]

            phone_allowed, mismatch_reason = self._masothue_phone_allowed(
                company_record, source_type, source_url, markdown_content
            )
            if phone and not phone_allowed:
                self.logger.logger.warning(f"Suppressing masothue phone for page {scraped_page_id}: {mismatch_reason}")
                self.logger.log_event("masothue_phone_suppressed", company_id, {"reason": mismatch_reason, "source_url": source_url})
                phone = None

            self.db.insert_extracted_contact(
                company_id=company_id,
                scraped_page_id=scraped_page_id,
                source_type=source_type,
                source_url=source_url,
                address=address,
                phone=phone,
                email=email,
                website=website,
                fax=fax,
                representative=representative,
                raw_ai_response=raw_response,
                confidence_score=confidence
            )

            extracted_fields_list = []
            if address: extracted_fields_list.append("address")
            if phone: extracted_fields_list.append("phone")
            if email: extracted_fields_list.append("email")
            if website: extracted_fields_list.append("website")
            if representative: extracted_fields_list.append("rep")

            has_contacts = len(extracted_fields_list) > 0
            self._record_domain_stat(source_url, has_contacts)

            metadata = {"extracted_fields": ",".join(extracted_fields_list) if extracted_fields_list else "none"}
            self.logger.log_step_end(log_id, "SUCCESS", data_saved=True, metadata=metadata)

            return {
                "status": "success",
                "extracted_fields": data,
                "confidence": confidence
            }

        try:
            try:
                return retry_executor.execute(lambda: _do_extract(self.config.AI_EXTRACTOR_MODEL))
            except RetryableError as primary_exc:
                if self.config.AI_EXTRACTOR_MODEL == "models/gemini-3.5-flash":
                    raise  # already on the fallback model, nothing left to fall back to
                self.logger.logger.warning(
                    f"Primary model {self.config.AI_EXTRACTOR_MODEL} exhausted retries for page {scraped_page_id}; "
                    f"attempting fallback to models/gemini-3.5-flash..."
                )
                return retry_executor.execute(lambda: _do_extract("models/gemini-3.5-flash"))
        except CriticalError as e:
            self.logger.logger.error(f"Gemini API Rate Limit/Quota Exceeded (429/Quota)! Stop processing.")
            self.logger.log_step_end(log_id, "FAILED", error_message="Rate Limit/Quota Exceeded", error_category="critical")
            raise
        except RetryableError as e:
            self.logger.log_step_end(log_id, "FAILED", error_message=str(e)[:100], error_category="retryable")
            raise
        except SkippableError as e:
            self.logger.log_step_end(log_id, "FAILED", error_message=str(e)[:100], error_category="skippable")
            raise
        except Exception as e:
            error_msg = str(e)
            self.logger.logger.error(f"Gemini API error: {error_msg}")
            category = e.category if isinstance(e, PipelineError) else "unknown"
            self.logger.log_step_end(log_id, "FAILED", error_message=error_msg[:100], error_category=category)
            raise SkippableError(f"AI extraction error: {error_msg[:100]}")

    def extract_for_company(self, company_id: int, delay_seconds: float = 4.0) -> list[dict]:
        """Extracts data for all valid scraped pages of a single company."""
        # Note: We fetch 'success' scraped pages for this company
        scraped_pages = self.db.fetch_all(
            "SELECT * FROM scraped_pages WHERE company_id = ? AND scrape_status = 'success'",
            (company_id,)
        )

        if not scraped_pages:
            self.logger.logger.info(f"No successful scraped pages found for company {company_id}.")
            self.db.update_company(company_id, status='done') # No text to extract means it's fully processed
            return []

        company_record = self.db.get_company(company_id)
        company_name = company_record['original_name'] if company_record else "Unknown Company"

        priority_order = [
            "masothue", "thuvienphapluat", "yellowpages", "hosocongty",
            "official_website", "vietnamworks", "topcv", "vietcareer",
            "facebook", "linkedin"
        ]

        def get_priority(source_type):
            try:
                return priority_order.index(source_type)
            except ValueError:
                return 999

        scraped_pages.sort(key=lambda p: get_priority(p['source_type']))

        results = []
        for page in scraped_pages:
            result = self.extract_from_page(page['id'])
            results.append(result)
            if not result.get("cached", False) and delay_seconds > 0:
                time.sleep(delay_seconds)

        return results

    def _record_domain_stat(self, source_url: str, has_contacts: bool):
        """Record domain statistics for auto-blacklisting."""
        if not source_url:
            return
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        existing = self.db.fetch_one(
            "SELECT scrape_count, success_count FROM domain_stats WHERE domain = ?",
            (domain,)
        )
        if existing:
            self.db.execute_query(
                "UPDATE domain_stats SET scrape_count = scrape_count + 1, success_count = success_count + ? WHERE domain = ?",
                (1 if has_contacts else 0, domain)
            )
        else:
            self.db.execute_query(
                "INSERT INTO domain_stats (domain, scrape_count, success_count) VALUES (?, 1, ?)",
                (domain, 1 if has_contacts else 0)
            )