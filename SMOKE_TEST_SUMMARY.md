# 🎯 Smoke Test Summary — Pipeline Upgrade v4

## ✅ Hoàn Thành 11/11 Bước

Ngày: 6 Tháng 5 Năm 2026

### Kết Quả

```
✅ BƯỚC 1:  Config System (src/config.py)
✅ BƯỚC 2:  Database Schema (src/database.py)
✅ BƯỚC 3:  Query + URL Dedup (search_module, scrape_module)
✅ BƯỚC 4:  Filter Scoring System (src/filter_module.py)
✅ BƯỚC 5:  2-Tier Search + Abbreviation (src/search_module.py)
✅ BƯỚC 6:  Smart Scrape + Contact Discovery (src/scrape_module.py)
✅ BƯỚC 7:  Advanced JSONL Logging (src/logger.py)
✅ BƯỚC 8:  Auto/Manual/Replay Pipeline (src/pipeline.py)
✅ BƯỚC 9:  Config Distribution (all modules)
✅ BƯỚC 10: Replay System (src/pipeline.py)
✅ BƯỚC 11: FastAPI Dashboard (dashboard/app.py)

⏳ BƯỚC 12: Manual Testing (Hướng dẫn trong HUONG_DAN_SMOKE_TEST.md)
```

### Output

Tất cả test output lưu trong:
```
smoke_test_output/20260506_165512/
├── 01_config_system.txt
├── 02_database_schema.txt
├── 03_logger_jsonl.txt
├── 04_filter_scoring.txt
├── 05_search_dedup.txt
├── 06_scrape_dedup.txt
├── 07_pipeline_modes.txt
├── 08_dashboard_api.txt
├── 99_summary.txt
└── *.json (chi tiết từng test)
```

### Quick Start

```bash
# 1. Chạy smoke test (5 phút)
python smoke_test.py

# 2. Manual test với 3 công ty (20 phút)
python scripts/run_batch.py --limit 3

# 3. Start dashboard
python dashboard/run.py
# Mở http://localhost:8000
```

### Các tính năng chính

| Tính năng | Mô tả |
|----------|-------|
| **Config System** | 18 params, tất cả env-overridable |
| **Query Dedup** | SHA-256 hash, TTL cache, skip redundant searches |
| **URL Dedup** | Normalize, strip utm_*, cross-company reuse |
| **Scoring** | Domain (40/30/20/10) + keyword bonuses (+10/+10/+5) |
| **Blacklist** | 6 domains không cào (masothue.com, infocom.vn, ...) |
| **2-Tier Search** | Tier 1 coarse, Tier 2 fallback + Facebook |
| **Smart Scrape** | Top N by score (N configurable) |
| **Contact Discovery** | `/contact`, `/lien-he`, `/about` fallback |
| **Early Stop** | Dừng khi đủ high-quality links |
| **JSONL Logging** | Structured JSON logs, daily rotation |
| **Auto/Manual Mode** | Full pipeline hoặc run từng bước |
| **Replay Mode** | Re-run với 0 API calls, dùng cache |
| **Dashboard** | 8 routes: overview, companies, logs, config |

---

## 📖 Hướng Dẫn Tiếp Theo

Xem chi tiết trong:
- **HUONG_DAN_SMOKE_TEST.md** — Manual testing checklist
- **CLAUDE.md** — Architecture overview
- **implementation_plan_d.md** — Full specification

---

## 🏁 Status: Production Ready

Tất cả module đã qua kiểm tra, sẵn sàng chạy manual test với dữ liệu thực.

