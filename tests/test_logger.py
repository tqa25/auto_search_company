import os
import sqlite3
import pytest
from src.database import DatabaseManager
from src.logger import PipelineLogger

@pytest.fixture
def db_manager():
    db_path = "data/test_logger.db"
    
    # Ensure cleanup before start
    if os.path.exists(db_path):
        os.remove(db_path)
        
    db = DatabaseManager(db_path)
    db.init_db()
    
    # insert dummy company
    db.insert_company(original_name="Test Company")
    
    yield db
    
    # cleanup after test
    if os.path.exists(db_path):
        os.remove(db_path)

def test_pipeline_logger(db_manager, caplog):
    logger = PipelineLogger(db_manager)
    
    # Test log_step_start
    log_id = logger.log_step_start(company_id=1, step='SEARCH', source_url="https://google.com")
    assert log_id > 0
    
    # Check DB
    log_record = db_manager.fetch_one("SELECT * FROM pipeline_logs WHERE id=?", (log_id,))
    assert log_record['status'] == 'started'
    assert log_record['step'] == 'SEARCH'
    
    # Test log_step_end
    metadata = {'links_found': 10}
    logger.log_step_end(log_id, 'SUCCESS', credits_used=2.5, metadata=metadata)
    
    # Check DB updated
    log_record = db_manager.fetch_one("SELECT * FROM pipeline_logs WHERE id=?", (log_id,))
    assert log_record['status'] == 'SUCCESS'
    assert log_record['credits_used'] == 2.5
    assert 'links_found' in log_record['metadata_json']
    assert log_record['duration_seconds'] >= 0
    
    # Test format check
    assert any("SUCCESS" in record.message for record in caplog.records)
    
    # Test daily summary
    summary = logger.get_daily_summary()
    assert summary['total_processed_all'] == 1
    assert summary['total_processed_today'] == 1
    assert summary['total_companies'] == 1
    assert summary['total_credits_used'] == 2.5
    
    # Test get last processed company id
    last_id = logger.get_last_processed_company_id()
    assert last_id == 1
    
    # Test exports
    csv_path = "logs/test_log.csv"
    excel_path = "logs/test_summary.xlsx"
    
    logger.export_log_to_csv(csv_path)
    assert os.path.exists(csv_path)
    
    logger.export_summary_to_excel(excel_path)
    assert os.path.exists(excel_path)
    
    # Cleanup dummy files
    if os.path.exists(csv_path): os.remove(csv_path)
    if os.path.exists(excel_path): os.remove(excel_path)
    if os.path.exists("logs"): os.rmdir("logs")
