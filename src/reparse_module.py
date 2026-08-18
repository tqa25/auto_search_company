import time
import logging
from src.database import DatabaseManager
from src.scrape_module import ScrapeModule
from src.ai_extractor import AIExtractor
from src.logger import PipelineLogger
from src.config import Config

logger = logging.getLogger(__name__)

class ReparseModule:
    """
    Module for re-parsing leftover/filtered data.
    It identifies URLs that were previously filtered out (should_scrape=0) or not scraped successfully,
    unlocks them, scrapes them, and extracts new contact information excluding already found ones.
    """
    def __init__(self, db: DatabaseManager, pipeline_logger: PipelineLogger, config: Config = None):
        self.db = db
        self.logger = pipeline_logger
        self.config = config or Config()
        
    def get_unscrapped_urls(self, company_id: int):
        """
        Returns a list of URLs from filtered_links that haven't been successfully scraped yet,
        sorted by relevance_score DESC.
        """
        query = """
            SELECT fl.id, fl.url, fl.source_type, fl.relevance_score, fl.should_scrape, fl.reason
            FROM filtered_links fl
            LEFT JOIN scraped_pages sp ON fl.id = sp.filtered_link_id AND sp.scrape_status = 'success'
            WHERE fl.company_id = ? AND sp.id IS NULL
            ORDER BY fl.relevance_score DESC
        """
        return self.db.fetch_all(query, (company_id,))

    def get_existing_phones(self, company_id: int) -> set:
        """Returns a set of all phone numbers already extracted for this company."""
        contacts = self.db.fetch_all(
            "SELECT phone FROM extracted_contacts WHERE company_id = ? AND phone IS NOT NULL AND phone != ''", 
            (company_id,)
        )
        phones = set()
        for contact in contacts:
            # Phone could be comma separated
            parts = [p.strip() for p in contact['phone'].split(',')]
            phones.update(parts)
        # Also check gemini_quick_results
        gemini_result = self.db.fetch_one(
            "SELECT phone FROM gemini_quick_results WHERE company_id = ? ORDER BY id DESC LIMIT 1",
            (company_id,)
        )
        if gemini_result and gemini_result['phone']:
            parts = [p.strip() for p in gemini_result['phone'].split(',')]
            phones.update(parts)
            
        return phones

    def unlock_urls(self, company_id: int, link_ids: list[int]):
        """Updates should_scrape=1 for the given filtered_link IDs."""
        if not link_ids:
            return 0
            
        placeholders = ",".join("?" * len(link_ids))
        query = f"UPDATE filtered_links SET should_scrape = 1 WHERE company_id = ? AND id IN ({placeholders})"
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, [company_id] + link_ids)
        conn.commit()
        
        return cursor.rowcount

    def scrape_unlocked(self, company_id: int, link_ids: list[int], delay: float = 2.0):
        """Scrapes the specified unlocked links using ScrapeModule."""
        if not link_ids:
            return []
            
        scraper = ScrapeModule(
            db=self.db, 
            logger=self.logger, 
            firecrawl_api_key=self.config.FIRECRAWL_API_KEY,
            config=self.config
        )
        
        results = []
        for link_id in link_ids:
            try:
                res = scraper.scrape_url(link_id)
                results.append(res)
                if not res.get("cached", False):
                    time.sleep(delay)
            except Exception as e:
                logger.error(f"Error scraping unlocked URL ID {link_id}: {e}")
                
        return results

    def get_newly_scraped_pages(self, company_id: int, link_ids: list[int]):
        """Returns scraped_page rows corresponding to the given link_ids."""
        if not link_ids:
            return []
            
        placeholders = ",".join("?" * len(link_ids))
        query = f"""
            SELECT id, url, source_type, markdown_content 
            FROM scraped_pages 
            WHERE company_id = ? AND filtered_link_id IN ({placeholders}) AND scrape_status = 'success'
        """
        return self.db.fetch_all(query, [company_id] + link_ids)

    def filter_new_contacts(self, extraction_result: dict, exclude_phones: set):
        """Filters out already known phones from the extraction result."""
        if extraction_result.get("status") != "success":
            return extraction_result
            
        fields = extraction_result.get("extracted_fields", {})
        if not fields.get("phone"):
            return extraction_result
            
        # Parse and filter phones
        extracted_phones = [p.strip() for p in fields["phone"].split(',') if p.strip()]
        new_phones = [p for p in extracted_phones if p not in exclude_phones]
        
        if new_phones:
            fields["phone"] = ", ".join(new_phones)
        else:
            fields["phone"] = None
            
        extraction_result["extracted_fields"] = fields
        extraction_result["new_phones_found"] = new_phones
        return extraction_result

    def reextract(self, company_id: int, page_ids: list[int], exclude_phones: set, delay: float = 4.0):
        """Runs AIExtractor on the new pages, and filters out excluded phones."""
        if not page_ids:
            return []
            
        extractor = AIExtractor(db=self.db, logger=self.logger, config=self.config)
        
        results = []
        for i, page_id in enumerate(page_ids):
            try:
                res = extractor.extract_from_page(page_id)
                filtered_res = self.filter_new_contacts(res, exclude_phones)
                # Store the page ID in the result for UI mapping
                filtered_res["page_id"] = page_id
                results.append(filtered_res)
                
                if i < len(page_ids) - 1 and res.get('status') == 'success':
                    time.sleep(delay)
            except Exception as e:
                logger.error(f"Error re-extracting from page ID {page_id}: {e}")
                results.append({"status": "failed", "reason": str(e)[:200], "page_id": page_id})

        return results

    def run_reparse(self, company_id: int, min_score: float = 0.3, max_urls: int = 5, delay_scrape: float = 2.0, delay_extract: float = 4.0):
        """
        Runs the full automated re-parse flow:
        1. Find unscrapped URLs above min_score, up to max_urls.
        2. Unlock them.
        3. Scrape them.
        4. Extract contacts from new pages.
        5. Return new phones found (excluding already existing phones).
        """
        log_id = self.logger.log_step_start(company_id, "reparse", source_name="system")
        try:
            existing_phones = self.get_existing_phones(company_id)
            
            unscrapped = self.get_unscrapped_urls(company_id)
            selected = [u for u in unscrapped if u['relevance_score'] >= min_score][:max_urls]
            
            if not selected:
                self.logger.log_step_end(log_id, "skipped", metadata={"reason": "no_qualifying_urls"})
                return {"status": "skipped", "reason": "No unscrapped URLs met the criteria."}
                
            selected_ids = [u['id'] for u in selected]
            
            unlocked_count = self.unlock_urls(company_id, selected_ids)
            scrape_results = self.scrape_unlocked(company_id, selected_ids, delay_scrape)
            
            new_pages = self.get_newly_scraped_pages(company_id, selected_ids)
            page_ids = [p['id'] for p in new_pages]
            
            extract_results = self.reextract(company_id, page_ids, existing_phones, delay_extract)
            
            new_phones = []
            for res in extract_results:
                if res.get("status") == "success" and res.get("new_phones_found"):
                    new_phones.extend(res["new_phones_found"])
                    
            credits_used = sum(1 for r in scrape_results if r.get("status") == "success" and not r.get("cached"))
            
            self.logger.log_step_end(log_id, "success", metadata={
                "unlocked": unlocked_count,
                "pages_scraped": len(page_ids),
                "new_phones_found": len(new_phones)
            })
            
            return {
                "status": "success",
                "unlocked_count": unlocked_count,
                "pages_scraped": len(page_ids),
                "credits_used": credits_used,
                "new_phones_found": list(set(new_phones)),
                "extract_results": extract_results
            }
        except Exception as e:
            self.logger.log_step_end(log_id, "failed", error_message=str(e))
            return {"status": "failed", "error": str(e)}
