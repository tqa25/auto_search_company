import os
import sys
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import Pipeline
from src.database import DatabaseManager

def main():
    # 1. Load .env
    load_dotenv()
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    
    if not firecrawl_api_key:
        print("Error: FIRECRAWL_API_KEY not found in .env")
        return
    if not gemini_api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        return

    print("1. Loaded API keys.")

    # Configurations
    config = {
        "firecrawl_api_key": firecrawl_api_key,
        "gemini_api_key": gemini_api_key,
        "delay_seconds": 4.0,  # Ensure 4s delay for Gemini rate limit
        "batch_size": 5,
        "output_dir": "output"
    }
    
    pipeline = Pipeline(config)
    
    # 2. Đọc Excel file -> lấy 5 công ty đầu tiên
    input_excel = "input_db_excel.xlsx"
    if not os.path.exists(input_excel):
        print(f"Error: {input_excel} not found in root directory!")
        return
        
    print(f"2. Reading {input_excel}...")
    companies_data = pipeline.excel_reader.read_company_list(input_excel)
    
    # Get 5 companies starting from index 0
    top_5 = companies_data[:5]
    
    if not top_5:
        print("No companies found. Exiting.")
        return
    
    # 3. Insert vào DB
    print("3. Inserting into DB...")
    company_ids = []
    for comp in top_5:
        try:
            if hasattr(pipeline.db, "insert_company"):
                comp_id = pipeline.db.insert_company(original_name=comp["name"], tax_code=comp.get("tax_code"))
            else:
                conn = pipeline.db._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO companies (original_name, tax_code, status) VALUES (?, ?, ?)",
                    (comp["name"], comp.get("tax_code"), "pending")
                )
                conn.commit()
                comp_id = cursor.lastrowid
            company_ids.append(comp_id)
        except Exception as e:
            print(f"Failed to insert DB for {comp['name']}: {e}")
            
    if not company_ids:
        print("No companies inserted. Exiting.")
        return
        
    # 4. Chạy Pipeline.run
    print(f"4. Running Full Pipeline for {len(company_ids)} companies...")
    pipeline.run(company_ids=company_ids)
    
    # 5. In summary chi tiết
    print("\n=== PIPELINE EXECUTION SUMMARY ===")
    summary = pipeline.logger.get_daily_summary()
    print(f"- Total companies processed: {summary.get('total_processed_all', 0)}")
    
    if pipeline.ai_extractor:
        ai_stats = pipeline.ai_extractor.get_extraction_stats()
        print(f"- Total Gemini AI calls: {ai_stats.get('total_pages_processed', 0)}")

    # 6. Xuất báo cáo
    os.makedirs(config["output_dir"], exist_ok=True)
    report_path = os.path.join(config["output_dir"], "test_5_full_report.xlsx")
    pipeline.generate_report(report_path)
    print(f"-> Full Report exported to {report_path}")

if __name__ == "__main__":
    main()
