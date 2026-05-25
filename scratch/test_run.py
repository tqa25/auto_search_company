import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from dashboard.app import _pipeline_config
from src.pipeline import Pipeline
from dashboard.app import MonitorDatabase
from dashboard.app import DB_PATH

try:
    p = Pipeline(_pipeline_config())
    monitor_db = MonitorDatabase(DB_PATH)
    p.db = monitor_db
    p.logger.db = monitor_db
    p.run(company_ids=[5])
except Exception as e:
    import traceback
    traceback.print_exc()
