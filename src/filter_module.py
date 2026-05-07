import urllib.parse
from src.database import DatabaseManager
from src.logger import PipelineLogger


class LinkFilter:
    # Domains that never contain phone numbers — score 0, never scrape.
    BLACKLISTED_DOMAINS = [
        "masothue.com",
        "infocom.vn",
        "xinvoice.vn",
        "dauthau.info",
        "dauthau.net",
        "thuonghieuviet.info.vn",
    ]

    # News / social-aggregator domains — tracked as score 0, should_scrape=False.
    SKIP_DOMAINS = [
        "google.com", "youtube.com", "wikipedia.org", "baomoi.com",
        "vnexpress.net", "bing.com", "twitter.com", "tiktok.com",
        "pinterest.com", "amazon.com", "shopee.vn", "lazada.vn",
    ]

    # Domain → (source_type, domain_score_category)
    # The numeric score is resolved at runtime from self.config.DOMAIN_SCORES.
    KNOWN_DOMAINS = {
        "thuvienphapluat.vn":  ("thuvienphapluat", "legal"),
        "hosocongty.vn":       ("hosocongty",       "legal"),
        "vietnamworks.com":    ("vietnamworks",     "job"),
        "topcv.vn":            ("topcv",            "job"),
        "vietcareer.vn":       ("vietcareer",       "job"),
        "facebook.com":        ("facebook",         "social"),
        "linkedin.com":        ("linkedin",         "social"),
        "yellowpages.vn":      ("yellowpages",      "official"),
    }

    # URL-path keywords → score category
    # Each entry is (list_of_keywords, category_key_in_KEYWORD_SCORES).
    KEYWORD_PATTERNS = [
        (["lien-he", "lienhe", "contact", "contacts"],                              "contact"),
        (["hanh-chinh", "hanchinh", "admin", "administration"],                     "admin"),
        (["tuyen-dung", "tuyendung", "career", "careers", "recruitment", "jobs"],   "recruitment"),
    ]

    def __init__(self, db: DatabaseManager, logger: PipelineLogger, config=None):
        from src.config import default_config
        self.config = config or default_config
        self.db = db
        self.logger = logger

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Return bare domain (no www. prefix) from a URL string."""
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return ""

    def _match_domain_list(self, domain: str, domain_list: list) -> str | None:
        """Return the first entry in domain_list that the domain equals or is a subdomain of."""
        for entry in domain_list:
            if domain == entry or domain.endswith("." + entry):
                return entry
        return None

    def _compute_keyword_bonuses(self, url: str) -> dict:
        """Return {category: bonus_score} for each keyword category matched in the URL path."""
        try:
            path = urllib.parse.urlparse(url).path.lower()
        except Exception:
            return {}

        bonuses = {}
        for keywords, category in self.KEYWORD_PATTERNS:
            bonus_value = self.config.KEYWORD_SCORES.get(category, 0)
            if bonus_value and any(kw in path for kw in keywords):
                bonuses[category] = bonus_value
        return bonuses

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_url(self, url: str, company_name: str) -> dict:
        """
        Classify a single URL and return a dict with:
            source_type, should_scrape, reason, relevance_score, score_breakdown
        """
        try:
            domain = self._extract_domain(url)
            if not domain:
                raise ValueError("Could not parse domain from URL")

            # 1. Blacklisted — score 0, never scrape.
            if self._match_domain_list(domain, self.BLACKLISTED_DOMAINS):
                return {
                    "source_type": "blacklisted",
                    "should_scrape": False,
                    "reason": f"Blacklisted domain: {domain}",
                    "relevance_score": 0.0,
                    "score_breakdown": {
                        "domain_score": 0.0,
                        "keyword_bonuses": {},
                        "total": 0.0,
                    },
                }

            # 2. Skip (news / aggregator) — score 0, tracked but not scraped.
            matched_skip = self._match_domain_list(domain, self.SKIP_DOMAINS)
            if matched_skip:
                return {
                    "source_type": "other",
                    "should_scrape": False,
                    "reason": f"Matched skip domain: {matched_skip}",
                    "relevance_score": 0.0,
                    "score_breakdown": {
                        "domain_score": 0.0,
                        "keyword_bonuses": {},
                        "total": 0.0,
                    },
                }

            # 3. Known classified domain.
            matched_known = None
            for known_domain, (src_type, score_category) in self.KNOWN_DOMAINS.items():
                if domain == known_domain or domain.endswith("." + known_domain):
                    matched_known = (known_domain, src_type, score_category)
                    break

            if matched_known:
                known_domain, src_type, score_category = matched_known
                domain_score = float(self.config.DOMAIN_SCORES.get(score_category, 0))
                keyword_bonuses = self._compute_keyword_bonuses(url)
                total = domain_score + sum(keyword_bonuses.values())
                return {
                    "source_type": src_type,
                    "should_scrape": True,
                    "reason": f"Matched known domain: {known_domain} ({score_category})",
                    "relevance_score": total,
                    "score_breakdown": {
                        "domain_score": domain_score,
                        "keyword_bonuses": keyword_bonuses,
                        "total": total,
                    },
                }

            # 4. Possible official website.
            domain_score = float(self.config.DOMAIN_SCORES.get("official", 40))
            keyword_bonuses = self._compute_keyword_bonuses(url)
            total = domain_score + sum(keyword_bonuses.values())
            return {
                "source_type": "official_website",
                "should_scrape": True,
                "reason": f"Possible official website: {domain}",
                "relevance_score": total,
                "score_breakdown": {
                    "domain_score": domain_score,
                    "keyword_bonuses": keyword_bonuses,
                    "total": total,
                },
            }

        except Exception as e:
            return {
                "source_type": "error",
                "should_scrape": False,
                "reason": f"Error parsing URL: {str(e)}",
                "relevance_score": 0.0,
                "score_breakdown": {
                    "domain_score": 0.0,
                    "keyword_bonuses": {},
                    "total": 0.0,
                },
            }

    def score_urls_batch(self, urls: list[dict], company_name: str) -> list[dict]:
        """
        Inline score a batch of URLs without saving to DB.
        """
        scored_urls = []
        for item in urls:
            url = item.get("url", "")
            if not url:
                continue
            
            classification = self.classify_url(url, company_name)
            scored_item = {
                "url": url,
                "source_type": classification["source_type"],
                "relevance_score": classification["relevance_score"],
                "should_scrape": classification["should_scrape"],
                "breakdown": classification["score_breakdown"],
            }
            scored_urls.append(scored_item)
            
        return scored_urls

    def filter_company_links(self, company_id: int) -> list[dict]:
        """
        Classify and persist filtered links for a company.

        Returns a list of dicts, each containing the classification result
        plus `search_result_id`, `url`, and `early_stop` fields.
        """
        company = self.db.get_company(company_id)
        if not company:
            return []

        company_name = company["original_name"]
        log_id = self.logger.log_step_start(
            company_id=company_id, step="filter", source_name="db"
        )

        try:
            search_results = self.db.get_search_results_for_company(company_id)
            seen_domains: set = set()
            filtered_results: list[dict] = []
            scores: list[float] = []
            saved_count = 0
            early_stop = False

            for result in search_results:
                url = result["url"]
                classification = self.classify_url(url, company_name)

                self.logger.log_event("score_calculated", company_id, {
                    "url": url,
                    "source_type": classification["source_type"],
                    "relevance_score": classification["relevance_score"],
                    "should_scrape": classification["should_scrape"],
                    "breakdown": classification.get("score_breakdown", {}),
                    "reason": classification.get("reason", "")
                })

                # Dedup by domain.
                try:
                    domain = self._extract_domain(url) or "unknown"
                except Exception:
                    domain = "unknown"

                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                # Persist the link.
                link_id = self.db.insert_filtered_link(
                    search_result_id=result["id"],
                    company_id=company_id,
                    url=url,
                    source_type=classification["source_type"],
                    should_scrape=classification["should_scrape"],
                    reason=classification["reason"],
                )

                # Update the score column.
                score = classification["relevance_score"]
                self.db.update_filtered_link_score(link_id, score)

                filtered_results.append({
                    "search_result_id": result["id"],
                    "url": url,
                    "early_stop": False,   # will be updated below if triggered
                    **classification,
                })
                scores.append(score)

                if classification["should_scrape"]:
                    saved_count += 1

            # Early-stop check: if enough links already exceed the threshold,
            # we can stop scraping the rest.
            high_score_count = sum(
                1 for s in scores if s >= self.config.EARLY_STOP_SCORE
            )
            if high_score_count >= self.config.EARLY_STOP_COUNT:
                early_stop = True
                self.logger.log_event(
                    "early_stop_triggered",
                    company_id,
                    {
                        "high_score_count": high_score_count,
                        "early_stop_count_threshold": self.config.EARLY_STOP_COUNT,
                        "early_stop_score_threshold": self.config.EARLY_STOP_SCORE,
                        "total_links_evaluated": len(scores),
                    },
                )

            # Propagate early_stop flag to all result dicts.
            for entry in filtered_results:
                entry["early_stop"] = early_stop

            self.logger.log_step_end(
                log_id=log_id,
                status="success",
                data_saved=bool(filtered_results),
                metadata={
                    "total_filtered": saved_count,
                    "total_search_results": len(search_results),
                    "early_stop": early_stop,
                    "top_score": max(scores) if scores else 0,
                    "avg_score": sum(scores) / len(scores) if scores else 0,
                },
            )
            return filtered_results

        except Exception as e:
            self.logger.log_step_end(
                log_id=log_id,
                status="failed",
                error_message=str(e),
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
