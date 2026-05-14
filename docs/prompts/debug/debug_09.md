# Debug Task 09: Error Classification

**Model:** Gemini 3 Flash | **Files:** `src/errors.py`, `src/pipeline.py`

## Mục tiêu kiểm tra
3 loại error được xử lý khác nhau: Retryable (retry), Skippable (skip), Critical (stop).

## Lệnh kiểm tra
```bash
# 1. errors.py tồn tại
cat src/errors.py

# 2. Pipeline import errors
grep -n "from src.errors import\|RetryableError\|SkippableError\|CriticalError" src/pipeline.py

# 3. Modules raise correct types
grep -n "RetryableError\|SkippableError\|CriticalError" src/search_module.py src/scrape_module.py src/ai_extractor.py

# 4. JSONL error_category
grep "error_category" output/logs/pipeline_*.jsonl | head -3
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `ImportError: errors` | File chưa tạo hoặc sai path | Check `src/errors.py` exists |
| CriticalError không stop pipeline | `raise` bị catch ở except khác | Đặt `except CriticalError` TRƯỚC `except Exception` |
| RetryableError loop vô hạn | Retry count không tăng | Check retry counter logic |
| Mọi lỗi thành "unknown" | Modules không raise custom errors | Check modules import và raise đúng type |

## Debug steps
1. Simulate HTTP 429 → verify RetryableError → pipeline retries
2. Simulate HTTP 402 → verify CriticalError → pipeline stops
3. Simulate invalid data → verify SkippableError → pipeline continues
4. Check JSONL: `error_category` có giá trị đúng (retryable/skippable/critical/unknown)
