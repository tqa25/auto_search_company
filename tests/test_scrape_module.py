import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from src.database import DatabaseManager
from src.logger import PipelineLogger
from src.scrape_module import ScrapeModule
import os


def make_scrape_config(**overrides):
    values = {
        "DELAY_SECONDS": 0,
        "TOP_N": 10,
        "ENABLE_URL_DEDUP": True,
        "FORCE_REFRESH": False,
        "CACHE_TTL_DAYS": 7,
        "FIRECRAWL_BATCH_SCRAPE_ENABLED": False,
        "FIRECRAWL_MAX_CONCURRENCY": 10,
        "FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS": 0,
        "FIRECRAWL_BATCH_TIMEOUT_SECONDS": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)

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

    from src.errors import CriticalError
    with pytest.raises(CriticalError) as excinfo:
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

def test_scrape_company_batch_disabled_uses_sequential_path(setup_db):
    db, scraper, company_id = setup_db
    scraper.config = make_scrape_config(FIRECRAWL_BATCH_SCRAPE_ENABLED=False)

    with patch.object(scraper, 'scrape_url', return_value={"status": "success", "cached": False}) as mock_scrape_url:
        res = scraper.scrape_company(company_id, delay_seconds=0)

    assert len(res) == 2
    assert mock_scrape_url.call_count == 2


@patch('requests.get')
@patch('requests.post')
def test_scrape_company_batch_enabled_inserts_successes(mock_post, mock_get, setup_db):
    db, scraper, company_id = setup_db
    scraper.config = make_scrape_config(FIRECRAWL_BATCH_SCRAPE_ENABLED=True)

    post_resp = MagicMock(status_code=200)
    post_resp.json.return_value = {"success": True, "id": "batch_123"}
    mock_post.return_value = post_resp

    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "status": "completed",
        "data": [
            {"success": True, "markdown": "# Masothue", "metadata": {"sourceURL": "https://masothue.com/1"}},
            {"success": True, "markdown": "# Facebook", "metadata": {"sourceURL": "https://facebook.com/1"}},
        ],
    }
    mock_get.return_value = get_resp

    res = scraper.scrape_company(company_id, delay_seconds=0)

    assert [r['status'] for r in res] == ['success', 'success']
    assert mock_post.call_args.kwargs['json']['maxConcurrency'] == 2
    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 2
    assert {p['filtered_link_id'] for p in pages} == {1, 2}
    assert {p['markdown_content'] for p in pages} == {"# Masothue", "# Facebook"}


@patch('requests.get')
@patch('requests.post')
def test_scrape_company_batch_respects_top_n_and_configured_concurrency(mock_post, mock_get, setup_db):
    db, scraper, company_id = setup_db
    scraper.config = make_scrape_config(
        FIRECRAWL_BATCH_SCRAPE_ENABLED=True,
        TOP_N=10,
        FIRECRAWL_MAX_CONCURRENCY=50,
    )
    for idx in range(3, 13):
        db.insert_filtered_link(1, company_id, f"https://example.com/{idx}", "other", True)

    post_resp = MagicMock(status_code=200)
    post_resp.json.return_value = {"id": "batch_top_n"}
    mock_post.return_value = post_resp

    urls = ["https://masothue.com/1", "https://facebook.com/1"] + [f"https://example.com/{idx}" for idx in range(3, 11)]
    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "status": "completed",
        "data": [{"success": True, "markdown": url, "metadata": {"sourceURL": url}} for url in urls],
    }
    mock_get.return_value = get_resp

    res = scraper.scrape_company(company_id, delay_seconds=0)

    sent_body = mock_post.call_args.kwargs['json']
    assert len(sent_body['urls']) == 10
    assert sent_body['maxConcurrency'] == 10
    assert len(res) == 10
    assert len(db.get_scraped_pages_for_company(company_id)) == 10


@patch('requests.get')
@patch('requests.post')
def test_scrape_company_batch_partial_failure_preserves_successes(mock_post, mock_get, setup_db):
    db, scraper, company_id = setup_db
    scraper.config = make_scrape_config(FIRECRAWL_BATCH_SCRAPE_ENABLED=True)

    post_resp = MagicMock(status_code=200)
    post_resp.json.return_value = {"id": "batch_partial"}
    mock_post.return_value = post_resp

    get_resp = MagicMock(status_code=200)
    get_resp.json.return_value = {
        "status": "completed",
        "data": [
            {"success": True, "markdown": "ok", "metadata": {"sourceURL": "https://masothue.com/1"}},
            {"success": False, "statusCode": 500, "error": "boom", "metadata": {"sourceURL": "https://facebook.com/1"}},
        ],
    }
    mock_get.return_value = get_resp

    res = scraper.scrape_company(company_id, delay_seconds=0)

    assert [r['status'] for r in res] == ['success', 'failed']
    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 2
    assert [p['scrape_status'] for p in pages] == ['success', 'failed']
    assert pages[1]['error_message'] == 'boom'


@patch('requests.post')
def test_scrape_company_batch_402_remains_critical(mock_post, setup_db):
    db, scraper, company_id = setup_db
    scraper.config = make_scrape_config(FIRECRAWL_BATCH_SCRAPE_ENABLED=True)

    mock_post.return_value = MagicMock(status_code=402, text='no credits')

    from src.errors import CriticalError
    with pytest.raises(CriticalError):
        scraper.scrape_company(company_id, delay_seconds=0)

    pages = db.get_scraped_pages_for_company(company_id)
    assert len(pages) == 2
    assert {p['scrape_status'] for p in pages} == {'failed'}
    assert all('Insufficient credits' in p['error_message'] for p in pages)
