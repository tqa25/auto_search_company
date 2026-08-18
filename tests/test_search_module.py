"""
Test suite for src/search_module.py — SearchModule.

All external API calls (Firecrawl) are mocked to avoid consuming credits.
Uses a real temporary SQLite database to verify DB interactions end-to-end.
"""

import os
import sys
import json
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.search_module import (
    SearchModule,
    FirecrawlCreditExhausted,
    FirecrawlSearchError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Create a temporary directory for each test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)

@pytest.fixture
def db(tmp_dir):
    """Create a fresh DatabaseManager with an in-memory-like temp DB."""
    db_path = os.path.join(tmp_dir, "data", "test.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()
    return db

@pytest.fixture
def pipeline_logger(db):
    """Create a PipelineLogger backed by the test DB."""
    return PipelineLogger(db)

@pytest.fixture
def search_module(db, pipeline_logger):
    """Create a SearchModule with fake API keys."""
    return SearchModule(
        db=db,
        pipeline_logger=pipeline_logger,
        firecrawl_api_key="fc-test-key-12345",
        gemini_api_key="gemini-test-key-12345",
    )

def _make_firecrawl_response(urls, status_code=200):
    """Helper: build a mock requests.Response for Firecrawl."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if status_code == 200:
        data = []
        for i, url in enumerate(urls):
            data.append({
                "url": url,
                "title": f"Title for {url}",
                "description": f"Công ty TNHH XYZ - Mã số thuế: 0123456789" if "masothue.com" in url else f"Snippet for {url}",
            })
        mock_resp.json.return_value = {"success": True, "data": data}
    else:
        mock_resp.text = f"Error {status_code}"
        mock_resp.json.return_value = {}
    return mock_resp

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchCompanySingleStrategy:
    """Test search_company with the 3+1 architecture."""

    @patch("src.search_module.requests.post")
    def test_search_stops_early_step1(self, mock_post, search_module, db):
        """Step 1 (Anchor) finds enough good links to early stop."""
        cid = db.insert_company("Test Corp Ltd")

        # Mocking anchor search to return multiple good official/vietnamworks links
        # that will score high.
        # Wait, the score calculation happens in filter_module.
        # If it returns 3 non-blacklisted results, it might not early stop if score is < 3.
        # But for test simplicity, if _step1_anchor gets results and filter scores them,
        # we can mock or just see what happens.
        # Override config to ensure early stop triggers deterministically
        search_module.config.EARLY_STOP_COUNT = 2
        search_module.config.EARLY_STOP_SCORE = 40

        # English search returns high quality links
        mock_post.return_value = _make_firecrawl_response([
            "https://www.testcorp.com/about", # score ~ 1.5
            "https://www.topcv.vn/cong-ty/test-corp", # score ~ 1.0
            "https://www.vietnamworks.com/cong-ty/test-corp", # score ~ 1.0
            "https://www.vietcareer.vn/cong-ty/test-corp", # score ~ 1.0
            "https://www.test-corp.vn", # score 55.0
        ])

        results = search_module.search_company(cid)

        # Only one search should be made (Anchor)
        assert mock_post.call_count == 1
        assert len(results) > 0
        assert results[0]["search_type"] == "step1_contact"

    @patch("src.search_module.requests.post")
    def test_search_infer_vn_data(self, mock_post, search_module, db):
        """Step 1 (Anchor) finds masothue.com link, extracts VN name, then Step 3 Expand is run."""
        cid = db.insert_company("Unknown Corp JSC")

        # First call: Step 1 (Anchor) returns a masothue.com link.
        # Since it's blacklisted, score=0, so it won't early stop.
        # Step 2 will infer the Vietnamese name "Công ty TNHH XYZ"
        # Step 3 (Expand) runs with the Vietnamese name.
        
        # Provide enough responses for retries (each call may retry up to 3 times)
        mock_post.side_effect = [
            _make_firecrawl_response(["https://masothue.com/abc"]),  # Step 1 success
            _make_firecrawl_response(["https://masothue.com/abc"]),  # retry 1 (not used)
            _make_firecrawl_response(["https://masothue.com/abc"]),  # retry 2 (not used)
            _make_firecrawl_response(["https://vietnamworks.com/xyz"]), # Step 3 success
            _make_firecrawl_response(["https://vietnamworks.com/xyz"]), # retry 1 (not used)
            _make_firecrawl_response(["https://vietnamworks.com/xyz"]), # retry 2 (not used)
        ]

        results = search_module.search_company(cid)
        
        # Check that VN name was extracted and saved
        company = db.get_company(cid)
        assert company["vietnamese_name"] == "Công ty TNHH XYZ"

        # Check search types
        types = [r["search_type"] for r in results]
        assert "step1_contact" in types
        assert "step3_tax" in types
        
    @patch("src.search_module.requests.post")
    def test_search_falls_through_to_fallback(self, mock_post, search_module, db):
        """Step 1 fails, Step 2 fails, Step 3 skipped, Step 4 runs."""
        cid = db.insert_company("Empty Corp")

        # First call: Step 1 returns junk links -> score = 0 -> no early stop
        # Step 2 fails (no masothue, no thuvienphapluat)
        # Step 3 skipped because no vn_name
        # Step 4 runs (fallback with bare name)
        
        mock_post.side_effect = [
            _make_firecrawl_response(["https://randomsite.com/junk"]), # Step 1
            _make_firecrawl_response(["https://example.com/fallback"]) # Step 4
        ]

        results = search_module.search_company(cid)

        # Check search types
        types = [r["search_type"] for r in results]
        assert "step1_contact" in types
        assert "step4_bare" in types

class TestSearchBatch:
    """Test search_batch processing."""

    @patch("src.search_module.requests.post")
    @patch("src.search_module.time.sleep")  # Skip real delays in tests
    def test_batch_success(self, mock_sleep, mock_post, search_module, db):
        cids = []
        for name in ["Company A", "Company B", "Company C"]:
            cids.append(db.insert_company(name))

        # Each company gets one anchor search, we mock it returning topcv links
        mock_post.return_value = _make_firecrawl_response([
            "https://www.topcv.vn/cong-ty/abc",
            "https://www.vietnamworks.com/cong-ty/abc"
        ])

        summary = search_module.search_batch(cids, delay_seconds=0.01)

        assert summary["success"] == 3
        assert summary["failed"] == 0

class TestErrorHandling:
    """Test HTTP error handling in _firecrawl_search."""

    @patch("src.search_module.requests.post")
    @patch("src.search_module.time.sleep")
    def test_429_rate_limit_retry(self, mock_sleep, mock_post, search_module):
        mock_post.side_effect = [
            _make_firecrawl_response([], status_code=429),
            _make_firecrawl_response(["https://example.com/ok"]),
        ]

        results = search_module._firecrawl_search("test query")
        assert len(results) == 1
        assert mock_post.call_count == 2

    @patch("src.search_module.requests.post")
    def test_402_credit_exhausted(self, mock_post, search_module):
        from src.errors import CriticalError
        mock_post.return_value = _make_firecrawl_response([], status_code=402)
        with pytest.raises(CriticalError):
            search_module._firecrawl_search("test query")

    @patch("src.search_module.requests.post")
    def test_500_server_error(self, mock_post, search_module):
        from src.errors import RetryableError
        mock_post.return_value = _make_firecrawl_response([], status_code=500)
        with pytest.raises(RetryableError):
            search_module._firecrawl_search("test query")

class TestSearchStats:
    """Test get_search_stats aggregation."""

    @patch("src.search_module.requests.post")
    def test_stats_after_searches(self, mock_post, search_module, db):
        cid1 = db.insert_company("Company Alpha")
        cid2 = db.insert_company("Company Beta")

        mock_post.return_value = _make_firecrawl_response([
            "https://masothue.com/alpha",
            "https://example.com/alpha",
        ])

        search_module.search_company(cid1)
        search_module.search_company(cid2)

        stats = search_module.get_search_stats()
        assert stats["total_searched"] == 2
        assert stats["total_results"] >= 2

class TestQueryCacheIsolation:
    """A global query-cache hit must not return empty results for a company that
    did not originate the cache entry — the origin company's results are copied."""

    def test_cache_hit_copies_results_to_other_company(self, search_module, db):
        from src.time_utils import vn_cache_expiry

        search_module.config.ENABLE_QUERY_DEDUP = True
        search_module.config.FORCE_REFRESH = False

        cid_a = db.insert_company("Origin Corp")
        cid_b = db.insert_company("Second Corp")
        query = "shared query text"

        # Simulate company A having already searched this query: persisted results
        # (as search_company would save) plus the global query-cache entry.
        db.insert_search_result(cid_a, query, "firecrawl_search", 1, "https://example.com/a", "A", "sa", 0)
        db.insert_search_result(cid_a, query, "firecrawl_search", 2, "https://example.com/b", "B", "sb", 0)
        db.insert_query_cache(
            query_hash=search_module._normalize_and_hash(query),
            query_text=query,
            company_id=cid_a,
            expires_at=vn_cache_expiry(search_module.config.CACHE_TTL_DAYS),
            result_count=2,
        )

        # Company B hits the (global) cache; the live API must NOT be called, yet B
        # must still receive non-empty results (copied from A).
        with patch.object(search_module, "_firecrawl_search") as mock_live_b:
            results_b, hit_b = search_module._search_with_dedup(query, cid_b)
        assert hit_b is True
        assert mock_live_b.call_count == 0
        assert len(results_b) == 2
        # And they are now persisted under company B for the downstream filter step.
        rows_b = db.fetch_all(
            "SELECT url FROM search_results WHERE company_id = ? AND search_query = ?",
            (cid_b, query),
        )
        assert {r["url"] for r in rows_b} == {"https://example.com/a", "https://example.com/b"}

    def test_cache_hit_with_no_persisted_results_falls_through_to_live(self, search_module, db):
        """If the cache flag exists but no results survive anywhere, do a live search
        instead of returning empty."""
        from src.time_utils import vn_cache_expiry

        search_module.config.ENABLE_QUERY_DEDUP = True
        search_module.config.FORCE_REFRESH = False
        cid = db.insert_company("Lonely Corp")
        query = "orphaned cache query"
        db.insert_query_cache(
            query_hash=search_module._normalize_and_hash(query),
            query_text=query,
            company_id=cid,
            expires_at=vn_cache_expiry(search_module.config.CACHE_TTL_DAYS),
            result_count=0,
        )
        fake = [{"url": "https://example.com/live", "title": "L", "snippet": "s"}]
        with patch.object(search_module, "_firecrawl_search", return_value=fake) as mock_live:
            results, hit = search_module._search_with_dedup(query, cid)
        assert hit is False
        assert mock_live.call_count == 1
        assert results == fake


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
