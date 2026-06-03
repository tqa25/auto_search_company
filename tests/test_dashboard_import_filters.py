import os
import unittest
import asyncio
import json
from datetime import datetime, timedelta

os.environ["DB_PATH"] = "data/test_dashboard_company_data.db"
os.environ["DASHBOARD_PASS"] = ""

import dashboard.app as dashboard_app
from src.database import DatabaseManager


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
        ))["companies"]
        self.assertEqual([c["name"] for c in companies], ["HCM Logistics"])

        ids_payload = response_json(dashboard_app.api_spa_company_ids(
            import_batch_id=payload["batch_id"],
            search="hcm",
        ))
        self.assertEqual(ids_payload["count"], 1)
        self.assertEqual(len(ids_payload["company_ids"]), 1)

    def test_filters_done_companies_by_completed_date(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        older = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
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


if __name__ == "__main__":
    unittest.main()
