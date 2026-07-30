# Bàn giao dự án Auto Search Company

> Ngày lập: 2026-07-29  
> V1 đóng băng để đối chiếu: `/home/ubuntu/workspaces2/projects/auto_search_company_v1`  
> Root tiếp tục phát triển V2: `/home/ubuntu/workspaces2/projects/auto_search_company`

## 1. Dự án được bàn giao

Auto Search Company nhận danh sách công ty, tìm URL liên quan, scrape nội dung và dùng AI lấy phone, email, địa chỉ, website, fax và người đại diện.

V1 được giữ làm bản đối chiếu và phương án quay lại. Đội nhận dự án tiếp tục phát triển V2 tại root hiện tại, không sửa trong thư mục backup V1.

Tài liệu này là trang bắt đầu. Nó cho biết cần nhận gì, rủi ro nào phải biết và nên đọc tài liệu nào tiếp theo.

## 2. Bộ hồ sơ cần nhận

Repository Git phải có:

- `src/`, `dashboard/`, `scripts/` và `tests/`;
- `requirements.txt`, `.env.example` và `pipeline_config.json`;
- `AGENTS.md`;
- `docs/v2-modular-refactor-plan.md`;
- `docs/v2-modular-refactor-plan.en.md`;
- `docs/v2-stage1-critical-fixes-implementation-plan.md`;
- `docs/v1-operational-audit.md`;
- tài liệu bàn giao này.

Không đưa `.env`, API key, token, `venv/`, log, output hoặc file tạm vào gói code.

Database và `Factory PIC Collection progress.xlsx` đang bị `.gitignore` bỏ qua. Chúng không tự đi theo Git và chỉ được gửi qua kênh dữ liệu đã được phê duyệt.

Nếu bàn giao database, phải dừng worker trước khi tạo bản chụp. Biên bản cần có ngày chụp, mã kiểm tra toàn vẹn SHA-256, số bản ghi chính và kết quả `PRAGMA integrity_check`.

## 3. Năm cảnh báo V1 quan trọng nhất

### 3.1 Batch AI làm sai dấu vết nguồn

V1 từng ghép markdown của nhiều URL cùng công ty vào một lần gọi AI. App sau đó lưu cùng một response contact cho mọi URL trong batch.

Database xác nhận 22.696 bản ghi contact thuộc 5.964 nhóm có dấu vết này, ảnh hưởng 5.645 công ty.

Nội dung scrape không bị lỗi này ghi đè trên diện rộng. Phần không đáng tin là quan hệ “contact này đến từ URL nào” trong `extracted_contacts`.

Khi dùng dữ liệu V1, phải kiểm tra từng phone/email với `scraped_pages.markdown_content` của đúng URL.

### 3.2 Trạng thái `done` không bảo đảm có contact

Database có 156 công ty mang trạng thái `done` nhưng không có contact.

Không dùng riêng `companies.status` để tính tỷ lệ hoàn thành. Phải kiểm tra dữ liệu thực có và tách rõ: hoàn tất, chưa hoàn tất, không có contact và thất bại.

### 3.3 Database có dữ liệu lặp

Đã xác nhận:

- 89.070 bản ghi search bị lặp;
- 33.953 bản ghi filtered link bị lặp;
- 8.665 bản ghi scraped page bị lặp;
- 696 scraped page có nhiều bản ghi contact.

Số lượng bản ghi không chứng minh một công ty có dữ liệu tốt hơn.

### 3.4 Quick Search là dữ liệu chưa xác nhận

Có 12.072 contact `gemini_grounding` không gắn `scraped_page_id`.

Tên tiếng Việt, tax code và contact do Quick Search bổ sung phải được xem là dữ liệu chưa xác nhận cho đến khi có nguồn độc lập.

### 3.5 Merge có thể thay toàn bộ dữ liệu công ty

`scripts/merge_db.py` có thể xóa toàn bộ dữ liệu đích của một công ty rồi chép bản từ database khác vào.

