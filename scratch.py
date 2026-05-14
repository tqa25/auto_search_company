import sys
import os
sys.path.append(os.getcwd())
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.search_module import SearchModule
from src.config import default_config

db = DatabaseManager("data/test_scratch.db")
logger = PipelineLogger(db)
search = SearchModule(db, logger)
search.config.EARLY_STOP_COUNT = 2
search.config.EARLY_STOP_SCORE = 40

results = [
    {"url": "https://www.testcorp.com/about", "title": "Title for https://www.testcorp.com/about"},
    {"url": "https://www.topcv.vn/cong-ty/test-corp", "title": "Title for topcv"},
    {"url": "https://www.vietnamworks.com/cong-ty/test-corp", "title": "Title for vietnamworks"},
    {"url": "https://www.vietcareer.vn/cong-ty/test-corp", "title": "Title for vietcareer"},
    {"url": "https://www.hosocongty.vn/test-corp", "title": "Title for hoso"}
]
count = search._count_qualified("Test Corp Ltd", results)
print("Count:", count)

scored = search.filter_module.score_urls_batch(results, "Test Corp Ltd")
for s in scored:
    print(s["url"], s["relevance_score"])

