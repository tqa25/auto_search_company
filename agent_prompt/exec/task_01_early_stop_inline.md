# Task 01: Fix Early Stop — Inline Scoring

**Model:** Gemini 3.1 Pro
**Files:** `src/search_module.py`, `src/filter_module.py`
**Phụ thuộc:** Không

## Bối cảnh
Hàm `_check_early_stop()` trong `search_module.py` query bảng `filtered_links` để kiểm tra xem đã có đủ kết quả chất lượng cao chưa. Tuy nhiên, bước filter chưa chạy tại thời điểm search → bảng `filtered_links` luôn trống → early stop KHÔNG BAO GIỜ hoạt động.

**Giải pháp:** Tích hợp inline scoring ngay trong quá trình search.

## Sub-task A: Thêm method `score_urls_batch()` vào FilterModule

**File:** `src/filter_module.py`
**Class:** `FilterModule`

**Thêm method mới:**
```
def score_urls_batch(self, urls: list[dict], company_name: str) -> list[dict]
```

**Input:**
```json
[
  {"url": "https://masothue.com/...", "title": "...", "snippet": "..."},
  {"url": "https://facebook.com/...", "title": "...", "snippet": "..."}
]
```

**Output:**
```json
[
  {"url": "...", "source_type": "masothue", "relevance_score": 65.0, "should_scrape": true,
   "breakdown": {"domain": 50, "keyword": 10, "title": 5}},
  ...
]
```

**Logic:**
1. Duyệt từng URL trong danh sách
2. Gọi `classify_url(url, company_name)` cho mỗi URL → lấy score
3. Trả về list đã scored, **KHÔNG ghi DB** (khác với `filter_company_links()`)
4. Method này phải lightweight — chỉ tính score, không persist

## Sub-task B: Hook inline scoring vào search tiers

**File:** `src/search_module.py`
**Function:** `search_company()`

**Thay đổi logic:**
1. Sau mỗi tier (T1, T2a, T2b, T2c) nhận kết quả search
2. Gọi `self.filter_module.score_urls_batch(results, company_name)` ngay
3. Kiểm tra: nếu có >= `EARLY_STOP_COUNT` URLs với score >= `EARLY_STOP_SCORE` → skip tiers còn lại
4. Log event `"early_stop_triggered"` khi skip:
```json
{"event": "early_stop_triggered", "company_id": 123, "tier": "T2a",
 "qualified_count": 5, "threshold": 3}
```

**Lưu ý:**
- `search_module.py` cần nhận `filter_module` instance qua constructor hoặc parameter
- Kiểm tra `__init__()` hiện tại có chấp nhận filter_module không — nếu không, thêm param
- Config keys đã có sẵn: `EARLY_STOP_COUNT`, `EARLY_STOP_SCORE` trong `config.py`

## Tiêu chí hoàn thành
- [ ] `score_urls_batch()` trả list scored URLs mà không ghi DB
- [ ] Sau mỗi search tier, inline scoring được thực hiện
- [ ] Early stop hoạt động: tier sau bị skip khi đủ điều kiện
- [ ] Log JSONL ghi event `early_stop_triggered` khi xảy ra
- [ ] Không break logic search hiện tại khi early stop KHÔNG trigger
