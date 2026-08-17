# Kế hoạch triển khai chi tiết V2 — Giai đoạn 1

> Phạm vi: ba sửa lỗi có giá trị cao nhất và rủi ro triển khai thấp nhất
> Ngày lập: 2026-07-29 — Sửa đổi: 2026-08-17
> Nguồn quyết định: `docs/v2-modular-refactor-plan.md`; quy trình theo `AGENTS.md`
> Không gọi API trả phí trong test
> Các đường dẫn code bên dưới là đường dẫn tương đối **trong chính repo này**,
> làm việc trên nhánh riêng — không còn mô hình copy sang thư mục V2 (§3.1)

## 1. Ba mục được chọn

Ba mục này chính là “ba lỗi rẻ nhất” ở §16.2 của kế hoạch V2:

1. Bỏ thời gian chờ cố định: `waitFor: 3000` và `DELAY_SECONDS=3`.
2. Cache hit không lưu lại; dọn dữ liệu trùng và thêm unique key.
3. Retry đủ số attempt, phân loại đúng lỗi tạm thời và không retry lại toàn bộ công ty.

Thứ tự triển khai:

```text
Stage 0: chốt mẫu 30 công ty + ghi kết quả V1 (điều kiện tiên quyết)
        ↓
Khóa baseline và test đỏ
        ↓
Đo A/B chất lượng scrape ở waitFor 3000 vs 0
        ↓
Bỏ fixed wait
        ↓
Chặn phát sinh duplicate mới
        ↓
Dọn duplicate cũ + unique index
        ↓
Sửa retry và error propagation
        ↓
Replay + smoke test + báo cáo Stage 1
```

Không chạy script dọn database trước khi code đã ngừng tạo duplicate mới.

## 2. Hiện trạng đã đối chiếu

Đối chiếu lại với cây làm việc ngày **2026-08-17**: cả tám dòng dưới đây vẫn còn
nguyên, chưa có phần nào của Stage 1 được thực hiện, `src/v2/` chưa tồn tại.

| Vấn đề | Code hiện tại (xác minh 2026-08-17) | Hậu quả |
|---|---|---|
| Batch Scrape chờ cố định | `src/scrape_module.py:230` `"waitFor": 3000` | Mọi URL trong batch bị chờ thêm |
| Scrape tuần tự chờ cố định | `src/scrape_module.py:452` `"waitFor": 3000`; `scrape_company()` gọi `time.sleep(delay)` | Hai URL nhanh vẫn bị cộng thêm thời gian |
| Config mặc định vẫn là 3 giây | `src/config.py:178` `DELAY_SECONDS` mặc định `3.0`; `pipeline_config.json:96` cũng `3.0` | Sửa một đường gọi vẫn chưa đủ |
| Cache hit vẫn đi qua hàm save | `src/search_module.py:214-216` — `_save_results()` chạy vô điều kiện sau `_search_with_dedup()`, bất kể `cache_hit` | Dòng cache cũ bị insert thêm |
| Không có hàng rào database | `search_results` chỉ có `idx_search_results_company_id` | Hai worker hoặc code sai vẫn ghi trùng |
| Deep Search che lỗi tạm thời | `src/firecrawl_deep_search.py` trả `[]` ở 429, 5xx và `except Exception` (dòng 77, 88, 144) | Lớp retry phía trên không thấy lỗi |
| Retry bị chia nhiều nơi | **Sáu** owner, không phải năm — xem §6.2. Bản kế hoạch cũ bỏ sót `src/rate_limiter.py` | Một operation có thể bị retry lồng nhau hoặc không retry |
| Company retry sai cấp | `src/company_run.py:59` `max_retries = 2`, chạy lại cả pipeline attempt | Có thể gọi lại bước đã trả tiền thay vì chỉ operation lỗi |
| Hàm gộp nhiều trang vào một lần gọi AI vẫn nằm trong cây | `src/ai_extractor.py:285` `_batch_short_pages`, không nơi nào gọi | Agent được giao "giảm chi phí AI" sẽ đấu lại nó — xóa trong Stage 1 |

Baseline test đã chạy ngày 2026-07-29 (chỉ nhóm test liên quan):

```text
pytest -q \
  tests/test_scrape_module.py \
  tests/test_search_module.py \
  tests/test_company_run.py \
  tests/test_connection_pool.py \
  tests/test_database.py

53 passed
```

Baseline toàn bộ suite, chạy lại ngày 2026-08-17 theo `AGENTS.md` §6:

```text
venv/bin/python -m pytest tests/ -q

1 failed, 190 passed in 20.39s
```

Lỗi duy nhất là
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'`) — đã có từ trước, không liên quan Stage 1. **Bất kỳ
lỗi nào thêm ngoài nó là do thay đổi của mình.**

Baseline này chỉ chứng minh test cũ đang xanh. Nó chưa khóa ba hành vi lỗi; phải thêm test đỏ trước khi sửa.

## 3. Điều kiện bắt đầu

### 3.0 Stage 0 là điều kiện tiên quyết, không phải bước khởi động tùy chọn

Gate B (§8) so sánh kết quả replay với baseline Stage 0. Không có baseline thì
câu "không có regression" không chứng minh được, và Stage 1 không thể nghiệm thu
theo đúng định nghĩa của chính nó.

Tính đến 2026-08-17, `docs/implementation/work-items/` **chưa có** file Stage 0 nào.

Phải làm trước:

