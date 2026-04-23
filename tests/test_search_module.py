"""
Test suite for src/search_module.py — SearchModule.

All external API calls (Firecrawl, Gemini) are mocked to avoid consuming credits.
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
                "description": f"Snippet for {url}",
            })
        mock_resp.json.return_value = {"success": True, "data": data}
    else:
        mock_resp.text = f"Error {status_code}"
        mock_resp.json.return_value = {}
    return mock_resp


def _make_gemini_response(translated_name, status_code=200):
    """Helper: build a mock requests.Response for Gemini."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if status_code == 200:
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": translated_name}]
                }
            }]
        }
    else:
        mock_resp.text = f"Gemini error {status_code}"
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchCompanySingleStrategy:
    """Test search_company with various company configurations."""

    @patch("src.search_module.requests.post")
    def test_search_with_tax_code(self, mock_post, search_module, db):
        """① Tax code search + ② English search should both execute."""
        # Insert company with tax code
        cid = db.insert_company("Test Corp Ltd", tax_code="0123456789")

        # First call = tax_code search, second = english search
        mock_post.side_effect = [
            _make_firecrawl_response(["https://masothue.com/0123456789"]),
            _make_firecrawl_response(["https://example.com/test-corp"]),
        ]

        results = search_module.search_company(cid)

        assert len(results) == 2
        assert mock_post.call_count == 2  # tax_code + english

        # Verify DB records
        db_results = db.get_search_results_for_company(cid)
        assert len(db_results) == 2
        types = {r["search_type"] for r in db_results}
        assert "tax_code" in types
        assert "english" in types

        # Company status should be 'searched'
        company = db.get_company(cid)
        assert company["status"] == "searched"

    @patch("src.search_module.requests.post")
    def test_search_without_tax_code(self, mock_post, search_module, db):
        """Without tax code, only ② English search runs. If key target found, skip ③."""
        cid = db.insert_company("ABC Software Co., Ltd")

        # English search returns a masothue link → skip Vietnamese
        mock_post.return_value = _make_firecrawl_response([
            "https://masothue.com/abc-software",
            "https://example.com/abc",
        ])

        results = search_module.search_company(cid)

        assert len(results) == 2
        assert mock_post.call_count == 1  # Only english search
        assert results[0]["search_type"] == "english"

    @patch("src.search_module.requests.post")
    def test_search_falls_through_to_vietnamese(self, mock_post, search_module, db):
        """If ② has no key target domains, ③ Vietnamese search should trigger."""
        cid = db.insert_company("Unknown Corp JSC")

        # English search: no key target domains
        firecrawl_resp_en = _make_firecrawl_response([
            "https://randomsite.com/page1",
        ])
        # Gemini translation
        gemini_resp = _make_gemini_response("Công ty Cổ phần Unknown")
        # Vietnamese search via Firecrawl
        firecrawl_resp_vn = _make_firecrawl_response([
            "https://thuvienphapluat.vn/cong-ty/unknown",
        ])

        mock_post.side_effect = [firecrawl_resp_en, gemini_resp, firecrawl_resp_vn]

        results = search_module.search_company(cid)

        assert len(results) == 2  # 1 from english + 1 from vietnamese
        assert mock_post.call_count == 3  # firecrawl(en) + gemini + firecrawl(vn)

        # Vietnamese name should be saved
        company = db.get_company(cid)
        assert company["vietnamese_name"] == "Công ty Cổ phần Unknown"

        # Check search types
        types = [r["search_type"] for r in results]
        assert "english" in types
        assert "vietnamese" in types


