import unittest
from unittest.mock import MagicMock, patch
import json
from src.ai_extractor import AIExtractor

class TestAIExtractor(unittest.TestCase):
    @patch('src.ai_extractor.genai')
    def setUp(self, mock_genai):
        self.mock_db = MagicMock()
        self.mock_logger = MagicMock()
        self.api_key = "fake_api_key"
        self.extractor = AIExtractor(self.mock_db, self.mock_logger, self.api_key)

    def test_extract_from_page_handles_json_properly(self):
        mock_response = MagicMock()
        mock_response.text = '{"address": "123 Main St", "phone": "123-456", "email": "test@test.com", "website": "example.com", "fax": null, "representative": "John Doe", "confidence": 0.9}'
        self.extractor.model.generate_content.return_value = mock_response
        
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "some text"}, # scraped_page
            None # existing extracted contact -> None means not extracted yet
        ]
        
        result = self.extractor.extract_from_page(1)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(result["extracted_fields"]["address"], "123 Main St")
        self.mock_db.insert_extracted_contact.assert_called_once()

    def test_extract_from_page_handles_markdown_json(self):
        mock_response = MagicMock()
        mock_response.text = "```json\n{\"address\": \"123 Main\"}\n```"
        self.extractor.model.generate_content.return_value = mock_response
        
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "text"},
            None
        ]
        
        result = self.extractor.extract_from_page(1)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["extracted_fields"]["address"], "123 Main")
        
    def test_already_extracted(self):
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "text"}, # scraped
            {"id": 10, "confidence_score": 0.8} # already extracted
        ]
        result = self.extractor.extract_from_page(1)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "already_extracted")

    def test_json_parse_error_saves_raw_text(self):
        mock_response = MagicMock()
        mock_response.text = "Sorry I can't do this"
        self.extractor.model.generate_content.return_value = mock_response
        
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "text"},
            None
        ]
        
        result = self.extractor.extract_from_page(1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "json_parse_error")
        # Ensure it inserted to DB with raw_ai_response and logic fallbacks to None
        self.mock_db.insert_extracted_contact.assert_called_once()

if __name__ == '__main__':
    unittest.main()
