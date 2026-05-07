# Debug Task 01: Early Stop Inline Scoring

**Model:** Gemini 3 Flash | **File:** `src/search_module.py`, `src/filter_module.py`

## Mục tiêu kiểm tra
Verify early stop hoạt động đúng: khi đủ URLs có score cao sau 1 tier → các tier sau bị skip.

## Lệnh kiểm tra
```bash
# 1. Check method score_urls_batch tồn tại
grep -n "def score_urls_batch" src/filter_module.py

# 2. Check search_module gọi score_urls_batch
grep -n "score_urls_batch" src/search_module.py

# 3. Check JSONL log có early_stop_triggered events
grep "early_stop_triggered" output/logs/pipeline_*.jsonl | head -5

# 4. Check early stop logic
grep -A5 "early_stop" src/search_module.py
```

## Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `score_urls_batch` not found | Method chưa được tạo | Kiểm tra filter_module.py có method mới không |
| `AttributeError: filter_module` | search_module không nhận filter_module | Kiểm tra `__init__` params |
| Early stop never triggers | Threshold quá cao hoặc scoring sai | Check config `EARLY_STOP_COUNT`, `EARLY_STOP_SCORE` |
| Early stop always triggers | Threshold quá thấp | Tăng `EARLY_STOP_SCORE` |
| Search results empty after change | Lỗi logic khi skip tier | Check return value khi early stop trigger |

## Debug steps
1. Chạy pipeline cho 1 company nhỏ → check JSONL có `early_stop_triggered`?
2. Nếu không trigger: in ra `qualified_count` và `threshold` để so sánh
3. Nếu crash: check traceback — thường là missing import hoặc wrong params
4. Verify `score_urls_batch` trả đúng format: list of dicts với key `relevance_score`
