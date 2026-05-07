# Hướng Dẫn Smoke Test — Pipeline Upgrade v4

## ✅ Các bước đã hoàn thành

Tất cả **11 bước** từ `implementation_plan_d.md` đã được triển khai:

| Bước | Module | Trạng thái |
|------|--------|-----------|
| 1 | `src/config.py` — Config system | ✅ Xong |
| 2 | `src/database.py` — DB schema | ✅ Xong |
| 3 | `src/search_module.py` + `src/scrape_module.py` — Dedup | ✅ Xong |
| 4 | `src/filter_module.py` — Scoring | ✅ Xong |
| 5 | `src/search_module.py` — 2-tier search | ✅ Xong |
| 6 | `src/scrape_module.py` — Smart scrape + Contact discovery | ✅ Xong |
| 7 | `src/logger.py` — JSONL logging | ✅ Xong |
| 8 | `src/pipeline.py` — Auto/Manual + Replay | ✅ Xong |
| 9 | Tất cả module — Config distribution | ✅ Xong |
| 10 | `src/pipeline.py` — Replay system | ✅ Xong |
| 11 | `dashboard/` — FastAPI web UI | ✅ Xong |
| **12** | **Manual testing** | ⏳ **Bước tiếp theo** |

---

## 🚀 Chạy Smoke Test (Bước 12)

### A. Smoke Test Tự động (5 phút)

Kiểm tra tất cả 8 bước triển khai:

```bash
python smoke_test.py
```

**Output:** Lưu vào `smoke_test_output/TIMESTAMP/`
- Tất cả các file `.txt` + `.json` chi tiết
- JSONL test logs tại `logs/pipeline_*.jsonl`
- Test database tại `test_smoke.db`

---

### B. Manual Testing với Dữ Liệu Thực (20-30 phút)

#### Chuẩn bị:
1. Tạo file Excel đầu vào với **3 công ty**:
   - 1 công ty **lớn** (multinational): VNDirect, Samsung, LG
   - 1 công ty **vừa** (local SME): công ty chạy dịch vụ IT local
   - 1 công ty **nhỏ** (startup): startup fintech local

2. Tạo `.env` test nếu cần:
```bash
FIRECRAWL_API_KEY=your_test_key
GEMINI_API_KEY=your_test_key
```

#### Chạy pipeline:

```bash
# Bước 1: Dry-run (không tốn credits)
python scripts/run_batch.py --limit 3 --dry-run

# Bước 2: Chạy thực
python scripts/run_batch.py --limit 3
```

#### Kiểm tra kết quả:

**1. Verify blacklist:**
```bash
# Kiểm tra: masothue.com, infocom.vn KHÔNG xuất hiện trong cào
sqlite3 data/company_data.db \
  "SELECT DISTINCT source_type FROM scraped_pages WHERE company_id IN (1,2,3);" 
```
❌ Không nên có: `masothue`, `infocom`, `xinvoice`, `dauthau`

**2. Verify dedup:**
```bash
# Chạy lần 2 (resume)
python scripts/run_batch.py --resume --limit 3

# Kiểm tra: lần 2 phải skip do cache
sqlite3 data/company_data.db \
  "SELECT COUNT(*) FROM pipeline_logs WHERE step='search' AND status='success';"
```
✅ Lần 2 phải ít hơn lần 1 (due to query/URL cache)

**3. Verify scoring:**
```bash
# Kiểm tra relevance_score
sqlite3 data/company_data.db \
  "SELECT url, relevance_score FROM filtered_links LIMIT 5;"
```
✅ Phải có scores: 40 (official), 30 (legal), 20 (job), 10 (social)

**4. Verify JSONL logs:**
```bash
# Xem JSONL logs hôm nay
tail -10 output/logs/pipeline_*.jsonl | jq '.'
```
✅ Nên thấy: `step_start`, `step_end`, `dedup_query_cache_hit`, `early_stop_*`

**5. Verify Contact Discovery:**
```bash
# Kiểm tra: có scraped_pages với source_type='contact_page'?
sqlite3 data/company_data.db \
  "SELECT COUNT(*) FROM scraped_pages WHERE source_type='contact_page';"
```
✅ Nếu có phone được trích → 0 contact_page
❌ Nếu KHÔNG có phone → phải thử `/contact`, `/lien-he`, `/about`

**6. Kiểm tra extracted_contacts:**
```bash
sqlite3 data/company_data.db \
  "SELECT company_id, source_type, phone, email FROM extracted_contacts LIMIT 5;"
```
✅ Nên có phone/email được trích từ các source tốt

---

## 💻 Sử Dụng Dashboard

```bash
# Start dashboard
python dashboard/run.py

# Hoặc với tuỳ chọn
python dashboard/run.py --port 8080 --reload
```

