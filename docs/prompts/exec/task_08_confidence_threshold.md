# Task 08: Confidence Threshold

**Model:** Gemini 3.1 Pro
**Files:** `src/ai_extractor.py`, `src/config.py`
**Phụ thuộc:** Task 07 (AI extractor đã được tối ưu)

## Bối cảnh
AI trả `confidence` score (0.0-1.0) nhưng pipeline không dùng nó để filter kết quả kém hoặc chọn "best" contact khi nhiều nguồn mâu thuẫn.

## Thay đổi

### 1. Config (`src/config.py`)
```python
MIN_CONFIDENCE_THRESHOLD = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.3"))
```

### 2. Trong `extract_from_page()` (`src/ai_extractor.py`)
Sau khi parse JSON từ AI, thêm check:
```
if confidence < Config.MIN_CONFIDENCE_THRESHOLD:
    log_event("low_confidence_extraction", {confidence, page_id, source_type})
    # Vẫn lưu DB nhưng đánh dấu low_confidence
```

### 3. Trong `extract_for_company()` (`src/ai_extractor.py`)
Sau khi extract tất cả pages, thêm logic chọn best contact:
```
Khi có nhiều nguồn cho cùng 1 field:
  → Ưu tiên nguồn có confidence cao nhất
  → Log: {"event": "contact_conflict_resolved", "field": "phone",
          "chosen_source": "masothue", "confidence": 0.9,
          "rejected_source": "facebook", "confidence": 0.4}
```

## Input/Output
- **Input:** Không thay đổi interface
- **Output JSONL mới:**
```json
{"event": "low_confidence_extraction", "company_id": 123,
 "confidence": 0.2, "source_type": "facebook", "page_id": 456}
```

## Tiêu chí hoàn thành
- [ ] Config có `MIN_CONFIDENCE_THRESHOLD` (default 0.3)
- [ ] Low confidence extractions được log warning
- [ ] Khi nhiều nguồn conflict → chọn confidence cao nhất
- [ ] Log event `contact_conflict_resolved` khi resolve
