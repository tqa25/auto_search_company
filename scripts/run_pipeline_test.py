import os
import sqlite3
import pandas as pd
from openpyxl import load_workbook
import time
from datetime import datetime
import json
import logging

from src.database import DatabaseManager
from src.pipeline import Pipeline
from src.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

INPUT_EXCEL = "input_db_excel-05-13.xlsx"

def setup_db_for_test(db_path="data/company_data.db"):
    db = DatabaseManager(db_path)
    
    # Read top 10 from excel
    try:
        df = pd.read_excel(INPUT_EXCEL)
        top_10 = df.head(10).to_dict(orient='records')
    except Exception as e:
        logger.error(f"Error reading Excel: {e}")
        return []

    company_ids = []
    
    for row in top_10:
        # Assuming the column header is ' COMPANY NAME' based on previous inspection
        name = row.get(' COMPANY NAME', '') or row.get('COMPANY NAME', '')
        if not name:
            name = list(row.values())[0] # Fallback to first column
        
        # Check if exists in DB
        existing = db.fetch_one("SELECT id FROM companies WHERE original_name = ?", (name,))
        if existing:
            comp_id = existing['id']
            # Reset status and clean previous results
            db.execute_query("UPDATE companies SET status='pending', vietnamese_name=NULL, tax_code=NULL, address=NULL WHERE id=?", (comp_id,))
            db.execute_query("DELETE FROM search_results WHERE company_id=?", (comp_id,))
            db.execute_query("DELETE FROM filtered_links WHERE company_id=?", (comp_id,))
            db.execute_query("DELETE FROM extracted_contacts WHERE company_id=?", (comp_id,))
            db.execute_query("DELETE FROM pipeline_logs WHERE company_id=?", (comp_id,))
            # Scraped pages delete is skipped for simplicity but can be joined if needed
            company_ids.append((comp_id, name))
        else:
            db.execute_query("INSERT INTO companies (original_name, status) VALUES (?, 'pending')", (name,))
            comp_id = db.fetch_one("SELECT last_insert_rowid() as id")['id']
            company_ids.append((comp_id, name))
            
    return company_ids

def get_pipeline_log_for_step(db, comp_id, step_name):
    query = "SELECT * FROM pipeline_logs WHERE company_id=? AND step=? ORDER BY id DESC LIMIT 1"
    return db.fetch_one(query, (comp_id, step_name))

def get_all_search_results(db, comp_id):
    query = """
    SELECT sr.*, fl.source_type, fl.relevance_score, fl.should_scrape, fl.reason,
           sp.scrape_status, sp.content_length, sp.credits_used as scrape_credits,
           ec.phone as extracted_phone, ec.email as extracted_email, 
           ec.address as extracted_address, ec.website as extracted_website, ec.confidence_score as ai_confidence
    FROM search_results sr
    LEFT JOIN filtered_links fl ON sr.id = fl.search_result_id
    LEFT JOIN scraped_pages sp ON fl.id = sp.filtered_link_id
    LEFT JOIN extracted_contacts ec ON sp.id = ec.scraped_page_id
    WHERE sr.company_id=?
    ORDER BY sr.id ASC
    """
    return db.fetch_all(query, (comp_id,))

