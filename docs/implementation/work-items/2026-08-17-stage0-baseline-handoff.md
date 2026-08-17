# Bàn giao việc: Giai đoạn 0 (Stage 0) — chốt baseline cho kế hoạch V2

> File này là **hướng dẫn thực thi**, viết cho một AI agent khác (không phải người viết
> ra kế hoạch) tiếp nhận và làm. Đọc hết trước khi bắt đầu, làm đúng thứ tự.
> Người giao việc: phiên Claude trước, dừng vì gần hết usage (giới hạn mức dùng).
> Ngày giao: 2026-08-17.

## 1. Việc này là gì, vì sao phải làm

Repo này có kế hoạch nâng cấp hệ thống lên "V2", nằm ở hai file:

- `docs/v2-modular-refactor-plan.md` (tiếng Việt, bản quyết định nghiệp vụ)
- `docs/v2-stage1-critical-fixes-implementation-plan.md` (chi tiết giai đoạn 1)

Cả hai đều quy định: trước khi sửa bất kỳ dòng code nào, phải có **baseline** (đường
mốc — bộ số liệu ghi lại hệ thống đang chạy ra sao *trước khi sửa*), để sau này so
sánh "sau khi sửa có tệ đi chỗ nào không". Đây gọi là **Giai đoạn 0 (Stage 0)**.

Tính đến giờ, `docs/implementation/work-items/` **chưa có** file baseline nào. Đây là
việc phải làm trước tiên, đứng trước mọi việc sửa code khác.

**Việc này chỉ đọc dữ liệu đã có sẵn trong database. Không gọi API nào, không chạy lại
pipeline, không tốn tiền, không sửa một dòng code nào trong `src/` hay `dashboard/`.**

## 2. Ràng buộc cứng — đọc kỹ trước khi làm

1. **Chỉ đọc, không ghi vào database.** Mọi câu lệnh SQL trong file này đều là
   `SELECT`. Không chạy `UPDATE`, `DELETE`, `INSERT` trên bất kỳ bảng nào.
2. **Không chạy pipeline** (`scripts/run_batch.py`, `dashboard/run.py`,
   `src/pipeline_worker.py`, hay bất kỳ lệnh nào gọi Gemini/Firecrawl). Việc này chỉ
   lấy số liệu hiện có, không tạo số liệu mới.
3. **Không sửa code.** Đây là việc tài liệu (docs-only). Theo `AGENTS.md` §5, việc chỉ
   sửa tài liệu không cần tạo nhánh Git riêng — làm thẳng trên nhánh đang đứng
   (`git branch --show-current` để kiểm tra, hiện tại là `snapshot/ban-lasted-20260730`).
4. **Không tự ý `git commit`.** Làm xong, để nguyên các file đã tạo trong working tree
   (chưa commit), báo cho người dùng. Người dùng sẽ đưa kết quả cho phiên Claude sau
   phân tích rồi mới quyết định commit.
5. **Database dùng để đọc — chỉ một file, ghi rõ đường dẫn khi báo cáo:**

   ```
   /home/ubuntu/workspaces2/projects/auto_search_company/data/company_data.db
   ```

   Đã xác minh ngày 2026-08-17: file này có đúng 8.701 công ty, 1.252 công ty thiếu
   địa chỉ, 7.448 công ty có tax code — khớp chính xác với các con số mà cả hai bản kế
   hoạch trích dẫn nhiều lần. Đây là database gốc, không phải suy đoán.

   **Cảnh báo:** có một database khác trong cùng thư mục `data/`, tên
   `company_data_1013_companies.db` (chỉ 1.013 công ty) — **không dùng file đó** cho
   việc này, nó là bản mẫu nhỏ hơn/cũ hơn.

   Cũng cảnh báo tương tự ở cấp thư mục dự án: có một thư mục tên giống
   `/home/ubuntu/workspaces2/projects/auto_search_company_v1` trên cùng máy chủ — đó là
   bản clone cũ của cùng repo GitHub, cũ hơn nhiều (còn nguyên `SERPER_API_KEY` chưa gỡ).
   **Không đọc, không sửa gì trong thư mục đó.** Toàn bộ việc này làm trong
   `/home/ubuntu/workspaces2/projects/auto_search_company` (không có hậu tố `_v1`).

6. Mở database ở chế độ chỉ đọc để tự bảo vệ khỏi gõ nhầm lệnh ghi:

   ```bash
   cd /home/ubuntu/workspaces2/projects/auto_search_company
   venv/bin/python
   ```
   ```python
   import sqlite3
   conn = sqlite3.connect(
       "file:data/company_data.db?mode=ro", uri=True
   )
   ```

