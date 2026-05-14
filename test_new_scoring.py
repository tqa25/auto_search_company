import sys
from unittest.mock import MagicMock
from src.filter_module import LinkFilter

db = MagicMock()
logger = MagicMock()

filter_mod = LinkFilter(db=db, logger=logger)
company_name = "Công ty TNHH Vận tải Toàn Cầu"
vn_name = "Công ty TNHH MTV Giao nhận Toàn Cầu"

test_urls = [
    {"url": "https://www.toancau.com.vn", "title": "Trang chủ - Giao nhận Toàn Cầu"},
    {"url": "https://masothue.com/123456789-cong-ty-tnhh-van-tai-toan-cau", "title": "Mã số thuế Công ty Toàn Cầu"},
    {"url": "https://www.facebook.com/toancau", "title": "Toàn Cầu Transport on Facebook"},
    {"url": "https://jobsgo.vn/cong-ty-toan-cau-tuyen-dung", "title": "Tuyển dụng Toàn Cầu Transport"},
    {"url": "https://randomsite.xyz/post/123", "title": "Some random post about transport"},
]

scored = []
for u in test_urls:
    classification = filter_mod.classify_url(u['url'], company_name, title=u.get('title', ''), vn_name=vn_name)
    scored.append({
        "url": u['url'],
        "score": classification["relevance_score"],
        "should_scrape": classification["should_scrape"],
        "reason": classification.get("reason", "")
    })

import os
os.makedirs("results/report", exist_ok=True)
report_content = "# Báo cáo thử nghiệm quy trình chấm điểm URL mới\n\n"
report_content += f"**Tên tiếng Anh / Tên gốc:** {company_name}\n"
report_content += f"**Tên tiếng Việt:** {vn_name}\n\n"
report_content += "| URL Đầu Vào | URL Được Xếp Hạng (Điểm) | Nên Scrape | Lý do |\n"
report_content += "| --- | --- | --- | --- |\n"

for s in scored:
    report_content += f"| {s['url']} | {s['score']:.1f} | {s['should_scrape']} | {s['reason']} |\n"

with open("results/report/new-scoring-test-05-13.md", "w") as f:
    f.write(report_content)
    
print("Report saved.")
