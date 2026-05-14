# Agent Prompt System

Hệ thống prompt chia nhỏ tác vụ tối ưu pipeline, thiết kế cho 2 loại agent:

## Cấu trúc

```
agent_prompt/
├── exec/          # Prompt thực thi (Gemini 3.1 Pro)
│   ├── task_01_early_stop_inline.md
│   ├── task_02_ai_company_name.md
│   ├── ...
│   └── task_13_db_connection_pool.md
├── debug/         # Prompt debug (Gemini 3 Flash)
│   ├── debug_01.md
│   ├── ...
│   └── debug_13.md
└── README.md
```

## Cách sử dụng

### Thực thi (Gemini 3.1 Pro)
1. Mở file `exec/task_XX.md`
2. Copy toàn bộ nội dung → paste vào Gemini 3.1 Pro
3. Agent sẽ thực hiện code changes theo spec
4. Kiểm tra output theo tiêu chí trong prompt

### Debug (Gemini 3 Flash)
1. Sau khi exec agent hoàn thành, mở `debug/debug_XX.md` tương ứng
2. Copy → paste vào Gemini 3 Flash kèm code/log output
3. Agent sẽ phân tích lỗi và đề xuất fix

## Thứ tự thực hiện
Thực hiện theo thứ tự task_01 → task_13. Một số task có phụ thuộc (ghi trong prompt).

## Quy ước
- **Sub-task**: Task phức tạp được chia thành sub-task (a, b, c). Hoàn thành lần lượt.
- **Input/Output**: Mỗi prompt ghi rõ chuẩn I/O để verify.
- **Codebase root**: `/home/baguf/workspaces/auto_search_company/`