1. Chọn 30 công ty theo §16 stage 0 của kế hoạch tổng: trùng tên khác tỉnh, domain
   tin tức, timeout, cache hit, blacklist, công ty đã giải thể, thiếu tỉnh/thành.
2. Ghi kết quả V1 hiện tại của đúng 30 công ty đó: số URL, số contact, trạng thái
   kết thúc, credit đã dùng, thời lượng.
3. Lưu thành `docs/implementation/work-items/stage0-baseline.md`, kèm ID công ty
   và đường dẫn database đã đo.

### 3.1 Nhánh làm việc — không copy sang thư mục riêng

Mô hình "copy code sang `<V2_ROOT>`, V1 read-only, venv riêng" **đã bị bỏ**. Lý do:
repo hiện tại đã có luật riêng ở `AGENTS.md` §5 (mỗi thay đổi code nằm trên một
nhánh, merge về base branch khi người dùng xác nhận), và một bản copy song song sẽ
làm doc-sync gate (`scripts/check-doc-sync.sh` + hook chặn `git commit`) mất tác dụng.

Thay bằng:

1. Chạy `git status`. Nếu có thay đổi chưa commit không phải của mình — dừng, hỏi
   người dùng. Không branch chồng lên việc dở dang của người khác.
2. Ghi lại nhánh hiện tại; đó là **base branch** sẽ merge về, không mặc định là `main`.
3. Tạo nhánh làm việc từ đó, ví dụ `perf/stage1-remove-fixed-wait`,
   `fix/stage1-cache-readonly`, `fix/stage1-retry-attempts`.
4. Commit theo bước logic (§7), không dồn một commit cuối.
5. Chạy test (§8) và cập nhật tài liệu **trong cùng commit** (`AGENTS.md` §7).
6. Báo cáo cho người dùng rồi **dừng**. Chỉ merge sau khi được xác nhận rõ ràng.

Rollback không còn là "quay về bản V1 bên cạnh" mà là revert commit hoặc bỏ nhánh —
xem phần rollback của từng work item.

### 3.2 Tài liệu bàn giao — đã có sẵn, chỉ tạo work item

Bộ tài liệu bootstrap **đã tồn tại**: `AGENTS.md`, `docs/architecture/MAP.md`,
`INDEX.md`, `symbols.md`, `docs/implementation/STATUS.md`,
`scripts/check-doc-sync.sh`, `scripts/gen-symbols.sh` và hook chặn commit.
Không tạo lại, không ghi đè.

Trước commit code đầu tiên chỉ cần tạo:

```text
docs/implementation/work-items/stage0-baseline.md
docs/implementation/work-items/stage1-wait.md
docs/implementation/work-items/stage1-cache.md
docs/implementation/work-items/stage1-retry.md
```

Mỗi work item có owner, file scope, acceptance criteria và evidence.

`STATUS.md` theo đúng `AGENTS.md` §9: **thay nội dung, không nối thêm**, giữ dưới
~40 dòng, chỉ trả lời "đang làm gì / vừa quyết định gì / hành động tiếp theo là gì /
đang kẹt ở đâu". Mọi thứ đã xong nằm ở git history và file work item. Mẫu STATUS
8 mục trong §21.6 bản cũ đã bị rút lại vì mâu thuẫn với luật này.

### 3.3 Khóa dữ liệu

Trước migration:

0. **Ghi rõ đường dẫn database đích trong lệnh chạy.** Repo hiện có ít nhất hai file:
   `data/company_data.db` (1,98 GB, sửa lần cuối 17/07/2026) và
   `data/company_data_1013_companies.db` (310 MB). Chúng có số liệu khác nhau. Không
   dùng glob, không đoán, không giả định file nào là "production".
1. Dừng dashboard worker và mọi process có thể ghi vào database đích.
2. Tạo backup nhất quán bằng SQLite backup API; không chỉ copy riêng file `.db` khi WAL đang mở.
3. Ghi kích thước, checksum và đường dẫn backup vào `STATUS.md`.
4. Chạy audit read-only và lưu:
   - tổng dòng `search_results`;
   - số nhóm trùng;
   - số dòng dư;
   - số `filtered_links` đang tham chiếu dòng trùng;
   - nhóm lớn nhất;
   - tổng `credits_used`.
5. Chưa có backup được xác minh thì không chạy cleanup.

Con số 89.070 trong kế hoạch là baseline lịch sử **của một file database không được
ghi tên**. Script phải đo lại database đích tại thời điểm migration, không hardcode
con số này và cũng không dùng nó làm tiêu chí nghiệm thu.

Số đo tham chiếu ngày 2026-08-17:

| Database | Dòng `search_results` | Nhóm trùng | Dòng dư |
|---|---:|---:|---:|
| `data/company_data_1013_companies.db` | 193.588 | 19.069 | 19.946 (10,3%) |
| `data/company_data.db` | chưa đo | chưa đo | chưa đo |

Tỷ lệ trùng khớp với chẩn đoán ban đầu; con số tuyệt đối thì không.

## 4. Work item 1 — Bỏ thời gian chờ cố định

### 4.1 Hành vi đích

```text
Mặc định:
firecrawl_wait_for_ms = 0
DELAY_SECONDS = 0

Domain không có override:
không chờ thêm sau khi Firecrawl báo trang sẵn sàng

Domain đặc biệt:
có thể cấu hình wait hoặc selector riêng ở giai đoạn policy
```