**Mở:** http://localhost:8000

### Các trang chính:

| Trang | Chức năng |
|-------|----------|
| **Dashboard** (`/`) | Tổng quan: progress, credits, stats |
| **Companies** (`/companies`) | Danh sách công ty, filter by status, re-run |
| **Logs** (`/logs`) | JSONL logs viewer (realtime) |
| **Config** (`/config`) | Xem/sửa config trực tiếp |

---

## 🎯 Checklist Verification

Sau khi chạy smoke test + manual test:

- [ ] **Config System**: 18 config values loaded từ .env
- [ ] **Database**: query_cache + url_cache tables tạo được
- [ ] **Logger JSONL**: file pipeline_*.jsonl tạo hàng ngày
- [ ] **Filter Scoring**: Domain scores (40/30/20/10) + keyword bonuses
- [ ] **Blacklist**: masothue.com, infocom.vn, xinvoice.vn KHÔNG cào
- [ ] **Dedup Search**: Query dedup working (hash check)
- [ ] **Dedup URL**: URL dedup working (hash check)
- [ ] **Search 2-tier**: Tier 1 coarse + Tier 2 fallback
- [ ] **Smart Scrape**: Chỉ top N link by score
- [ ] **Contact Discovery**: Chỉ kích hoạt khi no phone found
- [ ] **Early Stop**: Dừng khi đủ link chất lượng
- [ ] **Pipeline Flow**: search → filter → scrape → ai_extract → contact_discovery → done
- [ ] **Auto Mode**: Chạy full tự động
- [ ] **Manual Mode**: `run_step()` từng bước riêng
- [ ] **Replay Mode**: `replay_mode=True` = 0 API calls
- [ ] **Dashboard Routes**: Tất cả 8 route working

---

## 📊 Output Files

**Smoke Test Output:**
```
smoke_test_output/TIMESTAMP/
├── 01_config_system.txt
├── 01_config_values.json
├── 02_database_schema.txt
├── 02_database_tables.json
├── 03_logger_jsonl.txt
├── 04_filter_scoring.txt
├── 04_filter_scoring_results.json
├── 05_search_dedup.txt
├── 05_search_abbreviations.json
├── 05_search_hashes.json
├── 06_scrape_dedup.txt
├── 06_scrape_url_hashes.json
├── 07_pipeline_modes.txt
├── 07_pipeline_status_flow.json
├── 08_dashboard_api.txt
├── 08_dashboard_routes.json
├── logs/pipeline_*.jsonl
└── test_smoke.db
```

**Manual Test Output:**
```
output/
├── batch_report_*.xlsx        — Final report
├── batch_log_*.csv            — CSV log
└── logs/
    └── pipeline_*.jsonl       — JSONL logs
```

---

## 🔧 Troubleshooting

| Vấn đề | Cách sửa |
|--------|---------|
| `ModuleNotFoundError: No module named 'fastapi'` | `pip install fastapi uvicorn jinja2 python-multipart` |
| `No phone found` cho company | Contact Discovery sẽ kích hoạt, cào `/contact`, `/lien-he`, `/about` |
| Dedup không hoạt động | Check: `ENABLE_QUERY_DEDUP=true` + `ENABLE_URL_DEDUP=true` in .env |
| JSONL logs không tạo | Check: `output/logs/` folder có tồn tại không |
| Dashboard not starting | `python dashboard/run.py --port 8080 --reload` (debug mode) |

---

## 📝 Lệnh Nhanh

```bash
# Smoke test tự động
python smoke_test.py

# Manual test: dry-run (không tốn credits)
python scripts/run_batch.py --limit 3 --dry-run

# Manual test: chạy thực
python scripts/run_batch.py --limit 3

# Resume (tiếp tục từ lần trước)
python scripts/run_batch.py --resume --limit 3

# Replay mode (0 API calls)
python scripts/run_batch.py --limit 3 --replay  # (nếu script hỗ trợ)

# Dashboard
python dashboard/run.py

# SQL check
sqlite3 data/company_data.db ".tables"
sqlite3 data/company_data.db "SELECT COUNT(*) FROM companies WHERE status='done';"

# View JSONL logs
tail -20 output/logs/pipeline_*.jsonl | jq '.'
```

---

## ✨ Kết Luận

**Tất cả 11 bước đã xong, sẵn sàng dùng:**
- ✅ Config system: tất cả tham số tùy chỉnh
- ✅ Dedup: tiết kiệm credits
- ✅ Scoring: tìm được link tốt trước
- ✅ Manual + Replay: debug dễ
- ✅ Dashboard: quản lý pipeline dễ dàng

**Step 12 (Manual Testing):** Chạy smoke test + test với 3 công ty thực để verify tất cả features.

🎉 **Done!**
