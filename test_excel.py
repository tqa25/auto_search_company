import sys
import os
import glob
from src.database import DatabaseManager
from src.result_aggregator import ResultAggregator
from src.excel_handler import ExcelWriter

# Find the latest DB in data/
db_files = glob.glob("data/*.db")
if not db_files:
    print("No DB found")
    sys.exit(1)
latest_db = max(db_files, key=os.path.getctime)
print(f"Using DB: {latest_db}")

db = DatabaseManager(latest_db)
agg = ResultAggregator(db)
all_data = agg.aggregate_all()
stats = agg.generate_summary_stats(all_data)

writer = ExcelWriter()
writer.write_final_report("test_report.xlsx", all_data, stats)
print("Saved test_report.xlsx")
