import sys
import os
import pandas as pd
from datetime import datetime
import time

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.database import DatabaseManager
from src.pipeline import Pipeline
from src.config import Config
from src.errors import CriticalError

def main():
    print("==================================================")
    print("    LIVE TEST: 3 COMPANIES (OPENROUTER EXTRACT)   ")
    print("==================================================")
    
    # 1. Setup Live Test DB with dynamic timestamp to preserve logs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = f"live_test_{timestamp}.db"
    db_path = os.path.join(PROJECT_ROOT, "data", db_name)
    print(f"Creating dynamic test DB at {db_path}")
        
    db = DatabaseManager(db_path)
    db.init_db()
    
    # 2. Insert the 2 target companies
    target_companies = [
        "anh binh production co., ltd",
        "asia best investment co., ltd"
    ]
    
    company_ids = []
    for comp in target_companies:
        cid = db.insert_company(comp)
        company_ids.append(cid)
        print(f"Inserted company: {comp} (ID: {cid})")
        
    # 3. Setup and Run Pipeline
    config = Config()
    # Force settings for the test
    config.GEMINI_QUICK_ENABLED = True
    config.SERPER_ENABLED = True
    config.GOOGLE_MAPS_ENABLED = False
    
    print("\nStarting pipeline execution... (This might take a few minutes)")
    start_time = time.time()
    
    # Inject our isolated DB into Pipeline by instantiating components manually, 
    # but the easiest way is to let Pipeline use default DB, wait Pipeline uses default unless modified.
    # Actually, Pipeline instantiates DatabaseManager() without arguments! 
    # So we need to override the db_path globally or patch it.
    # To do it properly, we just instantiate Pipeline and replace its db.
    
    pipeline = Pipeline(config={}, pipeline_config=config)
    # Patch the DB manager to use our live test DB
    pipeline.db = db
    pipeline.logger.db = db
    pipeline.search_module.db = db
    pipeline.filter_module.db = db
    pipeline.scrape_module.db = db
    pipeline.gemini_quick.db = db
    pipeline.serper.db = db
    if pipeline.ai_extractor:
        pipeline.ai_extractor.db = db
    pipeline.result_aggregator.db = db
    
    # Run the pipeline
    try:
        pipeline.run(company_ids=company_ids)
    except CriticalError as e:
        print(f"\n⛔ DỪNG KHẨN: {e}")
        print("   -> Dữ liệu đã xử lý được bảo toàn trong DB.")
        print(f"   -> Sau khi nạp tiền, chạy lại với --resume để tiếp tục (Dùng DB: {db_path}).")
        # We can still generate the report for whatever was done so far
        pass
    
    end_time = time.time()
    print(f"\nPipeline finished in {end_time - start_time:.2f} seconds.")
    
    # 4. Generate Detailed Excel Report
    print("\nGenerating Detailed Excel Report...")
    report_data = []
    
    for cid, company_name in zip(company_ids, target_companies):
        # Quick Search Info
        quick_logs = db.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? AND step = 'gemini_quick' ORDER BY id DESC LIMIT 1", (cid,))
        quick_res = db.fetch_all("SELECT * FROM gemini_quick_results WHERE company_id = ? ORDER BY id DESC LIMIT 1", (cid,))
        
        # Pipeline status
        steps = ['gemini_quick', 'serper_search', 'filter', 'scrape', 'AI_EXT'] # Keep serper_search for now until we replace it
        status_parts = []
        for step in steps:
            logs = db.fetch_all(
                "SELECT status, error_message FROM pipeline_logs "
                "WHERE company_id = ? AND step = ? ORDER BY id DESC LIMIT 1",
                (cid, step)
            )
            if logs:
                s = logs[0]['status']
                if s in ('FAILED', 'failed', 'error'):
                    status_parts.append(f"❌ {step}: {(logs[0].get('error_message') or '')[:50]}")
                else:
                    status_parts.append(f"✅ {step}")
            else:
                status_parts.append(f"⏭️ {step}")
        pipeline_status = " | ".join(status_parts)
        
        core_name = ""
        core_name_vi = ""
        if quick_res:
            core_name = quick_res[0].get('core_name', '')
            core_name_vi = quick_res[0].get('core_name_vi', '')
            
        quick_duration = quick_logs[0]['duration_seconds'] if quick_logs and quick_logs[0]['duration_seconds'] else 0
            
        report_data.append({
            "Company": company_name,
            "Step": "1. Gemini Quick Search",
            "Duration (s)": round(quick_duration, 2),
            "Logic / Processing Method": "LLM Extract Core Name & Contact",
            "Input": f"Full Name: {company_name}",
            "Output": f"Core: {core_name} | Core VI: {core_name_vi}",
            "Score / Decision": quick_logs[0]['status'] if quick_logs else "N/A",
            "Details": quick_logs[0]['metadata_json'] if quick_logs else "",
            "Pipeline Status": pipeline_status
        })
        
        # Deep Search Logs to aggregate duration
        search_logs = db.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? AND step = 'serper_search'", (cid,))
        total_search_duration = sum([log['duration_seconds'] for log in search_logs if log['duration_seconds']])
        
        # Deep Search & Filter (URLs)
        search_res = db.fetch_all("SELECT * FROM search_results WHERE company_id = ?", (cid,))
        
        for sr in search_res:
            url = sr['url']
            filter_row = db.fetch_one("SELECT * FROM filtered_links WHERE company_id = ? AND url = ?", (cid, url))
            
            score = 0
            decision = "Unknown"
            if filter_row:
                score = filter_row['relevance_score']
                decision = filter_row['reason']
                
            report_data.append({
                "Company": company_name,
                "Step": "2 & 3. Deep Search & Filter",
                "Duration (s)": round(total_search_duration, 2) if total_search_duration > 0 else 0, # Total serper search time mapped to rows
                "Logic / Processing Method": f"Search Query: {sr['search_query']}",
                "Input": f"Query: {sr['search_query']}",
                "Output": url,
                "Score / Decision": f"Score: {score} | {decision}",
                "Details": sr['title'],
                "Pipeline Status": pipeline_status
            })
            
            # Scrape info
            scrape_row = db.fetch_one("SELECT * FROM scraped_pages WHERE company_id = ? AND url = ?", (cid, url))
            if scrape_row:
                scrape_logs = db.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? AND step = 'scrape' AND source_url = ? ORDER BY id DESC LIMIT 1", (cid, url))
                scrape_duration = scrape_logs[0]['duration_seconds'] if scrape_logs and scrape_logs[0]['duration_seconds'] else 0
                
                report_data.append({
                    "Company": company_name,
                    "Step": "4. Web Scraping",
                    "Duration (s)": round(scrape_duration, 2),
                    "Logic / Processing Method": "Firecrawl Scrape",
                    "Input": url,
                    "Output": f"Content Length: {scrape_row['content_length']}",
                    "Score / Decision": scrape_row['scrape_status'],
                    "Details": scrape_row['error_message'] or "Success",
                    "Pipeline Status": pipeline_status
                })
                
                # AI Extract info
                extract_row = db.fetch_one("SELECT * FROM extracted_contacts WHERE company_id = ? AND scraped_page_id = ?", (cid, scrape_row['id']))
                if extract_row:
                    extract_logs = db.fetch_all("SELECT * FROM pipeline_logs WHERE company_id = ? AND step = 'ai_extract' ORDER BY id DESC LIMIT 1", (cid,))
                    extract_duration = extract_logs[0]['duration_seconds'] if extract_logs and extract_logs[0]['duration_seconds'] else 0
                    
                    report_data.append({
                        "Company": company_name,
                        "Step": "5. AI Extraction (OpenRouter)",
                        "Duration (s)": round(extract_duration, 2),
                        "Logic / Processing Method": "OpenRouter LLM Extract",
                        "Input": f"Scraped Page ID: {scrape_row['id']}",
                        "Output": f"Phone: {extract_row['phone']} | Email: {extract_row['email']}",
                        "Score / Decision": f"Confidence: {extract_row['confidence_score']}",
                        "Details": f"Address: {extract_row['address']}",
                        "Pipeline Status": pipeline_status
                    })
    
    # Save to Excel
    out_df = pd.DataFrame(report_data)
    out_name = f"live_test_{timestamp}.xlsx"
    out_path = os.path.join(PROJECT_ROOT, "results", "report", out_name)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        out_df.to_excel(writer, index=False, sheet_name='Live Test')
        
    print(f"\nDetailed Live Test report saved to: {out_path}")

if __name__ == "__main__":
    main()
