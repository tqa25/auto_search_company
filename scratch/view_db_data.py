import sqlite3
import os

def format_row(row, headers):
    formatted = []
    for val in row:
        s = str(val)
        if len(s) > 30:
            s = s[:27] + "..."
        formatted.append(s.ljust(30))
    return "| " + " | ".join(formatted) + " |"

def view_data(db_path="data/company_data.db"):
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n--- Summary of Database Tables ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        print(f"- {table['name']}")

    def print_table(title, query):
        print(f"\n--- {title} ---")
        cursor.execute(query)
        rows = cursor.fetchall()
        if not rows:
            print("No data found.")
            return
        
        headers = rows[0].keys()
        header_line = "| " + " | ".join([h.ljust(30) for h in headers]) + " |"
        print(header_line)
        print("|" + "-" * (len(header_line) - 2) + "|")
        
        for row in rows:
            print(format_row(row, headers))

    print_table("Last 10 Companies", "SELECT id, original_name, tax_code, status, created_at FROM companies ORDER BY id DESC LIMIT 10")
    
    print_table("Last 10 Extracted Contacts", """
        SELECT c.original_name, ec.email, ec.phone, ec.address, ec.website
        FROM extracted_contacts ec
        JOIN companies c ON ec.company_id = c.id
        ORDER BY ec.id DESC
        LIMIT 10
    """)

    print_table("Last 10 Search Results", """
        SELECT c.original_name, sr.url, sr.search_type
        FROM search_results sr
        JOIN companies c ON sr.company_id = c.id
        ORDER BY sr.id DESC
        LIMIT 10
    """)

    conn.close()

if __name__ == "__main__":
    view_data()
