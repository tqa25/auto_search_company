# Debug Task 04: Logger Replay Fields

**Model:** Gemini 3 Flash | **Files:** `src/logger.py`, `src/search_module.py`

## Mục tiêu kiểm tra
Verify JSONL entries có `raw_request`, `network_latency_ms`, `raw_response_summary`.

## Lệnh kiểm tra
```bash
# 1. Check logger accepts new params
grep -n "raw_request\|network_latency_ms\|processing_time_ms\|raw_response_summary" src/logger.py

# 2. Check search_module passes raw_request
grep -n "raw_request" src/search_module.py

# 3. Check JSONL output
grep "step_start" output/logs/pipeline_*.jsonl | head -1 | python3 -m json.tool
grep "step_end" output/logs/pipeline_*.jsonl | head -1 | python3 -m json.tool
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `raw_request` missing in JSONL | Logger chấp nhận param nhưng không ghi | Check `log_event` dict construction |
| `network_latency_ms: null` | Timing chưa được tính | Wrap API call với `time.time()` before/after |
| `TypeError` khi gọi log_step_start | Signature thay đổi nhưng callers cũ không cập nhật | Đảm bảo `raw_request=None` default |

## Debug steps
1. Grep JSONL cho `raw_request` — nên có trong mọi search step_start
2. Check `network_latency_ms` > 0 cho non-cache-hit entries
3. Cache hit entries nên có `"cache_hit": true` trong raw_request
