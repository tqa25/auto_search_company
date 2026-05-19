"""Quick verification: Overmatch Penalty logic in filter_module."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.filter_module import LinkFilter

# Setup with temp DB
import tempfile
db_path = os.path.join(tempfile.gettempdir(), "test_overmatch.db")
db = DatabaseManager(db_path)
logger = PipelineLogger(db)
lf = LinkFilter(db, logger)

# Test cases
test_cases = [
    # (url, company_name, title, expected_behavior)
    ("https://pointgrey.vn/contact/", "point grey", "Liên hệ - Point Grey", "SHOULD PASS (exact match)"),
    ("https://westpointgrey.org/contact/", "point grey", "West Point Grey", "SHOULD be PENALIZED (overmatch)"),
    ("https://masothue.com/0317955111-point-grey", "point grey", "Point Grey MST", "SHOULD PASS (known domain)"),
    ("https://kinfreit.com.vn/lien-he/", "kinfreit", "Kinfreit liên hệ", "SHOULD PASS (exact match)"),
    ("https://example-kinfreit-global.com/", "kinfreit", "Kinfreit Global", "SHOULD be PENALIZED (overmatch)"),
]

print("=" * 80)
print("OVERMATCH PENALTY VERIFICATION")
print("=" * 80)

for url, company_name, title, expected in test_cases:
    result = lf.classify_url(url, company_name, title=title)
    score = result["relevance_score"]
    should_scrape = result["should_scrape"]
    reason = result["reason"]
    breakdown = result["score_breakdown"]
    
    print(f"\n  URL: {url}")
    print(f"  Company: {company_name}")
    print(f"  Expected: {expected}")
    print(f"  Score: {score:.1f} | Scrape: {should_scrape}")
    print(f"  Breakdown: domain={breakdown['domain']}, keyword={breakdown['keyword']}, name_match={breakdown['name_match']:.1f}")
    print(f"  Reason: {reason}")

print("\n" + "=" * 80)
print("DONE")
