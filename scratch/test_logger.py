
from src.logger import PipelineLogger
from src.database import DatabaseManager
import os

db = DatabaseManager("data/test_debug.db")
db.init_db()

logger = PipelineLogger(db, log_dir="output/logs")

log_id = logger.log_step_start(
    company_id=999,
    step="debug_test",
    raw_request={"test": "data"}
)

logger.log_step_end(
    log_id=log_id,
    status="success",
    network_latency_ms=123.45,
    raw_response_summary={"res": "ok"}
)

print("Test log entry created.")
