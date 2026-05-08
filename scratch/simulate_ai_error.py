import unittest
from unittest.mock import MagicMock, patch
from src.ai_extractor import AIExtractor
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.errors import CriticalError, SkippableError
import json

class TestAIErrorClassification(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock(spec=DatabaseManager)
        self.logger = MagicMock(spec=PipelineLogger)
        self.extractor = AIExtractor(self.db, self.logger, gemini_api_key="test_key")

    @patch('google.generativeai.GenerativeModel.generate_content')
    def test_ai_critical_quota(self, mock_generate):
        # Mock quota exceeded error
        mock_generate.side_effect = Exception("Quota exceeded for this project")

        # Mock page data
        self.db.fetch_one.return_value = {
            "id": 1, "company_id": 1, "source_type": "official", "url": "http://test.com", "markdown_content": "contact: 123"
        }
        self.db.get_company.return_value = {"original_name": "Test Co"}

        print("--- Starting extract_from_page (Quota) ---")
        try:
            self.extractor.extract_from_page(1)
        except CriticalError:
            print("✅ Caught expected CriticalError in AI Extractor")
        
        # Verify log_step_end
        found = False
        for call in self.logger.log_step_end.call_args_list:
            if call.kwargs.get('error_category') == 'critical':
                found = True
                break
        self.assertTrue(found)
        print("✅ log_step_end with category='critical' verified in AI Extractor.")

if __name__ == '__main__':
    unittest.main()
