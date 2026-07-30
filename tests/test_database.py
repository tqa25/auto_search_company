import os
import sqlite3
import unittest
from src.database import DatabaseManager
from src.time_utils import parse_timestamp_as_vn, vn_date_str

class TestDatabaseManager(unittest.TestCase):
    DB_PATH = "data/test_runtime_company_data.db"

    def setUp(self):
        # Ensure clean state before tests
        for suffix in ("", "-wal", "-shm"):
            path = f"{self.DB_PATH}{suffix}"
            if os.path.exists(path):
                os.remove(path)
        self.db = DatabaseManager(self.DB_PATH)
        self.db.init_db()

    def tearDown(self):
        # Cleanup
        self.db.close()
        for suffix in ("", "-wal", "-shm"):
            path = f"{self.DB_PATH}{suffix}"
            if os.path.exists(path):
                os.remove(path)

    def test_init_db(self):
        self.assertTrue(os.path.exists(self.DB_PATH))
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        # Test if all tables run correctly
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row['name'] for row in cursor.fetchall()}
        expected_tables = {
            'companies', 'search_results', 'filtered_links', 
            'scraped_pages', 'extracted_contacts', 'pipeline_logs',
            'company_import_items', 'company_match_candidates', 'sqlite_sequence'
        }
        self.assertTrue(expected_tables.issubset(tables))

        # Check for the index
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row['name'] for row in cursor.fetchall()}
        self.assertIn('idx_pipeline_logs_company_step', indexes)

    def test_crud_company(self):
        # Insert
        company_id = self.db.insert_company(original_name="Test Corp", tax_code="12345")
        self.assertIsNotNone(company_id)

        # Query
        company = self.db.get_company(company_id)
        self.assertIsNotNone(company)
        self.assertEqual(company['original_name'], "Test Corp")
        self.assertEqual(company['tax_code'], "12345")
        self.assertEqual(company['status'], "pending")

        # Update
        self.db.update_company(company_id, status="success", vietnamese_name="Công ty Test")
        company_updated = self.db.get_company(company_id)
        self.assertEqual(company_updated['status'], "success")
        self.assertEqual(company_updated['vietnamese_name'], "Công ty Test")

    def test_insert_company_rejects_normalized_duplicate_names(self):
        self.db.insert_company(original_name="ABC   Company")

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.insert_company(original_name=" abc company ")

    def test_insert_company_can_allow_duplicate_name_with_distinct_key(self):
        first_id = self.db.insert_company(original_name="ABC Company", tax_code="0123456789")
        second_id = self.db.insert_company(
            original_name=" abc company ",
            tax_code="9876543210",
            allow_duplicate_name=True,
        )

        first = self.db.get_company(first_id)
        second = self.db.get_company(second_id)

        self.assertEqual(first["original_name_key"], "abc company")
        self.assertEqual(second["original_name"], "abc company")
        self.assertEqual(second["original_name_key"], f"abc company#duplicate-{second_id}")

    def test_company_name_normalization_unescapes_markdown_punctuation(self):
        self.assertEqual(
            self.db.normalize_company_name("LOCK & LOCK VINA"),
            self.db.normalize_company_name(r"LOCK \& LOCK   VINA"),
        )
        company_id = self.db.insert_company(original_name=r"LOCK \& LOCK VINA")
        company = self.db.get_company(company_id)

        self.assertEqual(company["original_name"], "LOCK & LOCK VINA")
        self.assertEqual(company["original_name_key"], "lock & lock vina")

    def test_import_batch_and_completed_at_fields(self):
        batch_id = self.db.create_import_batch(source_filename="companies.csv", total=2)
        company_id = self.db.insert_company("Done Corp", import_batch_id=batch_id)

        self.db.update_company(company_id, status="done")
        company = self.db.get_company(company_id)
        batches = self.db.get_import_batches()

        self.assertEqual(company["import_batch_id"], batch_id)
        self.assertEqual(company["status"], "done")
        self.assertIsNotNone(company["completed_at"])
        self.assertEqual(batches[0]["id"], batch_id)
        self.assertEqual(batches[0]["current_company_count"], 1)

    def test_runtime_timestamps_use_vn_local_strings(self):
        today = vn_date_str()
        company_id = self.db.insert_company("VN Timestamp Co", status="done")
        company = self.db.get_company(company_id)

        self.assertTrue(company['created_at'].startswith(today))
        self.assertTrue(company['updated_at'].startswith(today))
        self.assertTrue(company['completed_at'].startswith(today))
        self.assertIsNotNone(parse_timestamp_as_vn(company['created_at']))
        self.assertIsNotNone(parse_timestamp_as_vn(company['completed_at']))

        updated_before = company['updated_at']
        self.db.update_company(company_id, vietnamese_name='Cong ty VN Timestamp')
        company = self.db.get_company(company_id)
        self.assertIsNotNone(parse_timestamp_as_vn(company['updated_at']))
        self.assertGreaterEqual(company['updated_at'], updated_before)

    def test_init_db_preserves_existing_duplicate_rows(self):
        legacy_path = "data/test_legacy_duplicate_company_data.db"
        if os.path.exists(legacy_path):
            os.remove(legacy_path)
        conn = sqlite3.connect(legacy_path)
        conn.execute(
            "CREATE TABLE companies ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "original_name TEXT NOT NULL,"
            "vietnamese_name TEXT,"
            "tax_code TEXT,"
            "status TEXT DEFAULT 'pending',"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        conn.execute("INSERT INTO companies (original_name) VALUES (?)", ("ABC Company",))
        conn.execute("INSERT INTO companies (original_name) VALUES (?)", (" abc   company ",))
        conn.commit()
        conn.close()

        legacy_db = None
        try:
            legacy_db = DatabaseManager(legacy_path)
            legacy_db.init_db()
            rows = legacy_db.fetch_all("SELECT id, original_name_key FROM companies ORDER BY id")

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["original_name_key"], "abc company")
            self.assertEqual(rows[1]["original_name_key"], "abc company#duplicate-2")
            with self.assertRaises(sqlite3.IntegrityError):
                legacy_db.insert_company("ABC COMPANY")
        finally:
            if legacy_db:
                legacy_db.close()
            for suffix in ("", "-wal", "-shm"):
                path = f"{legacy_path}{suffix}"
                if os.path.exists(path):
                    os.remove(path)

    def test_reported_checkpoint_mark_unmark_and_status_map(self):
        first_id = self.db.insert_company("Reported A")
        second_id = self.db.insert_company("Reported B")

        result = self.db.mark_companies_reported(
            [first_id, second_id],
            window_start="2026-07-01 17:00:00",
            window_end="2026-07-02 17:00:00",
            note="daily report",
            reported_by="tester",
        )
        self.assertEqual(result["marked"], 2)
        self.assertIsNotNone(result["report_run_id"])

        status = self.db.get_reported_status_for_companies([first_id, second_id])
        self.assertEqual(set(status.keys()), {first_id, second_id})
        self.assertEqual(status[first_id]["reported_by"], "tester")

        unmarked = self.db.unmark_companies_reported([first_id])
        self.assertEqual(unmarked["unmarked"], 1)
        status = self.db.get_reported_status_for_companies([first_id, second_id])
        self.assertNotIn(first_id, status)
        self.assertIn(second_id, status)

if __name__ == '__main__':
    unittest.main()
