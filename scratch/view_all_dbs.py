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

def view_data(db_path):
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    print(f"\n===== Viewing Database: {db_path} =====")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        table_name = table['name']
        if table_name == 'sqlite_sequence': continue
        
        print(f"\n--- Table: {table_name} (Last 5 rows) ---")
        try:
            cursor.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT 5")
            rows = cursor.fetchall()
            if not rows:
                print("No data found.")
                continue
            
            headers = rows[0].keys()
            header_line = "| " + " | ".join([h.ljust(30) for h in headers]) + " |"
            print(header_line)
            print("|" + "-" * (len(header_line) - 2) + "|")
            
            for row in rows:
                print(format_row(row, headers))
        except Exception as e:
            print(f"Error reading table {table_name}: {e}")

    conn.close()

if __name__ == "__main__":
    view_data("data/company_data.db")
    view_data("data/companies.db")
    view_data("data/integration_test.db")