## 3. Bước 1 — Chọn 30 công ty mẫu

Kế hoạch yêu cầu mẫu phủ đủ 7 tình huống. Đề xuất số lượng mỗi nhóm (tổng = 30), một
công ty có thể thuộc nhiều hơn một nhóm — không sao, cứ ghi rõ nó thuộc nhóm nào khi
liệt kê:

| Nhóm | Số lượng đề xuất | Độ chắc chắn của câu SQL bên dưới |
|---|---:|---|
| A. Trùng tên khác địa chỉ | 4 | Chắc chắn — có dữ liệu thật |
| B. Domain trang tin (footer công ty báo bị lấy nhầm) | 4 | Suy đoán theo domain — cần xem lại bằng mắt |
| C. Timeout khi scrape | 4 | Chắc chắn |
| D. Cache hit (nghi vấn, xem ghi chú) | 4 | Yếu — xem mục D bên dưới trước khi dùng |
| E. Có URL bị blacklist | 4 | Chắc chắn |
| F. Công ty đã giải thể / tạm ngừng hoạt động | 6 | Chắc chắn |
| G. Thiếu địa chỉ hoàn toàn | 4 | Chắc chắn |

Vì sao nhóm F có 6: đây là quy tắc nghiệp vụ quan trọng nhất bị ảnh hưởng nếu sửa sai
(mục 3.6 của kế hoạch — business status gate), nên lấy mẫu dày hơn.

### Nhóm A — Trùng tên khác địa chỉ

```sql
SELECT vietnamese_name, count(*) AS n
FROM companies
WHERE vietnamese_name IS NOT NULL AND vietnamese_name <> ''
GROUP BY vietnamese_name
HAVING n > 1
ORDER BY n DESC
LIMIT 20;
```

Đã thử ngày 2026-08-17, có kết quả thật, ví dụ:
`CÔNG TY TRÁCH NHIỆM HỮU HẠN SEJONG VINA` (2 dòng),
`CÔNG TY TRÁCH NHIỆM HỮU HẠN NISSEI ELECTRIC HÀ NỘI` (2 dòng).

Lấy 2 cặp (= 4 công ty) từ kết quả trên, **nhưng phải mở từng cặp ra xem cột `address`
có thật sự khác tỉnh/thành hay không** — có thể trùng tên do lỗi nhập liệu chứ không
phải hai pháp nhân khác nhau thật:

```sql
SELECT id, vietnamese_name, address, tax_code, status
FROM companies
WHERE vietnamese_name = '<tên lấy được ở trên>';
```

Chỉ giữ cặp nào `address` rõ ràng khác tỉnh/thành (ví dụ một cái ở "Hà Nội", một cái ở
"Bình Dương").

### Nhóm B — Domain trang tin

Không có cột đánh dấu sẵn "đây là trang tin". Dò theo domain quen thuộc:

```sql
SELECT DISTINCT sp.company_id, sp.url
FROM scraped_pages sp
WHERE sp.url LIKE '%vnexpress%'
   OR sp.url LIKE '%dantri.com%'
   OR sp.url LIKE '%thanhnien%'
   OR sp.url LIKE '%tuoitre%'
   OR sp.url LIKE '%vietnamnet%'
   OR sp.url LIKE '%24h.com.vn%'
   OR sp.url LIKE '%kenh14%'
   OR sp.url LIKE '%zingnews%'
   OR sp.url LIKE '%cafef%'
   OR sp.url LIKE '%baomoi%'
LIMIT 20;
```

Nếu câu trên ra 0 dòng (domain tin tức nằm ngoài danh sách trên), mở rộng danh sách
domain hoặc thử tìm theo `filtered_links.source_type = 'unknown_web'` kết hợp lọc thủ
công. Ghi lại trong báo cáo cách đã tìm được 4 công ty này, kể cả khi phải mở rộng
danh sách domain.

### Nhóm C — Timeout khi scrape

```sql
SELECT DISTINCT company_id
FROM scraped_pages
WHERE scrape_status = 'timeout'
LIMIT 20;
```

Đã thử: có 1.620 công ty thỏa điều kiện này. Chọn ngẫu nhiên 4.

### Nhóm D — Cache hit (đọc kỹ trước khi dùng)

**Ghi chú quan trọng đã phát hiện ngày 2026-08-17:** trường `cache_hit` trong
`pipeline_logs.metadata_json` luôn ghi `false` trong toàn bộ mẫu đã kiểm — có thể vì
đúng lỗi mà kế hoạch V2 đang mô tả (cache hit vẫn chạy qua như một lần tìm mới, không
được đánh dấu đúng). Vì vậy **không dùng cột này để lọc**.