Chế độ `smart` dùng số bản ghi để tính độ phong phú. Dữ liệu lặp hoặc batch AI có thể làm bản chất lượng kém thắng.

Không chạy merge lên database chính nếu chưa có backup, dry-run, danh sách công ty bị tác động và người duyệt.

## 4. Chưa có mốc code chính thức sạch

Khi lập tài liệu:

- V1 backup và V2 cùng xuất phát từ commit `8be26342...`;
- V1 backup có nhiều thay đổi và file chưa được Git theo dõi;
- V2 có sửa đổi, xóa file và tài liệu mới chưa commit.

Không tuyên bố commit hiện tại là bản bàn giao chính thức.

Trước khi nộp:

1. Review toàn bộ `git diff`.
2. Tách thay đổi dọn dẹp khỏi thay đổi chức năng.
3. Chạy test phù hợp.
4. Commit mốc V1 đóng băng.
5. Commit mốc V2 bắt đầu.
6. Gắn tag rõ ràng cho hai mốc.
7. Ghi checksum database trong biên bản riêng.

## 5. Bản đồ tài liệu

| Cần biết | Tài liệu |
|---|---|
| Nhận dự án và kiểm tra hồ sơ | `PROJECT_HANDOVER.md` |
| V1 chạy thế nào, dữ liệu nào không đáng tin | `docs/v1-operational-audit.md` |
| Hành vi và kiến trúc V2 phải xây | `docs/v2-modular-refactor-plan.md` |
| Bản V2 cô đọng cho kỹ sư và AI agent | `docs/v2-modular-refactor-plan.en.md` |
| Ba sửa lỗi đầu tiên | `docs/v2-stage1-critical-fixes-implementation-plan.md` |
| Quy tắc bắt buộc cho AI agent | `AGENTS.md` |

Thứ tự đọc đề nghị:

1. `PROJECT_HANDOVER.md`.
2. Mục 1, 4 và 5 của `docs/v1-operational-audit.md`.
3. Mục 1–3 và mục 8 của kế hoạch V2.
4. Kế hoạch Stage 1 trước khi sửa code.
5. Các mục kiến trúc, test và agent protocol khi bắt đầu triển khai.

## 6. Checklist xác nhận bàn giao

### Code

- [ ] Working tree đã được review và commit.
- [ ] Có tag cho mốc V1 và V2.
- [ ] `git status` sạch tại commit bàn giao.
- [ ] Có command và kết quả test.
- [ ] Không có `.env` hoặc secret trong gói.
- [ ] Người nhận clone và chạy được trên máy khác.

### Database

- [ ] Worker đã dừng trước khi snapshot.
- [ ] `PRAGMA integrity_check` trả `ok`.
- [ ] Có mã SHA-256 và số bản ghi.
- [ ] Người nhận đã đọc cảnh báo batch AI và dữ liệu lặp.
- [ ] Có danh sách merge/snapshot lịch sử nếu còn tìm được.
- [ ] Quyền truy cập dữ liệu đã được phê duyệt.

### Tài liệu và trách nhiệm

- [ ] Người nhận xác nhận kế hoạch V2 là nguồn chuẩn về hành vi tương lai.
- [ ] Câu hỏi mở được ghi vào work item, không chỉ nằm trong chat.
- [ ] Bộ progress bootstrap được tạo trước lần sửa code đầu tiên.
- [ ] `scripts/check-doc-sync.sh` chạy pass trước khi kết thúc phiên code.
- [ ] Có người duyệt migration trước khi chạy trên database production.

## 7. Giới hạn của kết luận hiện tại

Chưa xác định được ai từng chạy merge, chạy lúc nào hoặc những công ty nào bị thay.

Chưa loại trừ khả năng file re-extract từng được import thủ công bằng công cụ nằm ngoài repository.

Khi cần kết luận chính thức, phải đối chiếu thêm backup theo ngày, shell history, log CI và các file export đã giao.
