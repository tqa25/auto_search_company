import unittest
from unittest.mock import MagicMock, patch
from src.search_module import SearchModule
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import RetryableError
import requests
import json

class TestErrorClassification(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock(spec=DatabaseManager)
        self.logger = MagicMock(spec=PipelineLogger)
        # Mock fetch_all to handle search dedup and link counting
        self.db.fetch_all.side_effect = lambda sql, params=(): [{"cnt": 0}] if "COUNT" in sql.upper() else []
        # Mock is_query_cached to return False to force live API call
        self.db.is_query_cached.return_value = False
        # Mock get_company
        self.db.get_company.return_value = {"id": 1, "original_name": "Test Company", "status": "pending"}
        
        self.search_module = SearchModule(self.db, self.logger, firecrawl_api_key="test_key")

    @patch('src.search_module.requests.post')
    @patch('time.sleep', return_value=None)
    def test_retryable_error_429(self, mock_sleep, mock_post):
        # Mock 429 response
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_post.return_value = mock_response

        print("--- Starting search_company ---")
        try:
            self.search_module.search_company(1)
            print("--- search_company finished without error ---")
        except Exception as e:
            print(f"--- search_company raised {type(e).__name__}: {e} ---")
        
        print(f"Log calls count: {len(self.logger.log_step_end.call_args_list)}")
        for i, call in enumerate(self.logger.log_step_end.call_args_list):
            print(f"Call {i}: status={call.kwargs.get('status')}, category={call.kwargs.get('error_category')}")

if __name__ == '__main__':
    unittest.main()