Stage 1 giữ khả năng người vận hành đặt delay lớn hơn 0 để rollback nhanh, nhưng mặc định và UI đều là 0.

### 4.1b Đo trước, đổi mặc định sau — bắt buộc

Câu "3 giây không đem lại lợi ích gì" là **giả thuyết, chưa từng được đo**. Đây là
thay đổi duy nhất trong Stage 1 có thể **âm thầm làm giảm chất lượng dữ liệu**: một
trang nặng JavaScript (nội dung do trình duyệt dựng sau khi tải, không có sẵn trong
HTML gốc) đang dùng 3 giây đó để dựng xong, bỏ đi thì nội dung trả về ngắn hơn — và
hậu quả hiện ra ba bước sau dưới dạng thiếu số điện thoại, không phải dưới dạng lỗi.

Test ở §4.2 kiểm tra "không còn gọi sleep". Nó **không** phát hiện được mất nội dung.

Quy trình đo:

1. Chọn ≥50 URL đã có trong `scraped_pages`, trải đều theo nhóm domain thực tế
   (registry, tax directory, business directory, job portal, Facebook), cố tình bao
   gồm những trang nặng JavaScript nhất.
2. Scrape mỗi URL hai lần vào một database tạm: một lần `waitFor: 3000`, một lần `0`.
3. So sánh theo từng URL: kết quả HTTP, độ dài markdown, và số field mà
   `src/ai_extractor.py` trích được từ nội dung đó.
4. Chỉ đổi mặc định thành 0 khi **không nhóm domain nào mất nội dung**. Nhóm nào có
   mất thì nhận một entry wait/selector riêng theo domain — chính entry đó là cách
   sửa, không phải giữ lại giá trị mặc định toàn cục.
5. Lưu bảng so sánh làm evidence của work item này.

Bước này **tốn credit Firecrawl** nên cần người dùng đồng ý trước khi chạy. Nó là
thí nghiệm đo đạc, không phải test — quy tắc "không gọi API trả phí trong test" vẫn
giữ nguyên.

### 4.2 Viết test đỏ

Sửa `tests/test_scrape_module.py`:

1. Batch payload gửi `waitFor == 0`.
2. Sequential payload gửi `waitFor == 0`.
3. Hai URL trả thành công ngay với config mặc định không gọi `time.sleep`.
4. Cache hit không gọi sleep.
5. Override `DELAY_SECONDS > 0` vẫn được tôn trọng nếu người vận hành chủ động bật.
6. Poll interval của Batch API không bị nhầm với page `waitFor`; polling vẫn hoạt động.

Sửa test config:

```text
DELAY_SECONDS = 0
FIRECRAWL_WAIT_FOR_MS = 0
```

Không đo bằng thời gian thật; patch `time.sleep` và kiểm tra call.

### 4.3 Thay đổi code

| File | Thay đổi |
|---|---|
| `src/config.py` | Thêm `FIRECRAWL_WAIT_FOR_MS`, mặc định 0; đổi `DELAY_SECONDS` mặc định thành 0 |
| `src/scrape_module.py` | Cả batch và sequential lấy `waitFor` từ config, không hardcode 3000 |
| `src/scrape_module.py` | Chỉ sleep sau URL khi delay được cấu hình lớn hơn 0 |
| `pipeline_config.json` | Đổi default của hai key thành 0 |
| `dashboard/frontend/assets/app.js` | Hiển thị rõ “additional wait”; default 0, đơn vị ms/giây đúng |
| `docs/architecture/scrape-adapter.md` | Ghi input/output và invariant “không fixed wait” |

Không xóa poll sleep trong `_poll_firecrawl_batch()`. Đây là chờ kiểm tra trạng thái job, không phải thời gian chờ trang.

### 4.4 Tiêu chí nghiệm thu

- Tất cả test đỏ ở 4.2 chuyển xanh.
- `rg` không còn `"waitFor": 3000`.
- Config mới tạo có hai default bằng 0.
- Hai scrape success tuần tự không tạo sleep call.
- Cache hit không sleep.
- Không gọi API thật **trong test**.
- **Bảng so sánh A/B ở §4.1b tồn tại và cho thấy không nhóm domain nào mất nội dung**;
  nhóm nào mất thì đã có entry policy riêng theo domain.

### 4.5 Rollback

Không cần revert code để rollback vận hành. Đặt:

```text
FIRECRAWL_WAIT_FOR_MS=3000
DELAY_SECONDS=3
```

Nếu cần quay lại hoàn toàn, revert riêng commit Work item 1; không ảnh hưởng schema.

## 5. Work item 2 — Cache hit read-only và chống duplicate

Work item này chia thành hai hàng rào: code không tạo duplicate và database không cho duplicate lọt qua.

### 5.1 Định danh duy nhất

Danh tính một search result:

```text
(company_id, search_query, normalized_url)
```

Chuẩn hóa dùng đúng hàm production `src/utils.py::normalize_url` (hạ chữ thường
host, bỏ `www.`, bỏ dấu `/` cuối, bỏ `utm_*` và `fbclid`).

**Cột được ép duy nhất phải là cột đã chuẩn hóa.** Index trên cột `url` thô không
ép được danh tính này: hai dòng có normalized form giống nhau nhưng chuỗi lưu khác
nhau (`http://X.vn/a/` và `https://x.vn/a?utm_source=…`) vẫn lọt qua, và lỗi trùng
quay lại bằng cửa sau đối với mọi dòng đã ghi trước khi có chuẩn hóa.

