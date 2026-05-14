# Debug Task 06: Abbreviation Stop Words

**Model:** Gemini 3 Flash | **File:** `src/search_module.py`, `src/config.py`

## Mục tiêu kiểm tra
Verify abbreviation bỏ stop words và nhận dạng abbreviation sẵn có.

## Lệnh kiểm tra
```bash
# 1. Check config
grep -n "ABBREVIATION_STOP_WORDS" src/config.py

# 2. Check logic
grep -A15 "def _compute_abbreviation" src/search_module.py
```

## Test cases
```python
# Chạy thủ công hoặc unit test:
assert _compute_abbreviation("ABC Software Co., Ltd") == "ABC"   # detect existing abbr
assert _compute_abbreviation("FPT Software") == "FPT"            # detect existing abbr
assert _compute_abbreviation("Hòa Phát Group Joint Stock") == "HPG"  # filter stop words
assert _compute_abbreviation("Vietnam Dairy Products") == "DP"    # filter "Vietnam"
assert _compute_abbreviation("A") is None                        # too short
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| "ASCL" thay vì "ABC" | Stop word filter không hoạt động | Check case-insensitive comparison |
| "FS" thay vì "FPT" | Edge case detection thiếu | Check logic: word len>=3 and word.isupper() |
| None cho mọi input | Filter quá aggressive | Check stop words list không chứa từ quan trọng |
