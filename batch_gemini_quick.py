import sqlite3
import time
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.gemini_quick_search import GeminiQuickSearch
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("batch_gemini")

def run_batch_gemini():
    db = DatabaseManager("data/company_data.db")
    pipeline_logger = PipelineLogger(db)
    gemini = GeminiQuickSearch(db, pipeline_logger)
    
    # Get all company IDs that have search results
    conn = sqlite3.connect("data/company_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT company_id FROM search_results")
    company_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    print(f"Bắt đầu chạy Gemini Quick cho {len(company_ids)} công ty...")
    
    success_count = 0
    for cid in company_ids:
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                # Skip if already has both VN name and Tax Code
                company = db.get_company(cid)
                if company.get("vietnamese_name") and company.get("tax_code"):
                    print(f"Bỏ qua company_id={cid} (Đã có đủ dữ liệu VN Name và MST).")
                    success_count += 1
                    break
                    
                print(f"Đang xử lý company_id={cid} (Lần thử {retry_count+1})...")
                res = gemini.search(cid)
                if res.get("result"):
                    success_count += 1
                
                # Delay to stay within conservative limits
                time.sleep(15)
                break
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    print(f"Hết Quota (429). Đang chờ 60 giây để thử lại...")
                    time.sleep(65)
                    retry_count += 1
                else:
                    print(f"Lỗi khi xử lý company_id={cid}: {e}")
                    break
            
    print(f"Hoàn thành Gemini Quick. Thành công: {success_count}/{len(company_ids)}")

if __name__ == "__main__":
    run_batch_gemini()
