# Kế hoạch nâng cấp Pipeline — Bản tổng hợp v4 (FINAL)

> Đã sửa theo tất cả review + tích hợp yêu cầu từ `prompt_upgrade_plan.md`

---

## I. Thay đổi từ review v2

| Feedback | Đã sửa |
|----------|--------|
| "Không loại trừ facebook/linkedin khỏi query" | ✅ Bỏ `-site:facebook.com -site:linkedin.com` |
| "Contact Page Discovery → bước cuối cùng, chỉ khi không cào được SĐT" | ✅ Chuyển thành bước cuối, sau AI Extract |
| "Bỏ phần test tự động" | ✅ Chỉ giữ test thủ công |
| "Ngưỡng dừng sớm → tùy chỉnh được" | ✅ `EARLY_STOP_COUNT` + `EARLY_STOP_SCORE` là config |
| "Facebook fallback < 3 link ≥ 40đ → OK" | ✅ Giữ nguyên |

---

## II. Quy trình tổng hợp v3

```
┌───────────────────────────────────────────────────────────────┐
│                     QUY TRÌNH MỚI (v4)                        │
│                                                               │
│  1. COARSE SEARCH (1 query rẻ, 2 credits)                    │
│     Tên CT + từ khóa liên hệ (GIỮ facebook/linkedin)         │
│     → Filter & Score → Đủ link tốt? → DỪNG                   │
│                                                               │
│  2. FALLBACK SEARCH (chỉ khi Bước 1 chưa đủ)                 │
│     2a. Query Tuyển dụng → Score → check                      │
│     2b. Query Tên viết tắt → Score → check                    │
│     2c. Facebook Search (khi < 3 link ≥ 40đ)                  │
│                                                               │
│  3. SMART SCRAPE (Top N, N cấu hình được)                     │
│     Chỉ cào Top N link điểm cao nhất                          │
│     Dedup: không cào lại URL đã cào                           │
│                                                               │
│  4. AI EXTRACT (giữ nguyên)                                    │
│     Trích xuất SĐT, Email, Địa chỉ                           │
│                                                               │
│  5. CONTACT PAGE DISCOVERY (bước cuối, fallback)               │
│     CHỈ khi AI Extract không tìm được SĐT nào                │
│     → Thử cào /contact, /lien-he, /about từ trang chủ CT     │
│     → AI Extract lại                                          │
│                                                               │
│  ═══ HẠ TẦNG MỚI (từ prompt_upgrade_plan.md) ═══             │
│                                                               │
│  6. DEDUP SYSTEM: Query dedup + URL dedup + Cross-company     │
│  7. ADVANCED LOGGING: JSON structured, time-focused           │
│  8. CONFIG SYSTEM: Tất cả tham số tùy chỉnh được             │
│  9. AUTO/MANUAL MODE: Chạy full hoặc từng bước               │
│ 10. WEB DASHBOARD: Quản lý pipeline qua trình duyệt          │
│ 11. MULTI-AGENT: Tách module thành agent độc lập              │
│ 12. REPLAY SYSTEM: Chạy lại từ cache, không tốn credits      │
└───────────────────────────────────────────────────────────────┘
```

---

## III. Chi tiết — Phần Search & Score (đã có từ v2, cập nhật)

### [MODIFY] [search_module.py](file:///home/baguf/workspaces/auto_search_company/src/search_module.py)

**Xóa:** 3 query cũ (Tax Code, English+Anchor, Vietnamese), `_translate_to_vietnamese()`, `ANCHOR_KEYWORDS`

**Thêm — Tầng 1 Coarse Search:**
```
("{TÊN TIẾNG ANH}" OR "{Tên tiếng Việt/TÊN VIẾT TẮT}") AND ("liên hệ" OR "contact")
```
- `limit` **cấu hình được** (mặc định 20), **KHÔNG loại trừ** facebook/linkedin
- Sau khi có kết quả → Filter & Score → kiểm tra early stop (ngưỡng cấu hình được)

**Thêm — Tầng 2 Fallback:** Query Tuyển dụng → Query Tên viết tắt → Facebook Search (khi < 3 link ≥ 40đ)

### [MODIFY] [filter_module.py](file:///home/baguf/workspaces/auto_search_company/src/filter_module.py)

**Blacklist (0đ, không cào):** `masothue.com`, `infocom.vn`, `xinvoice.vn`, `dauthau.info`, `dauthau.net`, `thuonghieuviet.info.vn`

**Bảng điểm Domain (cấu hình được, mặc định):** Trang chủ CT +40 | Tra cứu pháp lý +30 | Tuyển dụng +20 | MXH +10

**Bảng điểm Keyword (cấu hình được, mặc định):** Liên hệ **+10** | Admin/Hành chính **+10** | Tuyển dụng **+5** | ~~BĐS~~ BỎ