Chọn một, và ghi rõ lựa chọn đó trong script migration:

- **Ưu tiên** — thêm cột `normalized_url`, điền cho **toàn bộ** bảng bằng hàm
  production, rồi tạo unique index trên `(company_id, search_query, normalized_url)`.
  Generated column (cột tự suy ra bằng biểu thức SQL) không dùng được vì
  `normalize_url` hiện không diễn đạt được bằng SQL — phải điền bằng Python.
- **Chấp nhận được** — ghi đè `url` thành dạng chuẩn hóa cho **mọi dòng**, không chỉ
  các dòng nằm trong nhóm trùng, rồi index `(company_id, search_query, url)`. Mất
  chuỗi gốc; chỉ chọn khi chắc chắn không chỗ nào cần URL thô.

Dù chọn cách nào, audit sau migration phải chứng minh: chuẩn hóa lại toàn bộ bảng
**không sinh thêm nhóm trùng mới**. Chỉ chuẩn hóa các dòng đang được dedupe chính là
lỗi mà mục này sinh ra để chặn.

Mọi đường insert phải chuẩn hóa URL tại một boundary chung trước khi chạm database, gồm:

- SearchModule;
- FirecrawlDeepSearch trong `CompanyRun`;
- manual injection;
- cache copy cho công ty khác;
- script/import khác gọi `insert_search_result()`.

### 5.2 Viết test đỏ — cache control flow

Thêm vào `tests/test_search_module.py`:

1. Cùng công ty cache hit 100 lần:
   - 0 API call;
   - số row không đổi;
   - ID trả về là ID đã lưu;
   - `SUM(credits_used)` không đổi.
2. Công ty B dùng cache của công ty A:
   - copy đúng một lần sang B;
   - lần chạy tiếp theo không thêm row;
   - credit của row reuse bằng 0.
3. Cache marker tồn tại nhưng không có persisted result:
   - gọi live search;
   - không trả `[]` giả.
4. `_execute_search_query()` trên cache hit:
   - phát event `cache_reused`;
   - không gọi `_save_results()`;
   - log cost bằng 0 và `data_saved=false`.

### 5.3 Sửa cache flow

Trong `SearchModule._execute_search_query()`:

```text
cache miss:
    gọi API
    _save_results()
    trả rows mới

cache hit:
    trả rows đã persist/materialize
    ghi cache_reused, cost=0
    KHÔNG gọi _save_results()
```

`_search_with_dedup()` được phép materialize kết quả sang một công ty khác vì schema hiện lưu theo company. Nhưng việc này chỉ xảy ra một lần và phải đi qua idempotent insert.

Không xây shared search artifact. Quyết định loại bỏ thiết kế đó ở §10.4 vẫn giữ nguyên.

### 5.4 Viết test đỏ — database barrier

Thêm vào `tests/test_database.py` và test concurrency:

1. Insert cùng key hai lần chỉ còn một row.
2. Hai thread/worker insert cùng key chỉ còn một row và đều nhận canonical row ID.
3. URL khác hình thức nhưng normalize giống nhau chỉ còn một row — khác scheme, khác
   `www.`, khác dấu `/` cuối, có `utm_*`.
4. Hai company khác nhau hoặc hai query khác nhau vẫn lưu độc lập.
5. Unique index tồn tại trên database mới, **trên cột đã chuẩn hóa**.
6. Migration chạy lại lần hai không đổi dữ liệu.
7. Sau migration, chuẩn hóa lại toàn bảng cho ra 0 nhóm trùng mới.
8. Sau migration, một công ty đang `done` vẫn qua được strict completion (§5.5b).

`insert_search_result()` nên dùng conflict handling có chủ đích:

```text
INSERT ... ON CONFLICT DO NOTHING
SELECT id của canonical row
```

Database vẫn từ chối insert trùng; application chuyển conflict thành kết quả idempotent thay vì làm worker chết.

### 5.5 Script cleanup transaction-safe

Tạo:

```text
scripts/migrate_search_results_unique.py
```

Script bắt buộc có:

- `--dry-run` mặc định;
- `--apply` mới được ghi;
- đường dẫn database explicit, không dùng glob;
- kiểm tra không có writer đang chạy;
- một transaction `BEGIN IMMEDIATE`;
- báo cáo trước/sau;
- rollback toàn bộ khi bất kỳ invariant nào fail.

Thuật toán:

1. Chuẩn hóa URL cho **toàn bộ** bảng theo cùng hàm production (§5.1) — không chỉ
   các row nằm trong nhóm trùng.
2. Với mỗi key trùng, chọn canonical row:
   - ưu tiên row có dữ liệu title/snippet đầy đủ;
   - sau đó ID nhỏ nhất;
   - giữ `result_rank` nhỏ nhất;
   - không cộng dồn credit của duplicate.
3. Điền metadata còn thiếu cho canonical row từ duplicate tốt nhất.
4. Chuyển mọi `filtered_links.search_result_id` từ duplicate sang canonical ID.
5. Xóa các row duplicate.
6. Tạo unique index trên cột đã chuẩn hóa (§5.1):

   ```sql
   CREATE UNIQUE INDEX idx_search_results_company_query_url
   ON search_results(company_id, search_query, normalized_url);
   ```

