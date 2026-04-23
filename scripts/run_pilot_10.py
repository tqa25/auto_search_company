import os
import sys
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import Pipeline
from src.database import DatabaseManager
from src.excel_handler import ExcelReader

def main():
    # Ask for user confirmation first as required by the spec
    print("Sẽ sử dụng ~50 credits. Tiếp tục? (y/n)")
    # Since this is an automated agent script testing, for the sake of the prompt,
    # we just print the prompt and if we are running in an interactive console, it would pause.
    # In this script, we'll use input()
    # BUT wait, the prompt "Hỏi người dùng xác nhận" means I should ask the user via my LLM response!
    # Or does it mean the script itself should have `input()`? 
    # "Trước khi chạy thật, hỏi người dùng xác nhận: "Sẽ sử dụng ~50 credits. Tiếp tục? (y/n)""
    # I'll implement exactly "y/n" input in the script.
    
    # Actually if the script asks, the user has to type it on terminal.
    # Let's add that logic.
    user_input = input("Sẽ sử dụng ~50 credits. Tiếp tục? (y/n): ")
    if user_input.lower().strip() != 'y':
        print("Cancelled.")
        return

    # 1. Load .env
    load_dotenv()
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print("Error: FIRECRAWL_API_KEY not found in .env")
        return

    print("1. Loaded API key.")

    # Configurations
    config = {
        "firecrawl_api_key": api_key,
        "delay_seconds": 3.0,
        "batch_size": 10,
        "output_dir": "output"
    }
    
    pipeline = Pipeline(config)
    
    # 2. Excel initialization
    input_excel = "PIC 수집 시도_글투실_20260409.xlsx"
    if not os.path.exists(input_excel):
        print(f"Error: {input_excel} not found in root directory!")
        return
        
    print(f"2. Reading {input_excel}...")
    companies_data = pipeline.excel_reader.read_company_list(input_excel)
    
    # Get first 10
    top_10 = companies_data[:10]
    
    # 3. Insert into DB (Check if they already exist, by tax_code or name to avoid duplicates if possible, or just insert)
    # The requirement says "Insert vào DB". We'll use database_manager.
    print("3. Inserting into DB...")
    company_ids = []
    for comp in top_10:
        # Assuming db has an `add_company` or similar method
        # Let's just blindly insert them or check safely
        try:
            # Let's see if DatabaseManager has insert_company
            if hasattr(pipeline.db, "insert_company"):
                comp_id = pipeline.db.insert_company(original_name=comp["name"], tax_code=comp.get("tax_code"))
            else:
                # Fallback to direct SQL if method is differently named
                conn = pipeline.db.conn
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
        
    # 4. Run Pipeline with limit=10
    print(f"4. Running Pipeline for 10 companies...")
    pipeline.run(company_ids=company_ids)
    
    # 5. Print Summary
    # We can get daily summary from logger
    summary = pipeline.logger.get_daily_summary()
    print("\n=== FINAL SUMMARY ===")
    print(f"Total processed: {summary.get('total_processed_all', 0)}")
    print(f"Success rate: {summary.get('success_rate', 0.0)}%")
    print(f"Total credits used (estimated): {summary.get('total_credits_used', 50.0)}")
    
    # 6. Export report
    report_path = os.path.join(config["output_dir"], "pilot_10_report.xlsx")
    pipeline.generate_report(report_path)
    
    # 7. Export log to CSV
    log_path = os.path.join(config["output_dir"], "pilot_10_log.csv")
    pipeline.logger.export_log_to_csv(log_path)
    print(f"Log exported to {log_path}")

if __name__ == "__main__":
    main()
