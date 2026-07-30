# Kế hoạch triển khai chi tiết V2 — Giai đoạn 1

> Phạm vi: ba sửa lỗi có giá trị cao nhất và rủi ro triển khai thấp nhất
> Ngày lập: 2026-07-29
> Nguồn quyết định: `docs/v2-modular-refactor-plan.md`
> Không gọi API trả phí trong test
> Các đường dẫn code bên dưới là đường dẫn tương đối trong bản copy V2

## 1. Ba mục được chọn

Ba mục này chính là “ba lỗi rẻ nhất” ở §16.2 của kế hoạch V2:

1. Bỏ thời gian chờ cố định: `waitFor: 3000` và `DELAY_SECONDS=3`.
2. Cache hit không lưu lại; dọn dữ liệu trùng và thêm unique key.
3. Retry đủ số attempt, phân loại đúng lỗi tạm thời và không retry lại toàn bộ công ty.

Thứ tự triển khai:

```text
Khóa baseline và test đỏ
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

| Vấn đề | Code hiện tại | Hậu quả |
|---|---|---|
| Batch Scrape chờ cố định | `src/scrape_module.py`, `_start_firecrawl_batch()`: `"waitFor": 3000` | Mọi URL trong batch bị chờ thêm |
| Scrape tuần tự chờ cố định | `scrape_url()`: `"waitFor": 3000`; `scrape_company()` gọi `time.sleep(delay)` | Hai URL nhanh vẫn bị cộng thêm thời gian |
| Config mặc định vẫn là 3 giây | `src/config.py`: `DELAY_SECONDS` mặc định `3.0`; dashboard và `pipeline_config.json` cũng hiển thị `3.0` | Sửa một đường gọi vẫn chưa đủ |
| Cache hit vẫn đi qua hàm save | `SearchModule._execute_search_query()` luôn gọi `_save_results()` sau `_search_with_dedup()` | Dòng cache cũ bị insert thêm |
| Không có hàng rào database | `search_results` chỉ có index theo `company_id` | Hai worker hoặc code sai vẫn ghi trùng |
| Deep Search che lỗi tạm thời | `FirecrawlDeepSearch.search()` trả `[]` cho 429, 5xx và exception | Lớp retry phía trên không thấy lỗi |
| Retry bị chia nhiều nơi | `ConnectionManager`, `SearchModule`, `ScrapeModule`, `AIExtractor`, `CompanyRun` đều có loop riêng | Một operation có thể bị retry lồng nhau hoặc không retry |
| Company retry sai cấp | `CompanyRun._run_with_retries()` có `max_retries=2` và chạy lại pipeline attempt | Có thể gọi lại bước đã trả tiền thay vì chỉ operation lỗi |

Baseline test đã chạy ngày 2026-07-29:

```text
pytest -q \
  tests/test_scrape_module.py \
  tests/test_search_module.py \
  tests/test_company_run.py \
  tests/test_connection_pool.py \
  tests/test_database.py

