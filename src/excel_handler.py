import openpyxl
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class ExcelReader:
    """Reads input Excel files to extract company names and tax codes."""
    
    def __init__(self):
        self.name_keywords = ["company name (english)", "company name", "english name", "tên công ty", "name"]
        self.tax_code_keywords = ["tax code", "mã số thuế", "mst"]

    def _find_columns(self, sheet) -> tuple[Optional[int], Optional[int]]:
        """Finds the column indices for company name and tax code by scanning the first few rows."""
        name_col = None
        tax_col = None
        
        # Scan first 5 rows to find headers
        for row_idx, row in enumerate(sheet.iter_rows(min_row=1, max_row=5, values_only=True)):
            for col_idx, cell_value in enumerate(row):
                if not isinstance(cell_value, str):
                    continue
                cell_lower = cell_value.strip().lower()
                
                # Check for name keywords if not found yet
                if name_col is None:
                    if any(kw in cell_lower for kw in self.name_keywords):
                        name_col = col_idx
                
                # Check for tax code keywords if not found yet
                if tax_col is None:
                    if any(kw in cell_lower for kw in self.tax_code_keywords):
                        tax_col = col_idx
            
            # If both columns are found, stop scanning
            if name_col is not None and tax_col is not None:
                break
                
        return name_col, tax_col

    def read_company_list(self, file_path: str) -> List[Dict]:
        """Reads the Excel file and extracts company list."""
        logger.info(f"Reading Excel file: {file_path}")
        
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
        except Exception as e:
            logger.error(f"Failed to load Excel file {file_path}: {e}")
            raise
            
        name_col, tax_col = self._find_columns(sheet)
        
        if name_col is None:
            logger.warning("Could not find company name column in the file. Trying to fallback to index 1 if it exists.")
            # Based on the sample output, company name (English) is often column index 1
            name_col = 1
        
        companies = []
        empty_rows = 0
        tax_code_count = 0
        
        # We start looking for data from the row after the header. Assuming row 3 based on sample.
        # But to be safe, we'll iterate through all rows and ignore rows without a valid string name.
        has_found_header = False
        
        for row in sheet.iter_rows(values_only=True):
            if not row or len(row) <= max(name_col or 0, tax_col or 0):
                empty_rows += 1
                continue
                
            name_val = row[name_col] if name_col is not None else None
            
            # Skip empty names or header row (heuristic: matches keyword)
            if not isinstance(name_val, str) or not name_val.strip():
                empty_rows += 1
                continue
                
            name_str = name_val.strip()
            
            # Check if this is the header row we found earlier
            if any(kw in name_str.lower() for kw in self.name_keywords):
                has_found_header = True
                continue
                
            # It's a company name
            tax_val = row[tax_col] if tax_col is not None and tax_col < len(row) else None
            tax_str = str(tax_val).strip() if tax_val is not None and str(tax_val).strip() and str(tax_val).lower() != 'none' else None
            
            companies.append({
                "name": name_str,
                "tax_code": tax_str
            })
            
            if tax_str:
                tax_code_count += 1
                
        logger.info(f"Excel read complete. Total companies: {len(companies)}, With tax code: {tax_code_count}, Empty/skipped rows: {empty_rows}")
        return companies

