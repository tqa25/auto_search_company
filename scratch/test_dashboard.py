
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.health_monitor import HealthMonitor

db = DatabaseManager()
logger = PipelineLogger(db)
monitor = HealthMonitor(db, logger)
monitor.print_dashboard()
