import hashlib
import datetime
import time
import requests
from urllib.parse import urlparse, urlencode, parse_qs
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import RetryableError, CriticalError, SkippableError, PipelineError

class ScrapeModule:
    def __init__(self, db: DatabaseManager, logger: PipelineLogger, firecrawl_api_key: str,
                 rate_limiter=None, connection_manager=None, config=None):
        """Initialize the ScrapeModule.

        Args:
            db: DatabaseManager instance.
            logger: PipelineLogger instance.
            firecrawl_api_key: Firecrawl API key.
            rate_limiter: Optional AdaptiveRateLimiter instance. When provided,
                          replaces fixed delay with adaptive pacing.
            connection_manager: Optional ConnectionManager instance. When provided,
                                uses session-based connection pooling instead of raw requests.
            config: Optional Config instance. Defaults to default_config when None.
        """
        from src.config import default_config
        self.config = config or default_config

        self.db = db
        self.logger = logger
        self.api_key = firecrawl_api_key
        self.api_url = "https://api.firecrawl.dev/v1/scrape"
        self.batch_api_url = "https://api.firecrawl.dev/v2/batch/scrape"
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

    def _normalize_url_and_hash(self, url: str) -> str:
        """Return a SHA-256 hex digest of the normalized URL (lowercase, no trailing slash, UTM params stripped)."""
        parsed = urlparse(url.lower().rstrip('/'))
        # Remove utm_* tracking params
        qs = parse_qs(parsed.query)
        filtered_qs = {k: v for k, v in qs.items() if not k.startswith('utm_')}
        clean_query = urlencode(sorted(filtered_qs.items()), doseq=True)
        clean_url = parsed._replace(query=clean_query).geturl()
        return hashlib.sha256(clean_url.encode('utf-8')).hexdigest()

    def _firecrawl_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _store_url_cache_success(self, url: str, markdown_content: str) -> None:
        ttl = datetime.datetime.now() + datetime.timedelta(days=self.config.CACHE_TTL_DAYS)
        self.db.insert_url_cache(
            url_hash=self._normalize_url_and_hash(url),
            url=url,
            scrape_status='success',
            content_hash=hashlib.sha256((markdown_content or '').encode('utf-8')).hexdigest(),
            ttl_expires_at=ttl.strftime("%Y-%m-%d %H:%M:%S")
        )

    def _cached_result_for_link(self, link: dict) -> dict | None:
        url = link['url']
        url_hash = self._normalize_url_and_hash(url)

        if self.config.ENABLE_URL_DEDUP and not self.config.FORCE_REFRESH:
            if self.db.is_url_cached(url_hash):
                self.logger.log_event("dedup_url_cache_hit", link['company_id'], {"url": url, "hash": url_hash})
                existing_page = self.db.fetch_one(
                    "SELECT * FROM scraped_pages WHERE url = ? AND scrape_status = 'success' LIMIT 1",
                    (url,)
                )
                if existing_page:
                    self.db.insert_scraped_page(
                        filtered_link_id=link['id'],
                        company_id=link['company_id'],
                        url=url,
                        source_type=link['source_type'],
                        markdown_content=existing_page['markdown_content'],
                        content_length=existing_page['content_length'],
                        scrape_status='success',
                        credits_used=0,
                        error_message=None
                    )
                    return {
                        "status": "success",
                        "content_length": existing_page['content_length'],
                        "source_type": link['source_type'],
                        "cached": True
                    }

        existing = self.db.fetch_one(
            "SELECT * FROM scraped_pages WHERE filtered_link_id = ? AND scrape_status = 'success'",
            (link['id'],)
        )
        if not existing:
            existing = self.db.fetch_one(
                "SELECT * FROM scraped_pages WHERE url = ? AND scrape_status = 'success'",
                (url,)
            )

        if existing:
            return {
                "status": "success",
                "content_length": existing['content_length'],
                "source_type": link['source_type'],
                "cached": True
            }
        return None

    def _insert_batch_failure(self, link: dict, error_msg: str, status_val: str = "failed") -> dict:
        self.db.insert_scraped_page(
            filtered_link_id=link['id'],
            company_id=link['company_id'],
            url=link['url'],
            source_type=link['source_type'],
            markdown_content=None,
            content_length=0,
            scrape_status=status_val,
            credits_used=0,
            error_message=error_msg
        )
        return {
            "status": status_val,
            "content_length": 0,
            "source_type": link['source_type'],
            "error": error_msg
        }

    def _insert_batch_success(self, link: dict, markdown_content: str, credits_used: float = 1.0) -> dict:
        content_length = len(markdown_content) if markdown_content else 0
        self.db.insert_scraped_page(
            filtered_link_id=link['id'],
            company_id=link['company_id'],
            url=link['url'],
            source_type=link['source_type'],
            markdown_content=markdown_content,
            content_length=content_length,
            scrape_status="success",
            credits_used=credits_used,
            error_message=None
        )
        self._store_url_cache_success(link['url'], markdown_content or '')
        return {
            "status": "success",
            "content_length": content_length,
            "source_type": link['source_type'],
            "cached": False
        }

    def _batch_result_url(self, result: dict) -> str | None:
        metadata = result.get('metadata') if isinstance(result, dict) else None
        if isinstance(metadata, dict):
            for key in ('sourceURL', 'sourceUrl', 'url'):
                if metadata.get(key):
                    return metadata[key]
        if isinstance(result, dict):
            return result.get('url') or result.get('sourceURL') or result.get('sourceUrl')
        return None

    def _batch_result_markdown(self, result: dict) -> str:
        if not isinstance(result, dict):
            return ''
        data = result.get('data')
        if isinstance(data, dict):
            return data.get('markdown') or ''
        return result.get('markdown') or ''

    def _batch_result_error(self, result: dict) -> str:
        if not isinstance(result, dict):
            return 'Unknown Firecrawl batch result error'
        metadata = result.get('metadata') if isinstance(result.get('metadata'), dict) else {}
        error = (
            result.get('error')
            or result.get('errorMessage')
            or result.get('message')
            or metadata.get('error')
            or metadata.get('errorMessage')
        )
        if error:
            return str(error)
        status_code = self._batch_result_status_code(result)
        if status_code:
            return f"HTTP {status_code}"
        return 'Firecrawl batch scrape failed for URL'

    def _batch_result_status_code(self, result: dict) -> int | None:
        if not isinstance(result, dict):
            return None
        metadata = result.get('metadata') if isinstance(result.get('metadata'), dict) else {}
        status_code = (
            result.get('statusCode')
            or result.get('status_code')
            or result.get('httpStatusCode')
            or metadata.get('statusCode')
            or metadata.get('status_code')
            or metadata.get('httpStatusCode')
        )
        try:
            return int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            return None

    def _start_firecrawl_batch(self, links: list[dict]) -> str:
        max_concurrency = max(1, min(
            len(links),
            int(getattr(self.config, 'TOP_N', 10) or 10),
            int(getattr(self.config, 'FIRECRAWL_MAX_CONCURRENCY', 10) or 10)
        ))
        body = {
            "urls": [link['url'] for link in links],
            "formats": ["markdown"],
            "timeout": 30000,
            "waitFor": 3000,
            "maxConcurrency": max_concurrency
        }

        retries = 0
        max_retries = 3
        while retries <= max_retries:
            try:
                response = requests.post(self.batch_api_url, headers=self._firecrawl_headers(), json=body, timeout=35)
            except requests.exceptions.Timeout as exc:
                raise RetryableError("timeout") from exc

            if response.status_code in (200, 201):
                data = response.json()
                job_id = data.get('id') or data.get('jobId') or data.get('batchId')
                if not job_id:
                    raise SkippableError("Firecrawl batch scrape did not return a job id")
                return job_id
            if response.status_code == 429:
                retries += 1
                if retries > max_retries:
                    raise RetryableError("Rate limit exceeded after max retries")
                time.sleep(60)
                continue
            if response.status_code == 402:
                raise CriticalError("HTTP 402: Insufficient credits")
            raise SkippableError(f"HTTP {response.status_code}: {response.text}")

        raise RetryableError("Unable to start Firecrawl batch scrape")

    def _poll_firecrawl_batch(self, job_id: str) -> dict | None:
        deadline = time.monotonic() + float(getattr(self.config, 'FIRECRAWL_BATCH_TIMEOUT_SECONDS', 300.0) or 300.0)
        poll_interval = float(getattr(self.config, 'FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS', 2.0) or 2.0)
        status_url = f"{self.batch_api_url}/{job_id}"

        while time.monotonic() <= deadline:
            response = requests.get(status_url, headers=self._firecrawl_headers(), timeout=35)
            if response.status_code == 402:
                raise CriticalError("HTTP 402: Insufficient credits")
            if response.status_code == 429:
                raise RetryableError("Rate limit exceeded while polling Firecrawl batch scrape")
            if response.status_code >= 400:
                raise SkippableError(f"HTTP {response.status_code}: {response.text}")

            data = response.json()
            status = str(data.get('status') or '').lower()
            if status in ('completed', 'finished', 'done') or data.get('completed') is True:
                return data
            if status in ('failed', 'cancelled', 'canceled'):
                raise SkippableError(data.get('error') or data.get('message') or 'Firecrawl batch scrape failed')
            time.sleep(poll_interval)

        return None

    def _scrape_company_with_firecrawl_batch(self, company_id: int, links: list[dict]) -> list:
        results = []
        batch_links = []
        log_ids = {}

        for link in links:
            cached = self._cached_result_for_link(link)
            if cached:
                results.append(cached)
                continue
            batch_links.append(link)
            log_ids[link['id']] = self.logger.log_step_start(
                company_id,
                "scrape",
                source_url=link['url'],
                source_name=link['source_type']
            )

        if not batch_links:
            return results

        try:
            job_id = self._start_firecrawl_batch(batch_links)
            batch_data = self._poll_firecrawl_batch(job_id)
        except CriticalError as exc:
            error_msg = str(exc)
            for link in batch_links:
                results.append(self._insert_batch_failure(link, error_msg))
                self.logger.log_step_end(log_ids[link['id']], status="failed", credits_used=0, error_message=error_msg, error_category="critical")
            raise
        except RetryableError as exc:
            error_msg = str(exc)
            for link in batch_links:
                status_val = "skipped" if link['source_type'] in ["facebook", "linkedin"] and "timeout" in error_msg.lower() else "timeout" if "timeout" in error_msg.lower() else "failed"
                stored_error = "skipped - secondary source" if status_val == "skipped" else error_msg
                results.append(self._insert_batch_failure(link, stored_error, status_val=status_val))
                self.logger.log_step_end(log_ids[link['id']], status="skipped" if status_val == "skipped" else "failed", credits_used=0, error_message=stored_error, error_category="retryable")
            return results
        except Exception as exc:
            error_msg = str(exc)
            for link in batch_links:
                results.append(self._insert_batch_failure(link, error_msg))
                self.logger.log_step_end(log_ids[link['id']], status="failed", credits_used=0, error_message=error_msg, error_category="skippable")
            return results

        if batch_data is None:
            error_msg = "timeout"
            for link in batch_links:
                status_val = "skipped" if link['source_type'] in ["facebook", "linkedin"] else "timeout"
                stored_error = "skipped - secondary source" if status_val == "skipped" else error_msg
                results.append(self._insert_batch_failure(link, stored_error, status_val=status_val))
                self.logger.log_step_end(log_ids[link['id']], status="skipped" if status_val == "skipped" else "failed", credits_used=0, error_message=stored_error, error_category="retryable")
            return results

        raw_results = batch_data.get('data') or batch_data.get('results') or []
        if isinstance(raw_results, dict):
            raw_results = raw_results.get('data') or raw_results.get('results') or []

        results_by_url = {}
        for result in raw_results:
            result_url = self._batch_result_url(result)
            if result_url:
                results_by_url[result_url] = result

        critical_error = None
        for index, link in enumerate(batch_links):
            result = results_by_url.get(link['url'])
            if result is None and index < len(raw_results):
                result = raw_results[index]

            if result is None:
                error_msg = "Firecrawl batch scrape returned no result for URL"
                results.append(self._insert_batch_failure(link, error_msg))
                self.logger.log_step_end(log_ids[link['id']], status="failed", credits_used=0, error_message=error_msg, error_category="skippable")
                continue

            status_code = self._batch_result_status_code(result)
            if status_code == 402:
                error_msg = "HTTP 402: Insufficient credits"
                results.append(self._insert_batch_failure(link, error_msg))
                self.logger.log_step_end(log_ids[link['id']], status="failed", credits_used=0, error_message=error_msg, error_category="critical")
                critical_error = CriticalError(error_msg)
                continue

            markdown_content = self._batch_result_markdown(result)
            result_success = result.get('success') is not False and (markdown_content or status_code in (200, None))
            if result_success:
                res = self._insert_batch_success(link, markdown_content, credits_used=1.0)
                results.append(res)
                self.logger.log_step_end(log_ids[link['id']], status="success", credits_used=1.0, data_saved=True, metadata={"content_length": res['content_length']})
                continue

            error_msg = self._batch_result_error(result)
            if status_code == 429:
                error_msg = f"HTTP 429: {error_msg}"
            results.append(self._insert_batch_failure(link, error_msg))
            self.logger.log_step_end(log_ids[link['id']], status="failed", credits_used=0, error_message=error_msg, error_category="retryable" if status_code == 429 else "skippable")

        if critical_error:
            raise critical_error
        return results

    def scrape_url(self, filtered_link_id: int) -> dict:
        """Call Firecrawl Scrape API, save content to DB, handle 429/402 and timeout."""
        link = self.db.fetch_one("SELECT * FROM filtered_links WHERE id = ?", (filtered_link_id,))
        if not link:
            return {"status": "failed", "content_length": 0, "source_type": "unknown", "error": "Link not found"}

        url = link['url']
        source_type = link['source_type']
        company_id = link['company_id']

        # --- URL deduplication check (before the per-link DB check) ---
        url_hash = self._normalize_url_and_hash(url)
        if self.config.ENABLE_URL_DEDUP and not self.config.FORCE_REFRESH:
            if self.db.is_url_cached(url_hash):
                self.logger.log_event("dedup_url_cache_hit", company_id, {"url": url, "hash": url_hash})
                existing_page = self.db.fetch_one(
                    "SELECT * FROM scraped_pages WHERE url = ? AND scrape_status = 'success' LIMIT 1",
                    (url,)
                )
                if existing_page:
                    self.db.insert_scraped_page(
                        filtered_link_id=filtered_link_id,
                        company_id=company_id,
                        url=url,
                        source_type=source_type,
                        markdown_content=existing_page['markdown_content'],
                        content_length=existing_page['content_length'],
                        scrape_status='success',
                        credits_used=0,  # 0 credits — reused
                        error_message=None
                    )
                    return {
                        "status": "success",
                        "content_length": existing_page['content_length'],
                        "source_type": source_type,
                        "cached": True
                    }

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

                        # Store in url_cache so future requests for this URL are deduplicated
                        ttl = datetime.datetime.now() + datetime.timedelta(days=self.config.CACHE_TTL_DAYS)
                        self.db.insert_url_cache(
                            url_hash=url_hash,
                            url=url,
                            scrape_status='success',
                            content_hash=hashlib.sha256((md_content or '').encode('utf-8')).hexdigest(),
                            ttl_expires_at=ttl.strftime("%Y-%m-%d %H:%M:%S")
                        )

                        return {"status": "success", "content_length": content_length, "source_type": source_type, "cached": False}
                    else:
                        error_msg = data.get('error', 'Unknown error inside 200 OK')
                        raise ValueError(error_msg)

                elif response.status_code == 429:
                    if self.rate_limiter:
                        self.rate_limiter.report_error(429)
                    retries += 1
                    if retries > max_retries:
                        raise RetryableError("Rate limit exceeded after max retries")
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
                    self.logger.log_step_end(log_id, status="failed", credits_used=0, error_message=error_msg, error_category="critical")
                    raise CriticalError(error_msg)

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    self.logger.log_step_end(log_id, status="failed", credits_used=0, error_message=error_msg, error_category="skippable")
                    raise SkippableError(error_msg)

            except Exception as e:
                if isinstance(e, (RuntimeError, CriticalError)):
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
                category = e.category if isinstance(e, PipelineError) else "unknown"
                self.logger.log_step_end(log_id, status=log_status, credits_used=0, error_message=error_msg, error_category=category)

                return {"status": status_val, "content_length": 0, "source_type": source_type, "error": error_msg}

    def scrape_company(self, company_id: int, delay_seconds: float = None) -> list:
        """Scrape top-scored links for a company; falls back to priority-sorted should_scrape=1 links."""
        delay = delay_seconds if delay_seconds is not None else self.config.DELAY_SECONDS
        self.db.update_company(company_id, status='scraping')

        # Use Top-N by relevance_score instead of all links
        links = self.db.get_top_scored_links(company_id, top_n=self.config.TOP_N)

        # Fallback: if no scored links (filter hasn't run yet), use old logic
        if not links:
            links = self.db.fetch_all(
                "SELECT * FROM filtered_links WHERE company_id = ? AND should_scrape = 1",
                (company_id,)
            )
            links = sorted(links, key=self._get_sort_key)[:self.config.TOP_N]

        if getattr(self.config, 'FIRECRAWL_BATCH_SCRAPE_ENABLED', False):
            results = self._scrape_company_with_firecrawl_batch(company_id, links)
            self.db.update_company(company_id, status='scraped')
            return results

        results = []
        for link in links:
            try:
                res = self.scrape_url(link['id'])
                results.append(res)
                if not res.get("cached", False):
                    if self.rate_limiter:
                        pass
                    else:
                        time.sleep(delay)
            except (RuntimeError, CriticalError) as e:
                self.logger.logger.error(f"Stopping immediately: {e}")
                raise
            except Exception as e:
                self.logger.logger.error(f"Unexpected error scraping URL ID {link['id']}: {e}")
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
