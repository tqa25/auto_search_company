import os
import unittest
import asyncio
import json
from datetime import timedelta
from unittest.mock import patch

os.environ["DB_PATH"] = "data/test_dashboard_company_data.db"
os.environ["DASHBOARD_PASS"] = ""

import dashboard.app as dashboard_app
from src.database import DatabaseManager
from src.time_utils import vn_now, vn_timestamp


class FakeJsonRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


class TestDashboardImportFilters(unittest.TestCase):
    DB_PATH = "data/test_dashboard_company_data.db"

    def setUp(self):
        for suffix in ("", "-wal", "-shm"):
            path = f"{self.DB_PATH}{suffix}"
            if os.path.exists(path):
                os.remove(path)
        self.db = DatabaseManager(self.DB_PATH)
        self.db.init_db()
        dashboard_app.DB_PATH = os.path.abspath(self.DB_PATH)
        dashboard_app._pipeline_running = False
        dashboard_app._active_pipeline = None

    def tearDown(self):
        self.db.close()
        for suffix in ("", "-wal", "-shm"):
            path = f"{self.DB_PATH}{suffix}"
            if os.path.exists(path):
                os.remove(path)

    def test_import_returns_batch_and_filters_by_batch_and_search(self):
        response = asyncio.run(
            dashboard_app.api_import(
                FakeJsonRequest({
                "source_filename": "companies.csv",
                "names": ["HCM Logistics", "Da Nang Trading", " hcm   logistics "],
                })
            )
        )
        self.assertEqual(response.status_code, 200)
        payload = response_json(response)

        self.assertEqual(payload["imported"], 2)
        self.assertEqual(payload["skipped"], 1)
        self.assertIsNotNone(payload["batch_id"])

        companies = response_json(dashboard_app.api_spa_companies(
            import_batch_id=payload["batch_id"],
            search="hcm",
            import_outcome="imported",
        ))["companies"]
        self.assertEqual([c["name"] for c in companies], ["HCM Logistics"])

        ids_payload = response_json(dashboard_app.api_spa_company_ids(
            import_batch_id=payload["batch_id"],
            search="hcm",
            import_outcome="imported",
        ))
        self.assertEqual(ids_payload["count"], 1)
        self.assertEqual(len(ids_payload["company_ids"]), 1)

    def test_import_records_ambiguous_name_only_items_in_batch_view(self):
        existing_id = self.db.insert_company(r"LOCK & LOCK VINA")
        self.db.update_company(existing_id, status="done")
        before_total = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

        response = asyncio.run(
            dashboard_app.api_import(
                FakeJsonRequest({
                    "source_filename": "companies.md",
                    "names": [r"LOCK \& LOCK VINA", "New Import Co", "New Import Co", "  "],
                })
            )
        )
        payload = response_json(response)
        after_total = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

        self.assertEqual(payload["imported"], 1)
        self.assertEqual(payload["summary"]["ambiguous"], 1)
        self.assertEqual(payload["summary"]["duplicate_in_file"], 1)
        self.assertEqual(payload["summary"]["invalid"], 1)
        self.assertEqual(after_total, before_total + 1)

        batch_payload = response_json(dashboard_app.api_spa_companies(
            import_batch_id=payload["batch_id"],
        ))
        rows = batch_payload["companies"]
        ambiguous = next(row for row in rows if row["outcome"] == "ambiguous")

        self.assertEqual(len(rows), 4)
        self.assertIsNone(ambiguous["id"])
        self.assertIsNone(ambiguous["matched_company_id"])
        self.assertEqual(ambiguous["display_status"], "Cần kiểm tra")
        self.assertEqual(ambiguous["pipeline_status"], "not_created")
        self.assertEqual(ambiguous["normalized_key"], "lock & lock vina")

        ambiguous_ids = response_json(dashboard_app.api_spa_company_ids(
            import_batch_id=payload["batch_id"],
            import_outcome="ambiguous",
        ))
        self.assertEqual(ambiguous_ids["company_ids"], [])

    def test_import_matches_existing_company_by_tax_code(self):
        existing_id = self.db.insert_company("LOCK & LOCK VINA", tax_code="0123456789")
        self.db.update_company(existing_id, status="done")
        before_total = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

        response = asyncio.run(
            dashboard_app.api_import(
                FakeJsonRequest({
                    "source_filename": "companies.csv",
                    "companies": [{"name": r"LOCK \& LOCK VINA", "tax_code": "0123456789"}],
                })
            )
        )
        payload = response_json(response)
        after_total = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

        self.assertEqual(payload["imported"], 0)
        self.assertEqual(payload["summary"]["matched_by_tax_code"], 1)
        self.assertEqual(after_total, before_total)

        rows = response_json(dashboard_app.api_spa_companies(
            import_batch_id=payload["batch_id"],
            import_outcome="matched_by_tax_code",
        ))["companies"]
        self.assertEqual(rows[0]["id"], existing_id)
        self.assertEqual(rows[0]["matched_company_id"], existing_id)
        self.assertEqual(rows[0]["display_status"], "Matched by MST")

    def test_import_all_name_only_duplicates_does_not_grow_total_companies(self):
        self.db.insert_company("ABC Company")
        before_total = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

        response = asyncio.run(
            dashboard_app.api_import(
                FakeJsonRequest({"source_filename": "dups.txt", "names": [" abc   company "]})
            )
        )
        payload = response_json(response)
        after_total = self.db.fetch_one("SELECT COUNT(*) as cnt FROM companies")["cnt"]

        self.assertEqual(payload["imported"], 0)
        self.assertEqual(payload["summary"]["ambiguous"], 1)
        self.assertEqual(after_total, before_total)

    def test_filters_done_companies_by_completed_date(self):
        yesterday = (vn_now() - timedelta(days=1)).strftime("%Y-%m-%d")
        older = (vn_now() - timedelta(days=3)).strftime("%Y-%m-%d")
        done_yesterday = self.db.insert_company("Done Yesterday")
        done_older = self.db.insert_company("Done Older")
        self.db.update_company(done_yesterday, status="done")
        self.db.update_company(done_older, status="done")
        self.db.execute_query(
            "UPDATE companies SET completed_at = ? WHERE id = ?",
            (f"{yesterday} 12:00:00", done_yesterday),
        )
        self.db.execute_query(
            "UPDATE companies SET completed_at = ? WHERE id = ?",
            (f"{older} 12:00:00", done_older),
        )

        payload = response_json(dashboard_app.api_spa_companies(
            status="done",
            completed_from=yesterday,
            completed_to=yesterday,
        ))

        self.assertEqual([c["name"] for c in payload["companies"]], ["Done Yesterday"])

    def test_suggest_resume_status_uses_cost_saving_checkpoint(self):
        company_id = self.db.insert_company("Resume Corp")
        company = self.db.get_company(company_id)
        counts = dashboard_app._company_data_counts(self.db, company_id)
        self.assertEqual(dashboard_app._suggest_resume_status(company, counts), ("pending", "no_intermediate_data"))

        self.db.execute_query(
            "INSERT INTO gemini_quick_results (company_id, core_name, confidence) VALUES (?, ?, ?)",
            (company_id, "Resume Corp", 0.9),
        )
        counts = dashboard_app._company_data_counts(self.db, company_id)
        self.assertEqual(dashboard_app._suggest_resume_status(company, counts)[0], "gemini_quick_done")

        self.db.execute_query(
            "INSERT INTO search_results (company_id, search_query, url) VALUES (?, ?, ?)",
            (company_id, "resume", "https://example.com"),
        )
        counts = dashboard_app._company_data_counts(self.db, company_id)
        self.assertEqual(dashboard_app._suggest_resume_status(company, counts)[0], "searched")

        self.db.execute_query(
            "INSERT INTO scraped_pages (company_id, url, source_type, scrape_status) VALUES (?, ?, ?, ?)",
            (company_id, "https://example.com", "official_website", "success"),
        )
        counts = dashboard_app._company_data_counts(self.db, company_id)
        self.assertEqual(dashboard_app._suggest_resume_status(company, counts)[0], "ai_extract_pending")


    def test_companies_page_audits_only_current_page_without_completion_filter(self):
        for index in range(60):
            self.db.insert_company(f"Company {index:03d}", status="pending")

        audited_ids = []

        def fake_audit(db, company_id, company=None):
            audited_ids.append(company_id)
            return {
                "checkpoint": "pipeline_init",
                "current_step": "Waiting",
                "last_activity_step": None,
                "completion_status": "incomplete",
                "completion_reason": "no_intermediate_data",
                "resume_status": "pending",
            }

        with patch.object(dashboard_app, "audit_company_completion", side_effect=fake_audit):
            payload = response_json(dashboard_app.api_spa_companies(page=2, page_size=10))

        self.assertEqual(len(payload["companies"]), 10)
        self.assertEqual(payload["pagination"]["total"], 60)
        self.assertEqual(audited_ids, [row["id"] for row in payload["companies"]])
        self.assertEqual(audited_ids, list(range(11, 21)))

    def test_completion_filter_marks_done_company_incomplete_when_only_gemini_exists(self):
        company_id = self.db.insert_company("Gemini Only Co", status="done")
        self.db.execute_query(
            "INSERT INTO gemini_quick_results (company_id, core_name, confidence) VALUES (?, ?, ?)",
            (company_id, "Gemini Only Co", 0.9),
        )

        payload = response_json(dashboard_app.api_spa_companies(status="done", completion="incomplete"))
        row = next(c for c in payload["companies"] if c["id"] == company_id)

        self.assertEqual(row["completion_status"], "incomplete")
        self.assertEqual(row["completion_reason"], "firecrawl_search_incomplete")
        self.assertEqual(row["resume_status"], "gemini_quick_done")
        self.assertTrue(row["can_resume_incomplete"])

    def test_completion_filter_marks_strict_done_company(self):
        company_id = self.db.insert_company("Strict Done Co", status="done")
        sr_id = self.db.execute_query(
            "INSERT INTO search_results (company_id, search_query, url) VALUES (?, ?, ?)",
            (company_id, "strict", "https://example.com"),
        )
        fl_id = self.db.insert_filtered_link(
            search_result_id=sr_id,
            company_id=company_id,
            url="https://example.com",
            source_type="official_website",
            should_scrape=True,
            reason="test",
        )
        self.db.insert_scraped_page(
            filtered_link_id=fl_id,
            company_id=company_id,
            url="https://example.com",
            source_type="official_website",
            markdown_content="ok",
            content_length=2,
            scrape_status="success",
            credits_used=1,
            error_message=None,
        )
        self.db.execute_query(
            "INSERT INTO extracted_contacts (company_id, scraped_page_id, source_type, phone) VALUES (?, ?, ?, ?)",
            (company_id, 1, "official_website", "0123456789"),
        )

        payload = response_json(dashboard_app.api_spa_companies(status="done", completion="strict_done"))
        row = next(c for c in payload["companies"] if c["id"] == company_id)

        self.assertEqual(row["completion_status"], "strict_done")
        self.assertFalse(row["can_resume_incomplete"])

    def test_stale_jobs_detects_crashed_running_company(self):
        company_id = self.db.insert_company("Stale Scrape Co", status="scraping")
        old_time = vn_timestamp(vn_now() - timedelta(minutes=30))
        dashboard_app._upsert_job(self.db, company_id, "scraping", current_step="Scrape", checkpoint="scrape", progress=65)
        self.db.execute_query(
            "UPDATE pipeline_jobs SET updated_at = ? WHERE company_id = ?",
            (old_time, company_id),
        )

        payload = response_json(dashboard_app.api_spa_runner_stale_jobs())

        self.assertEqual(payload["counts"]["stale"], 1)
        self.assertEqual(payload["stale"][0]["id"], company_id)
        self.assertEqual(payload["stale"][0]["suggested_status"], "pending")

    def test_monitor_snapshot_includes_stale_job_even_when_queued_limit_is_full(self):
        stale_id = self.db.insert_company("Hidden Stale Scrape Co", status="scraping")
        old_time = vn_timestamp(vn_now() - timedelta(minutes=30))
        dashboard_app._upsert_job(self.db, stale_id, "scraping", current_step="Scrape", checkpoint="scrape", progress=65)
        self.db.execute_query(
            "UPDATE pipeline_jobs SET updated_at = ? WHERE company_id = ?",
            (old_time, stale_id),
        )
        for index in range(501):
            cid = self.db.insert_company(f"Queued Co {index}", status="pending")
            dashboard_app._upsert_job(self.db, cid, "queued", current_step="Queued", checkpoint="pending", progress=0)

        payload = dashboard_app._monitor_snapshot(self.db)
        ids = [job["id"] for job in payload["jobs"]]

        self.assertIn(stale_id, ids)
        self.assertEqual(payload["jobs"][0]["id"], stale_id)
        self.assertEqual(payload["counts"]["stale"], 1)

    def test_companies_payload_marks_stale_running_company_for_reset_resume(self):
        company_id = self.db.insert_company("Companies Stale Co", status="extracting")
        self.db.execute_query(
            "INSERT INTO extracted_contacts (company_id, source_type, address) VALUES (?, ?, ?)",
            (company_id, "official_website", "Binh Duong"),
        )
        old_time = vn_timestamp(vn_now() - timedelta(minutes=30))
        dashboard_app._upsert_job(self.db, company_id, "extracting", current_step="AI Extract", checkpoint="ai_extract", progress=90)
        self.db.execute_query(
            "UPDATE pipeline_jobs SET updated_at = ? WHERE company_id = ?",
            (old_time, company_id),
        )

        payload = response_json(dashboard_app.api_spa_companies(status="extracting"))
        row = next(c for c in payload["companies"] if c["id"] == company_id)

        self.assertTrue(row["is_stale"])
        self.assertTrue(row["can_reset_resume"])
        self.assertEqual(row["suggested_status"], "ai_extract_pending")

    def test_reset_status_smart_resume_keeps_data_and_sets_checkpoint(self):
        company_id = self.db.insert_company("Partial Scrape Co", status="scraping")
        sr_id = self.db.execute_query(
            "INSERT INTO search_results (company_id, search_query, url) VALUES (?, ?, ?)",
            (company_id, "partial", "https://example.com"),
        )
        fl_id = self.db.insert_filtered_link(
            search_result_id=sr_id,
            company_id=company_id,
            url="https://example.com",
            source_type="official_website",
            should_scrape=True,
            reason="test",
        )
        self.db.insert_scraped_page(
            filtered_link_id=fl_id,
            company_id=company_id,
            url="https://example.com",
            source_type="official_website",
            markdown_content="ok",
            content_length=2,
            scrape_status="success",
            credits_used=1,
            error_message=None,
        )

        response = asyncio.run(dashboard_app.api_spa_runner_reset_status(
            FakeJsonRequest({"company_ids": [company_id], "mode": "smart_resume"})
        ))
        payload = response_json(response)
        company = self.db.get_company(company_id)

        self.assertEqual(payload["reset"], 1)
        self.assertEqual(company["status"], "ai_extract_pending")
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as cnt FROM scraped_pages WHERE company_id = ?", (company_id,))["cnt"], 1)
        reset_log = self.db.fetch_one("SELECT * FROM pipeline_logs WHERE company_id = ? AND step = 'status_reset'", (company_id,))
        self.assertIsNotNone(reset_log)

    def test_runner_start_resume_stale_queues_after_smart_reset(self):
        company_id = self.db.insert_company("Stale Extract Co", status="extracting")
        self.db.execute_query(
            "INSERT INTO extracted_contacts (company_id, source_type, address) VALUES (?, ?, ?)",
            (company_id, "official_website", "Binh Duong"),
        )
        old_time = vn_timestamp(vn_now() - timedelta(minutes=30))
        dashboard_app._upsert_job(self.db, company_id, "extracting", current_step="AI Extract", checkpoint="ai_extract", progress=90)
        self.db.execute_query(
            "UPDATE pipeline_jobs SET updated_at = ? WHERE company_id = ?",
            (old_time, company_id),
        )

        response = asyncio.run(dashboard_app.api_spa_runner_start(
            FakeJsonRequest({"company_ids": [company_id], "resume_stale": True})
        ))
        payload = response_json(response)
        company = self.db.get_company(company_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["started"], [company_id])
        self.assertEqual(company["status"], "ai_extract_pending")

    def test_runner_start_resume_incomplete_done_company(self):
        company_id = self.db.insert_company("Resume Incomplete Done Co", status="done")
        self.db.execute_query(
            "INSERT INTO gemini_quick_results (company_id, core_name, confidence) VALUES (?, ?, ?)",
            (company_id, "Resume Incomplete Done Co", 0.9),
        )

        response = asyncio.run(dashboard_app.api_spa_runner_start(
            FakeJsonRequest({"company_ids": [company_id], "resume_incomplete": True})
        ))
        payload = response_json(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["started"], [company_id])
        self.assertEqual(self.db.get_company(company_id)["status"], "gemini_quick_done")

    def test_runner_start_keeps_non_stale_running_company_skipped(self):
        company_id = self.db.insert_company("Active Scrape Co", status="scraping")
        dashboard_app._upsert_job(self.db, company_id, "scraping", current_step="Scrape", checkpoint="scrape", progress=65)

        response = asyncio.run(dashboard_app.api_spa_runner_start(
            FakeJsonRequest({"company_ids": [company_id], "resume_stale": True})
        ))
        payload = response_json(response)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["skipped"][0]["reason"], "already_running")
        self.assertEqual(self.db.get_company(company_id)["status"], "scraping")


if __name__ == "__main__":
    unittest.main()
