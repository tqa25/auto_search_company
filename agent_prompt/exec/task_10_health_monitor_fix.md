# Task 10: Health Monitor — Fix Status Count

**Model:** Gemini 3.1 Pro
**File:** `src/health_monitor.py`
**Phụ thuộc:** Không

## Bối cảnh
`get_system_status()` dòng 183-186 chỉ đếm `('searching', 'scraping', 'extracting')` là in_progress. Thiếu: `'searched'`, `'scraped'`, `'ai_done'`, `'contact_discovering'` → bị đếm sai vào `pending`.

## Thay đổi

### Sửa SQL query (dòng ~183-186):
**Trước:**
```python
"SELECT COUNT(*) as cnt FROM companies WHERE status IN ('searching', 'scraping', 'extracting')"
```

**Sau:**
```python
"SELECT COUNT(*) as cnt FROM companies WHERE status IN ('searching', 'searched', 'scraping', 'scraped', 'extracting', 'ai_done', 'contact_discovering')"
```

### Sửa pending calculation (dòng ~188):
Đảm bảo: `pending = total - completed - failed - perm_failed - in_progress`
(logic hiện tại đã đúng, chỉ cần in_progress count chính xác)

## Tiêu chí hoàn thành
- [ ] IN clause bao gồm tất cả status trung gian
- [ ] `pending` count chính xác (không đếm in_progress companies)
- [ ] Dashboard hiển thị đúng số liệu
