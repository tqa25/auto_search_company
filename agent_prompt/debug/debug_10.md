# Debug Task 10: Health Monitor Fix

**Model:** Gemini 3 Flash | **File:** `src/health_monitor.py`

## Mục tiêu kiểm tra
in_progress count bao gồm tất cả status trung gian.

## Lệnh kiểm tra
```bash
# 1. Check SQL IN clause
grep -A2 "IN (" src/health_monitor.py

# 2. Verify all statuses included
grep "'searched'\|'scraped'\|'ai_done'\|'contact_discovering'" src/health_monitor.py
```

## Test thủ công
```sql
-- Chạy trực tiếp trên SQLite
SELECT status, COUNT(*) FROM companies GROUP BY status;
-- So sánh với dashboard output
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| pending vẫn sai | Thiếu status trong IN clause | Thêm tất cả intermediate statuses |
| SQL syntax error | Thiếu dấu phẩy hoặc quote | Check SQL string carefully |
