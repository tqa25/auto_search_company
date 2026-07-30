import logging
import csv
import json
import os
from datetime import timedelta
from colorama import init, Fore, Style
from openpyxl import Workbook
from src.database import DatabaseManager
from src.time_utils import parse_timestamp_as_vn, vn_date_str, vn_iso, vn_now, vn_timestamp

init(autoreset=True)

class PipelineLogger:
    def __init__(self, db: DatabaseManager, log_dir: str = "output/logs"):
        self.db = db
        # Python logging configuration
        self.logger = logging.getLogger("PipelineLogger")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

        # JSONL structured log output
        self._log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._current_log_date = None
        self._jsonl_file = None
        self._open_jsonl_file()

    def _open_jsonl_file(self):
        """Opens (or reopens on date change) the daily JSONL log file."""
        today = vn_date_str()
        if self._current_log_date != today:
            if self._jsonl_file:
                self._jsonl_file.close()
            path = os.path.join(self._log_dir, f"pipeline_{today}.jsonl")
            self._jsonl_file = open(path, "a", encoding="utf-8")
            self._current_log_date = today

    def _write_jsonl(self, event: dict):
        """Rotates file if date changed, then appends one JSON line."""
        self._open_jsonl_file()  # handles rotation
        self._jsonl_file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._jsonl_file.flush()

    def log_step_start(self, company_id: int, step: str, source_url: str = None, source_name: str = None, raw_request: dict = None) -> int:
        """Ghi record mới với status='started', started_at=now(). Trả về log_id."""
        started_at = vn_timestamp()
        log_id = self.db.insert_pipeline_log(
            company_id=company_id,
            step=step,
            status='started',
            started_at=started_at,
            source_url=source_url,
            source_name=source_name
        )

        # JSONL event
        now_iso = vn_iso(timespec='milliseconds')
        self._write_jsonl({
            "timestamp": now_iso,
            "event_type": "step_start",
            "company_id": company_id,
            "step": step,
            "source_url": source_url,
            "source_name": source_name,
            "log_id": log_id,
            "start_time": now_iso,
            "raw_request": raw_request,
        })

        return log_id

    def log_step_end(self, log_id: int, status: str, credits_used: float = 0, error_message: str = None,
                     data_saved: bool = False, metadata: dict = None, network_latency_ms: float = None,
                     processing_time_ms: float = None, raw_response_summary: dict = None,
                     error_category: str = None):
        """Update record: finished_at=now(), tính duration_seconds, cập nhật status, in ra console format"""
        finished_at = vn_timestamp()

        # Calculate duration
        log_record = self.db.fetch_one("SELECT * FROM pipeline_logs WHERE id = ?", (log_id,))
        duration = 0.0
        company_id = 0
        step = "UNKNOWN"
        source_name = "UNKNOWN"

        if log_record:
            company_id = log_record['company_id']
            step = log_record['step']
            source_name = log_record['source_name'] or "UNKNOWN"
            if log_record['started_at']:
                try:
                    start_time = parse_timestamp_as_vn(log_record['started_at'])
                    finish_time = parse_timestamp_as_vn(finished_at)
                    if start_time is None or finish_time is None:
                        raise ValueError
                    duration = (finish_time - start_time).total_seconds()
                except ValueError:
                    duration = 0.0

        metadata_json = json.dumps(metadata) if metadata else None

        self.db.update_pipeline_log(
            log_id,
            status=status,
            finished_at=finished_at,
            duration_seconds=duration,
            credits_used=credits_used,
            error_message=error_message,
            data_saved=data_saved,
            metadata_json=metadata_json
        )

        # Console output
        # Format: [2026-04-20 09:15:23] [CMP-0001] [SEARCH] [SUCCESS] 2 credits | 3.2s | "ABC Corp" → 10 links found
        now_str = vn_timestamp()
        cmp_str = f"CMP-{company_id:04d}"

        color = Fore.WHITE
        if status.upper() == 'SUCCESS':
            color = Fore.GREEN
        elif status.upper() == 'FAILED':
            color = Fore.RED
        elif status.upper() == 'SKIPPED':
            color = Fore.YELLOW

        company_name = "Unknown"
        company = self.db.get_company(company_id)
        if company:
            company_name = company['original_name']

        msg_detail = ""
        if error_message:
            msg_detail = f"→ {error_message}"
        elif step.upper() == 'SEARCH':
            links_found = metadata.get('links_found', 0) if isinstance(metadata, dict) else 0
            if isinstance(metadata, dict) and 'links_found' in metadata:
                 msg_detail = f'"{company_name}" → {metadata["links_found"]} links found'
            else:
                 msg_detail = f'"{company_name}"'
        elif step.upper() == 'SCRAPE':
            chars = metadata.get('content_length', 0) if isinstance(metadata, dict) else 0
            msg_detail = f'{source_name} → {chars} chars saved'
        elif step.upper() == 'AI_EXT':
            msg_detail = f'Extracted: {metadata.get("extracted_fields", "")}' if isinstance(metadata, dict) else "Extracted"
        elif step.upper() == 'FILTER':
            msg_detail = f'Filtered links'
        else:
            msg_detail = f'"{company_name}"'

        credits_str = f"{credits_used:g} credit{'s' if credits_used != 1 else ''}"

        log_msg = f"[{now_str}] [{cmp_str}] [{step.upper()}] {color}[{status.upper()}]{Style.RESET_ALL} {credits_str:<10} | {duration:.1f}s | {msg_detail}"
        self.logger.info(log_msg)

        # JSONL event
        now_iso = vn_iso(timespec='milliseconds')
        started_at_iso = log_record['started_at'] if log_record and log_record['started_at'] else None
        self._write_jsonl({
            "timestamp": now_iso,
            "event_type": "step_end",
            "company_id": company_id,
            "step": step,
            "log_id": log_id,
            "status": status,
            "start_time": started_at_iso,
            "end_time": finished_at,
            "duration_ms": int(duration * 1000),
            "credits_used": credits_used,
            "error_message": error_message,
            "error_category": error_category,
            "data_saved": data_saved,
            "metadata": metadata,
            "dedup_action": metadata.get("dedup_action") if isinstance(metadata, dict) else None,
            "fallback_reason": metadata.get("fallback_reason") if isinstance(metadata, dict) else None,
            "retry_count": metadata.get("retry_count", 0) if isinstance(metadata, dict) else 0,
            "scoring_breakdown": metadata.get("scoring_breakdown") if isinstance(metadata, dict) else None,
            "network_latency_ms": network_latency_ms,
            "processing_time_ms": processing_time_ms,
            "raw_response_summary": raw_response_summary,
        })

    def log_event(self, event_type: str, company_id: int, data: dict = None):
        """Log a one-off event (cache hit, dedup skip, etc.) to JSONL only (no DB record)."""
        event = {
            "timestamp": vn_iso(timespec='milliseconds'),
            "event_type": event_type,
            "company_id": company_id,
        }
        if data:
            event.update(data)
        self._write_jsonl(event)

        # Brief console line for cache_ and dedup_ event types
        prefix = event_type.split("_")[0] if "_" in event_type else ""
        if prefix in ("cache", "dedup"):
            label = "CACHE" if prefix == "cache" else "DEDUP"
            cmp_str = f"CMP-{company_id:04d}"
            self.logger.info(f"[{label}] {cmp_str} {event_type}")

    def __del__(self):
        if self._jsonl_file:
            try:
                self._jsonl_file.close()
            except Exception:
                pass

    def get_daily_summary(self) -> dict:
        """Trả về dict summary"""
        today = vn_date_str()
        tomorrow = vn_date_str(vn_now() + timedelta(days=1))

        # total_companies
        row = self.db.fetch_one("SELECT COUNT(id) as cnt FROM companies")
        total_companies = row['cnt'] if row else 0

        # All pipeline_logs aggregates in one pass: distinct companies overall,
        # distinct companies today (half-open date range instead of a fragile LIKE),
        # total credits, and total duration.
        agg = self.db.fetch_one(
            """
            SELECT
                COUNT(DISTINCT company_id) AS processed_all,
                COUNT(DISTINCT CASE WHEN started_at >= ? AND started_at < ? THEN company_id END) AS processed_today,
                SUM(credits_used) AS total_credits,
                SUM(duration_seconds) AS total_duration
            FROM pipeline_logs
            """,
            (today, tomorrow),
        ) or {}
        total_processed_all = agg.get("processed_all") or 0
        total_processed_today = agg.get("processed_today") or 0
        total_credits = agg.get("total_credits") or 0.0
        total_duration = agg.get("total_duration") or 0.0

        # success_rate: % of processed companies that have some extracted contacts (approximation)
        # Using extracted_contacts table to determine if we have info. If the table is empty for that company, then no info.
        row = self.db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts")
        companies_with_info = row['cnt'] if row and row['cnt'] else 0
        success_rate = (companies_with_info / total_processed_all * 100) if total_processed_all > 0 else 0.0

        # avg_time_per_company
        avg_time = (total_duration / total_processed_all) if total_duration and total_processed_all > 0 else 0.0

        # top_5_errors
        errors = self.db.fetch_all("SELECT error_message, COUNT(*) as count FROM pipeline_logs WHERE error_message IS NOT NULL AND error_message != '' AND status='failed' GROUP BY error_message ORDER BY count DESC LIMIT 5")

        # source_distribution
        sources = self.db.fetch_all("SELECT source_type, COUNT(*) as cnt FROM scraped_pages WHERE scrape_status='success' GROUP BY source_type")
        total_sources = sum(s['cnt'] for s in sources)
        source_dist = {}
        for s in sources:
            source_dist[s['source_type']] = f"{(s['cnt'] / total_sources * 100):.1f}%" if total_sources > 0 else "0%"

        return {
            "total_processed_today": total_processed_today,
            "total_processed_all": total_processed_all,
            "total_companies": total_companies,
            "progress_percent": (total_processed_all / total_companies * 100) if total_companies > 0 else 0.0,
            "success_rate": success_rate,
            "total_credits_used": float(total_credits),
            "avg_time_per_company": float(avg_time),
            "top_5_errors": errors,  # format: [{"error_message": "...", "count": ...}]
            "source_distribution": source_dist
        }

    def export_log_to_csv(self, output_path: str):
        """Xuất toàn bộ pipeline_logs ra file CSV"""
        logs = self.db.fetch_all("SELECT * FROM pipeline_logs ORDER BY started_at ASC")
        if not logs:
            return

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)

    def export_summary_to_excel(self, output_path: str):
        """Xuất daily_summary ra file Excel đẹp (dùng openpyxl)"""
        summary = self.get_daily_summary()
        wb = Workbook()
        ws = wb.active
        ws.title = "Daily Summary"

        # Write summary basic info
        ws.append(["Metric", "Value"])
        ws.append(["Total Processed Today", summary["total_processed_today"]])
        ws.append(["Total Processed All", summary["total_processed_all"]])
        ws.append(["Total Companies", summary["total_companies"]])
        ws.append(["Progress", f"{summary['progress_percent']:.2f}%"])
        ws.append(["Success Rate", f"{summary['success_rate']:.2f}%"])
        ws.append(["Total Credits Used", summary["total_credits_used"]])
        ws.append(["Avg Time per Company (s)", f"{summary['avg_time_per_company']:.2f}"])

        ws.append([])
        ws.append(["Top Errors"])
        ws.append(["Error Message", "Count"])
        for err in summary["top_5_errors"]:
            ws.append([err["error_message"], err["count"]])

        ws.append([])
        ws.append(["Source Distribution"])
        ws.append(["Source", "Percentage"])
        for src, pct in summary["source_distribution"].items():
            ws.append([src, pct])

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Simple formatting
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter # Get the column name
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        wb.save(output_path)

    def export_data_to_csv(self, output_path: str):
        """Export combined company data to CSV, with one row per URL according to ADR 0001."""
        companies = self.db.get_all_companies()
        
        fieldnames = [
            # Business Columns
            "Timestamp", "Company Name", "Tax Code", "URL", "Data Scope", "Source Type", 
            "Phone", "Email", "Address", "Website", "Representative",
            "Confidence Score", "Relevance Score", "Score Reason", "Status/Note",
            # Technical Columns
            "search_query", "result_rank", "search_snippet",
            "credits_used", "duration_seconds",
            "input_tokens", "output_tokens", "total_tokens",
            "raw_ai_response", "error_message", "fallback_reason"
        ]

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for company in companies:
                cid = company['id']
                c_name = company['original_name']
                t_code = company.get('tax_code', '')
                
                # 1. Process Gemini Quick Results
                gemini_results = self.db.get_gemini_quick_results_for_company(cid)
                for gr in gemini_results:
                    sources = []
                    if gr.get('grounding_sources_json'):
                        try:
                            sources = json.loads(gr['grounding_sources_json'])
                        except json.JSONDecodeError:
                            pass
                    elif gr.get('sources_json'):
                        try:
                            sources = json.loads(gr['sources_json'])
                        except json.JSONDecodeError:
                            pass
                    
                    if not sources:
                        sources = [""] # Create an empty row if no source
                        
                    for src_url in sources:
                        # Extract URL from dict if it's structured, else assume string
                        url_val = src_url
                        if isinstance(src_url, dict) and 'url' in src_url:
                            url_val = src_url['url']
                            
                        writer.writerow({
                            "Timestamp": gr.get('created_at', ''),
                            "Company Name": c_name,
                            "Tax Code": t_code,
                            "URL": url_val,
                            "Data Scope": "Company-Level",
                            "Source Type": "Gemini Quick Search",
                            "Phone": gr.get('phone', ''),
                            "Email": gr.get('email', ''),
                            "Address": gr.get('address', ''),
                            "Website": gr.get('website', ''),
                            "Representative": gr.get('representative', ''),
                            "Confidence Score": gr.get('confidence', ''),
                            "Relevance Score": "",
                            "Score Reason": "",
                            "Status/Note": "Thành công" if gr.get('is_sufficient') else "Không đủ thông tin",
                            # Tech
                            "credits_used": 0, 
                            "duration_seconds": gr.get('duration_seconds', ''),
                            "input_tokens": gr.get('input_tokens', ''),
                            "output_tokens": gr.get('output_tokens', ''),
                            "total_tokens": gr.get('total_tokens', ''),
                            "raw_ai_response": "", 
                            "error_message": "",
                            "fallback_reason": gr.get('fallback_reason', '')
                        })

                # 2. Process Deep Scrape Results
                scrape_data = self.db.get_deep_scrape_export_data_for_company(cid)
                for row in scrape_data:
                    status_note = ""
                    if row.get('scrape_status') == 'success':
                        status_note = "Thành công"
                    elif row.get('should_scrape') == 0:
                        status_note = "Bỏ qua (Lọc)"
                    elif row.get('scrape_status') == 'failed':
                        status_note = "Lỗi trang"
                    else:
                        status_note = "Chưa scrape"

                    writer.writerow({
                        "Timestamp": row.get('timestamp', ''),
                        "Company Name": c_name,
                        "Tax Code": t_code,
                        "URL": row.get('search_url', ''),
                        "Data Scope": "URL-Level",
                        "Source Type": "Deep Scrape",
                        "Phone": row.get('phone', ''),
                        "Email": row.get('email', ''),
                        "Address": row.get('address', ''),
                        "Website": row.get('website', ''),
                        "Representative": row.get('representative', ''),
                        "Confidence Score": row.get('confidence_score', ''),
                        "Relevance Score": row.get('relevance_score', ''),
                        "Score Reason": row.get('filter_reason', ''),
                        "Status/Note": status_note,
                        # Tech
                        "search_query": row.get('search_query', ''),
                        "result_rank": row.get('result_rank', ''),
                        "search_snippet": row.get('search_snippet', ''),
                        "credits_used": (row.get('search_credits') or 0) + (row.get('scrape_credits') or 0),
                        "duration_seconds": "",
                        "input_tokens": "",
                        "output_tokens": "",
                        "total_tokens": "",
                        "raw_ai_response": row.get('raw_ai_response', ''),
                        "error_message": row.get('error_message', ''),
                        "fallback_reason": ""
                    })

    def get_last_processed_company_id(self) -> int:
        """Trả về company_id cuối cùng đã xử lý xong (dùng cho resume)"""
        row = self.db.fetch_one("SELECT company_id FROM pipeline_logs ORDER BY id DESC LIMIT 1")
        return row['company_id'] if row else 0