53 passed
```

Baseline này chỉ chứng minh test cũ đang xanh. Nó chưa khóa ba hành vi lỗi; phải thêm test đỏ trước khi sửa.

## 3. Điều kiện bắt đầu

### 3.1 Tạo và khóa bản V2

1. Xác định chính xác source state được copy: commit hiện tại và danh sách file chưa commit.
2. Không tự động bỏ hoặc ghi đè thay đổi đang có của người dùng.
3. Copy code sang `<V2_ROOT>` theo §1 của kế hoạch tổng; không copy `venv/`, output và Graphify.
4. V1 chuyển sang chỉ đọc trong thời gian làm Stage 1.
5. Tạo venv mới cho V2 và chạy lại baseline test.

Mọi thay đổi dưới đây thực hiện trong V2. V1 chỉ dùng để so sánh và rollback.

### 3.2 Khởi tạo tài liệu bàn giao

Trước commit code đầu tiên, tạo:

```text
AGENTS.md
docs/architecture/INDEX.md
docs/implementation/STATUS.md
docs/implementation/work-items/stage1-wait.md
docs/implementation/work-items/stage1-cache.md
docs/implementation/work-items/stage1-retry.md
```

Mỗi work item có owner, file scope, acceptance criteria và evidence theo §21.6.

### 3.3 Khóa dữ liệu

Trước migration:

1. Dừng dashboard worker và mọi process có thể ghi database V2.
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

Con số 89.070 trong kế hoạch là baseline lịch sử. Script phải đo lại database V2 tại thời điểm migration, không hardcode con số này.

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
- Không gọi API thật.

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
3. URL khác hình thức nhưng normalize giống nhau chỉ còn một row.
4. Hai company khác nhau hoặc hai query khác nhau vẫn lưu độc lập.
5. Unique index tồn tại trên database mới.
6. Migration chạy lại lần hai không đổi dữ liệu.

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

1. Chuẩn hóa URL của các row cần xử lý theo cùng hàm production.
2. Với mỗi key trùng, chọn canonical row:
   - ưu tiên row có dữ liệu title/snippet đầy đủ;
   - sau đó ID nhỏ nhất;
   - giữ `result_rank` nhỏ nhất;
   - không cộng dồn credit của duplicate.
3. Điền metadata còn thiếu cho canonical row từ duplicate tốt nhất.
4. Chuyển mọi `filtered_links.search_result_id` từ duplicate sang canonical ID.
5. Xóa các row duplicate.
6. Tạo unique index:

   ```sql
   CREATE UNIQUE INDEX idx_search_results_company_query_url
   ON search_results(company_id, search_query, url);
   ```

7. Kiểm tra trong cùng transaction:
   - duplicate groups = 0;
   - không có `filtered_links` trỏ tới search result không tồn tại;
   - số company và query không đổi;
   - số row sau = số row trước − số row dư;
   - index tồn tại.
8. Chỉ commit khi tất cả kiểm tra đạt.

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
- Duplicate groups sau migration = 0.
- Unique index tồn tại.
- Không có orphan `filtered_links`.
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
| `src/company_run.py` | Bỏ immediate whole-company retry; nhận kết quả operation-exhausted và giữ checkpoint/status phù hợp |
| dashboard/config | Đổi nhãn “Max Retries” thành “Max Attempts”, mô tả gồm lần đầu |

Không chuyển tất cả resource/budget logic vào Stage 1. Việc đó vẫn thuộc Stage 6.

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
- `CompanyRun` không gọi lại toàn bộ công ty ngay lập tức.
- Retry operation không sinh dữ liệu trùng.
- Tất cả test dùng mock/fixture; 0 paid API call.

### 6.9 Rollback

Giữ alias `MAX_RETRIES` trong một release để config cũ không vỡ. Nếu retry executor có regression, feature flag có thể quay về adapter cũ cho một batch nhỏ, nhưng không chạy đồng thời cả hai retry layer.

Rollback code không cần rollback schema. Unique index của Work item 2 vẫn giữ.

## 7. Thứ tự commit đề xuất

Mỗi commit phải chạy được test liên quan và cập nhật `STATUS.md`.

| Commit | Nội dung |
|---:|---|
| 1 | `docs: bootstrap Stage 1 status and module contracts` |
| 2 | `test: lock fixed-wait, cache-hit and retry regressions` |
| 3 | `perf: remove unconditional scrape waits` |
| 4 | `fix: make search cache hits read-only` |
| 5 | `fix: make search-result inserts idempotent` |
| 6 | `data: dedupe search results and add unique index` |
| 7 | `fix: retry failed API operations with exact attempts` |
| 8 | `test: verify Stage 1 replay and acceptance report` |

Không gộp commit migration database với sửa retry. Nếu rollback, hai rủi ro này phải tách độc lập.

## 8. Test gate cho toàn Stage 1

### Gate A — unit/regression

```text
pytest -q \
  tests/test_scrape_module.py \
  tests/test_search_module.py \
  tests/test_database.py \
  tests/test_connection_pool.py \
  tests/test_company_run.py \
  tests/test_retry.py
```

### Gate B — replay không tốn credit

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
2. Targeted test và full relevant test suite xanh.
3. Migration rehearsal và restore rehearsal thành công.
4. 30-company replay có báo cáo.
5. `docs/implementation/STATUS.md` có command, kết quả, file đổi và next action.
6. `docs/architecture/` phản ánh config, cache identity, schema và retry contract.
7. Không có paid API call ngoài live smoke đã được người dùng cho phép.

Nếu một mục chưa đạt, Stage 1 giữ `in_progress`; không đánh dấu hoàn thành theo cảm tính.

## 10. Ước lượng và điểm kiểm tra của người dùng

| Work item | AI implementation | Người dùng kiểm tra | Rủi ro chính |
|---|---:|---:|---|
| Bỏ fixed wait | 1 phiên | 1 giờ | Nhầm poll delay với page wait |
| Cache + migration | 2 phiên | 3–4 giờ | Cleanup sai quan hệ dữ liệu |
| Retry | 2 phiên | 3 giờ | Retry lồng nhau hoặc retry lại cả công ty |
| Replay và handoff | 1 phiên | 2 giờ | Chấp nhận kết quả khi chưa có evidence |

Tổng dự kiến: 5–6 phiên AI và 9–10 giờ kiểm tra của người dùng. Migration trên database lớn có thể cần thêm thời gian chạy, nhưng không mở rộng phạm vi nghiệp vụ.
