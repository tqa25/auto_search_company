import sys
import os

path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, path)

from src.excel_handler import ExcelWriter

if not os.path.exists("output"):
    os.makedirs("output")

writer = ExcelWriter()

aggregated_data = [
    {
        "company_name": "Công ty Cổ phần Mẫu A",
        "tax_code": "0123456789",
        "has_data": True,
        "total_sources": 3,
        "collection_date": "2026-04-15",
        "sources": [
            {
                "source_type": "masothue",
                "address": "123 Đường Số 1, Quận 1, TP. HCM",
                "phone": "028 1234 5678",
                "representative": "Nguyễn Văn A",
                "confidence": 0.95
            },
            {
                "source_type": "topcv",
                "address": "Tầng 19, Tòa nhà ABC, Phường 2, Tân Bình",
                "phone": "0909 001 002",
                "email": "tuyendung@mauA.com",
                "confidence": 0.65
            },
            {
                "source_type": "website",
                "address": "123 Đường Số 1, Quận 1, TP. HCM",
                "website": "maua.com.vn",
                "confidence": 0.45
            }
        ]
    },
    {
        "company_name": "Công ty TNHH Mẫu B",
        "tax_code": "9876543210",
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
    "avg_sources_per_company": 1.5,
    "avg_confidence": 0.68,
    "field_coverage": {"address": 50.0, "phone": 50.0, "email": 50.0, "website": 50.0, "representative": 50.0},
    "source_distribution": {"masothue": 33.3, "topcv": 33.3, "website": 33.3}
}

writer.write_final_report("output/sample_final_report.xlsx", aggregated_data, summary_stats)
print("Created output/sample_final_report.xlsx")