7. Kiểm tra trong cùng transaction:
   - duplicate groups = 0;
   - chuẩn hóa lại toàn bảng không sinh nhóm trùng mới;
   - không có `filtered_links` trỏ tới search result không tồn tại;
   - số company và query không đổi;
   - số row sau = số row trước − số row dư;
   - index tồn tại.
8. Chỉ commit khi tất cả kiểm tra đạt.

### 5.5b Ảnh hưởng dây chuyền phải kiểm trong cùng thay đổi

Gộp dòng trùng làm đổi ID mà bảng khác đang trỏ tới. Ba điểm bắt buộc kiểm:

1. `filtered_links.search_result_id` được trỏ về canonical (bước 4). Nhưng **chính
   `filtered_links` cũng tích lũy URL trùng qua mỗi lần chạy** (`MAP.md` §9, trap 4).
   Stage 1 **không** dedupe bảng này; đừng đọc kế hoạch như thể đã làm.
2. `src/completion_audit.py` cố ý join ứng viên scrape với kết quả **theo `url`, không
   theo `filtered_link_id`**, chính vì sự tích lũy đó. Sau migration phải kiểm: một
   mẫu công ty đang `done` vẫn còn `done`, không bị strict completion đẩy ngược trạng
   thái. Regression ở đây không mất dữ liệu — nó làm công ty bị xếp hàng chạy lại vô
   hạn, tệ hơn, vì âm thầm tiêu tiền.
3. Export và dashboard vẫn truy được từng contact về đúng một search result.

Migration cho database mới phải tạo unique index ngay. Migration cho database cũ phải dùng cùng cleanup logic; không đưa một câu `CREATE UNIQUE INDEX` đơn lẻ vào startup vì nó sẽ fail trên database còn duplicate.

### 5.6 Thứ tự rollout

1. Merge code ngăn duplicate mới và test.
2. Dừng toàn bộ writer.
3. Backup database và xác minh backup.
4. Chạy cleanup `--dry-run`; lưu report.
5. Chạy `--apply`.
6. Chạy audit sau migration.
7. Khởi động V2.
8. Chạy 100 cache hit offline/replay và xác nhận delta row = 0.

### 5.7 Tiêu chí nghiệm thu

- 100 cache hit thêm 0 row và 0 credit.
- Duplicate groups sau migration = 0, và chuẩn hóa lại toàn bảng không sinh nhóm mới.
- Unique index tồn tại, đặt trên cột đã chuẩn hóa.
- Không có orphan `filtered_links`.
- Strict completion vẫn cho `done` với mẫu công ty đã `done` trước migration.
- Hai worker insert cùng key vẫn chỉ có một row.
- Export và filter vẫn truy được canonical search result.
- Backup phục hồi thử được trên một database tạm.

### 5.8 Rollback

Nếu fail trước commit transaction: rollback tự động.

Nếu phát hiện lỗi sau migration:

1. Dừng writer.
2. Giữ database lỗi để điều tra.
3. Phục hồi bản backup đã xác minh.
4. Revert commit cache/migration hoặc sửa rồi chạy lại dry-run.

Không cố tái tạo các row đã xóa từ log.

## 6. Work item 3 — Retry đúng operation, đúng số attempt

### 6.1 Quy ước

```text
max_attempts = 3
```

Nghĩa là một lần gọi đầu tiên và tối đa hai lần gọi lại. Không dùng tên `max_retries` cho giá trị này vì dễ hiểu thành “một lần đầu + ba retry”.

Retry chỉ chạy lại API operation lỗi. Không chạy lại toàn bộ company pipeline.

### 6.2 Một owner cho mỗi attempt

Stage 1 tạo `src/v2/runtime/retry.py` với một retry executor nhỏ dùng chung cho các paid API boundary. `ConnectionManager` chỉ giữ connection pool và timeout; không tự retry HTTP status bên dưới executor.

Nếu giữ retry ẩn trong `urllib3` đồng thời có loop ở module, `max_attempts=3` có thể tạo nhiều hơn ba HTTP request.

**Kiểm kê đầy đủ — sáu owner, không phải năm.** Bản kế hoạch cũ bỏ sót
`src/rate_limiter.py`. Bỏ sót một owner là đủ để sinh retry lồng nhau: ba "attempt"
thành chín HTTP request. Xác minh 2026-08-17:

| Owner | Hiện đang làm gì | Sau Stage 1 |
|---|---|---|
| `src/connection_pool.py:75-78` | `urllib3` `Retry(total=max_retries, status_forcelist=[500, 502, 504])` — **không có 503** | Tắt retry theo HTTP status; chỉ giữ pool và timeout |
| `src/search_module.py:606-679` | Loop riêng, `max_retries=3`, chờ cố định 60s khi 429 | Giao cho executor |
| `src/scrape_module.py:235,462` | Hai loop riêng, `max_retries = 3` | Giao cho executor |
| `src/ai_extractor.py:371-545` | Loop riêng, `max_retries = 3`, đường xử lý 503 riêng chờ 60s, kết thúc bằng `{"status": "failed", "reason": "max_retries"}` | Giao cho executor; ngừng biến lỗi thành dict trông như thành công |
| `src/company_run.py:59` | Retry cả công ty, `max_retries = 2` | Bỏ khỏi vai trò retry (§6.6b) |
| `src/rate_limiter.py` (`AdaptiveRateLimiter`) | **Throttle (điều tiết tốc độ), không phải retry**: 429 nhân đôi delay, 403/503 nhảy lên delay tối đa kèm cooldown 5 phút | Giữ nguyên. Nó nắn thời gian chờ *trước* một lần gọi; tuyệt đối không đồng thời quyết định có gọi lại hay không |

