# Task 03: Filter — Log Scoring Breakdown

**Model:** Gemini 3.1 Pro
**File:** `src/filter_module.py`
**Phụ thuộc:** Không

## Bối cảnh
`classify_url()` tính `score_breakdown` (dict chứa domain score, keyword bonus, etc.) nhưng chỉ trả về — **không log** vào JSONL. Khi debug "tại sao URL X bị bỏ?", phải đọc source code.

## Thay đổi

### Trong `filter_company_links()`:
Sau mỗi lần gọi `classify_url()`, thêm log event:
```python
self.logger.log_event("score_calculated", company_id, {
    "url": url,
    "source_type": classification["source_type"],
    "relevance_score": classification["relevance_score"],
    "should_scrape": classification["should_scrape"],
    "breakdown": classification.get("score_breakdown", {}),
    "reason": classification.get("reason", "")
})
```

## Input/Output
- **Input:** Không thay đổi interface
- **Output JSONL mới:**
```json
{"timestamp": "...", "event": "score_calculated", "company_id": 123,
 "url": "https://masothue.com/...", "source_type": "masothue",
 "relevance_score": 65.0, "should_scrape": true,
 "breakdown": {"domain": 50, "keyword": 10, "title": 5}}
```

## Lưu ý
- Kiểm tra `classify_url()` trả về key nào — dùng đúng key names
- Log **tất cả** URLs (cả should_scrape=true và false) để debug đầy đủ
- Không thay đổi logic scoring hiện có

## Tiêu chí hoàn thành
- [x] Mỗi URL qua classify_url đều có log entry `score_calculated`
- [x] Log chứa đủ: url, source_type, score, breakdown, should_scrape
- [x] File JSONL có thể grep `score_calculated` để xem scoring history
