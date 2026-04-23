"""
Tests for Pipeline resume logic, checkpoint progression, graceful shutdown, and retry_failed.
"""

import os
import sys
import signal
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.pipeline import Pipeline


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database."""
    db_path = str(tmp_path / "test_resume.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()
    return db


@pytest.fixture
def pipeline_config(test_db):
    """Create a pipeline config pointing to the test database."""
    return {
        "firecrawl_api_key": "test_key",
        "gemini_api_key": None,  # No AI extraction for unit tests
        "delay_seconds": 0.0,    # No delay for tests
        "output_dir": "output",
    }


def _make_pipeline_with_db(test_db, config):
    """Create a Pipeline instance that uses our test DB instead of the default."""
    with patch('src.pipeline.DatabaseManager', return_value=test_db):
        with patch('src.pipeline.PipelineLogger') as MockLogger:
            mock_logger = MockLogger.return_value
            mock_logger.get_last_processed_company_id.return_value = 0
            mock_logger.log_step_start.return_value = 1
            with patch('src.pipeline.SearchModule'):
                with patch('src.pipeline.LinkFilter'):
                    with patch('src.pipeline.ScrapeModule'):
                        with patch('src.pipeline.ExcelReader'):
                            with patch('src.pipeline.ExcelWriter'):
                                with patch('src.pipeline.ResultAggregator'):
                                    pipeline = Pipeline(config)
                                    pipeline.db = test_db
                                    pipeline.logger = mock_logger
                                    return pipeline


# ------------------------------------------------------------------
# Test: _get_next_step
# ------------------------------------------------------------------

class TestGetNextStep:
    def test_pending_starts_at_search(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('pending') == 'search'

    def test_searched_starts_at_filter(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('searched') == 'filter'

    def test_scraped_starts_at_ai_extract(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('scraped') == 'ai_extract'

    def test_failed_starts_at_search(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('failed') == 'search'

    def test_searching_interrupted_restarts_search(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('searching') == 'search'

    def test_scraping_interrupted_restarts_filter(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('scraping') == 'filter'

    def test_extracting_interrupted_restarts_ai_extract(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._get_next_step('extracting') == 'ai_extract'


# ------------------------------------------------------------------
# Test: _should_do_step
# ------------------------------------------------------------------

class TestShouldDoStep:
    def test_search_from_search(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._should_do_step('search', 'search') is True

    def test_filter_from_search(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._should_do_step('search', 'filter') is True

    def test_search_from_filter(self, test_db, pipeline_config):
        """If next_step is filter, we should NOT do search."""
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._should_do_step('filter', 'search') is False

    def test_scrape_from_filter(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._should_do_step('filter', 'scrape') is True

    def test_search_from_ai_extract(self, test_db, pipeline_config):
        """If next_step is ai_extract, skip search/filter/scrape."""
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._should_do_step('ai_extract', 'search') is False
        assert pipeline._should_do_step('ai_extract', 'filter') is False
        assert pipeline._should_do_step('ai_extract', 'scrape') is False
        assert pipeline._should_do_step('ai_extract', 'ai_extract') is True


# ------------------------------------------------------------------
# Test: get_resumable_companies
# ------------------------------------------------------------------

class TestGetResumableCompanies:
    def test_empty_db_returns_empty(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert result == []

    def test_done_companies_excluded(self, test_db, pipeline_config):
        test_db.insert_company("Done Corp", status="done")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert len(result) == 0

    def test_permanently_failed_excluded(self, test_db, pipeline_config):
        test_db.insert_company("Perm Failed Corp", status="permanently_failed")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert len(result) == 0

    def test_pending_included(self, test_db, pipeline_config):
        test_db.insert_company("Pending Corp", status="pending")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert len(result) == 1
        assert result[0]['status'] == 'pending'
        assert result[0]['next_step'] == 'search'

    def test_searched_included_with_correct_next_step(self, test_db, pipeline_config):
        test_db.insert_company("Searched Corp", status="searched")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert len(result) == 1
        assert result[0]['status'] == 'searched'
        assert result[0]['next_step'] == 'filter'

    def test_scraped_included_with_correct_next_step(self, test_db, pipeline_config):
        test_db.insert_company("Scraped Corp", status="scraped")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert len(result) == 1
        assert result[0]['status'] == 'scraped'
        assert result[0]['next_step'] == 'ai_extract'

    def test_failed_included(self, test_db, pipeline_config):
        test_db.insert_company("Failed Corp", status="failed")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()
        assert len(result) == 1
        assert result[0]['status'] == 'failed'
        assert result[0]['next_step'] == 'search'

    def test_mixed_statuses(self, test_db, pipeline_config):
        """Multiple companies with different statuses."""
        test_db.insert_company("Done Corp", status="done")
        test_db.insert_company("Pending Corp", status="pending")
        test_db.insert_company("Searched Corp", status="searched")
        test_db.insert_company("Failed Corp", status="failed")
        test_db.insert_company("Perm Failed Corp", status="permanently_failed")

        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        result = pipeline.get_resumable_companies()

        # Should only include pending, searched, failed (3 companies)
        assert len(result) == 3
        statuses = {r['status'] for r in result}
        assert statuses == {'pending', 'searched', 'failed'}


# ------------------------------------------------------------------
# Test: Checkpoint progression in run()
# ------------------------------------------------------------------

class TestCheckpointProgression:
    def test_full_pipeline_sets_done(self, test_db, pipeline_config):
        """A company going through all steps should end with status='done'."""
        cid = test_db.insert_company("Test Corp", status="pending")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)

        # Mock all pipeline steps to succeed (they are already mocked via _make_pipeline_with_db)
        pipeline.search_module.search_company = MagicMock()
        pipeline.filter_module.filter_company_links = MagicMock()
        pipeline.scrape_module.scrape_company = MagicMock()
        # No AI extractor (gemini_api_key is None)

        pipeline.run(company_ids=[cid])

        company = test_db.get_company(cid)
        assert company['status'] == 'done'

    def test_search_failure_sets_failed(self, test_db, pipeline_config):
        """If search fails, company should be marked as 'failed'."""
        cid = test_db.insert_company("Fail Corp", status="pending")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)

        pipeline.search_module.search_company = MagicMock(side_effect=Exception("Search error"))

        pipeline.run(company_ids=[cid])

        company = test_db.get_company(cid)
        assert company['status'] == 'failed'

    def test_resume_skips_completed_steps(self, test_db, pipeline_config):
        """A company with status='searched' should skip the search step."""
        cid = test_db.insert_company("Searched Corp", status="searched")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)

        pipeline.search_module.search_company = MagicMock()
        pipeline.filter_module.filter_company_links = MagicMock()
        pipeline.scrape_module.scrape_company = MagicMock()

        pipeline.run(company_ids=[cid])

        # Search should NOT have been called (already searched)
        pipeline.search_module.search_company.assert_not_called()
        # But filter and scrape should have been called
        pipeline.filter_module.filter_company_links.assert_called_once_with(cid)
        pipeline.scrape_module.scrape_company.assert_called_once()

    def test_resume_scraped_only_does_ai_extract(self, test_db, pipeline_config):
        """A company with status='scraped' should only do AI extraction."""
        cid = test_db.insert_company("Scraped Corp", status="scraped")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)

        pipeline.search_module.search_company = MagicMock()
        pipeline.filter_module.filter_company_links = MagicMock()
        pipeline.scrape_module.scrape_company = MagicMock()

        pipeline.run(company_ids=[cid])

        # None of search/filter/scrape should be called
        pipeline.search_module.search_company.assert_not_called()
        pipeline.filter_module.filter_company_links.assert_not_called()
        pipeline.scrape_module.scrape_company.assert_not_called()

        # Status should be 'done' (no AI extractor configured)
        company = test_db.get_company(cid)
        assert company['status'] == 'done'

    def test_done_company_is_skipped(self, test_db, pipeline_config):
        """A company with status='done' should be completely skipped."""
        cid = test_db.insert_company("Done Corp", status="done")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)

        pipeline.search_module.search_company = MagicMock()

        pipeline.run(company_ids=[cid])

        pipeline.search_module.search_company.assert_not_called()


# ------------------------------------------------------------------
# Test: Graceful shutdown
# ------------------------------------------------------------------

class TestGracefulShutdown:
    def test_shutdown_flag_initially_false(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        assert pipeline._shutdown_requested is False

    def test_signal_handler_sets_flag(self, test_db, pipeline_config):
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        # Simulate receiving SIGINT
        pipeline._signal_handler(signal.SIGINT, None)
        assert pipeline._shutdown_requested is True

    def test_shutdown_stops_after_current_company(self, test_db, pipeline_config):
        """When shutdown is requested, pipeline should stop after the current company."""
        cid1 = test_db.insert_company("Corp 1", status="pending")
        cid2 = test_db.insert_company("Corp 2", status="pending")
        cid3 = test_db.insert_company("Corp 3", status="pending")

        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        pipeline.search_module.search_company = MagicMock()
        pipeline.filter_module.filter_company_links = MagicMock()
        pipeline.scrape_module.scrape_company = MagicMock()

        call_count = 0
        def search_side_effect(company_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # After first company, request shutdown
                pipeline._shutdown_requested = True

        pipeline.search_module.search_company.side_effect = search_side_effect

        pipeline.run(company_ids=[cid1, cid2, cid3])

        # Only 1 company should have been searched (first one completes, then shutdown)
        assert call_count == 1

        # First company should be done
        c1 = test_db.get_company(cid1)
        assert c1['status'] == 'done'

        # Second and third should still be pending
        c2 = test_db.get_company(cid2)
        assert c2['status'] == 'pending'
        c3 = test_db.get_company(cid3)
        assert c3['status'] == 'pending'


# ------------------------------------------------------------------
# Test: retry_failed
# ------------------------------------------------------------------

class TestRetryFailed:
    def test_no_failed_companies(self, test_db, pipeline_config):
        """If there are no failed companies, retry_failed does nothing."""
        test_db.insert_company("Good Corp", status="done")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        pipeline.search_module.search_company = MagicMock()

        pipeline.retry_failed()
        pipeline.search_module.search_company.assert_not_called()

    def test_retry_resets_status_to_pending(self, test_db, pipeline_config):
        """Failed companies should be reset to pending for retry."""
        cid = test_db.insert_company("Failed Corp", status="failed")
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)

        pipeline.search_module.search_company = MagicMock()
        pipeline.filter_module.filter_company_links = MagicMock()
        pipeline.scrape_module.scrape_company = MagicMock()

        pipeline.retry_failed(max_retries=2)

        # Company should have been processed (reset to pending then run)
        company = test_db.get_company(cid)
        assert company['status'] == 'done'


# ------------------------------------------------------------------
# Test: STATUS_FLOW mapping
# ------------------------------------------------------------------

class TestStatusFlow:
    def test_all_status_flow_entries(self, test_db, pipeline_config):
        """Verify STATUS_FLOW covers all expected intermediate statuses."""
        pipeline = _make_pipeline_with_db(test_db, pipeline_config)
        expected_statuses = ['pending', 'searching', 'searched', 'scraping', 'scraped', 'extracting', 'failed']
        for status in expected_statuses:
            assert status in pipeline.STATUS_FLOW, f"STATUS_FLOW missing entry for '{status}'"