Bảng này phơi ra một mâu thuẫn có thật: cùng một lỗi 503 đang được `ai_extractor`
chờ 60s rồi thử lại, `connection_pool` bỏ qua vì không có trong forcelist, còn
`rate_limiter` coi là cooldown 5 phút. Thống nhất ba chỗ này chính là phần việc thật
của work item 3.

Interface tối thiểu:

```text
execute(operation, policy, classify_error, should_stop, on_attempt)
    → result
    → RetryExhausted(cause, attempts)
    → CriticalError
    → SkippableError
```

Stage 6 sau này mở rộng module này và ghép với resource controller. Stage 1 chỉ triển khai phần cần để attempt chính xác và không bị nuốt lỗi.

### 6.3 Bảng phân loại

| Kết quả | Retry? | Kết thúc |
|---|---:|---|
| Timeout, connection reset, HTTP 408 | Có | `RetryableError` sau attempt cuối |
| HTTP 429 | Có | Tôn trọng `Retry-After`, rồi `RetryableError` nếu hết attempt |
| HTTP 500, 502, 503, 504 | Có | `RetryableError` sau attempt cuối |
| HTTP 400 | Không | `SkippableError`: request/config của operation sai |
| HTTP 401 | Không | `CriticalError`: API key sai, dừng pipeline |
| HTTP 402 | Không | `CriticalError`: hết credit, dừng pipeline |
| HTTP 404 hoặc lỗi company-specific chắc chắn | Không | `SkippableError` |
| DB corrupt hoặc invariant hỏng | Không | `CriticalError` |

HTTP 403 phải có rule theo provider trong policy; mặc định không retry và không được gom chung với 503.

### 6.4 Backoff

Policy:

```yaml
retry:
  max_attempts: 3
  base_delay_seconds: 2
  max_delay_seconds: 60
  honor_retry_after: true
  jitter: true
```

Ưu tiên thời gian chờ:

1. `Retry-After` hợp lệ do provider trả về.
2. Exponential backoff: khoảng 2 giây, 4 giây.
3. Cap tại 60 giây.
4. Jitter chỉ bật trong production; test inject clock/random để deterministic.

Backoff phải kiểm tra stop theo khoảng ngắn hoặc dùng interruptible event. Shutdown không chờ hết 60 giây.

### 6.5 Viết test đỏ

Thêm test table-driven cho retry executor:

1. `503, 503, 200` → đúng 3 call, success.
2. `timeout, timeout, 200` → đúng 3 call, success.
3. `500, 200`, `502, 200`, `504, 200` → đúng 2 call.
4. `400`, `401`, `402`, `404` → đúng 1 call.
5. `429` có `Retry-After: 7` → sleep 7 giây rồi retry.
6. `429` với HTTP-date hợp lệ → tính đúng delay không âm.
7. Ba lỗi retryable → đúng 3 call rồi `RetryExhausted`.
8. Stop trong backoff → thoát sớm, không gọi attempt tiếp.
9. Mỗi attempt có log: operation, attempt, max_attempts, status/error, delay, duration.
10. Retry không tạo duplicate search result, scraped page hoặc extracted contact.
11. Search/scrape cạn attempt → `companies.status = 'failed'` (§6.6b).
12. AI extraction cạn attempt → `companies.status = 'ai_extract_pending'`, checkpoint scrape còn nguyên (§6.6b).
13. Với `connection_pool` đã tắt retry theo status, không operation nào tạo quá `max_attempts` HTTP request.
14. Một lỗi 503 chỉ do đúng một owner xử lý; `AdaptiveRateLimiter` nắn delay nhưng không gọi lại (§6.2).

Thêm regression test ở từng adapter để bảo đảm lỗi không bị đổi thành `[]` hoặc `{"status":"failed"}` trước retry executor:

- `FirecrawlDeepSearch.search()`;
- `SearchModule._firecrawl_search()`;
- Batch start/poll và sequential scrape;
- Gemini Quick Search;
- AI Extractor.

### 6.6 Thay đổi code

| File | Thay đổi |
|---|---|
| `src/errors.py` | Giữ ba category; thêm error context/status code/cause nếu cần |
| `src/config.py` | Thêm `MAX_ATTEMPTS`; đọc `MAX_RETRIES` cũ như alias có warning |
| `src/connection_pool.py` | Tắt HTTP-status retry ẩn; giữ pool/timeout |
| `src/v2/runtime/retry.py` | Sở hữu attempt, backoff, jitter, stop check và attempt log |
| `src/firecrawl_deep_search.py` | Không trả `[]` cho 429/5xx/network; đưa lỗi vào executor |
| `src/search_module.py` | Dùng cùng classification; không biến 5xx thành unrecoverable sai loại |
| `src/scrape_module.py` | Không swallow `RetryableError` trong `except Exception`; batch và sequential cùng rule |
| `src/gemini_quick_search.py` | Propagate lỗi tạm thời, không đổi thành empty result |
| `src/ai_extractor.py` | Bỏ retry loop riêng sau khi đã chuyển sang executor |
| `src/company_run.py` | Bỏ immediate whole-company retry; nhận kết quả operation-exhausted và đặt status theo §6.6b |
| `src/rate_limiter.py` | Không sửa hành vi, nhưng phải bảo đảm nó không nằm trong đường retry — chỉ nắn delay trước khi gọi |
| `src/ai_extractor.py` | Ngoài việc bỏ retry loop: **xóa `_batch_short_pages` (dòng 285)**, hàm chết gộp nhiều trang vào một lần gọi AI |
| dashboard/config | Đổi nhãn “Max Retries” thành “Max Attempts”, mô tả gồm lần đầu |

