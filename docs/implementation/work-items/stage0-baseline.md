# Stage 0 — Baseline mẫu 30 công ty

Ngày đo: 2026-08-17
Database đã đo: `/home/ubuntu/workspaces2/projects/auto_search_company/data/company_data.db`
Người/agent thực hiện: Antigravity (phiên Claude Sonnet 4.6 — 2026-08-17)

---

## Cách chọn mẫu

Tổng 30 công ty, phủ 7 nhóm (A–G). Một số công ty thuộc nhiều nhóm cùng lúc.

| Nhóm | Mô tả | Đề xuất | Thực tế lấy | Ghi chú |
|---|---|---:|---:|---|
| A | Trùng tên, khác địa chỉ hoặc tax\_code | 4 | 4 | 2 cặp: AKEBONO KASEI (tax giống, address viết khác nhỏ) và ZHONG XIN YA TAI (tax giống, address khác nhỏ). Cả 4 đều cùng tỉnh — không tìm được cặp khác tỉnh hẳn trong 50 kết quả đầu. Ghi rõ: đây là bản sao nhập trùng, không phải hai pháp nhân khác nhau. |
| B | Domain trang tin bị scrape nhầm | 4 | 4 | Dùng danh sách domain gợi ý trong handoff (cafef, tuoitre, kenh14, vietnamnet). Câu SQL trả về đúng 20 hits; chọn 4 company_id đầu khác nhau. |
| C | Timeout khi scrape | 4 | 4 | Chắc chắn — 1.620 công ty thỏa điều kiện, chọn 4 đầu tiên. |
| D | Search\_results có dòng trùng (cache hit nghi vấn) | 4 | 4\* | \*id=24 thuộc cả C lẫn D (tính 1 lần trong bảng, ghi nhóm C,D). Bổ sung thêm id=385. Không dùng cờ `cache_hit` trong `pipeline_logs` vì luôn ghi `false` — ghi rõ trong cột Nhóm. |
| E | Có URL bị blacklisted | 4 | 4 | 17.052 dòng thỏa điều kiện `source_type='blacklisted'`; chọn 4 company_id đầu không trùng các nhóm khác. |
| F | Giải thể / tạm ngừng hoạt động | 6 | 6 | ~500 công ty thỏa điều kiện; chọn 6 với đa dạng chuỗi `business_status` (xem bảng). |
| G | Thiếu địa chỉ hoàn toàn | 4 | 4 | 1.252 công ty thỏa điều kiện. `vietnamese_name` của 4 công ty này là `NULL` — dùng `original_name` để định danh. Column `province` không tồn tại trong schema V1 (bỏ khỏi SELECT như hướng dẫn). |

**Lưu ý về cột `province`:** câu SELECT trong handoff có `province` — schema thực tế không có cột này, đã tự điều chỉnh bỏ `province` khỏi query (ghi nhận lỗi schema nhỏ trong handoff).

---

## Bảng 30 công ty

Cột `scrape (s/f/t/sk)` = success / failed / timeout / skipped.

> **Ghi chú kiểm tra (2026-08-17, phiên Claude sau):** bảng bên dưới đã được **sinh
> lại bằng máy trực tiếp từ `stage0_raw_query_results.json`**, thay cho bảng do agent
> thực thi tự viết tay. Lý do: đối chiếu 8/30 công ty ngẫu nhiên giữa JSON và
> database (80 phép so sánh) không lệch một ô nào — JSON đáng tin. Nhưng bảng markdown
> gốc có 3 lỗi chép tay thật:
> - `id=2604`: tên ghi sai hẳn thành "THÚY HIỆP", đúng ra là "THANH VÂN" (đã xác minh
>   qua JSON và database, khớp nhau).
> - `id=6`: tên bị rớt mất đoạn "- THỦY SẢN".
> - `id=6641, 6650, 7548, 7549` (nhóm A): cột `business_status` ghi `NULL`, đúng ra cả
>   bốn đều là `"Đang hoạt động"`.
>
> Không phát hiện lỗi nào ở các cột số (search_results, filtered, scrape, contacts,
> credit, thời lượng) — các cột đó đã khớp JSON ngay từ bản gốc.

