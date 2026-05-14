import os
import json
import time
import re
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import RetryableError, CriticalError, SkippableError, PipelineError
from src.config import Config

class AIExtractor:
    def __init__(self, db: DatabaseManager, logger: PipelineLogger, gemini_api_key: str):
        self.db = db
        self.logger = logger
        
        # Initialize Google Gemini client
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not provided.")
            
        genai.configure(api_key=gemini_api_key)
        # Using a valid model name (gemini-3-flash-preview)
        self.model = genai.GenerativeModel('gemini-3-flash-preview') 

    EXTRACTION_PROMPT_TEMPLATE = """
    Bạn đang trích xuất thông tin liên hệ của công ty: {company_name}
    CHỈ trích xuất thông tin của công ty trên, KHÔNG lấy thông tin của các công ty khác được đề cập trên trang.

    Bạn là một chuyên gia trích xuất dữ liệu. Hãy đọc nội dung Markdown dưới đây và
    trích xuất CHÍNH XÁC các thông tin liên hệ của công ty, bao gồm:

    1. address: Địa chỉ đầy đủ (bao gồm quận/huyện, tỉnh/thành phố). Nếu chỉ là kho hàng, hãy bỏ qua hoặc không coi là trụ sở chính (ưu tiên địa chỉ trụ sở).
    2. phone: Số điện thoại (có thể nhiều số, phân cách bằng dấu phẩy). Phân biệt số điện thoại cố định vs di động, ưu tiên số liên hệ chính (không nhầm với số hotline quảng cáo của nền tảng).
    3. email: Địa chỉ email (có thể nhiều, phân cách bằng dấu phẩy)
    4. website: URL website chính thức
    5. fax: Số fax
    6. representative: Tên người đại diện theo pháp luật / Giám đốc / CEO

    Nếu bạn không tìm thấy thông tin cho một trường nào đó, hãy để giá trị của nó là null.
    Ngoài ra, hãy tự đánh giá độ tin cậy của việc trích xuất và cung cấp trường "confidence"
    với giá trị là một số thực từ 0.0 đến 1.0.

    Nội dung bằng tiếng Việt hoặc tiếng Anh. Hãy lưu ý các định dạng đặc thù của
    số điện thoại và địa chỉ tại Việt Nam.

    BẮT BUỘC TRẢ VỀ DƯỚI ĐỊNH DẠNG JSON THUẦN TÚY KHÔNG KÈM KÝ TỰ ĐẶC BIỆT NÀO KHÁC
    (không dùng markdown code block như ```json).

    Định dạng trả về mong muốn:
    {
      "address": "...",
      "phone": "...",
      "email": "...",
      "website": "...",
      "fax": "...",
      "representative": "...",
      "confidence": 0.0
    }

    ---
    NỘI DUNG MARKDOWN TỪ TRANG WEB:

    {markdown_content}
    """

    BATCH_EXTRACTION_PROMPT_TEMPLATE = """
    Bạn đang trích xuất thông tin liên hệ của công ty: {company_name}
    CHỈ trích xuất thông tin của công ty trên, KHÔNG lấy thông tin của các công ty khác được đề cập trên trang.

    Bạn là một chuyên gia trích xuất dữ liệu. Hãy đọc nội dung Markdown dưới đây (có thể từ nhiều trang khác nhau) và
    trích xuất CHÍNH XÁC các thông tin liên hệ của công ty, bao gồm:

    1. address: Địa chỉ đầy đủ (bao gồm quận/huyện, tỉnh/thành phố). Nếu chỉ là kho hàng, hãy bỏ qua hoặc không coi là trụ sở chính (ưu tiên địa chỉ trụ sở).
    2. phone: Số điện thoại (có thể nhiều số, phân cách bằng dấu phẩy). Phân biệt số điện thoại cố định vs di động, ưu tiên số liên hệ chính (không nhầm với số hotline quảng cáo của nền tảng).
    3. email: Địa chỉ email (có thể nhiều, phân cách bằng dấu phẩy)
    4. website: URL website chính thức
    5. fax: Số fax
    6. representative: Tên người đại diện theo pháp luật / Giám đốc / CEO

    Nếu bạn không tìm thấy thông tin cho một trường nào đó, hãy để giá trị của nó là null.
    Ngoài ra, hãy tự đánh giá độ tin cậy của việc trích xuất và cung cấp trường "confidence"
    với giá trị là một số thực từ 0.0 đến 1.0.

    Nội dung bằng tiếng Việt hoặc tiếng Anh. Hãy lưu ý các định dạng đặc thù của
    số điện thoại và địa chỉ tại Việt Nam.

    BẮT BUỘC TRẢ VỀ DƯỚI ĐỊNH DẠNG JSON THUẦN TÚY KHÔNG KÈM KÝ TỰ ĐẶC BIỆT NÀO KHÁC
    (không dùng markdown code block như ```json).

    Định dạng trả về mong muốn:
    {
      "address": "...",
      "phone": "...",
      "email": "...",
      "website": "...",
      "fax": "...",
      "representative": "...",
      "confidence": 0.0
    }

    ---
    NỘI DUNG MARKDOWN TỪ CÁC TRANG WEB:

    {markdown_content}
    """

    def _has_contact_signals(self, markdown: str) -> bool:
        """
        Pre-filter to check if markdown contains contact signals.
        Returns True if >= 1 phone/email pattern OR >= 2 keywords found.
        """
        # Phone patterns
        phone_pattern_simple = r'\d{10,11}'
        phone_pattern_formatted = r'\d{2,4}[\s.\-]\d{3,4}[\s.\-]\d{3,4}'

        # Email pattern
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

        # Contact keywords (Vietnamese and English)
        keywords = ['liên hệ', 'contact', 'điện thoại', 'email', 'địa chỉ', 'phone', 'tel', 'fax']

        # Check for phone patterns
        phone_matches = len(re.findall(phone_pattern_simple, markdown)) + len(re.findall(phone_pattern_formatted, markdown))

        # Check for email pattern
        email_matches = len(re.findall(email_pattern, markdown))

        # Return True if >= 1 phone/email pattern found
        if phone_matches >= 1 or email_matches >= 1:
            return True

        # Check for keywords
        keyword_count = 0
        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', markdown, re.IGNORECASE):
                keyword_count += 1

        # Return True if >= 2 keywords found
        return keyword_count >= 2

    def _batch_short_pages(self, pages: list[dict], max_chars: int = 5000) -> list[list[dict]]:
        """
        Batch multiple short pages into single API calls.
        Returns list of batches where each batch is a list of page dicts.
        """
        short_pages = []
        long_pages = []

        # Separate pages into short and long
        for page in pages:
            markdown_len = len(page.get('markdown_content', '') or '')
            if markdown_len < max_chars:
                short_pages.append(page)
            else:
                long_pages.append(page)

        batches = []

        # Process short pages: group 2-3 into batches
        current_batch = []
        current_chars = 0
        max_batch_chars = 15000

        for page in short_pages:
            markdown_len = len(page.get('markdown_content', '') or '')

            # If adding this page would exceed max, start new batch
            if current_batch and current_chars + markdown_len > max_batch_chars:
                batches.append(current_batch)
                current_batch = [page]
                current_chars = markdown_len
            else:
                current_batch.append(page)
                current_chars += markdown_len

        # Don't forget the last batch
        if current_batch:
            batches.append(current_batch)

        # Add long pages as individual batches
        for page in long_pages:
            batches.append([page])

        return batches

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
        if len(markdown_content) > 30000:
            self.logger.logger.warning(f"Markdown content too long for scraped_page_id {scraped_page_id}, truncating to 30,000 chars.")
            markdown_content = markdown_content[:30000]

        prompt = self.EXTRACTION_PROMPT_TEMPLATE.replace(
            "{company_name}", company_name
        ).replace(
            "{markdown_content}", markdown_content
        )

        log_id = self.logger.log_step_start(company_id, "AI_EXT", source_url=source_url, source_name=source_type)
        
        attempt = 0
        max_retries = 3
        while attempt < max_retries:
            try:
                # Setting generation config to try enforcing JSON format
                self.logger.logger.info(f"Calling Gemini API for page ID {scraped_page_id}...")
                
                # Gemini free tier might strictly parse response_mime_type if correctly set
                generation_config = genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
                
                response = self.model.generate_content(
                    prompt, 
                    generation_config=generation_config
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
                        self.logger.log_step_end(log_id, "FAILED", error_message="json_parse_error", error_category="skippable")
                        return {"status": "failed", "reason": "json_parse_error", "confidence": 0.0}

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
                if confidence < Config().MIN_CONFIDENCE_THRESHOLD:
                    self.logger.logger.warning(f"Low confidence extraction for page {scraped_page_id}: confidence={confidence} < threshold={Config().MIN_CONFIDENCE_THRESHOLD}")
                    low_conf_data = {
                        "page_id": scraped_page_id,
                        "source_type": source_type,
                        "confidence": confidence,
                        "threshold": Config().MIN_CONFIDENCE_THRESHOLD
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
                
                metadata = {"extracted_fields": ",".join(extracted_fields_list) if extracted_fields_list else "none"}
                self.logger.log_step_end(log_id, "SUCCESS", data_saved=True, metadata=metadata)
                
                return {
                    "status": "success", 
                    "extracted_fields": data,
                    "confidence": confidence
                }
                
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    attempt += 1
                    if attempt < max_retries:
                        self.logger.logger.warning(f"Rate limit exceeded (429). Retrying in 60s... (Attempt {attempt}/{max_retries})")
                        time.sleep(60)
                        continue
                    else:
                        self.logger.log_step_end(log_id, "FAILED", error_message="Rate limit exceeded after retries")
                        raise RetryableError(f"Rate limit exceeded (429) after {max_retries} retries")
                elif "quota exceeded" in error_msg.lower():
                    self.logger.logger.error("Gemini API Quota Exceeded! Stop processing.")
                    self.logger.log_step_end(log_id, "FAILED", error_message="Quota Exceeded", error_category="critical")
                    raise CriticalError("Gemini API quota exceeded. Stop pipeline.")

                self.logger.logger.error(f"Gemini API error: {error_msg}")
                category = e.category if isinstance(e, PipelineError) else "unknown"
                self.logger.log_step_end(log_id, "FAILED", error_message=error_msg[:100], error_category=category)
                raise SkippableError(f"AI extraction error: {error_msg[:100]}")
                
        self.logger.log_step_end(log_id, "FAILED", error_message="max_retries reached")
        return {"status": "failed", "reason": "max_retries"}

    def _extract_batch(self, batch_pages: list[dict], company_id: int, company_name: str) -> dict:
        """
        Sub-task C: Extract from multiple pages as a single batch.
        Returns merged contact info from all pages in batch.
        """
        if not batch_pages:
            return {"status": "skipped", "reason": "empty_batch"}

        # Build markdown content with page headers
        markdown_parts = []
        page_urls = []
        for idx, page in enumerate(batch_pages, 1):
            markdown = page.get('markdown_content', '') or ''
            url = page.get('url', 'unknown')
            page_urls.append(url)
            markdown_parts.append(f"Trang {idx} (từ {url}):\n{markdown}")

        batch_markdown = "\n\n---TRANG MỚI---\n\n".join(markdown_parts)

        # Truncate if too long
        if len(batch_markdown) > 30000:
            self.logger.logger.warning(f"Batch markdown too long, truncating to 30,000 chars.")
            batch_markdown = batch_markdown[:30000]

        prompt = self.BATCH_EXTRACTION_PROMPT_TEMPLATE.replace(
            "{company_name}", company_name
        ).replace(
            "{markdown_content}", batch_markdown
        )

        log_id = self.logger.log_step_start(company_id, "AI_EXT_BATCH", source_url=",".join(page_urls), source_name="batch")

        attempt = 0
        max_retries = 3
        while attempt < max_retries:
            try:
                self.logger.logger.info(f"Calling Gemini API for batch of {len(batch_pages)} pages...")

                generation_config = genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )

                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config
                )

                raw_response = response.text

                # Parse JSON
                try:
                    data = json.loads(raw_response)
                except json.JSONDecodeError:
                    clean_text = raw_response.strip()
                    if clean_text.startswith("```json"):
                        clean_text = clean_text[7:]
                    if clean_text.endswith("```"):
                        clean_text = clean_text[:-3]

                    try:
                        data = json.loads(clean_text)
                    except json.JSONDecodeError:
                        self.logger.logger.warning(f"Failed to parse JSON for batch")
                        self.logger.log_step_end(log_id, "FAILED", error_message="json_parse_error", error_category="skippable")
                        return {"status": "failed", "reason": "json_parse_error", "confidence": 0.0}

                # Successfully parsed - store result for each page in batch
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

                first_page = batch_pages[0]
                # Check low confidence threshold
                if confidence < Config().MIN_CONFIDENCE_THRESHOLD:
                    self.logger.logger.warning(f"Low confidence extraction for batch: confidence={confidence} < threshold={Config().MIN_CONFIDENCE_THRESHOLD}")
                    low_conf_data = {
                        "page_ids": [p['id'] for p in batch_pages],
                        "source_type": first_page.get('source_type', 'batch'),
                        "confidence": confidence,
                        "threshold": Config().MIN_CONFIDENCE_THRESHOLD
                    }
                    self.logger.log_event("low_confidence_extraction", company_id, low_conf_data)

                # Normalize null strings
                for var, val in [("address", address), ("phone", phone), ("email", email),
                                 ("website", website), ("fax", fax), ("representative", representative)]:
                    if str(val).lower() == "null" or str(val).lower() == "none" or val == "":
                        if var == "address": address = None
                        elif var == "phone": phone = None
                        elif var == "email": email = None
                        elif var == "website": website = None
                        elif var == "fax": fax = None
                        elif var == "representative": representative = None

                # Store result for EACH page in batch to mark them as processed
                for page in batch_pages:
                    source_type = page.get('source_type', 'batch')
                    source_url = page.get('url', 'batch')

                    self.db.insert_extracted_contact(
                        company_id=company_id,
                        scraped_page_id=page['id'],
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

                metadata = {
                    "extracted_fields": ",".join(extracted_fields_list) if extracted_fields_list else "none",
                    "batch_size": len(batch_pages)
                }
                self.logger.log_step_end(log_id, "SUCCESS", data_saved=True, metadata=metadata)

                return {
                    "status": "success",
                    "extracted_fields": data,
                    "confidence": confidence,
                    "batch_size": len(batch_pages)
                }

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    attempt += 1
                    if attempt < max_retries:
                        self.logger.logger.warning(f"Rate limit exceeded (429). Retrying in 60s... (Attempt {attempt}/{max_retries})")
                        time.sleep(60)
                        continue
                    else:
                        self.logger.log_step_end(log_id, "FAILED", error_message="Rate limit exceeded after retries")
                        raise RetryableError(f"Rate limit exceeded (429) after {max_retries} retries")
                elif "quota exceeded" in error_msg.lower():
                    self.logger.logger.error("Gemini API Quota Exceeded! Stop processing.")
                    self.logger.log_step_end(log_id, "FAILED", error_message="Quota Exceeded", error_category="critical")
                    raise CriticalError("Gemini API quota exceeded. Stop pipeline.")

                self.logger.logger.error(f"Gemini API error: {error_msg}")
                category = e.category if isinstance(e, PipelineError) else "unknown"
                self.logger.log_step_end(log_id, "FAILED", error_message=error_msg[:100], error_category=category)
                raise SkippableError(f"AI extraction error: {error_msg[:100]}")

        self.logger.log_step_end(log_id, "FAILED", error_message="max_retries reached")
        return {"status": "failed", "reason": "max_retries"}

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
            if source_type in priority_order:
                return priority_order.index(source_type)
            return 999

        scraped_pages.sort(key=lambda x: get_priority(x['source_type']))

        # Apply Batching optimization
        batches = self._batch_short_pages(scraped_pages)
        
        results = []
        processed_count = 0
        for batch in batches:
            if len(batch) == 1:
                page = batch[0]
                res = self.extract_from_page(page['id'])
                results.append(res)
                processed_count += 1
                i = processed_count - 1 # for early stop logic compat
            else:
                res = self._extract_batch(batch, company_id, company_name)
                results.append(res)
                processed_count += len(batch)
                i = processed_count - 1 # for early stop logic compat

            # Sub-task B: Early stop extraction
            if res.get('status') == 'success':
                extracted_fields = res.get('extracted_fields', {})
                confidence = res.get('confidence', 0.0)

                # Count non-null fields (phone, email, address)
                fields_found = []
                if extracted_fields.get('phone'):
                    fields_found.append('phone')
                if extracted_fields.get('email'):
                    fields_found.append('email')
                if extracted_fields.get('address'):
                    fields_found.append('address')

                # Early stop if >= 3 fields and confidence >= 0.8
                if len(fields_found) >= 3 and confidence >= 0.8:
                    pages_skipped = len(scraped_pages) - i - 1
                    early_stop_event = {
                        "event": "early_stop_extraction",
                        "company_id": company_id,
                        "fields_found": fields_found,
                        "confidence": confidence,
                        "pages_processed": i + 1,
                        "pages_skipped": pages_skipped
                    }
                    self.logger.log_event("early_stop_extraction", company_id, early_stop_event)
                    self.logger.logger.info(f"Early stop extraction for company {company_id}: {early_stop_event}")
                    break

            # Since Gemini free tier is 15 RPM, we need to respect the delay between calls
            if i < len(scraped_pages) - 1 and res.get('status') == 'success':
                time.sleep(delay_seconds)

        # Conflict resolution: when multiple sources have extracted data for the same field,
        # choose the one with highest confidence
        extracted_contacts = self.db.fetch_all(
            "SELECT * FROM extracted_contacts WHERE company_id = ?",
            (company_id,)
        )

        if extracted_contacts and len(extracted_contacts) > 1:
            # Build a map of field -> list of (source_type, confidence, value)
            field_sources = {
                'address': [],
                'phone': [],
                'email': [],
                'website': [],
                'fax': [],
                'representative': []
            }

            for contact in extracted_contacts:
                if contact['address']:
                    field_sources['address'].append({
                        'source_type': contact['source_type'],
                        'confidence': contact['confidence_score'],
                        'value': contact['address']
                    })
                if contact['phone']:
                    field_sources['phone'].append({
                        'source_type': contact['source_type'],
                        'confidence': contact['confidence_score'],
                        'value': contact['phone']
                    })
                if contact['email']:
                    field_sources['email'].append({
                        'source_type': contact['source_type'],
                        'confidence': contact['confidence_score'],
                        'value': contact['email']
                    })
                if contact['website']:
                    field_sources['website'].append({
                        'source_type': contact['source_type'],
                        'confidence': contact['confidence_score'],
                        'value': contact['website']
                    })
                if contact['fax']:
                    field_sources['fax'].append({
                        'source_type': contact['source_type'],
                        'confidence': contact['confidence_score'],
                        'value': contact['fax']
                    })
                if contact['representative']:
                    field_sources['representative'].append({
                        'source_type': contact['source_type'],
                        'confidence': contact['confidence_score'],
                        'value': contact['representative']
                    })

            # For each field with multiple sources, resolve by choosing highest confidence
            for field, sources in field_sources.items():
                if len(sources) > 1:
                    # Sort by confidence descending
                    sources.sort(key=lambda x: x['confidence'], reverse=True)
                    chosen = sources[0]
                    rejected = sources[1:]

                    # Log conflict resolution for each rejected source
                    for rej in rejected:
                        conflict_data = {
                            "field": field,
                            "chosen_source": chosen['source_type'],
                            "chosen_confidence": chosen['confidence'],
                            "rejected_source": rej['source_type'],
                            "rejected_confidence": rej['confidence']
                        }
                        self.logger.log_event("contact_conflict_resolved", company_id, conflict_data)

        # Finalize company status
        self.db.update_company(company_id, status='done')
        return results

    def extract_batch(self, company_ids: list[int], delay_seconds: float = 4.0):
        """Extracts data for a batch of companies."""
        for cid in company_ids:
            self.logger.logger.info(f"--- Starting AI extraction for company ID {cid} ---")
            try:
                self.extract_for_company(cid, delay_seconds)
            except Exception as e:
                self.logger.logger.error(f"Error processing company {cid}: {e}")
                continue # move on to next if one fails completely

    def get_extraction_stats(self) -> dict:
        """Computes aggregate analytics over extracted_contacts."""
        total_extracted_row = self.db.fetch_one("SELECT COUNT(*) as c FROM extracted_contacts")
        total_extracted = total_extracted_row['c'] if total_extracted_row else 0
        
        total_pages_row = self.db.fetch_one("SELECT COUNT(DISTINCT scraped_page_id) as c FROM extracted_contacts")
        total_pages = total_pages_row['c'] if total_pages_row else 0
        
        avg_conf_row = self.db.fetch_one("SELECT AVG(confidence_score) as avg_conf FROM extracted_contacts")
        avg_conf = avg_conf_row['avg_conf'] if avg_conf_row and avg_conf_row['avg_conf'] else 0.0
        
        # fields coverage
        has_address = self.db.fetch_one("SELECT COUNT(*) as c FROM extracted_contacts WHERE address IS NOT NULL")['c'] or 0
        has_phone = self.db.fetch_one("SELECT COUNT(*) as c FROM extracted_contacts WHERE phone IS NOT NULL")['c'] or 0
        has_email = self.db.fetch_one("SELECT COUNT(*) as c FROM extracted_contacts WHERE email IS NOT NULL")['c'] or 0
        has_website = self.db.fetch_one("SELECT COUNT(*) as c FROM extracted_contacts WHERE website IS NOT NULL")['c'] or 0
        has_rep = self.db.fetch_one("SELECT COUNT(*) as c FROM extracted_contacts WHERE representative IS NOT NULL")['c'] or 0
        
        sources = self.db.fetch_all("SELECT source_type, COUNT(*) as c FROM extracted_contacts GROUP BY source_type")
        source_distribution = {s['source_type']: s['c'] for s in sources}
        
        return {
            "total_extracted": total_extracted,
            "total_pages_processed": total_pages,
            "avg_confidence_score": float(avg_conf),
            "fields_coverage": {
                "address_pct": (has_address / total_extracted * 100) if total_extracted else 0,
                "phone_pct": (has_phone / total_extracted * 100) if total_extracted else 0,
                "email_pct": (has_email / total_extracted * 100) if total_extracted else 0,
                "website_pct": (has_website / total_extracted * 100) if total_extracted else 0,
                "representative_pct": (has_rep / total_extracted * 100) if total_extracted else 0,
            },
            "source_distribution": source_distribution
        }