Không chuyển tất cả resource/budget logic vào Stage 1. Việc đó vẫn thuộc Stage 6.

### 6.6b Operation cạn attempt thì công ty mang status nào

Bỏ retry cấp công ty để lại một câu hỏi mà bản kế hoạch cũ không trả lời: sau khi
một operation hết attempt, `companies.status` bằng gì? Để mở là nguy hiểm, vì
`src/completion_audit.py` đẩy ngược trạng thái mọi công ty chưa đạt strict
completion — chọn sai thì công ty bị chạy lại vô hạn.

Ánh xạ bắt buộc, đối chiếu `Pipeline.STATUS_FLOW` (`MAP.md` §3):

| Operation cạn attempt | Status công ty |
|---|---|
| Search hoặc scrape | `failed` — chạy lại từ đầu bước đó. Các row `scraped_pages` đã lưu vẫn giữ và vẫn được tái sử dụng |
| AI extraction | **Giữ `ai_extract_pending`.** Phần scrape đã trả tiền và đã lưu; không bao giờ lùi qua checkpoint này |
| `CriticalError` (401, 402, hỏng invariant DB) | Giữ checkpoint hiện tại, dừng cả batch — hành vi V1, không đổi |

Mỗi dòng cần một test khẳng định **`companies.status` sau cùng**, không chỉ khẳng
định loại exception được ném ra.

### 6.7 Logging bắt buộc

Mỗi attempt ghi:

```text
company_id
work_unit/operation
provider
attempt
max_attempts
http_status hoặc exception_type
decision = retry | fail | stop | success
delay_seconds
duration_ms
```

Log cuối operation ghi tổng attempt và kết quả. Không ghi API key, request Authorization hoặc toàn bộ response có dữ liệu nhạy cảm.

### 6.8 Tiêu chí nghiệm thu

- `503,503,200` thành công đúng attempt 3.
- Không case nào vượt `max_attempts`.
- 401/402 không retry.
- 429 dùng `Retry-After`.
- Shutdown ngắt backoff.
- Deep Search không còn che lỗi tạm thời bằng `[]`.
- `CompanyRun` không gọi lại toàn bộ công ty ngay lập tức, và status sau khi cạn
  attempt đúng theo bảng §6.6b.
- Chỉ còn một owner cho mỗi attempt; `rate_limiter` không nằm trong đường retry.
- `_batch_short_pages` đã bị xóa khỏi `src/ai_extractor.py`.
- Retry operation không sinh dữ liệu trùng.
- Tất cả test dùng mock/fixture; 0 paid API call.

### 6.9 Rollback

Giữ alias `MAX_RETRIES` trong một release để config cũ không vỡ. Nếu retry executor có regression, feature flag có thể quay về adapter cũ cho một batch nhỏ, nhưng không chạy đồng thời cả hai retry layer.

Rollback code không cần rollback schema. Unique index của Work item 2 vẫn giữ.

## 7. Thứ tự commit đề xuất

Mỗi commit phải chạy được test liên quan và cập nhật tài liệu **trong cùng commit**
theo `AGENTS.md` §7 — không để lại thành việc dọn sau. Hook
`.claude/hooks/precommit-doc-sync.sh` sẽ chặn `git commit` nếu thiếu.

| Commit | Nội dung |
|---:|---|
| 1 | `docs: record Stage 0 baseline and Stage 1 work items` |
| 2 | `test: lock fixed-wait, cache-hit and retry regressions` |
| 3 | `perf: remove unconditional scrape waits` |
| 4 | `fix: make search cache hits read-only` |
| 5 | `fix: make search-result inserts idempotent` |
| 6 | `data: dedupe search results and add unique index` |
| 7 | `fix: retry failed API operations with exact attempts` |
| 8 | `chore: delete the dead multi-page AI batching helper` |
| 9 | `test: verify Stage 1 replay and acceptance report` |

Không gộp commit migration database với sửa retry. Nếu rollback, hai rủi ro này phải tách độc lập.

Với mỗi commit chạm `src/` hoặc `dashboard/`: cập nhật `docs/architecture/MAP.md`
nếu thay đổi thuộc bảng ở `AGENTS.md` §7 (bước pipeline, giá trị `companies.status`,
bảng/cột, entry point, dịch vụ ngoài), chạy lại `./scripts/gen-symbols.sh` nếu thêm
hoặc đổi tên hàm/lớp public, và viết lại `STATUS.md` theo `AGENTS.md` §9.

## 8. Test gate cho toàn Stage 1

### Gate A — unit/regression

Nhóm test liên quan:

```text
venv/bin/python -m pytest -q \
  tests/test_scrape_module.py \
  tests/test_search_module.py \
  tests/test_database.py \
  tests/test_connection_pool.py \
  tests/test_company_run.py \
  tests/test_retry.py
```

Và toàn bộ suite theo `AGENTS.md` §6:

```text
venv/bin/python -m pytest tests/ -q
```

