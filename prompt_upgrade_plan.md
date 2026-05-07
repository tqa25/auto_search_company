You are an AI Architect and Senior Backend Engineer specializing in automation pipelines, scraping systems, and AI integrations.

I am building a company data extraction system (Search → Filter → Scrape → AI Extract → Export) using Firecrawl and Google Gemini, processing ~6,000 companies.

---

# 🎯 TASK

Design a production-ready system including:

1. Web-based Management Dashboard
2. Advanced Logging System (AI-debug friendly, time-focused)
3. Auto vs Manual Execution Modes
4. Configurable Parameters
5. Smart URL Scoring
6. Deduplication System (critical)
7. Multi-Agent Task Decomposition (critical)

---

# 1. WEB DASHBOARD

(keep full pipeline + step-level execution control)

---

# 2. ADVANCED LOGGING SYSTEM

## REQUIREMENTS:

### TIME-FOCUSED:

* timestamp (ISO 8601 ms)
* start_time / end_time
* duration_ms
* queue_wait_time
* network_latency
* processing_time

---

### MUST INCLUDE:

* raw_request / raw_response
* scoring breakdown
* filtering reasoning
* fallback trigger reason
* retry count
* credits_used

---

### AI-FRIENDLY:

* JSON structured
* one event per line
* replayable

---

# 3. AUTO vs MANUAL EXECUTION

### AUTO MODE:

* full pipeline
* auto fallback
* auto retry

---

### MANUAL MODE:

* run individual steps
* inject custom data
* override configs
* force skip dedup (debug only)

---

# 4. CONFIG SYSTEM

(keep all previous config groups)

---

# 5. SMART SCORING

(keep same logic)

---

# 6. ❌ DEDUPLICATION SYSTEM (CRITICAL)

System must guarantee:

## NEVER:

* re-run the same query
* re-scrape the same URL

---

## DESIGN:

### A. QUERY DEDUP

* normalize + hash query
* store in DB
* skip if exists

---

### B. URL DEDUP

* normalize URL
* hash URL
* track status + timestamp

---

### C. CROSS-COMPANY DEDUP

* reuse scraped data if same domain

---

### D. CACHE LAYER

* cache:

  * search results
  * scraped content
* configurable TTL

---

### E. CONFIG:

* ENABLE_QUERY_DEDUP
* ENABLE_URL_DEDUP
* ENABLE_GLOBAL_CACHE
* FORCE_REFRESH

---

### F. LOGGING:

* "query_skipped_due_to_dedup"
* "url_skipped_already_scraped"
* "cache_hit"

---

# 7. REPLAY SYSTEM

Must support replay from:

* search results
* scraped content
* AI outputs

→ avoid re-calling Firecrawl

---

# 8. 🧩 MULTI-AGENT TASK DECOMPOSITION (CRITICAL)

## GOAL:

* reduce hallucination
* avoid context overflow
* improve output quality

---

## AGENTS:

### Agent 1 — Search Engine

* query generation
* bilingual logic

---

### Agent 2 — URL Filter & Scoring

* score URLs
* select candidates
* explain reasoning

---

### Agent 3 — Scraper

* fetch content
* clean HTML

---

### Agent 4 — AI Extractor

* extract structured data

---

### Agent 5 — Orchestrator

* manage pipeline
* fallback logic
* retries

---

### Agent 6 — Logger / Analyzer

* analyze logs
* suggest optimizations

---

## RULES:

* each agent:

  * strict input/output schema
* no agent has full system context

---

## INTERFACE CONTRACT:

Each agent must define:

* input JSON schema
* output JSON schema
* error format

---

# 9. REQUIRED OUTPUT

Provide:

1. System architecture (text diagram)
2. Database schema (jobs, logs, dedup, cache)
3. Full config list with defaults
4. Execution flow (auto + manual + fallback + dedup)
5. Sample detailed JSON logs
6. Agent design + interface contracts
7. Trade-offs in tuning parameters

---

# IMPORTANT

* No duplicate queries or scraping
* Optimize Firecrawl cost
* Designed for AI debugging (OpenCode / Claude Code)
* Practical and implementable
* Avoid over-engineering
