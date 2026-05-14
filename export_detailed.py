import sqlite3
import csv
import json

def export_detailed_csv():
    db_path = "data/company_data.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    target_ids = (23, 30, 42, 45, 67)
    id_str = ",".join(map(str, target_ids))
    
    output_file = "DETAILED_PIPELINE_URLS_2026-05-12.csv"
    
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["Company ID", "Company Name", "Pipeline Step", "URL", "Extra Info"])
        
        # Get Company Names map
        cursor.execute(f"SELECT id, original_name FROM companies WHERE id IN ({id_str})")
        names = {r['id']: r['original_name'] for r in cursor.fetchall()}
        
        # 1. Gemini Grounding URLs
        cursor.execute(f"SELECT company_id, grounding_sources_json FROM gemini_quick_results WHERE company_id IN ({id_str})")
        for row in cursor.fetchall():
            try:
                urls = json.loads(row['grounding_sources_json'])
                for url in urls:
                    writer.writerow([row['company_id'], names.get(row['company_id']), "Gemini Grounding", url, "Grounding Ref"])
            except: pass
            
        # 2. Serper / Search Results
        cursor.execute(f"SELECT company_id, url, title, search_type FROM search_results WHERE company_id IN ({id_str})")
        for row in cursor.fetchall():
            writer.writerow([row['company_id'], names.get(row['company_id']), f"Search ({row['search_type']})", row['url'], row['title']])
            
        # 3. Filtered Links
        cursor.execute(f"SELECT company_id, url, source_type, relevance_score FROM filtered_links WHERE company_id IN ({id_str})")
        for row in cursor.fetchall():
            writer.writerow([row['company_id'], names.get(row['company_id']), "Filtered Link", row['url'], f"Score: {row['relevance_score']}"])
            
    print(f"Exported to {output_file}")
    conn.close()

if __name__ == "__main__":
    export_detailed_csv()
