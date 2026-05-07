# Task 09: Error Classification

**Model:** Gemini 3.1 Pro
**Files:** `src/errors.py` [NEW], `src/pipeline.py`
**Phụ thuộc:** Không

## Bối cảnh
`pipeline.py` catch `Exception` chung → mọi lỗi đều set `status='failed'`. Không phân biệt lỗi tạm (429) vs vĩnh viễn (402) vs nghiêm trọng (DB corrupt).

## Sub-task A: Tạo Exception Hierarchy

**File MỚI:** `src/errors.py`

```python
class PipelineError(Exception):
    """Base class cho pipeline errors."""
    def __init__(self, message, company_id=None, step=None):
        super().__init__(message)
        self.company_id = company_id
        self.step = step

class RetryableError(PipelineError):
    """Lỗi tạm thời — nên retry (429, timeout, network)."""
    pass

class SkippableError(PipelineError):
    """Lỗi riêng company — skip company, continue batch (invalid data, no results)."""
    pass

class CriticalError(PipelineError):
    """Lỗi nghiêm trọng — stop toàn bộ pipeline (402, DB corrupt)."""
    pass
```

## Sub-task B: Cập nhật Pipeline Error Handling

**File:** `src/pipeline.py`

Trong `run()` method, thay thế `except Exception` bằng:
```python
try:
    self._process_company(company_id)
except RetryableError as e:
    # Increment retry count, backoff, re-queue
    log_step_end(log_id, "RETRY", error_message=str(e),
                 metadata={"error_category": "retryable", "retry_count": count})
    if retry_count < MAX_RETRIES:
        continue  # retry same company
    else:
        db.update_company(company_id, status="failed")
except SkippableError as e:
    # Log and skip to next company
    log_step_end(log_id, "SKIPPED", error_message=str(e),
                 metadata={"error_category": "skippable"})
    db.update_company(company_id, status="failed")
    continue
except CriticalError as e:
    # Stop entire pipeline
    log_step_end(log_id, "CRITICAL", error_message=str(e),
                 metadata={"error_category": "critical"})
    raise  # propagate up to stop pipeline
except Exception as e:
    # Unknown error — treat as skippable
    log_step_end(log_id, "FAILED", error_message=str(e),
                 metadata={"error_category": "unknown"})
    db.update_company(company_id, status="failed")
```

**Cập nhật modules khác raise đúng loại:**
- `search_module.py`: HTTP 429 → `RetryableError`, HTTP 402 → `CriticalError`
- `scrape_module.py`: HTTP 429 → `RetryableError`, HTTP 402 → `CriticalError`
- `ai_extractor.py`: Quota exceeded → `CriticalError`, parse error → `SkippableError`

## Tiêu chí hoàn thành
- [ ] `src/errors.py` tồn tại với 3 exception classes
- [ ] Pipeline xử lý mỗi loại error khác nhau
- [ ] Modules raise đúng loại error
- [ ] JSONL log ghi `error_category` trong metadata
- [ ] CriticalError stop toàn bộ pipeline