def run_test():
    logger.info("Setting up database for 10 companies...")
    db = DatabaseManager("data/company_data.db")
    companies = setup_db_for_test()
    
    if not companies:
        logger.error("No companies found to process.")
        return

    logger.info(f"Loaded {len(companies)} companies. Starting pipeline...")
    
    # Run pipeline
    pipeline = Pipeline(config={})
    
    # We want to run them sequentially and log
    for comp_id, name in companies:
        logger.info(f"Processing company ID {comp_id}: {name}")
        pipeline.run([comp_id])

    logger.info("Pipeline execution finished. Collecting provenance data...")
    
    # Generate Report Data
    summary_data = []
    url_details_data = []
    
    for comp_id, name in companies:
        comp_info = db.get_company(comp_id)
        
        # Step 1: Gemini Quick
        step1_log = get_pipeline_log_for_step(db, comp_id, 'gemini_quick')
        s1_meta = json.loads(step1_log['metadata_json']) if step1_log and step1_log['metadata_json'] else {}
        s1_status = step1_log['status'] if step1_log else "skipped"
        if step1_log and step1_log['error_message'] and '429' in step1_log['error_message']:
            s1_status = "quota_exhausted"
            
        # Step 2: Serper Places
        step2_log = get_pipeline_log_for_step(db, comp_id, 'google_maps')
        s2_meta = json.loads(step2_log['metadata_json']) if step2_log and step2_log['metadata_json'] else {}
        s2_req = s2_meta.get('raw_request', {})
        
        # Determine sources
        vn_name_source = "gemini_grounding" if comp_info.get('vietnamese_name') and s1_status == 'sufficient' else "snippet_or_other"
        tax_source = "gemini_grounding" if comp_info.get('tax_code') and s1_status == 'sufficient' else "snippet_or_other"
        if not comp_info.get('vietnamese_name'): vn_name_source = "not_found"
        if not comp_info.get('tax_code'): tax_source = "not_found"
        
        # Final Contact Output
        final_contact = db.fetch_one("SELECT * FROM extracted_contacts WHERE company_id=? ORDER BY id ASC LIMIT 1", (comp_id,))
        phone_source = final_contact['source_type'] if final_contact else "not_found"
        
        summary_row = {
            "Company Name (EN)": name,
            "Vietnamese Name": comp_info.get('vietnamese_name', ''),
            "VN Name Source": vn_name_source,
            "Tax Code": comp_info.get('tax_code', ''),
            "Tax Code Source": tax_source,
            
            "Final Phone": final_contact['phone'] if final_contact else "",
            "Phone Source": phone_source,
            "Final Address": final_contact['address'] if final_contact else "",
            "Final Website": final_contact['website'] if final_contact else "",
            "Final Email": final_contact['email'] if final_contact else "",
            
            "Step1 Timestamp": step1_log['started_at'] if step1_log else "",
            "Step1 Status": s1_status,
            "Step1 Confidence": s1_meta.get('confidence', ''),
            "Step1 Sources": str(s1_meta.get('grounding_sources_count', 0)) + " URLs",
            
            "Step2 Timestamp": step2_log['started_at'] if step2_log else "",
            "Step2 Query": s2_req.get('query', ''),
            "Step2 Places Count": s2_meta.get('results_count', 0),
            "Step2 Best Match": "Checked" if step2_log else "",
            "Step2 Phone": "Yes" if s2_meta.get('has_phone') else "No",
            "Step2 Status": step2_log['status'] if step2_log else "skipped",
            
            "Final Status": comp_info.get('status', ''),
            "Total Duration (s)": (step1_log['duration_seconds'] if step1_log and step1_log['duration_seconds'] else 0) + \
                                  (step2_log['duration_seconds'] if step2_log and step2_log['duration_seconds'] else 0)
        }
        summary_data.append(summary_row)
        
        # URL Details
        urls = get_all_search_results(db, comp_id)
        for u in urls:
            url_details_data.append({
                "Company Name": name,
                "URL": u['url'],
                "Title": u['title'],
                "Search Step": u['search_type'],
                "Search Query": u['search_query'],
                "Result Rank": u['result_rank'],
                
                "Source Type": u['source_type'] or "unknown",
                "Total Score": u['relevance_score'] or 0.0,
                "Should Scrape": bool(u['should_scrape']),
                "Score Reason": u['reason'] or "",
                
                "Scrape Status": u['scrape_status'] or "not_scraped",
                "Content Length": u['content_length'] or 0,
                "Scrape Credits": u['scrape_credits'] or 0.0,
                
                "Extracted Phone": u['extracted_phone'] or "",
                "Extracted Email": u['extracted_email'] or "",
                "Extracted Address": u['extracted_address'] or "",
                "AI Confidence": u['ai_confidence'] or ""
            })
            
    # Write to Excel
    logger.info("Writing results to Excel...")
    try:
        with pd.ExcelWriter(INPUT_EXCEL, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Pipeline Summary', index=False)
            
            df_urls = pd.DataFrame(url_details_data)
            df_urls.to_excel(writer, sheet_name='URL Details', index=False)
            
        logger.info(f"Successfully appended sheets to {INPUT_EXCEL}")
    except Exception as e:
        logger.error(f"Failed to append to {INPUT_EXCEL}: {e}")
        # Fallback to new file if the original is locked
        fallback_name = f"results/report/pipeline_test_fallback.xlsx"
        os.makedirs("results/report", exist_ok=True)
        with pd.ExcelWriter(fallback_name, engine='openpyxl') as writer:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Pipeline Summary', index=False)
            
            df_urls = pd.DataFrame(url_details_data)
            df_urls.to_excel(writer, sheet_name='URL Details', index=False)
        logger.info(f"Saved to fallback file: {fallback_name}")

if __name__ == "__main__":
    run_test()
