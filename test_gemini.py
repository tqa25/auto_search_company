import sys
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.config import Config
from src.gemini_quick_search import GeminiQuickSearch

db = DatabaseManager()
cfg = Config()
logger = PipelineLogger(db)
gqs = GeminiQuickSearch(db, logger, config=cfg)
print("Starting search...")
result = gqs.search(45)
print(result)
