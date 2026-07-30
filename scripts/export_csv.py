import os
import sys

# Thêm đường dẫn root vào sys.path để import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.time_utils import vn_filename_timestamp

def main():
    db = DatabaseManager("data/company_data.db")
    logger = PipelineLogger(db)
    
    timestamp = vn_filename_timestamp()
    output_path = f"output/exported_data_{timestamp}.csv"
    
    print(f"Exporting data to {output_path}...")
    logger.export_data_to_csv(output_path)
    print("Done!")

if __name__ == "__main__":
    main()
