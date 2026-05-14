# Debug Task 05: Company Name Matching Bonus

**Model:** Gemini 3 Flash | **File:** `src/filter_module.py`, `src/config.py`

## Mục tiêu kiểm tra
Verify domain chứa tên công ty/abbreviation nhận bonus +15.

## Lệnh kiểm tra
```bash
# 1. Check config
grep -n "NAME_MATCH\|name_match" src/config.py

# 2. Check filter logic
grep -n "name_match" src/filter_module.py

# 3. Check JSONL — breakdown nên có name_match key
grep "score_calculated" output/logs/pipeline_*.jsonl | grep "name_match" | head -3
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| name_match luôn = 0 | Normalization quá strict | Check lowercase + remove diacritics logic |
| name_match cho mọi URL | Normalization quá loose | Check chỉ match trên domain, không path |
| `KeyError` | Config chưa thêm key | Thêm `DOMAIN_SCORE_NAME_MATCH` vào config.py |

## Debug steps
1. Test thủ công: company "FPT Software" + URL "fpt.com.vn" → nên có name_match=15
2. Test negative: company "FPT" + URL "google.com" → name_match=0
3. Check score_breakdown trong JSONL log có key `name_match`
