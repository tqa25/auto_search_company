import urllib.parse
import unicodedata
import re
import logging
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.schemas import validate_scored_link

logger = logging.getLogger(__name__)


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
    def _remove_accents(text: str) -> str:
        """Remove diacritical marks from Vietnamese text and map đ/Đ to d/D."""
        if not text:
            return ""
        # Handle đ/Đ specifically as they are not decomposed by NFD
        text = text.replace('đ', 'd').replace('Đ', 'D')
        nfd = unicodedata.normalize('NFD', text)
        return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')

    @staticmethod
    def _normalize_company_name(company_name: str) -> tuple:
        """
        Normalize company name: lowercase, remove accents, remove stop words.
        Return (normalized_full_name, abbreviation).
        """
        if not company_name:
            return "", ""

        # Remove accents and lowercase
        normalized = LinkFilter._remove_accents(company_name).lower()

        # Remove common stop words
        stop_words = ['co.', 'ltd', 'inc.', 'llc', 'corp.', 'corporation',
                     'company', 'limited', 'cooperative', 'joint stock']
        for stop in stop_words:
            normalized = re.sub(r'\b' + re.escape(stop) + r'\b', '', normalized)

        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Extract abbreviation (first letter of each word from original)
        words = company_name.split()
        abbrev = ''.join(word[0].lower() for word in words if word)

        return normalized, abbrev

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """
        Normalize domain: remove TLDs (.com, .vn, .com.vn) and www prefix.
        """
        if not domain:
            return ""

        domain = domain.lower()

        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]

        # Remove TLDs
        for tld in ['.com.vn', '.com.br', '.co.uk', '.com', '.vn', '.io', '.net', '.org']:
            if domain.endswith(tld):
                domain = domain[:-len(tld)]
                break

        return domain

    @staticmethod
    def _check_name_match(normalized_domain: str, normalized_company: str, company_abbrev: str) -> bool:
        """
        Check if company name (or abbreviation) matches domain.
        Returns True if any word from normalized company name or the abbreviation appears in domain.
        """
        if not normalized_domain:
            return False

        # Check abbreviation first (more specific match)
        if company_abbrev and company_abbrev in normalized_domain:
            return True

        # Check individual words from normalized company name
        if normalized_company:
            words = normalized_company.split()
            for word in words:
                if word and word in normalized_domain:
                    return True

        return False

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

    def classify_url(self, url: str, company_name: str, title: str = "") -> dict:
        """
        Classify a single URL and return a dict with:
            source_type, should_scrape, reason, relevance_score, score_breakdown
        """
        try:
            domain = self._extract_domain(url)
            if not domain:
                raise ValueError("Could not parse domain from URL")

            # Initialize breakdown with new keys
            breakdown = {
                "domain": 0.0,
                "keyword": 0.0,
                "name_match": 0.0,
                "total": 0.0,
            }

            # 1. Blacklisted — score 0, never scrape.
            if self._match_domain_list(domain, self.BLACKLISTED_DOMAINS):
                return {
                    "source_type": "blacklisted",
                    "should_scrape": False,
                    "reason": f"Blacklisted domain: {domain}",
                    "relevance_score": 0.0,
                    "score_breakdown": breakdown,
                }

            # 2. Skip (news / aggregator) — score 0, tracked but not scraped.
            matched_skip = self._match_domain_list(domain, self.SKIP_DOMAINS)
            if matched_skip:
                return {
                    "source_type": "other",
                    "should_scrape": False,
                    "reason": f"Matched skip domain: {matched_skip}",
                    "relevance_score": 0.0,
                    "score_breakdown": breakdown,
                }

            # 3. Known classified domain.
            matched_known = None
            for known_domain, (src_type, score_category) in self.KNOWN_DOMAINS.items():
                if domain == known_domain or domain.endswith("." + known_domain):
                    matched_known = (known_domain, src_type, score_category)
                    break

            # Scoring variables
            domain_score = 0.0
            keyword_bonus_total = 0.0
            name_match_bonus = 0.0
            src_type = "official_website"
            reason = ""

            if matched_known:
                known_domain, src_type, score_category = matched_known
                domain_score = float(self.config.DOMAIN_SCORES.get(score_category, 0))
                reason = f"Matched known domain: {known_domain} ({score_category})"
            else:
                domain_score = float(self.config.DOMAIN_SCORES.get("official", 40))
                reason = f"Possible official website: {domain}"

            # Keyword bonuses
            keyword_bonuses = self._compute_keyword_bonuses(url)
            keyword_bonus_total = sum(keyword_bonuses.values())

            # Normalization (needed for title and domain match)
            normalized_company, company_abbrev = self._normalize_company_name(company_name)

            # 1. Title matching
            if title:
                normalized_title = self._remove_accents(title).lower()
                if (normalized_company and normalized_company in normalized_title) or \
                   (company_abbrev and company_abbrev in normalized_title):
                    name_match_bonus = float(self.config.DOMAIN_SCORES.get("name_match", 15))

            # 2. Name match in domain (if not already matched via title)
            if name_match_bonus == 0:
                normalized_domain = self._normalize_domain(domain)
                if self._check_name_match(normalized_domain, normalized_company, company_abbrev):
                    name_match_bonus = float(self.config.DOMAIN_SCORES.get("name_match", 15))

            total = domain_score + keyword_bonus_total + name_match_bonus

            return {
                "source_type": src_type,
                "should_scrape": True,
                "reason": reason,
                "relevance_score": total,
                "score_breakdown": {
                    "domain": domain_score,
                    "keyword": keyword_bonus_total,
                    "name_match": name_match_bonus,
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
                    "domain": 0.0,
                    "keyword": 0.0,
                    "name_match": 0.0,
                    "total": 0.0,
                },
            }

    def score_urls_batch(self, urls: list[dict], company_name: str) -> list[dict]:
        """
        Inline score a batch of URLs without saving to DB.
        Validates each scored link before returning.
        """
        scored_urls = []
        for item in urls:
            url = item.get("url", "")
            title = item.get("title", "")
            if not url:
                continue

            classification = self.classify_url(url, company_name, title=title)
            scored_item = {
                "url": url,
                "source_type": classification["source_type"],
                "relevance_score": classification["relevance_score"],
                "should_scrape": classification["should_scrape"],
                "breakdown": classification["score_breakdown"],
            }

            # Validate scored link
            try:
                validate_scored_link(scored_item)
                scored_urls.append(scored_item)
            except ValueError as e:
                logger.warning(f"Skipping invalid scored link: {e}")
                continue

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
                title = result.get("title", "")
                classification = self.classify_url(url, company_name, title=title)

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

                # Validate scored link before persisting
                scored_link_dict = {
                    "url": url,
                    "source_type": classification["source_type"],
                    "relevance_score": classification["relevance_score"],
                    "should_scrape": classification["should_scrape"],
                    "breakdown": classification.get("score_breakdown", {}),
                    "reason": classification.get("reason", "")
                }
                try:
                    validate_scored_link(scored_link_dict)
                except ValueError as e:
                    logger.warning(f"Skipping invalid scored link: {e}")
                    continue

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
