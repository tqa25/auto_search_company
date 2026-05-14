import re

with open('src/search_module.py', 'r') as f:
    content = f.read()

new_search_company = """
    VN_COMPANY_PATTERNS = [
        r"(?:Công ty|CÔNG TY)\\s+(?:TNHH|CP|CỔ PHẦN|HỢP DANH|MTV|MỘT THÀNH VIÊN)\\s+([\\w\\s&.,-]+?)(?:\\s+tại\\s+|-|Mã số thuế|Địa chỉ|\\n|$)",
        r"(?:Tập đoàn|TẬP ĐOÀN)\\s+([\\w\\s&.,-]+?)(?:\\s+tại\\s+|-|Mã số thuế|Địa chỉ|\\n|$)",
        r"(?:Tổng công ty|TỔNG CÔNG TY)\\s+([\\w\\s&.,-]+?)(?:\\s+tại\\s+|-|Mã số thuế|Địa chỉ|\\n|$)"
    ]

    def search_company(self, company_id: int) -> List[Dict]:
        \"\"\"Execute the 3-step Anchor -> Infer -> Expand -> Fallback search strategy.\"\"\"
        company = self.db.get_company(company_id)
        if not company:
            logger.error(f"Company with id={company_id} not found in DB.")
            return []

        company_name = company["original_name"]
        self.db.update_company(company_id, status="searching")
        abbreviation = self._compute_abbreviation(company_name)

        all_results = []

        # Step 1: Anchor
        anchor_results = self._step1_anchor(company_id, company_name, abbreviation)
        all_results.extend(anchor_results)
        if self._count_qualified(company_name, all_results) >= self.config.EARLY_STOP_COUNT:
            self.db.update_company(company_id, status="searched")
            return all_results

        # Step 2: Infer VN Name & Data
        vn_data = self._step2_infer_vn_data(company_id, anchor_results)
        vn_name = vn_data.get("vn_name")

        # Step 3: Expand
        if vn_name:
            expand_results = self._step3_expand(company_id, vn_name)
            all_results.extend(expand_results)
            if self._count_qualified(company_name, all_results) >= self.config.EARLY_STOP_COUNT:
                self.db.update_company(company_id, status="searched")
                return all_results

        # Step 4: Fallback
        all_results = self._step4_fallback(company_id, company_name, vn_name, all_results)
        self.db.update_company(company_id, status="searched")
        return all_results

    def _step1_anchor(self, company_id: int, company_name: str, abbreviation: str) -> List[Dict]:
        if abbreviation:
            query = f'("{company_name}" OR "{abbreviation}") AND ("liên hệ" OR "contact")'
        else:
            query = f'"{company_name}" AND ("liên hệ" OR "contact")'
            
        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"step1_anchor: {company_name}",
            raw_request={"query": query, "tier": "step1_anchor"}
        )
        return self._execute_search_query(company_id, query, "step1_anchor", log_id)

    def _step2_infer_vn_data(self, company_id: int, anchor_results: List[Dict]) -> dict:
        legal_results = [r for r in anchor_results if self._is_legal_domain(r.get("url", ""))]
        
        # 2a. Extract from snippets
        for result in legal_results:
            data = self._extract_vn_data_from_snippet(result.get("snippet", ""), result.get("url", ""))
            if data.get("vn_name"):
                self._update_company_vn_data(company_id, data)
                return data

        # 2b. Scrape fallback
        max_scrape = getattr(self.config, 'INFER_MAX_SCRAPE', 2)
        if max_scrape > 0 and legal_results:
            for result in legal_results[:max_scrape]:
                data = self._scrape_and_extract_vn_data(result.get("url", ""))
                if data.get("vn_name"):
                    self._update_company_vn_data(company_id, data)
                    return data
        return {}

    def _step3_expand(self, company_id: int, vn_name: str) -> List[Dict]:
        query = f'"{vn_name}" AND ("tuyển dụng" OR "nhân sự" OR "Zalo")'
        log_id = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"step3_expand: {vn_name}",
            raw_request={"query": query, "tier": "step3_expand"}
        )
        return self._execute_search_query(company_id, query, "step3_expand", log_id)

    def _step4_fallback(self, company_id: int, company_name_en: str, vn_name: str, existing_results: List[Dict]) -> List[Dict]:
        # 4a. Bare EN name
        query_en = f'"{company_name_en}"'
        log_id_en = self.pipeline_logger.log_step_start(
            company_id, "search", source_name=f"step4_fallback_en: {company_name_en}",
            raw_request={"query": query_en, "tier": "step4_fallback_en"}
        )
        saved_en = self._execute_search_query(company_id, query_en, "step4_fallback_en", log_id_en)
        existing_results.extend(saved_en)
        
        if self._count_qualified(company_name_en, existing_results) >= self.config.EARLY_STOP_COUNT:
            return existing_results
            
        # 4b. Bare VN name
        if vn_name:
            query_vn = f'"{vn_name}"'
            log_id_vn = self.pipeline_logger.log_step_start(
                company_id, "search", source_name=f"step4_fallback_vn: {vn_name}",
                raw_request={"query": query_vn, "tier": "step4_fallback_vn"}
            )
            saved_vn = self._execute_search_query(company_id, query_vn, "step4_fallback_vn", log_id_vn)
            existing_results.extend(saved_vn)
            
        return existing_results

    def _execute_search_query(self, company_id: int, query: str, search_type: str, log_id: int) -> List[Dict]:
        try:
            start_time = time.time()
            results, cache_hit = self._search_with_dedup(query, company_id, limit=self.config.SEARCH_LIMIT)
            elapsed_ms = (time.time() - start_time) * 1000
            saved = self._save_results(company_id, query, search_type, results)
            self.pipeline_logger.log_step_end(
                log_id,
                status="success",
                credits_used=0 if cache_hit else self.CREDITS_PER_SEARCH,
                data_saved=bool(saved),
                network_latency_ms=elapsed_ms,
                raw_response_summary={"result_count": len(saved), "status_code": 200},
                metadata={"links_found": len(saved), "search_type": search_type, "cache_hit": cache_hit},
            )
            return saved
        except Exception as e:
            category = getattr(e, 'category', 'unknown')
            self.pipeline_logger.log_step_end(log_id, status="failed", error_message=str(e), error_category=category)
            if isinstance(e, (CriticalError, RetryableError)):
                raise
            return []

    def _is_legal_domain(self, url: str) -> bool:
        if not url: return False
        domain = urllib.parse.urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain.endswith(d) or domain == d for d in self.config.VN_LEGAL_DOMAINS)

    def _extract_vn_data_from_snippet(self, snippet: str, url: str) -> dict:
        data = {"vn_name": None, "tax_code": None, "address": None, "source": f"snippet:{urllib.parse.urlparse(url).netloc}"}
        if not snippet: return data
        
        # Name
        for pattern in self.VN_COMPANY_PATTERNS:
            match = re.search(pattern, snippet, re.IGNORECASE)
            if match:
                name = match.group(0).strip()
                name = re.sub(r'(?i)\\s+tại\\s+.*$', '', name)
                name = re.sub(r'(?i)\\s*-\\s*.*$', '', name)
                name = re.sub(r'(?i)\\s+Mã số thuế.*$', '', name)
                name = re.sub(r'(?i)\\s+Địa chỉ.*$', '', name)
                if len(name) > 10:
                    data["vn_name"] = name.strip(',.- ')
                    break

        # MST
        mst_match = re.search(r'\\b\\d{10}(?:-\\d{3})?\\b', snippet)
        if mst_match:
            data["tax_code"] = mst_match.group(0)

        return data

    def _scrape_and_extract_vn_data(self, url: str) -> dict:
        data = {"vn_name": None, "tax_code": None, "address": None, "source": f"scrape:{urllib.parse.urlparse(url).netloc}"}
        try:
            headers = {"Authorization": f"Bearer {self.firecrawl_api_key}", "Content-Type": "application/json"}
            body = {"url": url, "formats": ["markdown"], "timeout": 30000}
            if self.rate_limiter:
                self.rate_limiter.wait()
            if self.connection_manager:
                resp = self.connection_manager.post("https://api.firecrawl.dev/v1/scrape", json=body, request_type="scrape")
            else:
                resp = requests.post("https://api.firecrawl.dev/v1/scrape", headers=headers, json=body, timeout=35)
            
            if resp.status_code == 200:
                if self.rate_limiter:
                    self.rate_limiter.report_success()
                res_json = resp.json()
                if res_json.get("success"):
                    md = res_json.get("data", {}).get("markdown", "")
                    data_ext = self._extract_vn_data_from_snippet(md[:2000], url)
                    data["vn_name"] = data_ext.get("vn_name")
                    data["tax_code"] = data_ext.get("tax_code")
                    data["address"] = data_ext.get("address")
            elif resp.status_code == 429 and self.rate_limiter:
                self.rate_limiter.report_error(429)
        except Exception as e:
            logger.warning(f"Failed to scrape legal URL {url}: {e}")
        return data

    def _update_company_vn_data(self, company_id: int, data: dict):
        updates = {}
        if data.get("vn_name"): updates["vietnamese_name"] = data["vn_name"]
        if data.get("tax_code"): updates["tax_code"] = data["tax_code"]
        if data.get("address"): updates["address"] = data["address"]
        if data.get("source"): updates["vn_data_source"] = data["source"]
        if updates:
            self.db.update_company(company_id, **updates)

    def _count_qualified(self, company_name: str, results: List[Dict]) -> int:
        if not self.config.EARLY_STOP_COUNT:
            return 0
        scored = self.filter_module.score_urls_batch(results, company_name)
        return sum(1 for item in scored if item["relevance_score"] >= self.config.EARLY_STOP_SCORE)
"""

# Find the start of def search_company(self, company_id: int) -> List[Dict]:
# and the start of def search_batch
start_idx = content.find('def search_company(self, company_id: int) -> List[Dict]:')
end_idx = content.find('def search_batch(')

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_search_company.lstrip() + "\n    " + content[end_idx:]
    with open('src/search_module.py', 'w') as f:
        f.write(new_content)
    print("Patch applied successfully.")
else:
    print("Could not find start/end indices.")

