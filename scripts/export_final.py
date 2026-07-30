import os
import sys

# Thêm đường dẫn root vào sys.path để import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import DatabaseManager
from src.excel_handler import ExcelWriter
from src.time_utils import vn_filename_timestamp

def main():
    db_path = "data/company_data.db"
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
        
    db = DatabaseManager(db_path)
    
    timestamp = vn_filename_timestamp()
    output_path = f"output/final_results_{timestamp}.xlsx"
    
    print(f"Bắt đầu xuất dữ liệu tổng hợp ra file Excel...")
    print(f"Đường dẫn lưu file: {output_path}")
    
    try:
        writer = ExcelWriter()
        writer.write_consolidated_report(db, output_path)
        print(f"\n🎉 Xuất file Excel thành công!")
        print(f"File kết quả cuối đã sẵn sàng tại: {output_path}")
    except Exception as e:
        print(f"\n❌ Đã xảy ra lỗi khi xuất file Excel: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
