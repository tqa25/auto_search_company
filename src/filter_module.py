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
        "infocom.vn",
        "xinvoice.vn",
        "dauthau.info",
        "dauthau.net",
        "thuonghieuviet.info.vn",
        "fiingate.vn",
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
        "jobsgo.vn":           ("jobsgo",           "job"),
        "facebook.com":        ("facebook",         "social"),
        "linkedin.com":        ("linkedin",         "social"),
        "yellowpages.vn":      ("yellowpages",      "official"),
        "masothue.com":        ("masothue",         "legal"),
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
        import json
        import os
        
        self.config = config or default_config
        self.db = db
        self.logger = logger
        
        self._blacklisted_domains = getattr(self.config, 'BLACKLISTED_DOMAINS', self.BLACKLISTED_DOMAINS)
        self._skip_domains = getattr(self.config, 'SKIP_DOMAINS', self.SKIP_DOMAINS)
        self._min_scrape_score = getattr(self.config, 'MIN_SCRAPE_SCORE', 35)
        
        # Load auto-blacklisted domains from DB
        try:
            auto_blacklisted = self.db.get_auto_blacklisted_domains()
            self._blacklisted_domains.extend(auto_blacklisted)
            self.logger.logger.info(f"Loaded {len(auto_blacklisted)} auto-blacklisted domains.")
        except Exception as e:
            self.logger.logger.error(f"Error loading auto-blacklist: {e}")

        # LinkedIn: toggle (default OFF = add to skip)
        if not self.config.SCRAPE_LINKEDIN_ENABLED:
            if "linkedin.com" not in self._skip_domains:
                self._skip_domains.append("linkedin.com")

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
                     'company', 'limited', 'cooperative', 'joint stock',
                     'viet nam', 'vietnam', 'cong ty', 'tnhh', 'cp', 'tap doan', 'co phan']
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
    def _get_best_partial_ratio(query: str, text: str) -> float:
        import difflib
        if not query or not text: return 0.0
        if query in text: return 1.0
        max_r = 0.0
        for i in range(len(text) - len(query) + 1):
            window = text[i:i+len(query)]
            r = difflib.SequenceMatcher(None, query, window).ratio()
            if r > max_r:
                max_r = r
        if len(text) < len(query):
            max_r = max(max_r, difflib.SequenceMatcher(None, query, text).ratio())
        return max_r

    def _calculate_name_match_score(self, url: str, title: str, company_name: str, vn_name: str) -> float:
        """
        Calculate % match between company names (EN/VN) and URL domain/path or title.
        Returns bonus points: 0 if < 80%, up to 20 if 100%.
        """
        names = [n for n in [company_name, vn_name] if n]
        normalized_names = [self._normalize_company_name(n)[0] for n in names]
        
        domain = self._normalize_domain(self._extract_domain(url))
        import urllib.parse
        path = urllib.parse.urlparse(url).path.lower().replace('-', ' ').replace('/', ' ')
        title_norm = self._remove_accents(title).lower() if title else ""
        
        match_texts = [t for t in [domain, path, title_norm] if t]
        
        max_ratio = 0.0
        for name in normalized_names:
            if not name: continue
            for text in match_texts:
                ratio = self._get_best_partial_ratio(name, text)
                if ratio > max_ratio:
                    max_ratio = ratio
                    
        # Calculate initial score (Scale 80%~100% to 0~20 points)
        final_score = 0.0
        if max_ratio >= 0.8:
            final_score = (max_ratio - 0.8) * (20.0 / 0.2)
            
        # OVERMATCH PENALTY
        # If the domain contains the core name but is significantly longer, it's likely a different company.
        penalty = 0.0
        domain_clean = domain.replace("-", "").replace(".", "")
        
        for name in normalized_names:
            if not name: continue
            core_clean = name.replace(" ", "")
            if len(core_clean) < 4: continue # Skip penalty for very short acronyms/names
            
            if core_clean in domain_clean and len(domain_clean) > len(core_clean) + 3:
                excess_ratio = (len(domain_clean) - len(core_clean)) / len(core_clean)
                current_penalty = min(15.0, excess_ratio * 25.0)
                if current_penalty > penalty:
                    penalty = current_penalty
                    
        return final_score - penalty

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

    def classify_url(self, url: str, company_name: str, title: str = "", vn_name: str = "", tax_code: str = "") -> dict:
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
            if self._match_domain_list(domain, self._blacklisted_domains):
                return {
                    "source_type": "blacklisted",
                    "should_scrape": False,
                    "reason": f"Blacklisted domain: {domain}",
                    "relevance_score": 0.0,
                    "score_breakdown": breakdown,
                }

            # 2. Skip (news / aggregator) — score 0, tracked but not scraped.
            matched_skip = self._match_domain_list(domain, self._skip_domains)
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
                
                # If social, set score to -100 and don't scrape
                if score_category == "social":
                    return {
                        "source_type": src_type,
                        "should_scrape": False,
                        "reason": f"Social media ignored: {known_domain}",
                        "relevance_score": -100.0,
                        "score_breakdown": breakdown,
                    }
                    
                reason = f"Matched known domain: {known_domain} ({score_category})"
            else:
                domain_score = float(self.config.DOMAIN_SCORES.get("unknown_web", 15))
                src_type = "unknown_web"
                reason = f"Unknown domain: {domain}"

            # TLD Bonus
            for tld, bonus in getattr(self.config, "TLD_SCORES", {}).items():
                if domain.endswith(tld):
                    domain_score += float(bonus)
                    reason += f" (TLD bonus {tld}: +{bonus})"
                    break

            # Keyword bonuses
            keyword_bonuses = self._compute_keyword_bonuses(url)
            keyword_bonus_total = sum(keyword_bonuses.values())

            # Name match bonus (fuzzy match 80-100% -> 0-20 points) with possible overmatch penalty
            name_match_bonus = self._calculate_name_match_score(url, title, company_name, vn_name)
            if name_match_bonus > 0:
                reason += f" (Name match bonus: +{name_match_bonus:.1f})"
            elif name_match_bonus < 0:
                reason += f" (Overmatch penalty: {name_match_bonus:.1f})"

            # Identity Match for upgrading unknown_web to official_website
            if src_type == "unknown_web":
                is_identity_match = False
                if name_match_bonus >= 15.0:  # Strong name match
                    is_identity_match = True
                    reason += " [Upgraded to official: strong name match]"
                elif tax_code and tax_code in url:
                    is_identity_match = True
                    reason += " [Upgraded to official: tax code in URL]"
                elif tax_code and tax_code in title:
                    is_identity_match = True
                    reason += " [Upgraded to official: tax code in title]"
                elif "contact" in keyword_bonuses or "admin" in keyword_bonuses:
                    is_identity_match = True
                    reason += " [Upgraded to official: contact/admin path]"
                    
                if is_identity_match:
                    src_type = "official_website"
                    domain_score = float(self.config.DOMAIN_SCORES.get("official", 40))

            total = domain_score + keyword_bonus_total + name_match_bonus
            
            should_scrape = True
            
            # Enforce MIN_SCRAPE_SCORE for unknown_web
            if src_type == "unknown_web" and total < self._min_scrape_score:
                should_scrape = False
                reason += f" [Skipped: score {total} < {self._min_scrape_score}]"

            return {
                "source_type": src_type,
                "should_scrape": should_scrape,
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

    def score_urls_batch(self, urls: list[dict], company_name: str, vn_name: str = "") -> list[dict]:
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

            # Note: We need vn_name for new fuzzy logic. We pass it down from arguments.
            classification = self.classify_url(url, company_name, title=title, vn_name=vn_name)
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

    def filter_urls_incremental(
        self,
        company_id: int,
        urls: list[dict],
        seen_domains: set,
        company_name: str,
        vn_name: str = "",
        tax_code: str = ""
    ) -> tuple[list[dict], int]:
        """
        Classify and persist a batch of new search result URLs for a company.
        Smart Dedup: if multiple URLs share a domain in this batch, keep the one with max relevance_score.
        Updates seen_domains set in-place.
        Returns: (filtered_results, good_count_above_threshold)
        """
        filtered_results = []
        good_count = 0
        
        # 1. First, classify all URLs and group by domain
        domain_best_url = {}
        for r in urls:
            url = r["url"]
            title = r.get("title", "")
            
            try:
                domain = self._extract_domain(url) or "unknown"
            except Exception:
                domain = "unknown"
                
            # If domain was seen in a *previous* batch, skip completely
            if domain in seen_domains and domain != "unknown":
                continue

            classification = self.classify_url(url, company_name, title=title, vn_name=vn_name, tax_code=tax_code)
            r['_classification'] = classification
            r['_domain'] = domain
            
            # Keep the highest scoring URL for each domain in this batch
            if domain not in domain_best_url:
                domain_best_url[domain] = r
            else:
                if classification['relevance_score'] > domain_best_url[domain]['_classification']['relevance_score']:
                    domain_best_url[domain] = r
                    
        # 2. Persist the best URLs
        best_urls = list(domain_best_url.values())
        best_urls.sort(key=lambda x: x['_classification']['relevance_score'], reverse=True)

        for r in best_urls:
            search_result_id = r.get("search_result_id")
            url = r["url"]
            classification = r['_classification']
            domain = r['_domain']

            self.logger.log_event("score_calculated", company_id, {
                "url": url,
                "source_type": classification["source_type"],
                "relevance_score": classification["relevance_score"],
                "should_scrape": classification["should_scrape"],
                "breakdown": classification.get("score_breakdown", {}),
                "reason": classification.get("reason", "")
            })

            # Mark domain as seen for future batches
            if domain != "unknown":
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
                self.logger.logger.warning(f"Skipping invalid scored link: {e}")
                continue

            # Persist the link.
            link_id = self.db.insert_filtered_link(
                search_result_id=search_result_id,
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
                "search_result_id": search_result_id,
                "url": url,
                "early_stop": False,
                **classification,
            })

            if classification["should_scrape"] and score >= self.config.EARLY_STOP_SCORE:
                good_count += 1

        return filtered_results, good_count

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
                vn_name = company.get("vietnamese_name", "")
                classification = self.classify_url(url, company_name, title=title, vn_name=vn_name)

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
