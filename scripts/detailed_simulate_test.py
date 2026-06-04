import sys
import os
import pandas as pd

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.filter_module import LinkFilter
from src.database import DatabaseManager
from src.logger import PipelineLogger

def main():
    csv_path = os.path.join(PROJECT_ROOT, "results", "report", "search_results_report.csv")
    if not os.path.exists(csv_path):
        print("CSV not found")
        sys.exit(1)

    # Read CSV
    df = pd.read_csv(csv_path)
    # The CSV might have a BOM, causing the column to be named "\ufeffCompany"
    company_col = 'Company'
    if '\ufeffCompany' in df.columns:
        company_col = '\ufeffCompany'
        
    companies = df[company_col].dropna().unique()[5:15]

    # Setup mock DB and Filter Module
    temp_db = os.path.join(PROJECT_ROOT, "data", "temp_detailed_test.db")
    db = DatabaseManager(temp_db)
    db.init_db()
    logger = PipelineLogger(db)
    filter_module = LinkFilter(db, logger)

    report_data = []

    for company in companies:
        print(f"Processing detailed simulation for: {company}")
        company_df = df[df[company_col] == company]
        
        # -------------------------------------------------------------
        # STEP 1: Gemini Quick Search
        # -------------------------------------------------------------
        report_data.append({
            "Company": company,
            "Step": "1. Gemini Quick Search",
            "Logic / Processing Method": "Truy vấn LLM (Gemini) dựa trên tên công ty để lấy các thông tin cơ bản trước khi Deep Search.",
            "Input": f"Tên công ty: {company}",
            "Output": "JSON (Mô phỏng): {'address': '...', 'phone': '...', 'website': '...'}",
            "Query / Details": "prompt = Extract contact info for {company}",
            "URL Received": "N/A",
            "Score / Decision": "Always proceed to Step 2 (Early Stop Removed)",
            "Score Reason": "Quy trình mới yêu cầu không dừng sớm."
        })

        # -------------------------------------------------------------
        # STEP 2 & 3: Deep Search + Filtering (Iterate over URLs)
        # -------------------------------------------------------------
        scored_urls = []
        for idx, row in company_df.iterrows():
            url = row['URL']
            query = row.get('Query', f"search: {company}")
            engine = row.get('Engine', 'Serper')
            
            if not isinstance(url, str):
                continue
                
            # Perform Filtering/Scoring
            result = filter_module.classify_url(url, company)
            scored_urls.append({
                "url": url,
                "query": query,
                "engine": engine,
                "score": result['relevance_score'],
                "should_scrape": result['should_scrape'],
                "breakdown": result['score_breakdown'],
                "source": result['source_type']
            })
            
            # Formulate the breakdown reason
            reasons = []
            if result['score_breakdown'].get('domain', 0) > 0:
                reasons.append(f"Domain chính thức/uy tín (+{result['score_breakdown']['domain']})")
            elif result['score_breakdown'].get('domain', 0) == -20:
                reasons.append("Domain không liên quan/Blacklist (-20)")
                
            if result['score_breakdown'].get('keyword', 0) > 0:
                reasons.append(f"URL chứa từ khóa liên hệ/giới thiệu (+{result['score_breakdown']['keyword']})")
                
            if result['score_breakdown'].get('name_match', 0) < 0:
                reasons.append(f"Tên miền không khớp tên công ty ({result['score_breakdown']['name_match']})")
                
            reason_str = " | ".join(reasons) if reasons else "Điểm cơ bản"
            
            report_data.append({
                "Company": company,
                "Step": "2 & 3. Deep Search & Scoring",
                "Logic / Processing Method": f"Sử dụng {engine} để search, sau đó chạy Filter Module chấm điểm URL.",
                "Input": f"Query: {query}",
                "Output": f"Nguồn: {result['source_type']}",
                "Query / Details": query,
                "URL Received": url,
                "Score / Decision": f"{result['relevance_score']} (Scrape: {result['should_scrape']})",
                "Score Reason": reason_str
            })
            
        # -------------------------------------------------------------
        # STEP 4: Scrape & AI Extract
        # -------------------------------------------------------------
        scored_urls.sort(key=lambda x: x['score'], reverse=True)
        top_urls = [u for u in scored_urls if u['should_scrape']][:3]
        
        top_url_list_str = "\n".join([u['url'] for u in top_urls])
        report_data.append({
            "Company": company,
            "Step": "4. Scrape & AI Extract",
            "Logic / Processing Method": "Sử dụng Firecrawl để đọc markdown từ Top 3 URLs, sau đó gộp nội dung gửi cho Gemini (google.genai) để trích xuất SĐT/Email.",
            "Input": f"Top URLs:\n{top_url_list_str}",
            "Output": "Final Extracted Contacts (JSON)",
            "Query / Details": "Lệnh: Extract phone, email, contact person from markdown content.",
            "URL Received": "N/A",
            "Score / Decision": "Hoàn tất trích xuất.",
            "Score Reason": "Dựa trên dữ liệu thu thập được."
        })

        # -------------------------------------------------------------
        # STEP 5: Facebook Fallback
        # -------------------------------------------------------------
        fb_urls = [u for u in scored_urls if 'facebook.com' in u['url'].lower()]
        if fb_urls:
            report_data.append({
                "Company": company,
                "Step": "5. Facebook Fallback (Dự phòng)",
                "Logic / Processing Method": "Nếu Step 4 không tìm ra SĐT, tiến hành cào dữ liệu từ trang Facebook tìm thấy trong Deep Search.",
                "Input": "Check phone_number == null",
                "Output": "Facebook Markdown -> AI Extract",
                "Query / Details": "Tìm thấy Facebook Page",
                "URL Received": fb_urls[0]['url'],
                "Score / Decision": "Tiến hành quét Facebook",
                "Score Reason": "Fallback mode"
            })
        else:
            report_data.append({
                "Company": company,
                "Step": "5. Facebook Fallback (Dự phòng)",
                "Logic / Processing Method": "Kiểm tra xem có link Facebook nào không.",
                "Input": "N/A",
                "Output": "Không có dữ liệu Facebook",
                "Query / Details": "Không tìm thấy link Facebook trong danh sách Deep Search",
                "URL Received": "N/A",
                "Score / Decision": "Bỏ qua",
                "Score Reason": "Không có tài nguyên."
            })

    # Save to Excel
    out_df = pd.DataFrame(report_data)
    out_path = os.path.join(PROJECT_ROOT, "results", "report", "detailed_pipeline_simulation_10_companies.xlsx")
    
    # Auto-adjust column width if using openpyxl (optional, pandas handles basic excel export)
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        out_df.to_excel(writer, index=False, sheet_name='Detailed Simulation')
        
    print(f"\nDetailed report saved to: {out_path}")

if __name__ == "__main__":
    main()
