import sqlite3

def report_companies(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM companies ORDER BY id ASC;")
    companies = [dict(row) for row in cursor.fetchall()]
    
    print(f"Total companies in database: {len(companies)}")
    for c in companies:
        # Check logs for this company
        cursor.execute("SELECT step, status, error_message FROM pipeline_logs WHERE company_id = ? ORDER BY id DESC LIMIT 1;", (c['id'],))
        last_log = cursor.fetchone()
        last_log_str = ""
        if last_log:
            last_log_str = f" | Last Log: Step={last_log['step']}, Status={last_log['status']}, Error={last_log['error_message']}"
            
        print(f"ID: {c['id']:2d} | Original Name: {c['original_name']} | VN Name: {c['vietnamese_name']} | Tax Code: {c['tax_code']} | Status: {c['status']}{last_log_str}")
        
    conn.close()

if __name__ == "__main__":
    report_companies("data/company_data.db")
