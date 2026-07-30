import os
import unittest

from src.company_matcher import resolve_company_match
from src.database import DatabaseManager


class TestCompanyMatcher(unittest.TestCase):
    DB_PATH = "data/test_company_matcher.db"

    def setUp(self):
        for suffix in ("", "-wal", "-shm"):
            path = f"{self.DB_PATH}{suffix}"
            if os.path.exists(path):
                os.remove(path)
        self.db = DatabaseManager(self.DB_PATH)
        self.db.init_db()

    def tearDown(self):
        self.db.close()
        for suffix in ("", "-wal", "-shm"):
            path = f"{self.DB_PATH}{suffix}"
            if os.path.exists(path):
                os.remove(path)

    def test_tax_code_exact_match_wins(self):
        company_id = self.db.insert_company("ABC Company", tax_code="0123456789")

        decision = resolve_company_match(self.db, {"name": "ABC Co", "tax_code": "0123456789"})

        self.assertEqual(decision.decision, "matched_by_tax_code")
        self.assertEqual(decision.candidate.company["id"], company_id)
        self.assertEqual(decision.candidate.score, 100.0)

    def test_name_only_duplicate_is_ambiguous(self):
        self.db.insert_company("ABC Company")

        decision = resolve_company_match(self.db, {"name": " abc   company "})

        self.assertEqual(decision.decision, "ambiguous")
        self.assertEqual(decision.reason, "insufficient_disambiguating_evidence")

    def test_same_name_different_tax_code_is_new_entity_candidate(self):
        self.db.insert_company("ABC Company", tax_code="0123456789")

        decision = resolve_company_match(self.db, {"name": "ABC Company", "tax_code": "9876543210"})

        self.assertEqual(decision.decision, "no_match")
        self.assertEqual(decision.candidates[0].method, "tax_code_mismatch")


if __name__ == "__main__":
    unittest.main()