Dùng cách gián tiếp: công ty có nhiều dòng `search_results` cùng `search_query` +
`url` (chính là bằng chứng dữ liệu trùng mà kế hoạch đang muốn sửa) là ứng viên tốt,
vì chúng cho thấy máy đã đi qua đường cache hit:

```sql
SELECT company_id, search_query, url, count(*) AS n
FROM search_results
GROUP BY company_id, search_query, url
HAVING n > 1
ORDER BY n DESC
LIMIT 20;
```

Chọn 4 `company_id` khác nhau từ kết quả trên. Ghi rõ trong báo cáo: "chọn theo bằng
chứng dòng trùng, không phải theo cờ cache_hit vì cờ đó không đáng tin."

### Nhóm E — Có URL bị blacklist

```sql
SELECT DISTINCT company_id
FROM filtered_links
WHERE source_type = 'blacklisted'
LIMIT 20;
```

Đã thử: có 17.052 dòng thỏa điều kiện. Chọn ngẫu nhiên 4 company_id khác nhau.

### Nhóm F — Đã giải thể / tạm ngừng hoạt động

```sql
SELECT id, vietnamese_name, business_status, business_status_category
FROM companies
WHERE business_status LIKE '%Ngừng hoạt động%'
   OR business_status LIKE '%Tạm ngừng%'
   OR business_status LIKE '%chấm dứt hiệu lực%'
LIMIT 40;
```

Đã thử: có khoảng 500 công ty thỏa điều kiện này (nhiều biến thể chuỗi khác nhau, ví
dụ có dòng còn kèm cả ngày đóng mã số thuế trong text). Chọn 6 công ty, ưu tiên đa
dạng cách viết `business_status` khác nhau (không chọn 6 công ty cùng một câu chữ).

### Nhóm G — Thiếu địa chỉ hoàn toàn

```sql
SELECT id, vietnamese_name, address, province
FROM companies
WHERE address IS NULL OR address = ''
LIMIT 20;
```

(Cột `province` không tồn tại ở bảng `companies` trong V1 — nếu câu trên báo lỗi
`no such column: province`, bỏ `province` khỏi câu SELECT, chỉ còn `id, vietnamese_name,
address`.) Đã thử: có 1.252 công ty thỏa điều kiện. Chọn ngẫu nhiên 4.

## 4. Bước 2 — Với mỗi công ty đã chọn, ghi lại "kết quả V1 hiện tại"

Sau khi có đúng 30 `company_id`, chạy các câu sau **cho từng công ty** (thay
`:id` bằng company_id thật) và ghi kết quả vào bảng ở bước 5:

```sql
-- Thông tin công ty và trạng thái cuối cùng
SELECT id, vietnamese_name, status, business_status, address, tax_code
FROM companies WHERE id = :id;

-- Số URL tìm được (search_results, chưa lọc)
SELECT count(*) FROM search_results WHERE company_id = :id;

-- Số URL sau khi lọc, có nên scrape hay không
SELECT count(*) FROM filtered_links WHERE company_id = :id AND should_scrape = 1;

-- Số trang đã scrape, theo trạng thái
SELECT scrape_status, count(*) FROM scraped_pages
WHERE company_id = :id GROUP BY scrape_status;

-- Số contact trích được
SELECT count(*) FROM extracted_contacts WHERE company_id = :id;

-- Tổng credit đã dùng (search + scrape), cộng dồn từ pipeline_logs
SELECT sum(credits_used) FROM pipeline_logs WHERE company_id = :id;

-- Tổng thời lượng chạy (giây), cộng dồn từ pipeline_logs
SELECT sum(duration_seconds) FROM pipeline_logs WHERE company_id = :id;
```

Nếu viết Python để lặp qua 30 công ty một lượt (khuyến khích, đỡ chạy tay 30 lần), làm
theo mẫu sau — chỉ đọc, đúng tinh thần ràng buộc ở mục 2:

