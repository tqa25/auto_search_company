# Testing

> Generated: 2026-05-18 | Source: auto_search_company

## Test Suite Overview

| Metric | Value |
|--------|-------|
| Total test files | 14 |
| Test framework | `pytest` (primary) + `unittest.TestCase` (some modules) |
| Mocking | `unittest.mock` (`MagicMock`, `patch`) |
| Database strategy | Temporary SQLite databases per test |
| API mocking | All external APIs mocked (no real credits consumed) |
| CI/CD integration | **None** — tests run manually |

## Test Coverage Map

| Module | Test File | Lines | Strategy |
|--------|-----------|-------|----------|
| `database.py` | `test_database.py` | 2,151 | Real temp SQLite |
| `search_module.py` | `test_search_module.py` | 8,870 | Mocked Firecrawl API |
| `filter_module.py` | `test_filter_module.py` | 1,581 | Unit tests on scoring logic |
| `scrape_module.py` | `test_scrape_module.py` | 3,557 | Mocked Firecrawl, dedup tests |
| `ai_extractor.py` | `test_ai_extractor.py` | 3,397 | Mocked Gemini API |
| `logger.py` | `test_logger.py` | 2,372 | DB logging + JSONL output |
| `rate_limiter.py` | `test_rate_limiter.py` | 8,874 | Timing, delay adjustment |
| `connection_pool.py` | `test_connection_pool.py` | 6,993 | Session pooling, retry |
| `health_monitor.py` | `test_health_monitor.py` | 8,674 | Credit tracking, ETA |
| `excel_handler.py` | `test_excel_handler.py` | 4,567 | Read/write Excel files |
| `excel_handler.py` | `test_excel_final.py` | 1,670 | Final report generation |
| `result_aggregator.py` | `test_result_aggregator.py` | 2,342 | Aggregation logic |
| `pipeline.py` | `test_resume.py` | 16,336 | Checkpoint, resume, shutdown |
| (multi-module) | `test_integration_phase1.py` | 17,009 | 3-module integration test |

## Untested Modules

| Module | Reason |
|--------|--------|
| `gemini_quick_search.py` | No dedicated test file (tested indirectly via integration) |
| `serper_search.py` | No dedicated test file |
| `config.py` | No dedicated test file |
| `schemas.py` | No dedicated test file |
| `evaluator.py` | No dedicated test file |
| `dashboard/app.py` | No test file (no API endpoint tests) |

## Test Patterns

### Database Test Pattern
```python
@pytest.fixture
def db():
    db = DatabaseManager(":memory:")  # or tempfile
    yield db
    # Cleanup handled by temp file
```

### API Mock Pattern
```python
@patch('src.scrape_module.requests.post')
def test_scrape_url(self, mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"success": True, "data": {"markdown": "content"}}
    )
```

### Integration Test Pattern
- Uses real temporary SQLite database
- Mocks only external API calls
- Tests multi-module interactions end-to-end

## Root-Level Ad-Hoc Tests

Several test scripts exist at the project root (not in `tests/`):

| File | Purpose |
|------|---------|
| `test_firecrawl.py` | Manual Firecrawl API connectivity test |
| `test_gemini.py` | Manual Gemini API test |
| `test_gemini_grounding.py` | Gemini grounding feature test |
| `test_scrape.py` | Manual scrape test |
| `test_match.py` | Name matching algorithm test |
| `test_new_scoring.py` | New scoring algorithm validation |
| `test_fuzz.py` | Fuzzy matching test |
| `smoke_test.py` | Full end-to-end smoke test (22K lines) |

These are **manual/exploratory tests**, not part of the automated test suite.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_database.py -v

# Run with output
pytest tests/ -v -s
```

## Test Quality Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| Unit test coverage | ⚠️ Partial | Core modules covered, some gaps |
| Integration tests | ✅ Good | `test_integration_phase1.py` covers 3-module flow |
| Pipeline resume tests | ✅ Excellent | Comprehensive checkpoint/resume coverage |
| API mock discipline | ✅ Good | No real API calls in tests |
| Dashboard tests | ❌ Missing | No endpoint or UI tests |
| CI/CD | ❌ Missing | No automated test execution |
| Test data management | ⚠️ Inline | Test data hardcoded in test files |
