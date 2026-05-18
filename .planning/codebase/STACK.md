# Technology Stack

> Generated: 2026-05-18 | Source: auto_search_company

## Language & Runtime

| Component | Version / Detail |
|-----------|-----------------|
| Language | Python 3.10+ (inferred from `match/case`-style type hints, `list[dict]` syntax) |
| Runtime | CPython (standard) |
| Package Manager | pip + `requirements.txt` (no `pyproject.toml`, no Poetry/Pipenv) |
| Virtual Environment | `venv/` (gitignored) |

## Core Dependencies

| Package | Role | Version | Notes |
|---------|------|---------|-------|
| `fastapi` | Web framework (Dashboard) | latest | ASGI, used with Jinja2 templates |
| `uvicorn` | ASGI server | latest | Dashboard runner (`dashboard/run.py`) |
| `google-generativeai` | Gemini AI extraction | latest | `genai` SDK for structured extraction prompts |
| `google-genai` | Gemini Quick Search (new SDK) | latest | Used for grounding search (`google.genai.Client`) |
| `requests` | HTTP client | latest | Firecrawl API, Serper API calls |
| `openpyxl` | Excel I/O | latest | Read input lists, write final reports |
| `python-dotenv` | Environment config | latest | `.env` loading throughout all modules |
| `colorama` | Console colors | latest | Pipeline logger colored output |

## External APIs & Services

| Service | Purpose | Auth Method | Rate Limits |
|---------|---------|-------------|-------------|
| **Firecrawl** (`api.firecrawl.dev/v1`) | Web scraping (Markdown extraction) | Bearer token (`FIRECRAWL_API_KEY`) | Plan-based credits (Free: 500, Hobby: 3K, Standard: 100K) |
| **Google Gemini** (generative AI) | AI contact extraction from scraped pages | API key (`GEMINI_API_KEY`) | Free tier: 15 RPM, 1,450 grounding/day |
| **Gemini + Google Search Grounding** | Quick company lookup (Step 1) | Same `GEMINI_API_KEY` | Daily quota tracked in `daily_quota` table |
| **Serper** (`google.serper.dev`) | Google Search + Google Maps Places | API key (`SERPER_API_KEY`) | Credit-based (1-2 credits/query) |

## Database

| Component | Detail |
|-----------|--------|
| Engine | **SQLite 3** (WAL mode) |
| Location | `data/company_data.db` (configurable via `DB_PATH` env var) |
| ORM | None — raw SQL via `sqlite3` module |
| Connection Strategy | Thread-local connections (`threading.local()`) with `row_factory = sqlite3.Row` |
| Schema Management | Inline `CREATE TABLE IF NOT EXISTS` in `DatabaseManager.__init__()` |

### Key Tables

| Table | Purpose |
|-------|---------|
| `companies` | Master company list with status tracking |
| `search_results` | Raw search results from Firecrawl/Serper |
| `filtered_links` | Scored/classified URLs with relevance scores |
| `scraped_pages` | Scraped Markdown content from Firecrawl |
| `extracted_contacts` | AI-extracted contact information |
| `gemini_quick_results` | Gemini grounding search results (Step 1) |
| `pipeline_logs` | Structured pipeline execution logs |
| `daily_quota` | Daily API usage tracking (Gemini + Serper) |
| `url_cache` | URL deduplication cache with TTL |

## Frontend / Dashboard

| Component | Detail |
|-----------|--------|
| Framework | FastAPI + Jinja2 Templates |
| Static Assets | `dashboard/static/` (CSS/JS served via `StaticFiles`) |
| Real-time | WebSocket (`/ws/logs`) for live log streaming |
| Pages | Monitor, Companies, Company Detail, Runner, Settings, Logs |

## Development Tools

| Tool | Purpose |
|------|---------|
| `pytest` | Unit testing (14 test files in `tests/`) |
| `unittest` | Some tests use `unittest.TestCase` |
| Git | Version control (7 commits on `main`) |
| `.env` / `.env.example` | Environment configuration |

## Infrastructure

| Aspect | Detail |
|--------|--------|
| Hosting | Local / Oracle Cloud Ubuntu 24.04 (referenced in conversations) |
| CI/CD | None configured |
| Containerization | None (no Dockerfile) |
| Deployment | Manual (`uvicorn` for dashboard, Python scripts for pipeline) |
