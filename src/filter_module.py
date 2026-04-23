import urllib.parse
from src.database import DatabaseManager
from src.logger import PipelineLogger

class LinkFilter:
    TARGET_DOMAINS = {
        "masothue.com": "masothue",
        "yellowpages.vn": "yellowpages", 
        "thuvienphapluat.vn": "thuvienphapluat",
        "hosocongty.vn": "hosocongty",
        "vietnamworks.com": "vietnamworks",
        "topcv.vn": "topcv",
        "vietcareer.vn": "vietcareer",
        "facebook.com": "facebook",
        "linkedin.com": "linkedin"
    }

    SKIP_DOMAINS = [
        "google.com", "youtube.com", "wikipedia.org", "baomoi.com",
        "vnexpress.net", "bing.com", "twitter.com", "tiktok.com",
        "pinterest.com", "amazon.com", "shopee.vn", "lazada.vn"
    ]

    def __init__(self, db: DatabaseManager, logger: PipelineLogger):
        self.db = db
        self.logger = logger

    def classify_url(self, url: str, company_name: str) -> dict:
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            
            if domain.startswith("www."):
                domain = domain[4:]
                
            matched_target_domain = None
            for target_domain in self.TARGET_DOMAINS:
                if domain == target_domain or domain.endswith("." + target_domain):
                    matched_target_domain = target_domain
                    break
                    
            if matched_target_domain:
                source_type = self.TARGET_DOMAINS[matched_target_domain]
                should_scrape = True
                
                if source_type in ["facebook", "linkedin"]:
                    reason = f"Matched target domain: {matched_target_domain} (secondary source)"
                else:
                    reason = f"Matched target domain: {matched_target_domain}"
                    
                return {
                    "source_type": source_type,
                    "should_scrape": should_scrape,
                    "reason": reason
                }

            matched_skip_domain = None
            for skip_domain in self.SKIP_DOMAINS:
                if domain == skip_domain or domain.endswith("." + skip_domain):
                    matched_skip_domain = skip_domain
                    break
                    
            if matched_skip_domain:
                return {
                    "source_type": "other",
                    "should_scrape": False,
                    "reason": f"Matched skip domain: {matched_skip_domain}"
                }
                
            return {
                "source_type": "official_website",
                "should_scrape": True,
                "reason": f"Possible official website: {domain}"
            }
        except Exception as e:
            return {
                "source_type": "error",
                "should_scrape": False,
                "reason": f"Error parsing URL: {str(e)}"
            }

    def filter_company_links(self, company_id: int) -> list[dict]:
        company = self.db.get_company(company_id)
        if not company:
            return []
            
        company_name = company['original_name']
        log_id = self.logger.log_step_start(company_id=company_id, step="filter", source_name="db")
        
        try:
            search_results = self.db.get_search_results_for_company(company_id)
            seen_domains = set()
            filtered_results = []
            saved_count = 0
            
            for result in search_results:
                url = result['url']
                classification = self.classify_url(url, company_name)
                
                try:
                    parsed = urllib.parse.urlparse(url)
                    domain = parsed.netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                except:
                    domain = "unknown"
                    
                if domain in seen_domains:
                    continue
                    
                seen_domains.add(domain)
                
                self.db.insert_filtered_link(
                    search_result_id=result['id'],
                    company_id=company_id,
                    url=url,
                    source_type=classification['source_type'],
                    should_scrape=classification['should_scrape'],
                    reason=classification['reason']
                )
                
                filtered_results.append({
                    "search_result_id": result['id'],
                    "url": url,
                    **classification
                })
                
                if classification['should_scrape']:
                    saved_count += 1
                
            self.logger.log_step_end(
                log_id=log_id,
                status="success",
                data_saved=bool(filtered_results),
                metadata={"total_filtered": saved_count, "total_search_results": len(search_results)}
            )
            return filtered_results
                
        except Exception as e:
            self.logger.log_step_end(
                log_id=log_id,
                status="failed",
                error_message=str(e)
            )
            return []

    def filter_batch(self, company_ids: list[int]):
        total = len(company_ids)
        print(f"Bắt đầu lọc link cho {total} công ty...")
        success = 0
        for idx, cid in enumerate(company_ids, 1):
            results = self.filter_company_links(cid)
            if results:
                success += 1
            print(f"Đang xử lý: {idx}/{total} công ty...")
            
        print(f"Đã hoàn thành lọc link. Thành công: {success}/{total} công ty.")