### [MODIFY] [scrape_module.py](file:///home/baguf/workspaces/auto_search_company/src/scrape_module.py)

- Cào Top N (N cấu hình được, mặc định 10)
- **Contact Page Discovery** chuyển thành **bước cuối** — chỉ chạy khi AI Extract không tìm được SĐT nào
- Khi kích hoạt: thử `/contact`, `/lien-he`, `/about` từ domain trang chủ CT → scrape → AI Extract lại

### [MODIFY] [database.py](file:///home/baguf/workspaces/auto_search_company/src/database.py) + [pipeline.py](file:///home/baguf/workspaces/auto_search_company/src/pipeline.py)

- Thêm cột `relevance_score` vào `filtered_links`
- Pipeline luồng mới: Search ↔ Score xen kẽ → Smart Scrape → AI Extract → (nếu không có SĐT) Contact Page Discovery

---

## IV. Chi tiết — Tính năng mới từ prompt_upgrade_plan.md

### 4.1 Deduplication System (CRITICAL)

> Hệ thống hiện tại có dedup cơ bản (check URL đã scrape trong `scrape_url()`). Cần nâng cấp toàn diện.

#### A. Query Dedup
- **Normalize query** (lowercase, bỏ dấu cách thừa, sort từ khóa) → tạo **hash SHA-256**
- Lưu hash vào bảng mới `query_cache` (hash, query_text, company_id, created_at, result_count)
- Trước khi gọi Firecrawl Search → check hash → nếu đã có → **skip, dùng kết quả cũ**
- Log: `"query_skipped_due_to_dedup"`

#### B. URL Dedup
- **Normalize URL** (lowercase domain, bỏ trailing slash, bỏ tracking params utm_*) → hash
- Bảng `url_cache` (url_hash, url, scrape_status, content_hash, scraped_at, ttl_expires_at)
- Trước khi scrape → check hash → nếu đã scrape thành công → **skip**
- Log: `"url_skipped_already_scraped"`

#### C. Cross-Company Dedup
- Nếu công ty B cần cào URL đã cào cho công ty A → **dùng lại nội dung**, không gọi Firecrawl
- Liên kết qua `url_cache` (shared across companies)

#### D. Cache Layer
- Cache search results + scraped content với **TTL cấu hình được** (mặc định 7 ngày)
- Config: `ENABLE_QUERY_DEDUP`, `ENABLE_URL_DEDUP`, `ENABLE_GLOBAL_CACHE`, `FORCE_REFRESH`
- `FORCE_REFRESH=true` → bỏ qua cache, chạy lại từ đầu (cho debug)

#### [NEW] Bảng DB mới
- `query_cache` — lưu query hash + kết quả
- `url_cache` — lưu URL hash + trạng thái scrape + TTL

---

### 4.2 Advanced Logging System

> Logger hiện tại (`PipelineLogger`) ghi vào DB + console. Cần nâng cấp thêm JSON structured log file.

#### [MODIFY] [logger.py](file:///home/baguf/workspaces/auto_search_company/src/logger.py)

**Thêm — JSON Log File** (song song với console log hiện tại):
- Mỗi event = 1 dòng JSON (JSONL format) → dễ cho AI đọc/debug
- File: `output/logs/pipeline_YYYY-MM-DD.jsonl`

**Các trường bắt buộc trong mỗi event:**

| Trường | Mô tả |
|--------|-------|
| `timestamp` | ISO 8601 với millisecond |
| `event_type` | `search_start`, `search_end`, `score_calculated`, `scrape_start`, `cache_hit`, `dedup_skip`... |
| `company_id` | |
| `start_time` / `end_time` | Cho mỗi operation |
| `duration_ms` | Tổng thời gian |
| `network_latency_ms` | Thời gian chờ API response |
| `processing_time_ms` | Thời gian xử lý nội bộ |
| `credits_used` | |
| `raw_request` | Query/URL gửi đi (cho replay) |
| `raw_response_summary` | Tóm tắt response (số kết quả, status code) |
| `scoring_breakdown` | `{domain_score: 40, keyword_scores: {contact: 10}}` |
| `dedup_action` | `null` / `query_cache_hit` / `url_cache_hit` |
| `fallback_reason` | Tại sao kích hoạt fallback |
| `retry_count` | |

**Tính năng Replayable:** Từ log file, có thể tái tạo lại toàn bộ luồng xử lý mà không cần gọi API.

---

### 4.3 Auto vs Manual Execution Mode

#### [MODIFY] [pipeline.py](file:///home/baguf/workspaces/auto_search_company/src/pipeline.py)

**Auto Mode (mặc định):**
- Chạy full pipeline: Search → Filter → Score → Scrape → AI Extract → Contact Discovery
- Tự động fallback, retry, dedup
- Dùng cho batch processing 6000 công ty

