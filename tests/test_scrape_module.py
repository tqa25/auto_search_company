import pytest
from unittest.mock import patch, MagicMock
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.scrape_module import ScrapeModule
import os

@pytest.fixture
def setup_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = DatabaseManager(db_file)
    db.init_db()
    
    # insert initial data
    db.insert_company("Test Company 1", status='pending')
    company_id = 1
    
    # create search result
    db.insert_search_result(company_id, "query", "english", 1, "https://masothue.com/1", "title", "snippet")
    search_result_id = 1
    
    # create filtered links
    db.insert_filtered_link(search_result_id, company_id, "https://masothue.com/1", "masothue", True)
    db.insert_filtered_link(search_result_id, company_id, "https://facebook.com/1", "facebook", True)

    logger = PipelineLogger(db)
    
    scraper = ScrapeModule(db, logger, "fake_api_key")
    return db, scraper, company_id

@patch('requests.post')
def test_scrape_url_success(mock_post, setup_db):
    db, scraper, company_id = setup_db
    
    # mock success
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "data": {"markdown": "# Hello MST"}}
    mock_post.return_value = mock_resp
    
    res = scraper.scrape_url(1) # link 1 is masothue
    assert res['status'] == 'success'
    assert res['content_length'] == len("# Hello MST")
    
    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 1
    assert pages[0]['markdown_content'] == "# Hello MST"
    assert pages[0]['credits_used'] == 1.0
    
    # test caching (idempotent)
    res2 = scraper.scrape_url(1)
    assert res2['cached'] is True
    assert mock_post.call_count == 1 # still 1 because cached

@patch('requests.post')
def test_scrape_url_402_abort(mock_post, setup_db):
    db, scraper, company_id = setup_db
    
    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_post.return_value = mock_resp
    
    with pytest.raises(RuntimeError) as excinfo:
        scraper.scrape_url(1)
        
    assert "Insufficient credits" in str(excinfo.value)
    
    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 1
    assert pages[0]['scrape_status'] == 'failed'

@patch('requests.post')
def test_scrape_url_facebook_timeout(mock_post, setup_db):
    db, scraper, company_id = setup_db
    
    import requests
    mock_post.side_effect = requests.exceptions.Timeout("Timeout occurred")
    
    res = scraper.scrape_url(2) # link 2 is facebook
    assert res['status'] == 'skipped'
    assert res['error'] == 'skipped - secondary source'
    
    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 1
    assert pages[0]['scrape_status'] == 'skipped'

@patch('requests.post')
def test_scrape_company_priorities(mock_post, setup_db):
    db, scraper, company_id = setup_db
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True, "data": {"markdown": "content"}}
    mock_post.return_value = mock_resp
    
    res = scraper.scrape_company(company_id, delay_seconds=0)
    assert len(res) == 2
    
    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 2
    # Check priorities:
    assert pages[0]['source_type'] == 'masothue'
    assert pages[1]['source_type'] == 'facebook'
    
    company = db.get_company(company_id)
    assert company['status'] == 'scraped'
