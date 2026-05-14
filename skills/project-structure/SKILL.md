---
name: project-structure
description: Hướng dẫn cấu trúc thư mục tiêu chuẩn của dự án để đảm bảo tính nhất quán.
---

# 📚 Tiêu chuẩn Cấu trúc Dự án Auto Search Company

Skill này hướng dẫn bạn (AI Agent) tuân thủ chặt chẽ cấu trúc thư mục của dự án. Không bao giờ lưu file bừa bãi ở thư mục gốc (root). Hãy lưu đúng file vào đúng vị trí theo quy chuẩn dưới đây.

## 🧭 Bản đồ Cấu trúc (Directory Layout)

```text
auto_search_company/
├── src/                  # Chứa toàn bộ mã nguồn (.py) cốt lõi của hệ thống (Search, Scrape, Extract...)
├── scripts/              # Chứa các file chạy độc lập (runners, benchmark, utils...)
├── tests/                # Chứa các kịch bản kiểm thử (unit test, integration test)
├── dashboard/            # Chứa mã nguồn ứng dụng Web UI (FastAPI)
├── docs/                 # Nơi tập trung toàn bộ tài liệu dự án
│   ├── architecture/     # Tài liệu thiết kế hệ thống, specs, guides
│   ├── diagrams/         # Hình ảnh, file sơ đồ (html, md, png)
│   └── prompts/          # Các template prompt AI dùng để tham khảo
├── data/                 # Chứa dữ liệu đầu vào và Database cục bộ
│   ├── inputs/           # File input (danh sách công ty, file Excel...)
│   └── db/               # File SQLite Database (*.db)
├── output/               # Chứa duy nhất kết quả xuất ra
│   ├── reports/          # Báo cáo cuối cùng (Excel, Markdown)
│   └── logs/             # Log chi tiết dạng CSV, JSONL, txt
├── skills/               # Nơi chứa các AI Skill (như file này)
├── .env                  # (KHÔNG GHI ĐÈ, chỉ cập nhật)
└── requirements.txt      # Khai báo phụ thuộc
```

## ⚠️ Nguyên Tắc Bắt Buộc (Strict Rules)

1. **KHÔNG** tạo file `*.py` tạm thời (scratch, test_*.py) ở ngoài thư mục gốc. Nếu là test, đặt vào `tests/`. Nếu là script tiện ích, đặt vào `scripts/`. Nếu là nháp cá nhân, đặt vào thư mục nháp được thiết lập trong não trạng (brain/scratch) hoặc xóa ngay sau khi dùng.
2. **KHÔNG** lưu file output (`.xlsx`, `.csv`, `.md` report) ở thư mục gốc. Phải bỏ vào `output/reports/` hoặc `output/logs/`.
3. **Cơ sở dữ liệu (SQLite)** luôn nằm trong `data/db/` (Ví dụ: `data/db/company_data.db`).
4. **Tài liệu hệ thống** luôn nằm trong `docs/`. Nếu tạo thêm sơ đồ mới, phải cho vào `docs/diagrams/`.

Bằng cách tuân thủ nghiêm ngặt các nguyên tắc này, bạn sẽ giữ cho không gian làm việc của USER gọn gàng và ổn định.
