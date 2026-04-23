"""
Tests for HealthMonitor — system health monitoring, credit tracking, and dashboard.
"""

import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.health_monitor import HealthMonitor


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary test database with schema."""
    db_path = str(tmp_path / "test_health.db")
    db = DatabaseManager(db_path=db_path)
    db.init_db()
    return db


@pytest.fixture
def health_monitor(test_db):
    """Create a HealthMonitor with the test database."""
    logger = PipelineLogger(test_db)
    return HealthMonitor(test_db, logger)


# ------------------------------------------------------------------
# Test: check_credits_remaining
# ------------------------------------------------------------------

class TestCheckCreditsRemaining:
    def test_empty_db_returns_zero_credits(self, health_monitor):
        result = health_monitor.check_credits_remaining()
        assert result['total_credits_used'] == 0.0
        assert result['search_credits_used'] == 0.0
        assert result['scrape_credits_used'] == 0.0

    def test_credits_from_search_results(self, test_db, health_monitor):
        """Credits from search_results table are counted."""
        cid = test_db.insert_company("Test Corp")
        test_db.insert_search_result(cid, "test query", "english", 1, "http://example.com", "Test", "snippet", credits_used=2.0)
        test_db.insert_search_result(cid, "test query 2", "vietnamese", 1, "http://example2.com", "Test2", "snippet2", credits_used=2.0)

        result = health_monitor.check_credits_remaining()
        assert result['search_credits_used'] == 4.0
        assert result['total_credits_used'] == 4.0

    def test_credits_from_scraped_pages(self, test_db, health_monitor):
        """Credits from scraped_pages table are counted."""
        cid = test_db.insert_company("Test Corp")
        test_db.insert_scraped_page(1, cid, "http://example.com", "masothue", "content", 100, "success", credits_used=1.0)
        test_db.insert_scraped_page(2, cid, "http://example2.com", "topcv", "content2", 200, "success", credits_used=1.0)

        result = health_monitor.check_credits_remaining()
        assert result['scrape_credits_used'] == 2.0

    def test_combined_credits(self, test_db, health_monitor):
        """Total credits are the sum of search + scrape credits."""
        cid = test_db.insert_company("Test Corp")
        test_db.insert_search_result(cid, "q", "english", 1, "http://a.com", "T", "s", credits_used=4.0)
        test_db.insert_scraped_page(1, cid, "http://b.com", "masothue", "c", 100, "success", credits_used=3.0)

        result = health_monitor.check_credits_remaining()
        assert result['total_credits_used'] == 7.0

    def test_free_plan_detection(self, health_monitor):
        """Empty DB should map to Free plan."""
        result = health_monitor.check_credits_remaining()
        assert result['estimated_plan'] == "Free"

    def test_warning_at_high_usage(self, test_db, health_monitor):
        """Should generate warning when usage exceeds 75%."""
        cid = test_db.insert_company("Test Corp")
        # Free plan = 500 credits. Insert 400 credits worth.
        for i in range(200):
            test_db.insert_search_result(cid, f"q{i}", "english", 1, f"http://{i}.com", "T", "s", credits_used=2.0)

        result = health_monitor.check_credits_remaining()
        assert result['total_credits_used'] == 400.0
        assert len(result['warnings']) > 0


# ------------------------------------------------------------------
# Test: estimate_completion_time
# ------------------------------------------------------------------

class TestEstimateCompletionTime:
    def test_zero_remaining(self, health_monitor):
        result = health_monitor.estimate_completion_time(0)
        assert result['remaining_companies'] == 0
        assert result['estimated_hours'] == 0.0
        assert result['estimated_credits_needed'] == 0

    def test_with_remaining_companies(self, health_monitor):
        result = health_monitor.estimate_completion_time(100)
        assert result['remaining_companies'] == 100
        assert result['estimated_hours'] > 0
        assert result['estimated_credits_needed'] > 0

    def test_uses_actual_data_for_estimation(self, test_db, health_monitor):
        """When there's actual pipeline data, estimates should use real averages."""
        cid = test_db.insert_company("Test Corp")
        # Insert some pipeline logs with duration
        import datetime
        started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_db.insert_pipeline_log(
            cid, "search", "success",
            started_at=started,
            finished_at=started,
            duration_seconds=10.0,
            credits_used=4.0
        )

        result = health_monitor.estimate_completion_time(100)
        assert result['remaining_companies'] == 100
        # With actual data, the avg should be based on real duration
        assert result['avg_seconds_per_company'] > 0


# ------------------------------------------------------------------
# Test: get_system_status
# ------------------------------------------------------------------

class TestGetSystemStatus:
    def test_empty_db(self, health_monitor):
        result = health_monitor.get_system_status()
        assert result['total_companies'] == 0
        assert result['completed'] == 0
        assert result['failed'] == 0
        assert result['pending'] == 0

    def test_mixed_statuses(self, test_db, health_monitor):
        """System status correctly counts different company statuses."""
        test_db.insert_company("Done Corp", status="done")
        test_db.insert_company("Done Corp 2", status="done")
        test_db.insert_company("Failed Corp", status="failed")
        test_db.insert_company("Pending Corp", status="pending")
        test_db.insert_company("Perm Failed Corp", status="permanently_failed")

        result = health_monitor.get_system_status()
        assert result['total_companies'] == 5
        assert result['completed'] == 2
        assert result['failed'] == 1
        assert result['permanently_failed'] == 1
        assert result['pending'] == 1

    def test_progress_percent(self, test_db, health_monitor):
        """Progress percentage calculated correctly."""
        test_db.insert_company("Done Corp", status="done")
        test_db.insert_company("Pending Corp", status="pending")

        result = health_monitor.get_system_status()
        assert result['progress_percent'] == 50.0

    def test_all_done(self, test_db, health_monitor):
        """100% progress when all companies are done."""
        test_db.insert_company("Done 1", status="done")
        test_db.insert_company("Done 2", status="done")

        result = health_monitor.get_system_status()
        assert result['progress_percent'] == 100.0
        assert result['completed'] == 2
        assert result['pending'] == 0

    def test_credit_sufficient_flag(self, test_db, health_monitor):
        """credit_sufficient should be True when enough credits remain."""
        test_db.insert_company("Pending Corp", status="pending")
        result = health_monitor.get_system_status()
        # Free plan has 500 credits, 1 company needs ~5 credits → sufficient
        assert result['credit_sufficient'] is True


# ------------------------------------------------------------------
# Test: print_dashboard (smoke test — just ensure it doesn't crash)
# ------------------------------------------------------------------

class TestPrintDashboard:
    def test_print_dashboard_no_crash_empty_db(self, health_monitor, capsys):
        """Dashboard should print without errors even on empty DB."""
        health_monitor.print_dashboard()
        captured = capsys.readouterr()
        assert "PIPELINE HEALTH DASHBOARD" in captured.out

    def test_print_dashboard_with_data(self, test_db, health_monitor, capsys):
        """Dashboard should print with data without errors."""
        test_db.insert_company("Done Corp", status="done")
        test_db.insert_company("Pending Corp", status="pending")
        test_db.insert_company("Failed Corp", status="failed")

        health_monitor.print_dashboard()
        captured = capsys.readouterr()
        assert "PIPELINE HEALTH DASHBOARD" in captured.out
        assert "TIẾN ĐỘ" in captured.out
        assert "TÍN DỤNG" in captured.out
        assert "ƯỚC TÍNH" in captured.out
