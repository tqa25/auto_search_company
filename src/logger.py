import logging
import csv
import json
import datetime
import os
from colorama import init, Fore, Style
from openpyxl import Workbook
from src.database import DatabaseManager

init(autoreset=True)

class PipelineLogger:
    def __init__(self, db: DatabaseManager):
        self.db = db
        # Python logging configuration
        self.logger = logging.getLogger("PipelineLogger")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def log_step_start(self, company_id: int, step: str, source_url: str = None, source_name: str = None) -> int:
        """Ghi record mới với status='started', started_at=now(). Trả về log_id."""
        started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_id = self.db.insert_pipeline_log(
            company_id=company_id,
            step=step,
            status='started',
            started_at=started_at,
            source_url=source_url,
            source_name=source_name
        )
        return log_id

    def log_step_end(self, log_id: int, status: str, credits_used: float = 0, error_message: str = None, 
                     data_saved: bool = False, metadata: dict = None):
        """Update record: finished_at=now(), tính duration_seconds, cập nhật status, in ra console format"""
        finished_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
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
                    start_time = datetime.datetime.strptime(log_record['started_at'], "%Y-%m-%d %H:%M:%S")
                    finish_time = datetime.datetime.strptime(finished_at, "%Y-%m-%d %H:%M:%S")
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
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def get_daily_summary(self) -> dict:
        """Trả về dict summary"""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # total_companies
        row = self.db.fetch_one("SELECT COUNT(id) as cnt FROM companies")
        total_companies = row['cnt'] if row else 0
        
        # total_processed_all
        row = self.db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM pipeline_logs")
        total_processed_all = row['cnt'] if row and row['cnt'] else 0
        
        # total_processed_today
        row = self.db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM pipeline_logs WHERE started_at LIKE ?", (f"{today}%",))
        total_processed_today = row['cnt'] if row and row['cnt'] else 0
        
        # success_rate: % of processed companies that have some extracted contacts (approximation)
        # Using extracted_contacts table to determine if we have info. If the table is empty for that company, then no info.
        row = self.db.fetch_one("SELECT COUNT(DISTINCT company_id) as cnt FROM extracted_contacts")
        companies_with_info = row['cnt'] if row and row['cnt'] else 0
        success_rate = (companies_with_info / total_processed_all * 100) if total_processed_all > 0 else 0.0
        
        # total_credits_used
        row = self.db.fetch_one("SELECT SUM(credits_used) as total FROM pipeline_logs")
        total_credits = row['total'] if row and row['total'] else 0.0
        
        # avg_time_per_company
        row = self.db.fetch_one("SELECT SUM(duration_seconds) as total FROM pipeline_logs")
        total_duration = row['total'] if row and row['total'] else 0.0
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

    def get_last_processed_company_id(self) -> int:
        """Trả về company_id cuối cùng đã xử lý xong (dùng cho resume)"""
        row = self.db.fetch_one("SELECT company_id FROM pipeline_logs ORDER BY id DESC LIMIT 1")
        return row['company_id'] if row else 0
