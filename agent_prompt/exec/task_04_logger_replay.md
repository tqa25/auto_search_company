# Task 04: Logger — Thêm trường cho Replay

**Model:** Gemini 3.1 Pro
**Files:** `src/logger.py`, `src/search_module.py`
**Phụ thuộc:** Task 03 (logger được dùng)

## Bối cảnh
JSONL log hiện tại thiếu các trường cần thiết cho replay system: `raw_request`, `network_latency_ms`, `processing_time_ms`, `raw_response_summary`.

## Sub-task A: Mở rộng Logger

**File:** `src/logger.py`

### 1. Cập nhật `log_step_start()`
Thêm parameter `raw_request: dict = None`:
```python
def log_step_start(self, company_id, step, source_url=None, source_name=None, raw_request=None):
```
Ghi `raw_request` vào JSONL entry.

### 2. Cập nhật `log_step_end()`
Thêm parameters:
```python
def log_step_end(self, log_id, status, ..., network_latency_ms=None, processing_time_ms=None, raw_response_summary=None):
```

### Output JSONL mới (step_start):
```json
{"event": "step_start", "company_id": 123, "step": "SEARCH_T1",
 "raw_request": {"query": "ABC Company Vietnam thông tin liên hệ", "type": "coarse"}}
```

### Output JSONL mới (step_end):
```json
{"event": "step_end", "company_id": 123, "step": "SEARCH_T1", "status": "success",
 "network_latency_ms": 1250, "processing_time_ms": 45,
 "raw_response_summary": {"result_count": 8, "status_code": 200}}
```

## Sub-task B: Search Module log raw_request

**File:** `src/search_module.py`

### Thay đổi:
1. Trong mỗi search tier, trước khi gọi API:
   - Gọi `log_step_start()` với `raw_request={"query": query_string, "tier": tier_name}`
2. Sau khi nhận response:
   - Tính `network_latency_ms` = thời gian API call
   - Gọi `log_step_end()` với `raw_response_summary={"result_count": len(results), "status_code": code}`
3. Khi cache hit:
   - Vẫn log `raw_request` nhưng thêm `"cache_hit": true`

## Tiêu chí hoàn thành
- [ ] `log_step_start` chấp nhận `raw_request` param
- [ ] `log_step_end` chấp nhận timing + response summary params
- [ ] Search module log query string vào `raw_request` cho mọi tier
- [ ] Cache hit vẫn được log với `raw_request`
- [ ] JSONL output có đủ thông tin để replay search flow
