import sys
import types as py_types
import unittest
from unittest.mock import MagicMock, patch
import json

if "google.genai" not in sys.modules:
    google_module = py_types.ModuleType("google")
    genai_module = py_types.ModuleType("google.genai")
    genai_types_module = py_types.ModuleType("google.genai.types")
    genai_module.Client = MagicMock()
    genai_types_module.GenerateContentConfig = MagicMock()
    genai_module.types = genai_types_module
    sys.modules.setdefault("google", google_module)
    sys.modules["google.genai"] = genai_module
    sys.modules["google.genai.types"] = genai_types_module

from src.ai_extractor import AIExtractor

class TestAIExtractor(unittest.TestCase):
    @patch('src.ai_extractor.genai')
    def setUp(self, mock_genai):
        self.mock_db = MagicMock()
        self.mock_db.get_company.return_value = {"original_name": "Test Company", "tax_code": "1234567890"}
        self.mock_logger = MagicMock()
        self.api_key = "fake_api_key"
        self.extractor = AIExtractor(self.mock_db, self.mock_logger, self.api_key)

    def test_extract_from_page_handles_json_properly(self):
        mock_response = MagicMock()
        mock_response.text = '{"address": "123 Main St", "phone": "123-456", "email": "test@test.com", "website": "example.com", "fax": null, "representative": "John Doe", "confidence": 0.9}'
        self.extractor.client.models.generate_content.return_value = mock_response
        
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "test@test.com"}, # scraped_page
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
        self.extractor.client.models.generate_content.return_value = mock_response
        
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "test@test.com"},
            None
        ]
        
        result = self.extractor.extract_from_page(1)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["extracted_fields"]["address"], "123 Main")
        

    def test_masothue_mst_mismatch_suppresses_phone_before_save(self):
        mock_response = MagicMock()
        mock_response.text = '{"address": "123 Main", "phone": "0901234567", "email": null, "website": null, "fax": null, "representative": null, "confidence": 0.9}'
        self.extractor.client.models.generate_content.return_value = mock_response

        self.mock_db.fetch_one.side_effect = [
            {
                "id": 1,
                "company_id": 100,
                "source_type": "masothue",
                "url": "https://masothue.com/9999999999-wrong-company",
                "markdown_content": "Mã số thuế: 9999999999. Điện thoại: 0901234567",
            },
            None,
        ]

        result = self.extractor.extract_from_page(1)

        self.assertEqual(result["status"], "success")
        kwargs = self.mock_db.insert_extracted_contact.call_args.kwargs
        self.assertIsNone(kwargs["phone"])

    def test_masothue_mst_exact_match_keeps_phone(self):
        mock_response = MagicMock()
        mock_response.text = '{"address": "123 Main", "phone": "0901234567", "email": null, "website": null, "fax": null, "representative": null, "confidence": 0.9}'
        self.extractor.client.models.generate_content.return_value = mock_response

        self.mock_db.fetch_one.side_effect = [
            {
                "id": 1,
                "company_id": 100,
                "source_type": "masothue",
                "url": "https://masothue.com/1234567890-right-company",
                "markdown_content": "Mã số thuế: 1234567890. Điện thoại: 0901234567",
            },
            None,
        ]

        result = self.extractor.extract_from_page(1)

        self.assertEqual(result["status"], "success")
        kwargs = self.mock_db.insert_extracted_contact.call_args.kwargs
        self.assertEqual(kwargs["phone"], "0901234567")

    def test_non_masothue_mst_mismatch_keeps_phone(self):
        mock_response = MagicMock()
        mock_response.text = '{"address": "123 Main", "phone": "0901234567", "email": null, "website": null, "fax": null, "representative": null, "confidence": 0.9}'
        self.extractor.client.models.generate_content.return_value = mock_response

        self.mock_db.fetch_one.side_effect = [
            {
                "id": 1,
                "company_id": 100,
                "source_type": "official_website",
                "url": "https://example.com/contact",
                "markdown_content": "Mã số thuế: 9999999999. Điện thoại: 0901234567",
            },
            None,
        ]

        result = self.extractor.extract_from_page(1)

        self.assertEqual(result["status"], "success")
        kwargs = self.mock_db.insert_extracted_contact.call_args.kwargs
        self.assertEqual(kwargs["phone"], "0901234567")

    def test_extract_from_page_suppresses_fields_not_present_in_markdown(self):
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "address": "Lo G11, Khu cong nghiep Que Vo, Bac Ninh",
            "phone": "0901234567",
            "email": "contact@example.vn",
            "website": None,
            "fax": None,
            "representative": None,
            "confidence": 0.9,
        })
        self.extractor.client.models.generate_content.return_value = mock_response

        self.mock_db.fetch_one.side_effect = [
            {
                "id": 1,
                "company_id": 100,
                "source_type": "official_website",
                "url": "https://banmaischool.edu.vn/lien-he",
                "markdown_content": "Lien he: 0901 234 567, email contact@example.vn, dia chi Ha Dong",
            },
            None,
        ]

        result = self.extractor.extract_from_page(1)

        self.assertEqual(result["status"], "success")
        kwargs = self.mock_db.insert_extracted_contact.call_args.kwargs
        self.assertIsNone(kwargs["address"])
        self.assertEqual(kwargs["phone"], "0901234567")
        self.assertEqual(kwargs["email"], "contact@example.vn")

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
        self.extractor.client.models.generate_content.return_value = mock_response
        
        self.mock_db.fetch_one.side_effect = [
            {"id": 1, "company_id": 100, "source_type": "masothue", "url": "http://123", "markdown_content": "test@test.com"},
            None
        ]
        
        result = self.extractor.extract_from_page(1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "json_parse_error")
        # Ensure it inserted to DB with raw_ai_response and logic fallbacks to None
        self.mock_db.insert_extracted_contact.assert_called_once()

if __name__ == '__main__':
    unittest.main()
