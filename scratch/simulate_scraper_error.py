import unittest
from unittest.mock import MagicMock, patch
from src.scrape_module import ScrapeModule
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import CriticalError, SkippableError
import requests

class TestScraperErrorClassification(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock(spec=DatabaseManager)
        self.logger = MagicMock(spec=PipelineLogger)
        self.scraper = ScrapeModule(self.db, self.logger, firecrawl_api_key="test_key")

    @patch('src.scrape_module.requests.get')
    def test_scraper_critical_402(self, mock_get):
        # Mock 402 response from Firecrawl scrape
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.text = "Payment required"
        mock_get.return_value = mock_response

        # Mock page data
        self.db.fetch_one.side_effect = lambda sql, params=(): {"id": 1, "company_id": 1, "url": "http://test.com", "source_type": "official"} if "filtered_links" in sql else None

        print("--- Starting scrape_page (402) ---")
        try:
            self.scraper.scrape_url(1)
        except CriticalError:
            print("✅ Caught expected CriticalError in Scraper")
        
        # Verify log_step_end
        print(f"Log calls: {self.logger.log_step_end.call_args_list}")
        found = False
        for call in self.logger.log_step_end.call_args_list:
            if call.kwargs.get('error_category') == 'critical':
                found = True
                break
        self.assertTrue(found)
        print("✅ log_step_end with category='critical' verified in Scraper.")

if __name__ == '__main__':
    unittest.main()
