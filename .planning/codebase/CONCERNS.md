# Concerns & Technical Debt

> Generated: 2026-05-18 | Source: auto_search_company

## 🔴 Critical

### 1. API Key Exposure Risk
- **Location**: All modules read API keys via `os.getenv()` at import/init time
- **Issue**: `.env` file is gitignored but `.env.example` contains key placeholder names. No secret rotation strategy. Dashboard `/settings` endpoint writes keys directly to `.env` file on disk via `set_key()`.
- **Recommendation**: Use a secrets manager or at minimum validate key format before use.

### 2. Dual Gemini SDK Usage
- **Location**: `gemini_quick_search.py` uses `google.genai` (new SDK); `ai_extractor.py` uses `google.generativeai` (old SDK)
- **Issue**: Two different SDKs for the same service with different APIs, auth patterns, and error handling. Creates maintenance confusion and potential version conflicts.
- **Recommendation**: Migrate `ai_extractor.py` to the new `google.genai` SDK.

### 3. No Input Validation on Dashboard API
- **Location**: `dashboard/app.py` — `/api/runner/step`, `/api/companies/import`
- **Issue**: User input (company IDs, step names) accepted without validation. Pipeline runs in daemon threads with no timeout or cancellation mechanism.
- **Recommendation**: Add input validation, request size limits, and background task management.

## 🟡 Important

### 4. Root Directory Pollution
- **Location**: Project root contains 20+ ad-hoc scripts, test files, and markdown docs
- **Issue**: `parse_full.py`, `parse_full2.py`, `parse_full3.py`, `test_firecrawl.py`, `scratch.py`, etc. clutter the root. Multiple `implementation_plan_*.md` files with no clear status.
- **Recommendation**: Move scripts to `scripts/`, tests to `tests/`, docs to `docs/`. Archive or delete stale implementation plans.

### 5. Hardcoded Model Name in AIExtractor
- **Location**: `ai_extractor.py:23` — `self.model = genai.GenerativeModel('gemini-3-flash-preview')`
- **Issue**: Model name hardcoded, unlike `GeminiQuickSearch` which reads from `Config.GEMINI_QUICK_MODEL`.
- **Recommendation**: Move to `Config` for consistency.

### 6. No Database Migration Strategy
- **Location**: `database.py` — `CREATE TABLE IF NOT EXISTS` in `__init__`
- **Issue**: Schema changes require manual intervention. No version tracking, no migration scripts. Adding columns to existing tables would require manual ALTER statements.
- **Recommendation**: Add a simple migration system (even a version table + sequential SQL scripts).

### 7. Thread Safety Concerns in Dashboard
- **Location**: `dashboard/app.py` — Pipeline runs in `threading.Thread(daemon=True)`
- **Issue**: Multiple concurrent pipeline runs possible with no coordination. `ws_clients` list modified without locks. `DatabaseManager` uses thread-local connections (safe), but `Pipeline` state is not thread-safe.
- **Recommendation**: Add a pipeline execution lock or queue.

### 8. No Authentication on Dashboard
- **Location**: `dashboard/app.py`
- **Issue**: All endpoints publicly accessible. `/settings` can modify `.env` including API keys. `/api/runner/start` can trigger pipeline execution.
- **Recommendation**: Add basic auth or IP restriction for production use.

## 🟢 Minor / Technical Debt

### 9. Legacy Search Module Retained
- **Location**: `src/search_module.py` (717 lines)
- **Issue**: Superseded by Gemini Quick Search + Serper but still present and imported by `pipeline.py`. Dead code adds confusion.
- **Recommendation**: Remove or clearly mark as deprecated.

### 10. Config Instantiation Anti-Pattern
- **Location**: `ai_extractor.py:286` — `Config().MIN_CONFIDENCE_THRESHOLD`
- **Issue**: Creates new `Config()` instances inline instead of using the injected `self.config`. This bypasses any config customization passed via constructor.
- **Recommendation**: Use `self.config` consistently.

### 11. Missing Type Safety in Database Layer
- **Location**: `database.py` — all methods return `sqlite3.Row` (dict-like)
- **Issue**: No typed return values. Callers access fields by string keys (`row["phone"]`) with no compile-time checking.
- **Recommendation**: Consider returning typed dataclasses or using `schemas.py` more consistently.

### 12. Prompt Templates as Class Constants
- **Location**: `ai_extractor.py:25-105`, `gemini_quick_search.py:38-51`
- **Issue**: Long Vietnamese prompt templates embedded as class-level string constants. Difficult to version, test, or A/B test independently.
- **Recommendation**: Extract to separate prompt template files or a prompt registry.

### 13. Incomplete Error Handling in Filter Module
- **Location**: `filter_module.py:136-148` — `_get_best_partial_ratio`
- **Issue**: O(n²) fuzzy matching with no size guard. Very long URLs or company names could cause performance issues.
- **Recommendation**: Add length limits or use a library like `rapidfuzz`.

### 14. JSONL Log File Handle Leak Risk
- **Location**: `logger.py:37` — `self._jsonl_file = open(path, "a", ...)`
- **Issue**: File handle opened in constructor, closed in `__del__`. If `__del__` is not called (e.g., crash), file handle leaks.
- **Recommendation**: Use context manager pattern or ensure `close()` in signal handlers.

### 15. No Automated CI/CD
- **Issue**: 14 test files exist but no GitHub Actions, no pre-commit hooks, no automated test execution on push.
- **Recommendation**: Add a minimal CI pipeline (`pytest` on push).

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| 🔴 Critical | 3 | Security (API keys, no auth), SDK inconsistency |
| 🟡 Important | 5 | Code organization, hardcoded values, thread safety |
| 🟢 Minor | 7 | Technical debt, performance, maintainability |
