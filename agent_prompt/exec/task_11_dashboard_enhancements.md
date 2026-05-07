# Task 11: Dashboard Enhancements

**Model:** Gemini 3.1 Pro
**File:** `dashboard/app.py`
**Phụ thuộc:** Task 03 (scoring data in JSONL), Task 10 (correct status)

## Sub-task A: Scoring Breakdown View

**Thêm endpoint:** `GET /companies/{company_id}/scores`

**Logic:**
1. Query `filtered_links` cho company: `SELECT * FROM filtered_links WHERE company_id = ? ORDER BY relevance_score DESC`
2. Render HTML table với columns: URL, Source Type, Score, Should Scrape, Reason
3. Thêm link từ company logs page: `<a href="/companies/{id}/scores">View Scores</a>`

**Output HTML:** Bảng hiển thị tất cả URLs + scores cho company đó.

## Sub-task B: Step-level Execution

**Thêm endpoint:** `POST /companies/{company_id}/run-step`

**Logic:**
1. Nhận form param `step` (giá trị: `search`, `filter`, `scrape`, `extract`)
2. Import Pipeline class, khởi tạo với DB + Logger
3. Gọi `pipeline.run_step(company_id, step)`
4. Redirect về `/companies/{company_id}/logs`

**HTML:** Thêm dropdown + button trên company logs page:
```html
<form method="post" action="/companies/{id}/run-step">
  <select name="step">
    <option value="search">Search</option>
    <option value="filter">Filter</option>
    <option value="scrape">Scrape</option>
    <option value="extract">Extract</option>
  </select>
  <button type="submit">Run Step</button>
</form>
```

## Sub-task C: SSE Realtime Logs

**Thêm endpoint:** `GET /api/logs/stream`

**Logic:**
1. Mở JSONL file ở append mode, seek to end
2. Yield new lines qua Server-Sent Events:
```python
from starlette.responses import StreamingResponse

async def log_generator():
    with open(log_file) as f:
        f.seek(0, 2)  # seek to end
        while True:
            line = f.readline()
            if line:
                yield f"data: {line.strip()}\n\n"
            else:
                await asyncio.sleep(1)

@app.get("/api/logs/stream")
async def logs_stream():
    return StreamingResponse(log_generator(), media_type="text/event-stream")
```

3. Thêm JavaScript trên `/logs` page để consume SSE:
```javascript
const source = new EventSource("/api/logs/stream");
source.onmessage = (e) => { /* append to log container */ };
```

## Tiêu chí hoàn thành
- [ ] `/companies/{id}/scores` hiển thị bảng scoring
- [ ] `/companies/{id}/run-step` chạy được từng bước
- [ ] `/api/logs/stream` trả SSE stream
- [ ] Logs page auto-update khi có log mới