class ExcelWriter:
    """Writes output data to standard Excel format."""
    
    def __init__(self):
        self.headers = [
            "STT", "Tên công ty", "Mã số thuế", "Nguồn", "Địa chỉ", 
            "SĐT", "Email", "Website", "Fax", "Người đại diện", "Ngày thu thập"
        ]
        
    def write_results(self, output_path: str, results: List[Dict]):
        """
        Writes results to Excel file.
        `results` format expected:
        [
            {
                "name": "ABC Corp",
                "tax_code": "0123456789",
                "sources": [
                    {
                        "source": "masothue",
                        "address": "123 Nguyến Huệ",
                        "phone": "028",
                        "email": "info",
                        "website": "",
                        "fax": "",
                        "rep": "",
                        "date": "2026-04-13"
                    },
                    ...
                ]
            },
            ...
        ]
        """
        logger.info(f"Writing results to Excel file: {output_path}")
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Kết quả thu thập"
        
        # Write headers
        for col_idx, header in enumerate(self.headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            
            # Set default column width
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 20
            
        # Freeze top row
        ws.freeze_panes = "A2"
        
        thin_border = Border(
            left=Side(style='thin'), 
            right=Side(style='thin'), 
            top=Side(style='thin'), 
            bottom=Side(style='thin')
        )
        
        row_idx = 2
        stt = 1
        
        for company in results:
            company_name = company.get("name", "")
            tax_code = company.get("tax_code", "")
            
            sources = company.get("sources", [])
            if not sources:
                # Still output a row even if no sources found
                sources = [{}]
                
            for i, source_data in enumerate(sources):
                # Display tax_code only on the first row of a company, use "—" otherwise
                display_tax_code = tax_code if i == 0 else "—"
                if not display_tax_code:
                    display_tax_code = "—"
                    
                row_data = [
                    stt,
                    company_name,
                    display_tax_code,
                    source_data.get("source", "—") or "—",
                    source_data.get("address", "—") or "—",
                    source_data.get("phone", "—") or "—",
                    source_data.get("email", "—") or "—",
                    source_data.get("website", "—") or "—",
                    source_data.get("fax", "—") or "—",
                    source_data.get("rep", "—") or "—",
                    source_data.get("date", "—") or "—"
                ]
                
                for col_idx, val in enumerate(row_data, start=1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.border = thin_border
                    # Only wrap text for long fields like address
                    if isinstance(val, str) and len(val) > 30:
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                    else:
                        cell.alignment = Alignment(vertical="top")
                        
                row_idx += 1
            stt += 1
            
        try:
            wb.save(output_path)
            logger.info(f"Successfully saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save to {output_path}: {e}")
            raise

    def write_final_report(self, output_path: str, aggregated_data: List[Dict], summary_stats: Dict):
        """
        Writes final report to Excel file with two sheets: details and summary stats.
        """
        logger.info(f"Writing final report to Excel file: {output_path}")
        
        wb = openpyxl.Workbook()
        ws_details = wb.active
        ws_details.title = "Kết quả thu thập"
        
        # Write headers for details sheet
        for col_idx, header in enumerate(self.headers + ["Độ tin cậy"], start=1):
            if header == "Ngày thu thập":
                # Ensure the order is "Độ tin cậy", "Ngày thu thập" as requested
                continue
            cell = ws_details.cell(row=1, column=col_idx, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws_details.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 20
            
        # Write the last header
        cell = ws_details.cell(row=1, column=len(self.headers)+1, value="Ngày thu thập")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws_details.column_dimensions[openpyxl.utils.get_column_letter(len(self.headers)+1)].width = 20
            
        ws_details.freeze_panes = "A2"
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        
        row_idx = 2
        stt = 1
        
        for company in aggregated_data:
            company_name = company.get("company_name", "")
            tax_code = company.get("tax_code", "")
            has_data = company.get("has_data", False)
            collection_date = company.get("collection_date", "")
            
            if not has_data:
                row_data = [
                    stt, company_name, tax_code, "(không tìm thấy)",
                    "—", "—", "—", "—", "—", "—", "—", collection_date
                ]
                for col_idx, val in enumerate(row_data, start=1):
                    cell = ws_details.cell(row=row_idx, column=col_idx, value=val)
                    cell.border = thin_border
                    cell.fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                row_idx += 1
            else:
                sources = company.get("sources", [])
                for i, source in enumerate(sources):
                    display_tax_code = tax_code if i == 0 else ""
                    display_company_name = company_name if i == 0 else ""
                    confidence = source.get("confidence")
                    
                    row_data = [
                        stt if i == 0 else "",
                        display_company_name,
                        display_tax_code,
                        source.get("source_url", "—") or "—",
                        source.get("address", "—") or "—",
                        source.get("phone", "—") or "—",
                        source.get("email", "—") or "—",
                        source.get("website", "—") or "—",
                        source.get("fax", "—") or "—",
                        source.get("representative", "—") or "—",
                        confidence if confidence is not None else "—",
                        collection_date if i == 0 else ""
                    ]
                    
                    for col_idx, val in enumerate(row_data, start=1):
                        cell = ws_details.cell(row=row_idx, column=col_idx, value=val)
                        cell.border = thin_border
                        if isinstance(val, str) and len(val) > 30:
                            cell.alignment = Alignment(wrap_text=True, vertical="top")
                        else:
                            cell.alignment = Alignment(vertical="top")
                            
                        # Conditional formatting for confidence column (11)
                        if col_idx == 11 and isinstance(val, (int, float)):
                            if val >= 0.8:
                                cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                                cell.font = Font(color="006100")
                            elif val >= 0.5:
                                cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
                                cell.font = Font(color="9C6500")
                            else:
                                cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                                cell.font = Font(color="9C0006")
                    row_idx += 1
            stt += 1
            
        # Sheet 2: Summary Stats
        ws_summary = wb.create_sheet(title="Thống kê tổng quát")
        
        ws_summary.column_dimensions['A'].width = 30
        ws_summary.column_dimensions['B'].width = 20
        
        cell = ws_summary.cell(row=1, column=1, value="Chỉ số")
        cell.font = Font(bold=True)
        cell = ws_summary.cell(row=1, column=2, value="Giá trị")
        cell.font = Font(bold=True)
        
        summary_rows = [
            ("Tổng số công ty", summary_stats.get("total_companies", 0)),
            ("Số công ty có dữ liệu", summary_stats.get("companies_with_data", 0)),
            ("Số công ty không có dữ liệu", summary_stats.get("companies_no_data", 0)),
            ("Tỷ lệ coverage (%)", round(summary_stats.get("coverage_rate", 0), 2)),
            ("Số nguồn trung bình / công ty", round(summary_stats.get("avg_sources_per_company", 0), 2)),
            ("Độ tin cậy trung bình", round(summary_stats.get("avg_confidence", 0), 2)),
        ]
        
        r_idx = 2
        for key, val in summary_rows:
            ws_summary.cell(row=r_idx, column=1, value=key)
            ws_summary.cell(row=r_idx, column=2, value=val)
            r_idx += 1
            
        r_idx += 1
        ws_summary.cell(row=r_idx, column=1, value="Độ phủ theo trường (%)").font = Font(bold=True)
        r_idx += 1
        for field, pct in summary_stats.get("field_coverage", {}).items():
            ws_summary.cell(row=r_idx, column=1, value=field)
            ws_summary.cell(row=r_idx, column=2, value=f"{round(pct, 2)}%")
            r_idx += 1
            
        r_idx += 1
        ws_summary.cell(row=r_idx, column=1, value="Phân bổ theo nguồn (%)").font = Font(bold=True)
        r_idx += 1
        for source, pct in summary_stats.get("source_distribution", {}).items():
            ws_summary.cell(row=r_idx, column=1, value=source)
            ws_summary.cell(row=r_idx, column=2, value=f"{round(pct, 2)}%")
            r_idx += 1
            
        r_idx += 2
        ws_summary.cell(row=r_idx, column=1, value="Danh sách công ty không tìm thấy").font = Font(bold=True)
        r_idx += 1
        for company in aggregated_data:
            if not company.get("has_data", False):
                ws_summary.cell(row=r_idx, column=1, value=company.get("company_name", ""))
                ws_summary.cell(row=r_idx, column=2, value=company.get("tax_code", ""))
                r_idx += 1
                
        try:
            wb.save(output_path)
            logger.info(f"Successfully saved final report to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save final report to {output_path}: {e}")
            raise