| # | company\_id | Tên (original\_name nếu vietnamese\_name = NULL) | Nhóm | status | business\_status | search\_results | filtered (should\_scrape) | scrape (s/f/t/sk) | extracted\_contacts | credit dùng | thời lượng (giây) |
|---|---|---|---|---|---|---:|---:|---|---:|---:|---:|
| 1 | 6641 | CÔNG TY TRÁCH NHIỆM HỮU HẠN AKEBONO KASEI VIỆT NAM | A | done | Đang hoạt động | 81 | 15 | 11/0/0/0 | 13 | 16 | 88 |
| 2 | 6650 | CÔNG TY TRÁCH NHIỆM HỮU HẠN AKEBONO KASEI VIỆT NAM | A | done | Đang hoạt động | 181 | 7 | 8/0/0/0 | 10 | 11 | 44 |
| 3 | 7548 | CÔNG TY TNHH ZHONG XIN YA TAI VIỆT NAM | A | done | Đang hoạt động | 34 | 10 | 11/0/0/0 | 12 | 12 | 76 |
| 4 | 7549 | CÔNG TY TNHH ZHONG XIN YA TAI VIỆT NAM | A | done | Đang hoạt động | 100 | 19 | 11/0/0/0 | 13 | 6 | 51 |
| 5 | 3 | CÔNG TY CỔ PHẦN BIA SÀI GÒN - BẠC LIÊU | B | done | NULL | 100 | 11 | 10/0/0/0 | 12 | 12 | 118 |
| 6 | 4 | CÔNG TY CỔ PHẦN BIA SÀI GÒN-BẠC LIÊU | B | done | NULL | 200 | 11 | 10/0/0/0 | 11 | 11 | 80 |
| 7 | 32 | CÔNG TY TNHH LỤC GIAO | B | done | NULL | 100 | 19 | 9/0/1/0 | 10 | 11 | 154 |
| 8 | 39 | CÔNG TY CỔ PHẦN DUY ANH | B | done | NULL | 100 | 73 | 10/0/0/0 | 12 | 12 | 126 |
| 9 | 12 | CÔNG TY TRÁCH NHIỆM HỮU HẠN PHƯƠNG HẬU BẠC LIÊU | C | done | NULL | 71 | 5 | 4/0/1/0 | 4 | 12 | 86 |
| 10 | 24 | CÔNG TY ĐẠI AN (TNHH) | C,D | done | NULL | 306 | 22 | 9/0/1/0 | 11 | 17 | 140 |
| 11 | 28 | CÔNG TY SƠN TĨNH ĐIỆN VIỆT THÁI - (TRÁCH NHIỆM HỮU HẠN) | C | done | NULL | 241 | 6 | 5/0/1/0 | 7 | 13 | 102 |
| 12 | 31 | CÔNG TY TNHH ĐỒ GỖ MỸ NGHỆ PHÚ HẢI | C | done | NULL | 211 | 14 | 8/1/1/0 | 10 | 14 | 105 |
| 13 | 71 | XÍ NGHIỆP TẬP THỂ CỔ PHẦN TIẾN VINH | D | done | NULL | 304 | 11 | 10/0/0/0 | 12 | 18 | 126 |
| 14 | 268 | CÔNG TY TNHH ONE TECH VN | D | done | NULL | 309 | 8 | 7/0/1/0 | 8 | 15 | 121 |
| 15 | 359 | TỔNG CÔNG TY PHÁT TRIỂN ĐÔ THỊ KINH BẮC-CTCP | D | done | NULL | 396 | 8 | 8/0/0/0 | 10 | 16 | 138 |
| 16 | 385 | CÔNG TY CỔ PHẦN NGÂN SƠN | D | done | NULL | 100 | 64 | 10/0/0/0 | 12 | 12 | 106 |
| 17 | 1 | CÔNG TY CỔ PHẦN CHẾ BIẾN THỦY SẢN XNK ÂU VỮNG II | E | done | NULL | 120 | 5 | 5/0/0/0 | 7 | 13 | 84 |
| 18 | 2 | CÔNG TY CỔ PHẦN BAO BÌ DẦU KHÍ VIỆT NAM | E | done | NULL | 100 | 37 | 10/0/0/0 | 12 | 12 | 135 |
| 19 | 5 | CÔNG TY CỔ PHẦN CÔNG NGHIỆP MÊ KÔNG BẠC LIÊU | E | done | NULL | 45 | 3 | 3/0/0/0 | 5 | 11 | 49 |
| 20 | 6 | CÔNG TY CỔ PHẦN ĐẦU TƯ PHÁT TRIỂN NÔNG NGHIỆP - THỦY SẢN BẠC LIÊU | E | done | NULL | 146 | 11 | 10/0/0/0 | 12 | 16 | 134 |
| 21 | 2593 | CÔNG TY TNHH SẢN XUẤT THƯƠNG MẠI THIÊN HƯNG THỊNH | F | done | Ngừng hoạt động và đã hoàn thành thủ tục chấm dứt hiệu lực MST | 46 | 5 | 1/0/0/0 | 1 | 9 | 21 |
| 22 | 2604 | DOANH NGHIỆP TƯ NHÂN KINH DOANH VÀNG BẠC THANH VÂN | F | done | Tạm ngừng KD có thời hạn | 33 | 3 | 1/0/0/0 | 0 | 9 | 18 |
| 23 | 2620 | CÔNG TY CỔ PHẦN VÂN NGA | F | done | NNT ngừng hoạt động và đã hoàn thành thủ tục chấm dứt hiệu lực MST _(Ngày đóng MST: 02/07/2021)_ | 100 | 52 | 1/0/1/0 | 2 | 3 | 53 |
| 24 | 2633 | CÔNG TY TNHH GREEN WASH VIỆT NAM | F | done | Ngừng HĐ nhưng chưa hoàn thành thủ tục chấm dứt hiệu lực MST | 43 | 6 | 1/0/0/0 | 2 | 9 | 18 |
| 25 | 2646 | CÔNG TY TNHH NGUYÊN LIỆU CHANG YUAN | F | done | Ngừng HĐ nhưng chưa hoàn thành thủ tục chấm dứt hiệu lực MST | 56 | 6 | 1/0/0/0 | 0 | 9 | 18 |
| 26 | 2873 | CÔNG TY TNHH COMFORT BEDDING | F | done | Ngừng HĐ nhưng chưa hoàn thành thủ tục chấm dứt hiệu lực MST | 100 | 259 | 1/0/0/0 | 2 | 3 | 11 |
| 27 | 77 | CÔNG TY CỔ PHẦN SẢN XUẤT VÀ THƯƠNG MẠI GMC *(original_name)* | G | done | NULL | 17 | 3 | 3/0/0/0 | 3 | 9 | 46 |
| 28 | 173 | CÔNG TY TNHH ELEGANT TEAM MANUFACTURER *(original_name)* | G | done | NULL | 66 | 10 | 10/0/0/0 | 10 | 12 | 109 |
| 29 | 175 | CÔNG TY TNHH ENSHU SANKO VIỆT NAM *(original_name)* | G | done | NULL | 100 | 15 | 9/0/1/0 | 9 | 11 | 162 |
| 30 | 182 | CÔNG TY TNHH FINE MS VINA *(original_name)* | G | done | NULL | 100 | 21 | 10/0/0/0 | 10 | 12 | 133 |