Baseline 2026-08-17: **190 passed, 1 failed**, lỗi duy nhất là
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`.
Bất kỳ lỗi nào thêm là do Stage 1.

### Gate B — replay không tốn credit

Điều kiện tiên quyết: baseline Stage 0 đã tồn tại (§3.0). Không có nó thì gate này
không kết luận được gì.

Chạy cùng bộ 30 công ty ở Stage 0:

- số URL/contact không giảm ngoài khác biệt đã giải thích;
- 0 API request;
- cache hit thêm 0 row;
- không có duplicate mới;
- trạng thái resume không lùi.

### Gate C — migration rehearsal

Trên bản copy database:

1. Dry-run report đúng.
2. Apply thành công.
3. Apply lần hai là no-op.
4. Audit không có duplicate/orphan.
5. Export và dashboard đọc được.
6. Restore backup thành công.

### Gate D — live smoke có kiểm soát

Chỉ sau khi người dùng cho phép gọi API:

- 3 công ty mẫu;
- database V2 riêng;
- cost cap nhỏ;
- gồm một cache hit, một trang tĩnh và một lỗi 503 giả lập trước live;
- so sánh số request, thời gian, credit và row delta với V1.

## 9. Điều kiện hoàn thành

Stage 1 chỉ được ghi `completed` khi:

1. Cả ba work item đạt acceptance criteria.
2. Targeted test xanh, và full suite không có lỗi nào ngoài baseline đã biết (§8 Gate A).
3. Migration rehearsal và restore rehearsal thành công.
4. Bảng so sánh A/B của `waitFor` tồn tại và không nhóm domain nào mất nội dung (§4.1b).
5. 30-company replay có báo cáo, đối chiếu với baseline Stage 0.
6. `docs/implementation/STATUS.md` có command, kết quả, file đổi và next action, viết theo `AGENTS.md` §9.
7. `docs/architecture/MAP.md` và `INDEX.md` phản ánh config, cache identity, schema và retry contract; `symbols.md` đã chạy lại nếu có symbol mới.
8. `bash scripts/check-doc-sync.sh` chạy qua.
9. Công việc nằm trên nhánh riêng và **chưa merge cho tới khi người dùng xác nhận rõ ràng** (`AGENTS.md` §5).
10. Không có paid API call ngoài phép đo §4.1b và live smoke, cả hai đều đã được người dùng cho phép.

Nếu một mục chưa đạt, Stage 1 giữ `in_progress`; không đánh dấu hoàn thành theo cảm tính.

## 10. Ước lượng và điểm kiểm tra của người dùng

| Work item | AI implementation | Người dùng kiểm tra | Rủi ro chính |
|---|---:|---:|---|
| Stage 0 baseline | 1 phiên | 1 giờ | Mẫu 30 công ty không phủ hết các ca khó |
| Bỏ fixed wait (gồm đo A/B §4.1b) | 1–2 phiên | 2 giờ | Mất nội dung trang nặng JS mà test không thấy; nhầm poll delay với page wait |
| Cache + migration | 2 phiên | 3–4 giờ | Cleanup sai quan hệ dữ liệu; index đặt trên cột chưa chuẩn hóa |
| Retry | 2 phiên | 3 giờ | Retry lồng nhau; công ty mang sai status sau khi cạn attempt |
| Replay và handoff | 1 phiên | 2 giờ | Chấp nhận kết quả khi chưa có evidence |

Tổng dự kiến: 7–8 phiên AI và 11–12 giờ kiểm tra của người dùng — cao hơn ước lượng
gốc vì đã thêm Stage 0 và phép đo A/B. Migration trên database lớn
(`data/company_data.db`, 1,98 GB) có thể cần thêm thời gian chạy, nhưng không mở
rộng phạm vi nghiệp vụ.

## 11. Nhật ký sửa đổi

| Ngày | Mục | Thay đổi |
|---|---|---|
| 2026-07-29 | tất cả | Bản đầu, dẫn xuất từ §16 stage 1 của kế hoạch tổng. |
| 2026-08-17 | 1, 2, 3.0, 3.1, 3.2, 3.3, 4.1b, 4.4, 5.1, 5.5, 5.5b, 5.4, 5.7, 6.2, 6.5, 6.6, 6.6b, 6.8, 7, 8, 9, 10, 11 | Đồng bộ với repo thật. Bỏ mô hình copy sang thư mục V2, thay bằng nhánh làm việc trong repo này theo `AGENTS.md` §5; bộ tài liệu bootstrap đã có sẵn nên chỉ tạo work item, `STATUS.md` theo `AGENTS.md` §9. Thêm §3.0 Stage 0 là điều kiện tiên quyết (hiện chưa tồn tại). Đối chiếu lại toàn bộ bằng chứng `file:line` ngày 2026-08-17 và thêm `_batch_short_pages`. Ghi số đo duplicate mới, bắt buộc nêu tên database đích. Thêm §4.1b cổng đo A/B trước khi đổi `waitFor` về 0. Thêm quy tắc unique index phải đặt trên cột đã chuẩn hóa và phải chuẩn hóa toàn bảng (§5.1, §5.5), thêm §5.5b về `filtered_links` và strict completion. Thêm owner thứ sáu `src/rate_limiter.py` vào kiểm kê retry và chỉ ra mâu thuẫn 503 giữa ba chỗ (§6.2). Thêm §6.6b ánh xạ `companies.status` khi operation cạn attempt. Cập nhật baseline test toàn suite (190 passed, 1 failed) và điều kiện hoàn thành. |
