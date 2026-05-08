import unittest
from unittest.mock import MagicMock, patch
from src.search_module import SearchModule
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import CriticalError
import requests

class TestErrorClassification(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock(spec=DatabaseManager)
        self.logger = MagicMock(spec=PipelineLogger)
        self.db.fetch_all.side_effect = lambda sql, params=(): [{"cnt": 0}] if "COUNT" in sql.upper() else []
        self.db.is_query_cached.return_value = False
        self.db.get_company.return_value = {"id": 1, "original_name": "Test Company", "status": "pending"}
        
        self.search_module = SearchModule(self.db, self.logger, firecrawl_api_key="test_key")

    @patch('src.search_module.requests.post')
    def test_critical_error_402(self, mock_post):
        # Mock 402 response
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.text = "Payment required"
        mock_post.return_value = mock_response

        print("--- Starting search_company (402) ---")
        try:
            self.search_module.search_company(1)
            self.fail("CriticalError not raised")
        except CriticalError as e:
            print(f"✅ Caught expected CriticalError: {e}")
            self.assertEqual(e.category, "critical")
        
        # Verify logger.log_step_end was called with error_category="critical"
        found = False
        for call in self.logger.log_step_end.call_args_list:
            if call.kwargs.get('status') == 'failed' and call.kwargs.get('error_category') == 'critical':
                found = True
                break
        
        self.assertTrue(found, "Log call with category='critical' not found")
        print("✅ log_step_end with error_category='critical' verified.")

if __name__ == '__main__':
    unittest.main()
