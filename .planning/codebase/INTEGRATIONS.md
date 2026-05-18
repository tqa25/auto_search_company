# External Integrations

> Generated: 2026-05-18 | Source: auto_search_company

## Integration Map

```
┌────────────────────────────────────────────────────────┐
│                    Pipeline Core                        │
│                                                        │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │ GeminiQuick  │  │ SerperSearch │  │ ScrapeModule  │ │
│  │ Search       │  │              │  │               │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘ │
│         │                 │                 │          │
└─────────┼─────────────────┼─────────────────┼──────────┘
          │                 │                 │
          ▼                 ▼                 ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
   │ Google Gemini │ │ Serper.dev   │ │ Firecrawl API    │
   │ + Grounding   │ │ (Search +    │ │ (Web Scraping)   │
   │              │ │  Maps)       │ │                  │
   └──────────────┘ └──────────────┘ └──────────────────┘
```

---

## 1. Google Gemini (Quick Search — Step 1)

| Aspect | Detail |
|--------|--------|
| **Module** | `src/gemini_quick_search.py` → `GeminiQuickSearch` |
| **SDK** | `google.genai.Client` (new `google-genai` package) |
| **Model** | Configurable via `Config.GEMINI_QUICK_MODEL` |
| **Auth** | `GEMINI_API_KEY` environment variable |
| **Features Used** | Google Search Grounding (`tools=[{"google_search": {}}]`) |

### Request Pattern
```python
response = self.client.models.generate_content(
    model=self.config.GEMINI_QUICK_MODEL,
    contents=prompt,
    config=types.GenerateContentConfig(
        tools=[{"google_search": {}}],
        temperature=0.0,
        max_output_tokens=2048
    )
)
```

### Quota Management
- Daily limit tracked in `daily_quota` table (`gemini_grounding_used` column)
- Warning threshold at configurable percentage (`GEMINI_DAILY_WARN_PERCENT`)
- Hard stop when `gemini_grounding_used >= GEMINI_DAILY_LIMIT`
- Timezone: Vietnam (UTC+7) for daily reset

### Fallback Behavior
- If grounding call fails → retries **without** grounding tools
- If quota exceeded → returns `_empty_result("quota_exceeded")` → pipeline falls through to Serper

### Output
- Structured JSON: `core_name`, `core_name_vi`, `abbreviation`, `address`, `phone`, `email`, `website`, `tax_code`, `sources`, `confidence`
- Grounding sources extracted from `response.candidates[0].grounding_metadata`

---

## 2. Google Gemini (AI Extraction — Step 5)

| Aspect | Detail |
|--------|--------|
| **Module** | `src/ai_extractor.py` → `AIExtractor` |
| **SDK** | `google.generativeai` (older `genai` package) |
| **Model** | `gemini-3-flash-preview` (hardcoded) |
| **Auth** | `GEMINI_API_KEY` via `genai.configure()` |

### Request Pattern
```python
generation_config = genai.types.GenerationConfig(
    response_mime_type="application/json",
    temperature=0.1
)
response = self.model.generate_content(prompt, generation_config=generation_config)
```

### Batching Optimization
- Short pages (<5,000 chars) are batched into groups (up to 15,000 chars combined)
- Single API call extracts from multiple pages simultaneously
- Reduces total API calls by ~40-60%

### Rate Limiting
- 3 retries on HTTP 429 with 60-second wait
- `CriticalError` raised on quota exhaustion → stops pipeline

### Pre-filtering
- `_has_contact_signals()` checks for phone/email regex patterns before calling AI
- Pages without contact signals skip the API call entirely

---

## 3. Serper.dev (Search + Maps — Steps 2 & 3)

| Aspect | Detail |
|--------|--------|
| **Module** | `src/serper_search.py` → `SerperSearch` |
| **Endpoints** | `https://google.serper.dev/search` (organic), `https://google.serper.dev/places` (Maps) |
| **Auth** | `X-API-KEY` header via `SERPER_API_KEY` |

### Google Maps Places (Step 2)
```python
resp = requests.post(
    self.PLACES_URL,
    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
    json={"q": query, "gl": "vn", "hl": "vi"},
    timeout=10
)
```
- Returns structured phone, address, website from the best Places result
- 1 credit per query

### Google Search (Step 3)
- Standard organic search with `gl=vn`, `hl=vi` locale
- Credits: 1 for ≤10 results, 2 for >10 results
- Smart fallback query generation based on Gemini results (Vietnamese name, site-specific, tax code, recruitment)

### URL Deduplication
- `normalize_url()` strips `www.`, lowercases, removes trailing slashes
- `dedup_results()` filters URLs already found by Gemini grounding

### Quota Tracking
- `serper_used` column in `daily_quota` table
- Incremented on every API call

---

## 4. Firecrawl (Web Scraping — Step 4)

| Aspect | Detail |
|--------|--------|
| **Module** | `src/scrape_module.py` → `ScrapeModule` |
| **Endpoint** | `https://api.firecrawl.dev/v1/scrape` |
| **Auth** | `Bearer` token via `FIRECRAWL_API_KEY` |

### Request Pattern
```python
body = {
    "url": url,
    "formats": ["markdown"],
    "timeout": 30000,
    "waitFor": 3000
}
response = requests.post(self.api_url, headers=headers, json=body, timeout=35)
```

### Credit Tracking
- 1 credit per successful scrape
- Credits tracked in `scraped_pages.credits_used`
- `HealthMonitor` aggregates total usage

### Connection Pooling (Optional)
- `ConnectionManager` wraps `requests.Session` for TCP connection reuse
- Configurable retry with exponential backoff (500→502→504 only)
- Per-request-type timeouts: Search=15s, Scrape=45s

### URL Deduplication
- SHA-256 hash of normalized URL (strips UTM params, lowercases)
- `url_cache` table with TTL-based expiration
- Cross-company dedup: same URL scraped once, reused for multiple companies

### Error Handling
| HTTP Code | Action |
|-----------|--------|
| 200 | Save content, report success to rate limiter |
| 429 | Double delay via `AdaptiveRateLimiter`, retry up to 3 times |
| 402 | `CriticalError` — stop pipeline (credits exhausted) |
| Timeout | Mark as `timeout` (or `skipped` for social media sources) |

---

## 5. Firecrawl (Legacy Search — `search_module.py`)

| Aspect | Detail |
|--------|--------|
| **Module** | `src/search_module.py` → `SearchModule` |
| **Endpoint** | `https://api.firecrawl.dev/v1/search` |
| **Status** | Retained but superseded by Gemini+Serper for Step 1-3 |

- Implements 2-tier search (broad query + refined query)
- SQLite query cache with configurable TTL
- Hash-based deduplication for search queries
- Credits: 1 per search call

---

## Integration Health Monitoring

| Metric | Location |
|--------|----------|
| Firecrawl credits used | `HealthMonitor.check_credits_remaining()` |
| Gemini daily quota | `daily_quota` table, checked pre-request |
| Serper daily quota | `daily_quota` table, incremented post-request |
| API latency | `pipeline_logs.duration_seconds`, JSONL logs |
| Error rates | `pipeline_logs` aggregated by `error_category` |
