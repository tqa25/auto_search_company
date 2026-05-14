# Task 07: AI Extractor — 3 Tối ưu

**Model:** Gemini 3.1 Pro
**File:** `src/ai_extractor.py`
**Phụ thuộc:** Task 02 (company name đã trong prompt)

## Bối cảnh
AI Extractor hiện gọi Gemini cho **mọi** scraped page, kể cả trang rác hoặc khi đã có đủ dữ liệu. Cần 3 tối ưu để tiết kiệm API calls.

## Sub-task A: Pre-filter Content (Regex Check)

**Thêm method:**
```
def _has_contact_signals(self, markdown: str) -> bool
```

**Logic:**
1. Regex check phone: `r'\d{10,11}'` hoặc `r'\d{2,4}[\s.\-]\d{3,4}[\s.\-]\d{3,4}'`
2. Regex check email: `r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'`
3. Keyword check: tìm "liên hệ", "contact", "điện thoại", "email", "địa chỉ", "phone", "tel", "fax"
4. Return `True` nếu tìm thấy >= 1 phone/email pattern HOẶC >= 2 keywords
5. Return `False` → skip AI call cho page này

**Trong `extract_from_page()`:**
- Trước khi gọi Gemini, check: `if not self._has_contact_signals(markdown_content): return {"status": "skipped", "reason": "no_contact_signals"}`
- Log event: `{"event": "ai_skipped", "reason": "no_contact_signals", "page_id": ...}`

## Sub-task B: Early Stop Extraction

**Trong `extract_for_company()`:**

Sau mỗi page được extract thành công, kiểm tra:
```
extracted_fields = set of non-null fields from result (phone, email, address)
if len(extracted_fields) >= 3 and confidence >= 0.8:
    log("early_stop_extraction", {fields: extracted_fields, pages_skipped: remaining})
    break  # skip remaining pages
```

**Output mới cho early stop:**
```json
{"event": "early_stop_extraction", "company_id": 123,
 "fields_found": ["phone", "email", "address"],
 "confidence": 0.85, "pages_processed": 2, "pages_skipped": 3}
```

## Sub-task C: Batch Multiple Pages

**Thêm method:**
```
def _batch_short_pages(self, pages: list[dict], max_chars: int = 5000) -> list[list[dict]]
```

**Logic:**
1. Tách pages thành 2 nhóm: short (< `max_chars`) và long
2. Gộp 2-3 short pages thành 1 batch (tổng chars < 15000)
3. Mỗi long page = 1 batch riêng
4. Return list of batches

**Cập nhật prompt cho batch:**
```
Trang 1 (từ {url_1}):
{markdown_1}

---TRANG MỚI---

Trang 2 (từ {url_2}):
{markdown_2}
```

**Output khi batch:** Mỗi batch trả 1 JSON (merge fields từ nhiều trang)

## Tiêu chí hoàn thành
- [ ] Pages không có phone/email pattern → skip AI call
- [ ] Log event `ai_skipped` khi skip
- [ ] 3+ trường chính found + confidence >= 0.8 → stop extract
- [ ] Log event `early_stop_extraction` khi stop
- [ ] Short pages được batch thành 1 API call
- [ ] Total API calls giảm đáng kể (verify bằng log count)