```python
import sqlite3, json

conn = sqlite3.connect("file:data/company_data.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

company_ids = [...]  # 30 id đã chọn ở bước 1, kèm ghi chú thuộc nhóm nào

results = []
for cid in company_ids:
    company = conn.execute(
        "SELECT id, vietnamese_name, status, business_status, address, tax_code "
        "FROM companies WHERE id = ?", (cid,)
    ).fetchone()
    n_search = conn.execute(
        "SELECT count(*) FROM search_results WHERE company_id = ?", (cid,)
    ).fetchone()[0]
    n_filtered = conn.execute(
        "SELECT count(*) FROM filtered_links WHERE company_id = ? AND should_scrape = 1",
        (cid,),
    ).fetchone()[0]
    scrape_by_status = dict(conn.execute(
        "SELECT scrape_status, count(*) FROM scraped_pages "
        "WHERE company_id = ? GROUP BY scrape_status", (cid,)
    ).fetchall())
    n_contacts = conn.execute(
        "SELECT count(*) FROM extracted_contacts WHERE company_id = ?", (cid,)
    ).fetchone()[0]
    credits = conn.execute(
        "SELECT sum(credits_used) FROM pipeline_logs WHERE company_id = ?", (cid,)
    ).fetchone()[0] or 0
    duration = conn.execute(
        "SELECT sum(duration_seconds) FROM pipeline_logs WHERE company_id = ?", (cid,)
    ).fetchone()[0] or 0

    results.append({
        "company_id": cid,
        "name": company["vietnamese_name"],
        "status": company["status"],
        "business_status": company["business_status"],
        "address": company["address"],
        "tax_code": company["tax_code"],
        "search_results": n_search,
        "filtered_should_scrape": n_filtered,
        "scraped_pages_by_status": scrape_by_status,
        "extracted_contacts": n_contacts,
        "credits_used_total": credits,
        "duration_seconds_total": duration,
    })

# In ra để dán vào báo cáo, và lưu JSON thô để nộp kèm (xem mục 6)
print(json.dumps(results, ensure_ascii=False, indent=2))
with open("stage0_raw_query_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
```

## 5. Bước 3 — Định dạng file phải nộp

Tạo file `docs/implementation/work-items/stage0-baseline.md` với cấu trúc sau
(giữ đúng tên file này — cả hai bản kế hoạch đều trỏ tới đúng tên này):

```markdown
# Stage 0 — Baseline mẫu 30 công ty

Ngày đo: <ngày thật lúc chạy>
Database đã đo: /home/ubuntu/workspaces2/projects/auto_search_company/data/company_data.db
Người/agent thực hiện: <tên>

## Cách chọn mẫu

<mô tả ngắn cách chọn từng nhóm A-G, số lượng thật lấy được mỗi nhóm,
và ghi rõ chỗ nào phải suy đoán/mở rộng tiêu chí (đặc biệt nhóm B và D)>

## Bảng 30 công ty

| # | company_id | Tên | Nhóm | status | business_status | search_results | filtered (should_scrape) | scraped: success/failed/timeout/skipped | extracted_contacts | credit dùng | thời lượng (giây) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ... | ... | F | done | Ngừng hoạt động... | 12 | 5 | 3/1/0/1 | 2 | 45 | 320 |
| ... | | | | | | | | | | | |

(30 dòng, một dòng một công ty. Cột "Nhóm" ghi chữ cái A-G; nếu công ty thuộc nhiều
nhóm, ghi cả hai, ví dụ "F, G".)

## Bất thường phát hiện được (nếu có)

<công ty nào có số liệu lạ, ví dụ 0 search_results nhưng status lại là done — ghi lại,
đừng tự sửa, đừng tự suy diễn nguyên nhân>

## Việc chưa làm được / cần người kiểm tra tiếp

<ví dụ: "Nhóm B chỉ tìm được 2/4 công ty theo danh sách domain gợi ý, cần bổ sung">
```

## 6. Nộp lại gì cho phiên Claude sau phân tích

Khi báo cáo xong việc cho người dùng, **đính kèm đủ 2 file**, không chỉ tóm tắt bằng lời:

1. `docs/implementation/work-items/stage0-baseline.md` — file chính, đúng định dạng mục 5.
2. `stage0_raw_query_results.json` (hoặc tên tương đương) — kết quả thô từ script Python
   ở mục 4, để phiên sau đối chiếu lại được từng con số mà không phải chạy lại toàn bộ
   truy vấn.

Đồng thời báo rõ trong tin nhắn text (không chỉ trong file):

- Đã dùng đúng `data/company_data.db` chưa, hay phải đổi vì lý do gì.
- Nhóm nào (trong A-G) không tìm đủ số lượng đề xuất, và đã hạ tiêu chí ra sao.
- Có gặp lỗi SQL nào phải tự sửa câu lệnh không (ví dụ tên cột khác so với file này ghi
  — schema có thể đã đổi sau ngày viết file này).
- Xác nhận: **không có lệnh ghi database nào được chạy**, không có code nào bị sửa,
  không có gì được commit.

**Không tự ý coi việc "Giai đoạn 1" (sửa `waitFor`, cache hit, retry) là đã được phép
bắt đầu.** File này chỉ giao đúng phạm vi Giai đoạn 0. Giai đoạn 1 cần một xác nhận
riêng của người dùng, và có một bước (đo A/B thời gian chờ scrape) tốn credit Firecrawl
thật — không được tự chạy bước đó.
