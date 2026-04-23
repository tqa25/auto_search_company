import os
import unittest
from src.database import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    DB_PATH = "data/test_company_data.db"

    def setUp(self):
        # Ensure clean state before tests
        if os.path.exists(self.DB_PATH):
            os.remove(self.DB_PATH)
        self.db = DatabaseManager(self.DB_PATH)
        self.db.init_db()

    def tearDown(self):
        # Cleanup
        if os.path.exists(self.DB_PATH):
            os.remove(self.DB_PATH)

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

if __name__ == '__main__':
    unittest.main()
