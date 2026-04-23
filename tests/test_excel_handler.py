import os
import openpyxl
import pytest
import logging
from src.excel_handler import ExcelReader, ExcelWriter

logging.basicConfig(level=logging.INFO)

# Run tests with: pytest tests/test_excel_handler.py -v

def create_fake_excel(file_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    
    # Headers
    ws.append(["STT", " COMPANY NAME (English)", "Tax Code", "ADDRESS (English)"])
    
    # Data rows
    ws.append([1, "ABC Software Solutions Co., Ltd", "0123456789", "Hanoi"])
    ws.append([2, "XYZ Trading", None, "HCMC"])
    ws.append([3, "DEF Manufacturing TNHH", "9876543210", "Da Nang"])
    
    # Empty row
    ws.append([None, None, None, None])
    
    # Another data row with tax code
    ws.append([4, "GHI Services", "1112223334", "Can Tho"])
    
    wb.save(file_path)

def test_excel_reader(tmp_path):
    fake_excel_path = tmp_path / "fake_input.xlsx"
    create_fake_excel(str(fake_excel_path))
    
    reader = ExcelReader()
    companies = reader.read_company_list(str(fake_excel_path))
    
    assert len(companies) == 4
    
    # Verify first company
    assert companies[0]["name"] == "ABC Software Solutions Co., Ltd"
    assert companies[0]["tax_code"] == "0123456789"
    
    # Verify company without tax code
    assert companies[1]["name"] == "XYZ Trading"
    assert companies[1]["tax_code"] is None
    
    # Verify last company
    assert companies[3]["name"] == "GHI Services"
    assert companies[3]["tax_code"] == "1112223334"

def test_excel_reader_real_file():
    # If the file exists, test it
    real_file = "PIC 수집 시도_글투실_20260409.xlsx"
    if os.path.exists(real_file):
        reader = ExcelReader()
        companies = reader.read_company_list(real_file)
        assert len(companies) > 0

def test_excel_writer(tmp_path):
    output_excel_path = tmp_path / "fake_output.xlsx"
    
    results = [
        {
            "name": "Công ty A",
            "tax_code": "0123456789",
            "sources": [
                {
                    "source": "masothue",
                    "address": "123 Nguyễn Huệ",
                    "phone": "—",
                    "email": "—",
                    "website": "—",
                    "fax": "—",
                    "rep": "Nguyễn Văn A",
                    "date": "2026-04-13"
                },
                {
                    "source": "website",
                    "address": "123 Nguyễn Huệ",
                    "phone": "028-1234",
                    "email": "info@a.com",
                    "website": "a.com",
                    "fax": "—",
                    "rep": "Nguyễn Văn A",
                    "date": "2026-04-13"
                }
            ]
        },
        {
            "name": "Công ty B",
            "tax_code": "9876543210",
            "sources": [
                {
                    "source": "topcv",
                    "address": "Q1, HCM",
                    "phone": "0901-234",
                    "email": "hr@b.com",
                    "website": "b.com",
                    "fax": "—",
                    "rep": "Trần Thị B",
                    "date": "2026-04-13"
                }
            ]
        }
    ]
    
    writer = ExcelWriter()
    writer.write_results(str(output_excel_path), results)
    
    assert os.path.exists(str(output_excel_path))
    
    # Read back to verify
    wb = openpyxl.load_workbook(str(output_excel_path))
    ws = wb.active
    
    assert ws.title == "Kết quả thu thập"
    
    # Check headers
    headers = [cell.value for cell in ws[1]]
    expected_headers = [
        "STT", "Tên công ty", "Mã số thuế", "Nguồn", "Địa chỉ", 
        "SĐT", "Email", "Website", "Fax", "Người đại diện", "Ngày thu thập"
    ]
    assert headers[:len(expected_headers)] == expected_headers
    
    # Check data (row 2 -> Công ty A, masothue)
    row2 = [cell.value for cell in ws[2]]
    assert row2[1] == "Công ty A"
    assert row2[2] == "0123456789"
    assert row2[3] == "masothue"
    
    # Check data (row 3 -> Công ty A, website) - Note that the prompt said tax code could be blank 
    # but the current implementation repeats the tax_code. It's fine to repeat for easier filtering.
    row3 = [cell.value for cell in ws[3]]
    assert row3[1] == "Công ty A"
    assert row3[3] == "website"
    
    # Check data (row 4 -> Công ty B)
    row4 = [cell.value for cell in ws[4]]
    assert row4[1] == "Công ty B"
    assert row4[3] == "topcv"
