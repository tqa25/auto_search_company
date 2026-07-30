import os
import sys
import types as py_types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "google.genai" not in sys.modules:
    google_module = sys.modules.setdefault("google", py_types.ModuleType("google"))
    genai_module = py_types.ModuleType("google.genai")
    genai_types_module = py_types.ModuleType("google.genai.types")
    genai_module.Client = MagicMock()
    genai_types_module.GenerateContentConfig = MagicMock()
    genai_module.types = genai_types_module
    google_module.genai = genai_module
    sys.modules["google.genai"] = genai_module
    sys.modules["google.genai.types"] = genai_types_module

from src.database import DatabaseManager
from src.pipeline import Pipeline


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_company_run.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()
    return db


@pytest.fixture
def pipeline_config():
    return {
        "firecrawl_api_key": "test_key",
        "gemini_api_key": None,
        "delay_seconds": 0.0,
        "output_dir": "output",
    }


def _make_pipeline_with_db(test_db, config):
    with patch("src.pipeline.DatabaseManager", return_value=test_db):
        with patch("src.pipeline.PipelineLogger") as MockLogger:
            mock_logger = MockLogger.return_value
            mock_logger.get_last_processed_company_id.return_value = 0
            mock_logger.log_step_start.return_value = 1
            with patch("src.pipeline.SearchModule"):
                with patch("src.pipeline.LinkFilter"):
                    with patch("src.pipeline.ScrapeModule"):
                        with patch("src.pipeline.ExcelReader"):
                            with patch("src.pipeline.ExcelWriter"):
                                with patch("src.pipeline.ResultAggregator"):
                                    with patch("src.pipeline.GeminiQuickSearch"):
                                        with patch("src.pipeline.FirecrawlDeepSearch"):
                                            pipeline = Pipeline(config)
                                            pipeline.db = test_db
                                            pipeline.logger = mock_logger
                                            return pipeline


def _seed_strict_completion_data(test_db, company_id):
    search_result_id = test_db.execute_query(
        "INSERT INTO search_results (company_id, search_query, url) VALUES (?, ?, ?)",
        (company_id, "test query", "https://example.com"),
    )
    filtered_link_id = test_db.insert_filtered_link(
        search_result_id=search_result_id,
        company_id=company_id,
        url="https://example.com",
        source_type="official_website",
        should_scrape=True,
        reason="test",
    )
    scraped_page_id = test_db.insert_scraped_page(
        filtered_link_id=filtered_link_id,
        company_id=company_id,
        url="https://example.com",
        source_type="official_website",
        markdown_content="ok",
        content_length=2,
        scrape_status="success",
        credits_used=1,
        error_message=None,
    )
    test_db.execute_query(
        "INSERT INTO extracted_contacts (company_id, scraped_page_id, source_type, phone) VALUES (?, ?, ?, ?)",
        (company_id, scraped_page_id, "official_website", "0123456789"),
    )


def test_run_company_processes_one_pending_company_through_public_interface(test_db, pipeline_config):
    company_id = test_db.insert_company("Test Corp", status="pending")
    _seed_strict_completion_data(test_db, company_id)
    pipeline = _make_pipeline_with_db(test_db, pipeline_config)

    pipeline.gemini_quick.search = MagicMock(return_value={})
    pipeline.filter_module.filter_company_links = MagicMock()
    pipeline.scrape_module.scrape_company = MagicMock()

    pipeline.run_company(company_id)

    assert test_db.get_company(company_id)["status"] == "done"
    pipeline.gemini_quick.search.assert_called_once_with(company_id)
    pipeline.filter_module.filter_company_links.assert_called_once_with(company_id)
    pipeline.scrape_module.scrape_company.assert_called_once()


def test_batch_run_delegates_each_company_to_company_run_interface(test_db, pipeline_config):
    company_id = test_db.insert_company("Delegated Corp", status="pending")
    pipeline = _make_pipeline_with_db(test_db, pipeline_config)
    pipeline.company_run.run = MagicMock(return_value={"outcome": "skipped"})

    pipeline.run(company_ids=[company_id])

    pipeline.company_run.run.assert_called_once_with(
        company_id,
        replay_mode=False,
        force_refresh=False,
        job_controller=None,
    )