**Manual Mode:**
- Chạy từng bước riêng lẻ: `pipeline.run_step("search", company_id=123)`
- Inject custom data: `pipeline.inject_search_results(company_id, custom_urls)`
- Override config tạm thời: `pipeline.run(company_id=123, config_override={"TOP_N": 5})`
- Force skip dedup: `pipeline.run(company_id=123, force_refresh=True)` (debug only)

---

### 4.4 Config System

#### [NEW] config.py

Tất cả tham số cấu hình tập trung 1 file, đọc từ `.env` hoặc default:

| Nhóm | Config | Default | Mô tả |
|------|--------|---------|-------|
| **Search** | `SEARCH_LIMIT` | 20 | Số kết quả tối đa/query (cấu hình được) |
| | `EARLY_STOP_COUNT` | 5 | Dừng khi có N link chất lượng (cấu hình được) |
| | `EARLY_STOP_SCORE` | 40 | Ngưỡng điểm "chất lượng" (cấu hình được) |
| | `FB_FALLBACK_THRESHOLD` | 3 | Kích hoạt FB khi < N link ≥ score |
| **Scoring** | `DOMAIN_SCORES` | `{official:40, legal:30, job:20, social:10}` | Bảng điểm domain (cấu hình được) |
| | `KEYWORD_SCORES` | `{contact:10, admin:10, recruitment:5}` | Bảng điểm keyword (cấu hình được) |
| **Scrape** | `TOP_N` | 10 | Số link cào tối đa/công ty (cấu hình được) |
| | `CONTACT_DISCOVERY_ENABLED` | true | Bật/tắt Contact Page Discovery |
| | `CONTACT_PATHS` | `/contact,/lien-he,/about` | Đường dẫn con thử cào |
| **Dedup** | `ENABLE_QUERY_DEDUP` | true | |
| | `ENABLE_URL_DEDUP` | true | |
| | `ENABLE_GLOBAL_CACHE` | true | |
| | `CACHE_TTL_DAYS` | 7 | |
| | `FORCE_REFRESH` | false | Bỏ qua cache (debug) |
| **Rate Limit** | `DELAY_SECONDS` | 3.0 | Delay giữa các request |
| | `MAX_RETRIES` | 3 | |
| **Pipeline** | `EXECUTION_MODE` | auto | `auto` hoặc `manual` |
| | `BATCH_SIZE` | 10 | |

---

### 4.5 Web Dashboard

#### [NEW] Thư mục `dashboard/`

Dashboard web dùng **FastAPI** (async, nhanh) để quản lý pipeline:

**Trang chính:**
- Tiến độ tổng thể: X/6000 công ty đã xong
- Credits đã dùng / còn lại
- Tỷ lệ tìm được SĐT, Email

**Quản lý công ty:**
- Xem danh sách công ty + trạng thái (pending/searched/scraped/done/failed)
- Chạy lại 1 công ty cụ thể
- Xem log chi tiết cho từng công ty

**Điều khiển pipeline:**
- Start/Stop/Pause pipeline
- Chuyển Auto ↔ Manual mode
- Chỉnh config trực tiếp trên web
- Chạy từng bước (Search/Filter/Scrape/Extract) cho 1 công ty

**Xem log:**
- Realtime log stream (JSONL)
- Filter theo company_id, step, status
- Xem scoring breakdown cho từng link

---

### 4.6 Multi-Agent Task Decomposition

> Hiện tại các module đã tách rời (SearchModule, LinkFilter, ScrapeModule, AIExtractor). Cần chuẩn hóa thành "Agent" với input/output schema rõ ràng.

**Mục tiêu:** Giảm hallucination AI, tránh context overflow, cải thiện chất lượng output.

#### Thiết kế Agent:

| Agent | File hiện tại | Input | Output |
|-------|--------------|-------|--------|
| **Agent 1 — Search** | `search_module.py` | `{company_id, company_name, config}` | `{search_results: [{url, title, snippet}], credits_used}` |
| **Agent 2 — Filter & Score** | `filter_module.py` | `{search_results, config}` | `{scored_links: [{url, score, breakdown}], early_stop: bool}` |
| **Agent 3 — Scraper** | `scrape_module.py` | `{top_links: [{url, score}], config}` | `{scraped_pages: [{url, markdown, status}], credits_used}` |
| **Agent 4 — AI Extractor** | `ai_extractor.py` | `{scraped_pages: [{markdown, source_type}]}` | `{contacts: [{phone, email, address, confidence}]}` |
| **Agent 5 — Orchestrator** | `pipeline.py` | `{company_id, mode, config}` | `{status, steps_completed, fallbacks_triggered}` |
| **Agent 6 — Logger** | `logger.py` | `{event}` | `{logged: true}` + file write |
| **Agent 7 — Debug** | `debug_agent.py` [NEW] | `{company_id, log_filter}` | `{root_cause, affected_steps, suggestion}` |

