import sqlite3
import pandas as pd
from src.filter_module import LinkFilter
from src.database import DatabaseManager
from src.logger import PipelineLogger
import os

def run_evaluation():
    db = DatabaseManager("data/company_data.db")
    logger = PipelineLogger(db)
    filter_mod = LinkFilter(db=db, logger=logger)
    
    # Connect to DB to fetch all search results and company info
    conn = sqlite3.connect("data/company_data.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = """
    SELECT 
        c.id as company_id,
        c.original_name,
        c.vietnamese_name,
        sr.id as search_result_id,
        sr.url,
        sr.title,
        sr.snippet,
        sr.search_type
    FROM search_results sr
    JOIN companies c ON sr.company_id = c.id
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    results = []
    
    print(f"Bắt đầu đánh giá {len(rows)} URLs...")
    for row in rows:
        url = row['url']
        company_name = row['original_name']
        vn_name = row['vietnamese_name'] or ""
        title = row['title'] or ""
        
        classification = filter_mod.classify_url(url, company_name, title=title, vn_name=vn_name)
        
        results.append({
            "Company ID": row['company_id'],
            "Tên Tiếng Anh": company_name,
            "Tên Tiếng Việt": vn_name,
            "Loại Search": row['search_type'],
            "URL Đầu Vào": url,
            "Title Đầu Vào": title,
            "Loại Nguồn": classification["source_type"],
            "Điểm Hệ Thống Mới": classification["relevance_score"],
            "Nên Scrape": classification["should_scrape"],
            "Lý Do": classification.get("reason", "")
        })
        
    df = pd.DataFrame(results)
    
    # Save to Excel
    os.makedirs("results/report", exist_ok=True)
    output_path = "results/report/evaluation_new_scoring_05-13.xlsx"
    df.to_excel(output_path, index=False)
    print(f"Đã lưu kết quả đánh giá cho {len(results)} URLs tại {output_path}")

if __name__ == "__main__":
    run_evaluation()