class SequencedJobController:
    def __init__(self, should_stop_results):
        self.should_stop_results = list(should_stop_results)
        self.updates = []

    def should_stop(self, company_id):
        if self.should_stop_results:
            return self.should_stop_results.pop(0)
        return False

    def update(self, company_id, status, current_step=None, checkpoint=None, progress=None):
        self.updates.append({
            "company_id": company_id,
            "status": status,
            "current_step": current_step,
            "checkpoint": checkpoint,
            "progress": progress,
        })


def test_run_company_resumes_from_searched_status_without_gemini_quick(test_db, pipeline_config):
    company_id = test_db.insert_company("Resume Corp", status="searched")
    _seed_strict_completion_data(test_db, company_id)
    pipeline = _make_pipeline_with_db(test_db, pipeline_config)

    pipeline.gemini_quick.search = MagicMock()
    pipeline.filter_module.filter_company_links = MagicMock()
    pipeline.scrape_module.scrape_company = MagicMock()

    result = pipeline.run_company(company_id)

    assert result["outcome"] == "success"
    pipeline.gemini_quick.search.assert_not_called()
    pipeline.filter_module.filter_company_links.assert_called_once_with(company_id)
    pipeline.scrape_module.scrape_company.assert_called_once()
    assert test_db.get_company(company_id)["status"] == "done"


def test_run_company_replay_mode_skips_api_steps(test_db, pipeline_config):
    company_id = test_db.insert_company("Replay Corp", status="scraped")
    _seed_strict_completion_data(test_db, company_id)
    pipeline = _make_pipeline_with_db(test_db, pipeline_config)

    pipeline.gemini_quick.search = MagicMock()
    pipeline.search_module.search_company = MagicMock()
    pipeline.filter_module.filter_company_links = MagicMock()
    pipeline.scrape_module.scrape_company = MagicMock()

    result = pipeline.run_company(company_id, replay_mode=True)

    assert result["outcome"] == "success"
    pipeline.gemini_quick.search.assert_not_called()
    pipeline.search_module.search_company.assert_not_called()
    pipeline.filter_module.filter_company_links.assert_not_called()
    pipeline.scrape_module.scrape_company.assert_not_called()
    assert test_db.get_company(company_id)["status"] == "done"


def test_run_company_force_refresh_is_scoped_to_interface_call(test_db, pipeline_config):
    company_id = test_db.insert_company("Refresh Corp", status="pending")
    _seed_strict_completion_data(test_db, company_id)
    pipeline = _make_pipeline_with_db(test_db, pipeline_config)

    observed = []

    def quick_search(_company_id):
        observed.append(pipeline.cfg.FORCE_REFRESH)
        return {}

    pipeline.gemini_quick.search = MagicMock(side_effect=quick_search)
    pipeline.filter_module.filter_company_links = MagicMock()
    pipeline.scrape_module.scrape_company = MagicMock()

    result = pipeline.run_company(company_id, force_refresh=True)

    assert result["outcome"] == "success"
    assert observed == [True]
    assert pipeline.cfg.FORCE_REFRESH is False


def test_run_company_observes_stop_requests_at_safe_points(test_db, pipeline_config):
    company_id = test_db.insert_company("Stop Corp", status="pending")
    pipeline = _make_pipeline_with_db(test_db, pipeline_config)
    controller = SequencedJobController([False, False, True])

    pipeline.gemini_quick.search = MagicMock(return_value={})
    pipeline.search_module.search_company = MagicMock()

    result = pipeline.run_company(company_id, job_controller=controller)

    assert result["outcome"] == "stopped"
    assert result["reason"] == "after_gemini_quick"
    pipeline.search_module.search_company.assert_not_called()
    assert test_db.get_company(company_id)["status"] == "gemini_quick_done"
    assert controller.updates[-1]["checkpoint"] == "deep_search"
