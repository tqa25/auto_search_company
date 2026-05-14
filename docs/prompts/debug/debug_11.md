# Debug Task 11: Dashboard Enhancements

**Model:** Gemini 3 Flash | **File:** `dashboard/app.py`

## Mục tiêu kiểm tra
3 tính năng mới: scoring view, step execution, SSE logs.

## Lệnh kiểm tra
```bash
# 1. New endpoints exist
grep -n "def.*scores\|def.*run.step\|def.*logs_stream" dashboard/app.py

# 2. Start dashboard
cd /home/baguf/workspaces/auto_search_company && uvicorn dashboard.app:app --port 8000 &

# 3. Test endpoints
curl http://localhost:8000/companies/1/scores
curl -X POST http://localhost:8000/companies/1/run-step -d "step=search"
curl -N http://localhost:8000/api/logs/stream  # SSE stream
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| 404 on /scores | Route chưa register | Check `@app.get` decorator |
| 500 on /run-step | Pipeline import lỗi | Check sys.path và import statement |
| SSE không stream | Generator không async | Dùng `async def` + `await asyncio.sleep()` |
| UI không auto-update | JavaScript EventSource lỗi | Check browser console for JS errors |

## Debug steps
1. Test từng endpoint riêng lẻ với curl
2. Check HTML render có đúng template không
3. SSE: mở browser tab → tail JSONL → verify events appear
