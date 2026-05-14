# Debug Task 13: DB Connection Pool

**Model:** Gemini 3 Flash | **File:** `src/database.py`

## Kiểm tra
```bash
grep -n "threading.local\|WAL\|busy_timeout\|def close" src/database.py
```

## Test
```python
from src.database import DatabaseManager
db = DatabaseManager()
db.init_db()
# Verify WAL mode
result = db.fetch_one("PRAGMA journal_mode")
assert result is not None  # should return "wal"
# Verify connection reuse (same thread = same connection)
conn1 = db._get_connection()
conn2 = db._get_connection()
assert conn1 is conn2  # same object
db.close()
```

## Lỗi thường gặp
- "database is locked" → busy_timeout chưa set, check PRAGMA
- Connection leak → close() không gọi, thêm try/finally trong pipeline
- WAL not enabled → PRAGMA phải chạy sau connect, trước query