class TestSearchBatch:
    """Test search_batch processing."""

    @patch("src.search_module.requests.post")
    @patch("src.search_module.time.sleep")  # Skip real delays in tests
    def test_batch_success(self, mock_sleep, mock_post, search_module, db):
        """Batch should process multiple companies sequentially."""
        cids = []
        for name in ["Company A", "Company B", "Company C"]:
            cids.append(db.insert_company(name))

        # Each company gets one english search that hits masothue (skip VN)
        mock_post.return_value = _make_firecrawl_response([
            "https://masothue.com/result",
        ])

        summary = search_module.search_batch(cids, delay_seconds=0.01)

        assert summary["success"] == 3
        assert summary["failed"] == 0
        assert summary["total_results_saved"] == 3

    @patch("src.search_module.requests.post")
    @patch("src.search_module.time.sleep")
    def test_batch_stops_on_credit_exhaustion(self, mock_sleep, mock_post, search_module, db):
        """Batch should stop immediately when credits are exhausted."""
        cids = [
            db.insert_company("Company A"),
            db.insert_company("Company B"),
        ]

        mock_post.return_value = _make_firecrawl_response([], status_code=402)

        summary = search_module.search_batch(cids, delay_seconds=0.01)

        assert summary["failed"] >= 1
        # Second company should not have been attempted (or also fails)
        assert summary["success"] == 0

    @patch("src.search_module.requests.post")
    @patch("src.search_module.time.sleep")
    def test_batch_continues_on_single_failure(self, mock_sleep, mock_post, search_module, db):
        """If one company's search fails (non-402), batch continues with the next.

        Note: search_company catches non-402 errors internally and still
        returns (with 0 results). The batch considers it a 'success' because
        no exception propagated. Company A gets 0 results but doesn't crash
        the batch; Company B gets real results.
        """
        cids = [
            db.insert_company("Company A"),
            db.insert_company("Company B"),
        ]

        # Company A: english search → 500, then Gemini translation fails,
        #            search_company catches everything internally → 0 results
        # Company B: english search → success with key target → 1 result
        mock_post.side_effect = [
            _make_firecrawl_response([], status_code=500),               # A english → fail
            _make_gemini_response("", status_code=500),                   # A gemini → fail
            _make_firecrawl_response(["https://masothue.com/b"]),         # B english → ok
        ]

        summary = search_module.search_batch(cids, delay_seconds=0.01)

        # Both companies are processed (no propagated exception)
        assert summary["success"] == 2
        assert summary["failed"] == 0
        # Company A contributed 0 results, Company B contributed 1
        assert summary["total_results_saved"] == 1


class TestErrorHandling:
    """Test HTTP error handling in _firecrawl_search."""

    @patch("src.search_module.requests.post")
    @patch("src.search_module.time.sleep")
    def test_429_rate_limit_retry(self, mock_sleep, mock_post, search_module):
        """Should retry on 429, then succeed."""
        mock_post.side_effect = [
            _make_firecrawl_response([], status_code=429),
            _make_firecrawl_response(["https://example.com/ok"]),
        ]

        results = search_module._firecrawl_search("test query")

        assert len(results) == 1
        assert mock_post.call_count == 2

    @patch("src.search_module.requests.post")
    def test_402_credit_exhausted(self, mock_post, search_module):
        """Should raise FirecrawlCreditExhausted on 402."""
        mock_post.return_value = _make_firecrawl_response([], status_code=402)

        with pytest.raises(FirecrawlCreditExhausted):
            search_module._firecrawl_search("test query")

    @patch("src.search_module.requests.post")
    def test_500_server_error(self, mock_post, search_module):
        """Should raise FirecrawlSearchError on 500."""
        mock_post.return_value = _make_firecrawl_response([], status_code=500)

        with pytest.raises(FirecrawlSearchError):
            search_module._firecrawl_search("test query")


class TestSearchStats:
    """Test get_search_stats aggregation."""

    @patch("src.search_module.requests.post")
    def test_stats_after_searches(self, mock_post, search_module, db):
        """Stats should reflect the data inserted."""
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
        assert stats["total_results"] >= 4  # At least 2 per company
        assert stats["avg_results_per_company"] >= 2.0
        assert "english" in stats["search_type_distribution"]
        assert stats["credits_used_total"] > 0


class TestGeminiTranslation:
    """Test the _translate_to_vietnamese helper."""

    @patch("src.search_module.requests.post")
    def test_translation_success(self, mock_post, search_module):
        """Should return the Vietnamese name from Gemini."""
        mock_post.return_value = _make_gemini_response("Công ty TNHH ABC")

        result = search_module._translate_to_vietnamese("ABC Co., Ltd")
        assert result == "Công ty TNHH ABC"

    @patch("src.search_module.requests.post")
    def test_translation_api_error(self, mock_post, search_module):
        """Should return None on Gemini API error."""
        mock_post.return_value = _make_gemini_response("", status_code=500)

        result = search_module._translate_to_vietnamese("ABC Co., Ltd")
        assert result is None

    def test_translation_no_api_key(self, db, pipeline_logger):
        """Should return None when no Gemini API key is provided."""
        sm = SearchModule(db, pipeline_logger, firecrawl_api_key="fc-key", gemini_api_key="")
        result = sm._translate_to_vietnamese("ABC Co., Ltd")
        assert result is None


class TestKeyTargetHit:
    """Test the _has_key_target_hit helper."""

    def test_hit_masothue(self, search_module):
        results = [{"url": "https://masothue.com/company/xyz"}]
        assert search_module._has_key_target_hit(results) is True

    def test_hit_thuvienphapluat(self, search_module):
        results = [{"url": "https://thuvienphapluat.vn/cong-ty/abc"}]
        assert search_module._has_key_target_hit(results) is True

    def test_no_hit(self, search_module):
        results = [
            {"url": "https://example.com/page1"},
            {"url": "https://linkedin.com/company/abc"},
        ]
        assert search_module._has_key_target_hit(results) is False

    def test_empty_results(self, search_module):
        assert search_module._has_key_target_hit([]) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
