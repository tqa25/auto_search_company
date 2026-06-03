from dashboard.app import _db
from src.excel_handler import ExcelWriter
db = _db()
writer = ExcelWriter()
writer.write_consolidated_report(db, 'test_export.xlsx', company_ids=[1, 2])
print("Done")
