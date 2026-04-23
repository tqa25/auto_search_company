import time
import requests
from src.database import DatabaseManager
from src.logger import PipelineLogger

class ScrapeModule:
    def __init__(self, db: DatabaseManager, logger: PipelineLogger, firecrawl_api_key: str,
                 rate_limiter=None, connection_manager=None):
        """Initialize the ScrapeModule.
        
        Args:
            db: DatabaseManager instance.
            logger: PipelineLogger instance.
            firecrawl_api_key: Firecrawl API key.
            rate_limiter: Optional AdaptiveRateLimiter instance. When provided,
                          replaces fixed delay with adaptive pacing.
            connection_manager: Optional ConnectionManager instance. When provided,
                                uses session-based connection pooling instead of raw requests.
        """
        self.db = db
        self.logger = logger
        self.api_key = firecrawl_api_key
        self.api_url = "https://api.firecrawl.dev/v1/scrape"
        self.rate_limiter = rate_limiter
        self.connection_manager = connection_manager
        
        self.PRIORITY_ORDER = {
            "masothue": 1,
            "yellowpages": 2,
            "thuvienphapluat": 3,
            "hosocongty": 4,
            "vietnamworks": 5,
            "topcv": 6,
            "vietcareer": 7,
            "official_website": 8,
            "other": 9,
            "facebook": 10,
            "linkedin": 11
        }

    def _get_sort_key(self, link):
        return self.PRIORITY_ORDER.get(link['source_type'], 99)

    def scrape_url(self, filtered_link_id: int) -> dict:
        """Call Firecrawl Scrape API, save content to DB, handle 429/402 and timeout."""
        link = self.db.fetch_one("SELECT * FROM filtered_links WHERE id = ?", (filtered_link_id,))
        if not link:
            return {"status": "failed", "content_length": 0, "source_type": "unknown", "error": "Link not found"}

        url = link['url']
        source_type = link['source_type']
        company_id = link['company_id']

        # KIỂM TRA TRƯỚC: URL này đã scrape chưa?
        existing = self.db.fetch_one(
            "SELECT * FROM scraped_pages WHERE filtered_link_id = ? AND scrape_status = 'success'", 
            (filtered_link_id,)
        )
        if not existing:
            # Maybe it was scraped under a different filtered_link_id but same url
            existing = self.db.fetch_one(
                "SELECT * FROM scraped_pages WHERE url = ? AND scrape_status = 'success'", 
                (url,)
            )

        if existing:
            return {
                "status": "success",
                "content_length": existing['content_length'],
                "source_type": source_type,
                "cached": True
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "url": url,
            "formats": ["markdown"],
            "timeout": 30000,
            "waitFor": 3000
        }

        log_id = self.logger.log_step_start(company_id, "scrape", source_url=url, source_name=source_type)
        
        # Wait for rate limiter before making request
        if self.rate_limiter:
            self.rate_limiter.wait()
        
        retries = 0
        max_retries = 3
        while retries <= max_retries:
            try:
                # Use ConnectionManager if available, otherwise raw requests
                if self.connection_manager:
                    response = self.connection_manager.post(
                        self.api_url,
                        json=body,
                        request_type="scrape",
                    )
                else:
                    response = requests.post(self.api_url, headers=headers, json=body, timeout=35)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        md_content = data.get('data', {}).get('markdown', '')
                        content_length = len(md_content) if md_content else 0
                        
                        self.db.insert_scraped_page(
                            filtered_link_id=filtered_link_id,
                            company_id=company_id,
                            url=url,
                            source_type=source_type,
                            markdown_content=md_content,
                            content_length=content_length,
                            scrape_status="success",
                            credits_used=1.0,
                            error_message=None
                        )
                        
                        self.logger.log_step_end(
                            log_id, 
                            status="success", 
                            credits_used=1.0, 
                            data_saved=True, 
                            metadata={"content_length": content_length}
                        )
                        # Report success to rate limiter
                        if self.rate_limiter:
                            self.rate_limiter.report_success()
                        return {"status": "success", "content_length": content_length, "source_type": source_type, "cached": False}
                    else:
                        error_msg = data.get('error', 'Unknown error inside 200 OK')
                        raise ValueError(error_msg)
                
                elif response.status_code == 429:
                    if self.rate_limiter:
                        self.rate_limiter.report_error(429)
                    retries += 1
                    if retries > max_retries:
                        raise Exception("Rate limit exceeded after max retries")
                    print("HTTP 429 Rate limit exceeded. Waiting 60 seconds...")
                    time.sleep(60)
                    continue
                    
                elif response.status_code == 402:
                    error_msg = "HTTP 402: Insufficient credits"
                    print(f"CRITICAL ERROR: {error_msg}")
                    # Log as failed
                    self.db.insert_scraped_page(
                        filtered_link_id=filtered_link_id,
                        company_id=company_id,
                        url=url,
                        source_type=source_type,
                        markdown_content=None,
                        content_length=0,
                        scrape_status="failed",
                        credits_used=0,
                        error_message=error_msg
                    )
                    self.logger.log_step_end(log_id, status="failed", credits_used=0, error_message=error_msg)
                    raise RuntimeError(error_msg)
                    
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    raise Exception(error_msg)
                
            except Exception as e:
                if isinstance(e, RuntimeError):
                    raise
                    
                error_msg = str(e)
                
                is_timeout = isinstance(e, requests.exceptions.Timeout) or "timeout" in error_msg.lower()
                status_val = "failed"
                
                if is_timeout:
                    if source_type in ["facebook", "linkedin"]:
                        error_msg = "skipped - secondary source"
                        status_val = "skipped"
                    else:
                        error_msg = "timeout"
                        status_val = "timeout"
                
                self.db.insert_scraped_page(
                    filtered_link_id=filtered_link_id,
                    company_id=company_id,
                    url=url,
                    source_type=source_type,
                    markdown_content=None,
                    content_length=0,
                    scrape_status=status_val,
                    credits_used=0,
                    error_message=error_msg
                )
                log_status = "skipped" if status_val == "skipped" else "failed"
                self.logger.log_step_end(log_id, status=log_status, credits_used=0, error_message=error_msg)
                
                return {"status": status_val, "content_length": 0, "source_type": source_type, "error": error_msg}

    def scrape_company(self, company_id: int, delay_seconds: float = 2.0) -> list:
        """Scrape all valid links for a company in priority order."""
        self.db.update_company(company_id, status='scraping')
        
        links = self.db.fetch_all("SELECT * FROM filtered_links WHERE company_id = ? AND should_scrape = 1", (company_id,))
        sorted_links = sorted(links, key=self._get_sort_key)
        
        results = []
        for link in sorted_links:
            try:
                res = self.scrape_url(link['id'])
                results.append(res)
                if not res.get("cached", False):
                    # Use rate_limiter delay if available, otherwise fixed delay
                    if self.rate_limiter:
                        # rate limiter wait already called inside scrape_url
                        pass
                    else:
                        time.sleep(delay_seconds)
            except RuntimeError as e:
                # 402 out of credit -> stop everything
                self.logger.logger.error(f"Stopping immediately: {e}")
                raise
            except Exception as e:
                # Unexpected errors that did not get handled inside scrape_url
                self.logger.logger.error(f"Unexpected error when scraping URL ID {link['id']}: {e}")
                continue
                
        self.db.update_company(company_id, status='scraped')
        return results

    def scrape_batch(self, company_ids: list, delay_seconds: float = 2.0):
        """Sequential processing of companies."""
        total_credits = 0.0
        for i, cid in enumerate(company_ids):
            print(f"Đang xử lý: {i+1}/{len(company_ids)} công ty (ID: {cid})...")
            try:
                res_list = self.scrape_company(cid, delay_seconds)
                for res in res_list:
                    if res.get("status") == "success" and not res.get("cached"):
                        total_credits += 1.0
            except RuntimeError as e:
                print(f"Scrape batch aborted: {e}")
                break
            except Exception as e:
                print(f"Lỗi công ty ID {cid}: {e}")
                continue
        print(f"Hoàn thành scrape_batch. Tổng credits tiêu tốn ước tính: {total_credits}")

    def get_scrape_stats(self) -> dict:
        row_pages = self.db.fetch_one("SELECT COUNT(id) as cnt FROM scraped_pages")
        total_pages = row_pages['cnt'] if row_pages else 0
        
        row_chars = self.db.fetch_one("SELECT SUM(content_length) as total FROM scraped_pages")
        total_chars = row_chars['total'] if row_chars and row_chars['total'] else 0
        
        avg_length = total_chars / total_pages if total_pages > 0 else 0
        
        row_success = self.db.fetch_one("SELECT COUNT(id) as cnt FROM scraped_pages WHERE scrape_status='success'")
        success_pages = row_success['cnt'] if row_success else 0
        success_rate = (success_pages / total_pages * 100) if total_pages > 0 else 0
        
        row_credits = self.db.fetch_one("SELECT SUM(credits_used) as total FROM scraped_pages")
        credits_used = row_credits['total'] if row_credits and row_credits['total'] else 0.0
        
        sources_breakdown = self.db.fetch_all("SELECT source_type, COUNT(*) as cnt FROM scraped_pages GROUP BY source_type")
        source_dict = {s['source_type']: s['cnt'] for s in sources_breakdown}
        
        return {
            "total_pages_scraped": total_pages,
            "total_chars_collected": total_chars,
            "avg_content_length": avg_length,
            "success_rate": success_rate,
            "credits_used_total": credits_used,
            "source_breakdown": source_dict
        }