**Agent 7 — Debug** chi tiết:
- **Đọc log:** Đọc JSONL log file, filter theo company_id / step / time range
- **Phân tích cross-step:** So sánh output step A vs input step B → phát hiện data bị mất/sai giữa các bước
- **Tìm root cause:** Khi 1 công ty failed → truy ngược log → chỉ ra bước nào lỗi đầu tiên và tại sao
- **Gợi ý sửa:** Đề xuất config thay đổi hoặc retry strategy dựa trên pattern lỗi

**Quy tắc:**
- Mỗi agent có **strict input/output JSON schema**
- Không agent nào biết toàn bộ context hệ thống
- Orchestrator (Agent 5) điều phối, quyết định fallback/retry
- Mỗi agent có **error format** chuẩn: `{error_code, error_message, recoverable: bool}`

---

### 4.7 Replay System

> Tránh gọi lại Firecrawl/Gemini khi debug hoặc chạy lại pipeline.

**Replay từ Search results:** Đọc từ `query_cache` + `search_results` DB → skip Firecrawl Search

**Replay từ Scraped content:** Đọc từ `url_cache` + `scraped_pages` DB → skip Firecrawl Scrape

**Replay từ AI outputs:** Đọc từ `extracted_contacts` DB → skip Gemini API

**Cách dùng:** `pipeline.run(company_id=123, replay_mode=True)` — chạy lại toàn bộ logic nhưng dùng data từ cache, **0 credits**.

---

## V. Những gì KHÔNG làm

| Ý tưởng | Lý do bỏ |
|----------|----------|
| Query cũ (Tax Code, English+Anchor, Vietnamese) | Kết quả chủ yếu là domain đã blacklist |
| masothue, infocom, xinvoice... | Cào về không có SĐT |
| Keyword "BĐS/Văn phòng" | Không liên quan mục tiêu |
| Facebook URL classifier (post/page/group) | Phức tạp, giá trị thấp |
| LinkedIn scraping | Firecrawl bị chặn |

---

## VI. Thứ tự triển khai

| Bước | Mô tả | File | Độ khó |
|------|-------|------|--------|
| 1 | Config System | `config.py` [NEW] | ⭐ |
| 2 | Database: thêm cột + bảng dedup | `database.py` | ⭐ |
| 3 | Dedup System | `search_module.py`, `scrape_module.py` | ⭐⭐ |
| 4 | Scoring System | `filter_module.py` | ⭐⭐ |
| 5 | Search 2 tầng | `search_module.py` | ⭐⭐⭐ |
| 6 | Smart Scrape + Contact Discovery | `scrape_module.py` | ⭐⭐ |
| 7 | Advanced Logging (JSONL) | `logger.py` | ⭐⭐ |
| 8 | Pipeline orchestration + Auto/Manual | `pipeline.py` | ⭐⭐⭐ |
| 9 | Multi-Agent interface contracts | Tất cả module | ⭐⭐ |
| 10 | Replay System | `pipeline.py` | ⭐⭐ |
| 11 | Web Dashboard | `dashboard/` [NEW] | ⭐⭐⭐ |
| 12 | Test thủ công với 2-3 công ty mẫu | — | ⭐⭐ |

---

## VII. Kiểm tra sau khi xong

- Thử pipeline với 2-3 công ty mẫu (lớn/vừa/nhỏ)
- Xác nhận blacklist domain KHÔNG xuất hiện trong danh sách cào
- Xác nhận dedup hoạt động (chạy 2 lần, lần 2 phải skip)
- Xác nhận Contact Page Discovery chỉ kích hoạt khi không có SĐT
- Xác nhận JSONL log file được tạo đúng format
- So sánh credits trước/sau

---

## VIII. Các quyết định đã chốt

| Câu hỏi | Quyết định |
|----------|------------|
| Contact Page Discovery paths | `/contact`, `/lien-he`, `/about` — sau này thêm được qua config |
| Web Dashboard framework | **FastAPI** |
| Cache TTL | **7 ngày** mặc định |
| Ngưỡng dừng sớm | **Cấu hình được** qua `EARLY_STOP_COUNT` + `EARLY_STOP_SCORE` |
| Top N | **Cấu hình được** qua `TOP_N` |
| Bảng điểm Domain/Keyword | **Cấu hình được** qua `DOMAIN_SCORES` + `KEYWORD_SCORES` |
| Search limit | **Cấu hình được** qua `SEARCH_LIMIT` |
| Facebook fallback | Kích hoạt khi < 3 link ≥ 40đ |
