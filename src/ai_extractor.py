import os
import json
import time
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from src.database import DatabaseManager
from src.logger import PipelineLogger

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
        
        # Long content safeguard
        if len(markdown_content) > 30000:
            self.logger.logger.warning(f"Markdown content too long for scraped_page_id {scraped_page_id}, truncating to 30,000 chars.")
            markdown_content = markdown_content[:30000]

        prompt = self.EXTRACTION_PROMPT_TEMPLATE.replace("{markdown_content}", markdown_content)
        
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
                        self.logger.log_step_end(log_id, "FAILED", error_message="json_parse_error")
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
                elif "quota exceeded" in error_msg.lower():
                    self.logger.logger.error("Gemini API Quota Exceeded! Stop processing.")
                    self.logger.log_step_end(log_id, "FAILED", error_message="Quota Exceeded")
                    raise e
                
                self.logger.logger.error(f"Gemini API error: {error_msg}")
                self.logger.log_step_end(log_id, "FAILED", error_message=error_msg[:100])
                return {"status": "failed", "reason": "api_error", "message": error_msg}
                
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
        
        results = []
        for i, page in enumerate(scraped_pages):
            res = self.extract_from_page(page['id'])
            results.append(res)
            
            # Since Gemini free tier is 15 RPM, we need to respect the delay between calls
            if i < len(scraped_pages) - 1 and res.get('status') == 'success':
                time.sleep(delay_seconds)
                
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
