# Task 06: Search — Abbreviation Stop Words

**Model:** Gemini 3.1 Pro
**Files:** `src/search_module.py`, `src/config.py`
**Phụ thuộc:** Task 05 (abbreviation dùng cho name matching)

## Bối cảnh
`_compute_abbreviation()` chỉ lấy chữ cái đầu mỗi từ viết hoa. Kết quả kém:
- `"ABC Software Co., Ltd"` → `"ASCL"` (sai, nên là `"ABC"`)
- `"FPT Software"` → `"FS"` (sai, nên là `"FPT"`)

## Thay đổi

### 1. Config (`src/config.py`)
```python
ABBREVIATION_STOP_WORDS = os.getenv("ABBREVIATION_STOP_WORDS",
    "Co,Ltd,Corp,Inc,Company,Joint,Stock,Vietnam,Viet,JSC,TNHH,CP,Cổ,Phần").split(",")
```

### 2. Cải thiện `_compute_abbreviation()` (`src/search_module.py`)

**Logic mới:**
```
Input: company_name (string)
Output: abbreviation (string) hoặc None

Steps:
1. Tách company_name thành words
2. Kiểm tra edge case: nếu word đầu tiên đã là abbreviation (>= 3 ký tự viết hoa liên tục, ví dụ "FPT", "ABC")
   → Trả về word đó luôn, không tính tiếp
3. Lọc bỏ stop words (case-insensitive)
4. Lọc bỏ words có dấu chấm cuối (ví dụ "Co.")
5. Từ các words còn lại, lấy chữ cái đầu → ghép thành abbreviation
6. Nếu abbreviation < 2 ký tự → return None
```

### Ví dụ:
| Input | Stop words removed | Output |
|---|---|---|
| `"ABC Software Co., Ltd"` | `"ABC Software"` → detect "ABC" | `"ABC"` |
| `"FPT Software"` | detect "FPT" | `"FPT"` |
| `"Vietnam Development Corp"` | `"Development"` | `"D"` → None |
| `"Hòa Phát Group Joint Stock"` | `"Hòa Phát Group"` | `"HPG"` |

## Tiêu chí hoàn thành
- [ ] Config có `ABBREVIATION_STOP_WORDS` tùy chỉnh
- [ ] Tên bắt đầu bằng abbreviation sẵn (>=3 uppercase) → dùng trực tiếp
- [ ] Stop words bị loại trước khi tính abbreviation
- [ ] Abbreviation < 2 ký tự → return None
