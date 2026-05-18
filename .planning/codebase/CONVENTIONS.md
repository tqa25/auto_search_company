# Conventions & Patterns

> Generated: 2026-05-18 | Source: auto_search_company

## Code Style

### Language & Locale
- **Primary language**: Python with Vietnamese comments, docstrings, and UI text
- **Variable/function names**: English
- **Logging messages**: Mixed English/Vietnamese with emoji indicators (`✅`, `❌`, `⚡`, `📊`, `⚠️`)
- **Prompt templates**: Vietnamese (targeting Vietnamese company data)

### Naming Conventions
| Element | Convention | Example |
|---------|-----------|---------|
| Classes | PascalCase | `DatabaseManager`, `AIExtractor`, `LinkFilter` |
| Functions/Methods | snake_case | `search_places()`, `filter_company_links()` |
| Private methods | Leading underscore | `_parse_response()`, `_check_quota()` |
| Constants | UPPER_SNAKE_CASE | `BLACKLISTED_DOMAINS`, `PROMPT_TEMPLATE` |
| Config properties | UPPER_SNAKE_CASE | `GEMINI_DAILY_LIMIT`, `TOP_N` |
| Module files | snake_case | `gemini_quick_search.py`, `filter_module.py` |

### Type Hints
- Modern Python 3.10+ syntax: `list[dict]`, `tuple[int, int]`, `str | None`
- Some modules use `typing` imports: `List`, `Dict`, `Optional`, `Set`
- No strict enforcement (mixed styles coexist)

## Module Patterns

### 1. Constructor Pattern (Dependency Injection)
All pipeline modules follow a consistent constructor:
```python
class ModuleName:
    def __init__(self, db: DatabaseManager, logger: PipelineLogger, config=None):
        from src.config import default_config
        self.config = config or default_config
        self.db = db
        self.logger = logger
```
- `db` and `logger` are always injected
- `config` defaults to `default_config` singleton via lazy import
- API keys injected via constructor or read from environment

### 2. Logging Pattern (3-Phase)
Every pipeline step follows a consistent logging lifecycle:
```python
# 1. Start
log_id = self.logger.log_step_start(company_id, "step_name", source_url=url)

# 2. Execute
try:
    result = do_work()
    # 3a. Success
    self.logger.log_step_end(log_id, status="success", data_saved=True, metadata={...})
except Exception as e:
    # 3b. Failure
    self.logger.log_step_end(log_id, status="failed", error_message=str(e))
```

### 3. Database Access Pattern
- No ORM — raw SQL queries via `DatabaseManager` methods
- `fetch_one()` / `fetch_all()` for reads (return `sqlite3.Row` dicts)
- `execute_query()` for writes
- Dedicated helper methods: `get_company()`, `insert_company()`, `update_company()`
- Thread-local connections via `threading.local()` for thread safety

### 4. Error Handling Pattern
```python
try:
    result = api_call()
except Exception as e:
    if isinstance(e, (CriticalError,)):
        raise  # Stop pipeline
    # Log and continue
    return {"status": "failed", "error": str(e)}
```

### 5. Result Dict Pattern
All modules return standardized dicts:
```python
return {
    "status": "success" | "failed" | "skipped",
    "content_length": int,
    "source_type": str,
    "cached": bool,  # For dedup tracking
    "error": str,    # Only on failure
}
```

### 6. Quota/Rate Limit Pattern
```python
# Pre-check
if not self._check_quota():
    return self._empty_result("quota_exceeded")

# Execute
result = api_call()

# Post-increment
self._increment_quota()
```

## Configuration Pattern

### Environment Variables (`.env`)
```
FIRECRAWL_API_KEY=...
GEMINI_API_KEY=...
SERPER_API_KEY=...
DB_PATH=data/company_data.db
```

### Config Class (`src/config.py`)
- Single `Config` class with all parameters as instance attributes
- Defaults hardcoded in constructor
- Some values read from environment via `os.getenv()`
- `default_config = Config()` singleton at module level
- No YAML/TOML config files — everything is code-defined

### Config Categories
| Category | Examples |
|----------|---------|
| Search limits | `MAX_RESULTS_PER_QUERY`, `TOP_N` |
| Scoring weights | `DOMAIN_SCORES`, `KEYWORD_SCORES`, `TLD_SCORES` |
| Rate limiting | `DELAY_SECONDS`, `RATE_LIMIT_*` |
| Feature toggles | `GEMINI_QUICK_ENABLED`, `SERPER_ENABLED`, `CONTACT_DISCOVERY_ENABLED` |
| Quality thresholds | `MIN_CONFIDENCE_THRESHOLD`, `EARLY_STOP_SCORE`, `EARLY_STOP_COUNT` |
| Cache settings | `CACHE_TTL_DAYS`, `ENABLE_URL_DEDUP` |

## Dashboard Patterns

### Route Structure
| Method | Path | Handler | Template |
|--------|------|---------|----------|
| GET | `/` | `monitor_page` | `monitor.html` |
| GET | `/companies` | `companies_page` | `companies.html` |
| GET | `/companies/{id}` | `company_detail_page` | `company_detail.html` |
| POST | `/companies/{id}/rerun` | `company_rerun` | redirect |
| GET | `/runner` | `runner_page` | `runner.html` |
| GET | `/settings` | `settings_page` | `settings.html` |
| POST | `/settings` | `settings_save` | redirect |
| GET | `/logs` | `logs_page` | `logs.html` |
| GET/POST | `/api/*` | JSON API | — |
| WS | `/ws/logs` | Live log stream | — |

### API Pattern
- JSON request/response
- Background threads for long-running pipeline execution
- `run_in_threadpool` for sync-to-async bridging

## Git Conventions

- Branch: `main` only (no feature branches observed)
- Commit style: `feat:`, `chore:` prefixes
- No CI/CD pipelines configured
- `.gitignore`: `.env`, `*.db`, `output/`, `venv/`, `__pycache__/`, `*.xlsx`
