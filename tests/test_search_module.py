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
                "description": f"Công ty TNHH XYZ" if "masothue.com" in url else f"Snippet for {url}",
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
        assert results[0]["search_type"] == "step1_anchor"

    @patch("src.search_module.requests.post")
    def test_search_infer_vn_data(self, mock_post, search_module, db):
        """Step 1 (Anchor) finds masothue.com link, extracts VN name, then Step 3 Expand is run."""
        cid = db.insert_company("Unknown Corp JSC")

        # First call: Step 1 (Anchor) returns a masothue.com link.
        # Since it's blacklisted, score=0, so it won't early stop.
        # Step 2 will infer the Vietnamese name "Công ty TNHH XYZ"
        # Step 3 (Expand) runs with the Vietnamese name.
        
        mock_post.side_effect = [
            _make_firecrawl_response(["https://masothue.com/abc"]), # Step 1: masothue link -> infers "Công ty TNHH XYZ"
            _make_firecrawl_response(["https://vietnamworks.com/xyz"]) # Step 3: Expand search with VN name
        ]

        results = search_module.search_company(cid)
        
        # Check that VN name was extracted and saved
        company = db.get_company(cid)
        assert company["vietnamese_name"] == "Công ty TNHH XYZ"

        # Check search types
        types = [r["search_type"] for r in results]
        assert "step1_anchor" in types
        assert "step3_expand" in types
        
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
        assert "step1_anchor" in types
        assert "step4_fallback_en" in types

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
        mock_post.return_value = _make_firecrawl_response([], status_code=500)
        with pytest.raises(FirecrawlSearchError):
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

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
