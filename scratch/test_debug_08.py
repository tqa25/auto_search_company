
import sys
import os
import json
import logging
from unittest.mock import MagicMock, patch

# Add current directory to path
sys.path.append(os.getcwd())

from src.ai_extractor import AIExtractor
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.config import Config

def test_debug_08():
    print("Testing Debug Task 08: Confidence Threshold and Conflict Resolution...")
    
    # Mock Database
    db = MagicMock(spec=DatabaseManager)
    
    # Mock Logger
    logger = PipelineLogger(db, log_dir="output/test_logs")
    
    # Initialize AIExtractor
    extractor = AIExtractor(db, logger, gemini_api_key="mock_key")
    
    # 1. Test Low Confidence Logging
    company_id = 1
    scraped_page_id = 101
    source_type = "official_website"
    source_url = "http://example.com"
    
    db.fetch_one.side_effect = [
        {"id": scraped_page_id, "company_id": company_id, "source_type": source_type, "url": source_url, "markdown_content": "contact: 1234567890"}, # scraped_page
        None, # existing check
        {"original_name": "Test Company"} # company_record
    ]
    
    # Mock Gemini response with LOW confidence (0.2 < 0.3)
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "address": "123 Test St",
        "phone": "1234567890",
        "email": "test@example.com",
        "website": "http://example.com",
        "fax": None,
        "representative": "John Doe",
        "confidence": 0.2
    })
    
    with patch.object(extractor.model, 'generate_content', return_value=mock_response):
        extractor.extract_from_page(scraped_page_id)
    
    # Check if low_confidence_extraction is in the log file
    log_file = os.path.join("output/test_logs", f"pipeline_{logger._current_log_date}.jsonl")
    with open(log_file, "r") as f:
        logs = f.readlines()
        found_low_conf = any("low_confidence_extraction" in line and "0.2" in line for line in logs)
        print(f"Low confidence event found in logs: {found_low_conf}")

    # 2. Test Conflict Resolution Logging
    company_id = 2
    # Mock multiple extracted contacts for the same company
    db.fetch_all.side_effect = [
        [], # scraped_pages for extract_for_company (we'll bypass the extraction loop)
        [
            {
                "id": 1, "company_id": company_id, "source_type": "official_website", "confidence_score": 0.9,
                "address": "High Conf Address", "phone": "111", "email": "e1", "website": "w1", "fax": "f1", "representative": "r1"
            },
            {
                "id": 2, "company_id": company_id, "source_type": "masothue", "confidence_score": 0.7,
                "address": "Low Conf Address", "phone": "222", "email": "e2", "website": "w2", "fax": "f2", "representative": "r2"
            }
        ] # extracted_contacts
    ]
    
    # We need to mock _batch_short_pages to return empty to skip extraction loop
    with patch.object(extractor, '_batch_short_pages', return_value=[]):
        extractor.extract_for_company(company_id)
    
    # Check if contact_conflict_resolved is in the log file
    with open(log_file, "r") as f:
        logs = f.readlines()
        found_conflict = any("contact_conflict_resolved" in line and "masothue" in line and "official_website" in line for line in logs)
        print(f"Conflict resolution event found in logs: {found_conflict}")

if __name__ == "__main__":
    test_debug_08()
