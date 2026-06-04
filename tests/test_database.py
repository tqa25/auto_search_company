import os
import sqlite3
import unittest
from src.database import DatabaseManager

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
            'sqlite_sequence'
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

if __name__ == '__main__':
    unittest.main()
