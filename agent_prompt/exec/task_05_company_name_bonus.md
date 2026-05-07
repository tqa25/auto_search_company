# Task 05: Filter — Company Name Matching Bonus

**Model:** Gemini 3.1 Pro
**File:** `src/filter_module.py`, `src/config.py`
**Phụ thuộc:** Task 01 (score_urls_batch cần name matching)

## Bối cảnh
Mọi domain không nằm trong `KNOWN_DOMAINS` đều nhận score `official` (+40). Tức `abc-random-blog.com` cũng +40 giống `companyname.com.vn`. Cần bonus cho domain chứa tên công ty.

## Thay đổi

### 1. Config (`src/config.py`)
Thêm vào `DOMAIN_SCORES`:
```python
"name_match": int(os.getenv("DOMAIN_SCORE_NAME_MATCH", "15"))
```

### 2. Filter logic (`src/filter_module.py`)

Trong `classify_url()`, sau khi tính domain score, thêm name matching check:

```
Input: url, company_name (đã có sẵn trong method params)
Logic:
  1. Lấy domain từ URL (dùng urlparse)
  2. Normalize company_name: lowercase, bỏ dấu, bỏ stop words (Co., Ltd, etc.)
  3. Normalize domain: bỏ .com, .vn, .com.vn, www.
  4. Nếu normalized_company_name (hoặc abbreviation) xuất hiện trong normalized_domain:
     → Thêm bonus DOMAIN_SCORES["name_match"] (+15)
  5. Ghi vào score_breakdown: {"name_match": 15} hoặc {"name_match": 0}
```

### Ví dụ:
| Company | URL | Name Match | Bonus |
|---|---|---|---|
| Vietnam Dev Corp (VDC) | `vdc.com.vn` | ✅ "vdc" in domain | +15 |
| FPT Software | `fpt.com.vn/contact` | ✅ "fpt" in domain | +15 |
| ABC Corp | `random-blog.com/abc-tuyen-dung` | ❌ "abc" not in domain | +0 |

## Input/Output
- **Input:** Không thay đổi interface — `classify_url(url, company_name)`
- **Output:** `score_breakdown` thêm key `name_match`

## Tiêu chí hoàn thành
- [ ] Config có `DOMAIN_SCORE_NAME_MATCH` (default 15)
- [ ] Domain chứa tên công ty/abbreviation → +15 bonus
- [ ] score_breakdown luôn chứa key `name_match` (0 hoặc 15)
- [ ] Không ảnh hưởng scoring cho KNOWN_DOMAINS (masothue, etc.)
