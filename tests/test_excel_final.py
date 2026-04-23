import os
import pytest
from src.excel_handler import ExcelWriter

def test_write_final_report():
    writer = ExcelWriter()
    
    aggregated_data = [
        {
            "company_name": "Test Company 1",
            "tax_code": "TC1",
            "has_data": True,
            "total_sources": 2,
            "collection_date": "2026-04-15",
            "sources": [
                {
                    "source_type": "masothue",
                    "address": "123 A St",
                    "confidence": 0.95
                },
                {
                    "source_type": "website",
                    "email": "test@test.com",
                    "confidence": 0.6
                }
            ]
        },
        {
            "company_name": "Test Company 2",
            "tax_code": "TC2",
            "has_data": False,
            "total_sources": 0,
            "collection_date": "2026-04-15",
            "sources": []
        }
    ]
    
    summary_stats = {
        "total_companies": 2,
        "companies_with_data": 1,
        "companies_no_data": 1,
        "coverage_rate": 50.0,
        "avg_sources_per_company": 1.0,
        "avg_confidence": 0.775,
        "field_coverage": {"address": 50.0, "email": 50.0},
        "source_distribution": {"masothue": 50.0, "website": 50.0}
    }
    
    output_path = "test_final_report.xlsx"
    if os.path.exists(output_path):
        os.remove(output_path)
        
    try:
        writer.write_final_report(output_path, aggregated_data, summary_stats)
        assert os.path.exists(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
