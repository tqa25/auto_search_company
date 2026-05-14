# Task 13: DB Connection Pool

**Model:** Gemini 3.1 Pro
**File:** `src/database.py`
**Phụ thuộc:** Không

## Bối cảnh
Mỗi method (`fetch_one`, `execute_query`) mở connection mới. Với 6000 công ty × ~20 queries = ~120K connections. Cần connection reuse + WAL mode cho concurrent reads (dashboard + pipeline).

## Thay đổi

### 1. Thêm thread-local connection

```python
import threading

class DatabaseManager:
    def __init__(self, db_path="data/company_data.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()

    def _get_connection(self):
        """Reuse connection per thread."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")      # WAL mode
            conn.execute("PRAGMA busy_timeout=5000")      # 5s wait on lock
            self._local.conn = conn
        return self._local.conn
```

### 2. Thêm close method

```python
def close(self):
    """Close current thread's connection."""
    if hasattr(self._local, 'conn') and self._local.conn:
        self._local.conn.close()
        self._local.conn = None
```

### 3. Context manager support

```python
def __enter__(self):
    return self

def __exit__(self, *args):
    self.close()
```

### 4. Cập nhật execute_query và fetch methods
Bỏ `with self._get_connection() as conn:` (tự close) → thay bằng:
```python
def execute_query(self, query, params=()):
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    return cursor.lastrowid
```

## Lưu ý quan trọng
- WAL mode cho phép concurrent reads trong khi write đang diễn ra
- `busy_timeout` tránh "database is locked" khi dashboard đọc đồng thời
- Connection chỉ close khi gọi `close()` hoặc thread kết thúc
- Pipeline nên gọi `db.close()` trong finally block

## Tiêu chí hoàn thành
- [ ] Connection được reuse trong cùng thread
- [ ] WAL mode enabled
- [ ] busy_timeout = 5000ms
- [ ] `close()` method hoạt động
- [ ] Dashboard đọc DB không bị "database is locked"