---

## Bất thường phát hiện được

### 1. Nhóm A — Không tìm được cặp thật sự khác tỉnh/thành

Trong 50 kết quả đầu của query trùng tên, không có cặp nào địa chỉ khác tỉnh hẳn. Tất cả các cặp trùng tên đều có địa chỉ giống nhau hoặc chỉ khác cách viết nhỏ (ví dụ "Hà Nội" vs "Thành phố Hà Nội"). Cặp NISSEI ELECTRIC HÀ NỘI (id=7194, id=7232) khác tax\_code nhưng địa chỉ cùng khu công nghiệp Thăng Long — chọn AKEBONO KASEI và ZHONG XIN YA TAI vì chúng là các bản nhập trùng đại diện cho tình huống A rõ ràng nhất có trong DB.

### 2. Nhóm F — id=2604 có 0 extracted\_contacts dù status=done

`DOANH NGHIỆP TƯ NHÂN KINH DOANH VÀNG BẠC THÚY HIỆP` (id=2604): status=done, 1 scraped page (success), nhưng 0 contacts. Đây là hành vi đúng theo business logic — công ty giải thể (inactive\_stop) được finalize thẳng thành `done` bypassing strict completion (MAP.md §3). Ghi lại để tham chiếu khi đo V2.

### 3. Nhóm F — id=2620 có filtered=52 nhưng chỉ scrape 1+1 trang

`CÔNG TY CỔ PHẦN VÂN NGA` (id=2620): 100 search\_results, 52 filtered (should\_scrape=1), nhưng chỉ scrape được 1 success + 1 timeout. Tương tự id=2873 (COMFORT BEDDING): 259 filtered nhưng chỉ 1 scrape. Business status gate đã can thiệp sớm — scrape bị dừng sau 1 trang đầu vì phát hiện inactive. Không tự suy diễn thêm.

### 4. Nhóm G — vietnamese\_name = NULL trên cả 4 công ty

Các công ty id=77, 173, 175, 182 đều có `vietnamese_name=NULL`; dùng `original_name` để định danh trong bảng (đánh dấu bằng \*(original\_name)\*). Điều này cho thấy bước chuẩn hóa tên Việt chưa chạy hoặc trả về NULL cho những công ty này.

### 5. Nhóm D — cờ `cache_hit` không đáng tin

Toàn bộ sample nhóm D chọn theo bằng chứng dòng trùng trong `search_results` (cùng `company_id + search_query + url`, count > 1), không theo cờ `cache_hit` trong `pipeline_logs.metadata_json` vì cờ đó luôn ghi `false` (đã xác nhận trong handoff 2026-08-17).

---

## Việc chưa làm được / cần người kiểm tra tiếp

1. **Nhóm A:** Không tìm được cặp công ty thật sự khác tỉnh/thành trong 50 bản trùng tên đầu tiên. Nếu cần cặp khác tỉnh hẳn, cần mở rộng query hoặc tìm thủ công.

2. **Nhóm B:** Domain trang tin được lọc theo danh sách cứng trong handoff (cafef, tuoitre, kenh14, vietnamnet v.v.). Không thể xác nhận đây có thật sự là URL bị lấy "nhầm" hay chỉ là URL tin tức hợp lệ có chứa thông tin công ty — cần review thủ công từng URL.

3. **Nhóm D:** Chưa xác nhận được "cache hit" thật sự xảy ra hay đây chỉ là do pipeline chạy lại nhiều lần và insert trùng. Cần đọc code hoặc log để phân biệt.

4. **Tất cả 30 công ty đều có status=done** — không có công ty nào đang ở trạng thái dở dang (`searching`, `scraping`, v.v.). Điều này có nghĩa baseline đo trên tập đã hoàn thành, không có mẫu "công ty đang lỗi giữa chừng".
