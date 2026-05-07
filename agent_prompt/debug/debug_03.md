# Debug Task 03: Filter Log Scoring

**Model:** Gemini 3 Flash | **File:** `src/filter_module.py`

## Mục tiêu kiểm tra
Verify JSONL log có `score_calculated` events cho mỗi URL được phân loại.

## Lệnh kiểm tra
```bash
# 1. Check log_event call tồn tại
grep -n "score_calculated" src/filter_module.py

# 2. Check JSONL output
grep "score_calculated" output/logs/pipeline_*.jsonl | head -3

# 3. Verify JSON structure
grep "score_calculated" output/logs/pipeline_*.jsonl | head -1 | python3 -m json.tool
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Không có `score_calculated` trong log | `log_event()` chưa được gọi | Thêm call sau `classify_url()` |
| Missing keys in log entry | Dict truyền thiếu fields | Check key names từ classify_url output |
| Log file quá lớn | Log cho mọi URL kể cả blacklisted | OK — cần log tất cả để debug |

## Debug steps
1. Chạy filter cho 1 company → check JSONL file
2. Count: `grep -c "score_calculated" pipeline_*.jsonl` — nên = số URLs found
3. Verify breakdown có đủ keys: domain, keyword, title
