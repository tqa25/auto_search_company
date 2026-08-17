# Bàn giao việc: Stage 1 — Work item 3 (Retry correctness)

> File này là **hướng dẫn thực thi**, viết cho một AI agent khác tiếp nhận và làm.
> Đọc hết mục 1–4 trước khi gõ dòng code đầu tiên.
> Người giao việc: phiên Claude điều phối. Ngày giao: 2026-08-17.
> Repo: `/home/ubuntu/workspaces2/projects/auto_search_company` (**không có** hậu tố `_v1`).

---

## 1. Đọc context thế nào cho đúng — làm trước tiên

Repo này có luật riêng về cách đọc code, ghi trong `AGENTS.md` mục 1–2. Tóm tắt:

**Bước 1 — đọc đúng hai file này, không đọc gì thêm:**

1. `docs/architecture/MAP.md` — hệ thống chạy thế nào (ổn định, ít đổi)
2. `docs/implementation/STATUS.md` — công việc đang đứng ở đâu (thay đổi liên tục)

**Bước 2 — khi cần tìm code cụ thể, đi theo thứ tự rẻ nhất:**

1. `docs/architecture/INDEX.md` — "muốn sửa X thì vào file nào"
2. `docs/architecture/symbols.md` — bảng tra tên hàm/class → `file:dòng`
3. `grep -n "<tên hàm cụ thể>"` — tìm đúng định danh
4. `Read` với `offset`/`limit` quanh dòng vừa tìm được

**CẤM tuyệt đối:**

- **Không đọc nguyên file dài quá 500 dòng.** Trong work item này, ba file dính luật đó:
  `src/search_module.py` (749 dòng), `src/ai_extractor.py` (707 dòng),
  `src/scrape_module.py` (670 dòng). Tìm đúng hàm rồi đọc quanh nó, đừng đọc cả file.
- **Không đọc lan man `src/`, `dashboard/`, `tests/` để "làm quen hệ thống".**
  `MAP.md` tồn tại chính là để khỏi phải làm chuyện đó.
- Nếu thấy `MAP.md` mô tả sai so với code: **code đúng, MAP.md sai** — sửa `MAP.md`
  ngay trong cùng commit, kể cả khi chỗ sai đó không liên quan việc bạn đang làm
  (`AGENTS.md` mục 10).

**Tài liệu KHÔNG được tin** (lịch sử, đã lỗi thời): `PROJECT_HANDOVER.md`,
`docs/v1-operational-audit*.md`. Chỉ mở khi cần hiểu lý do nghiệp vụ, và không bao giờ
được ưu tiên hơn code.

---

## 2. Bối cảnh: đang ở đâu trong kế hoạch tổng

Kế hoạch nâng cấp V2 chia làm nhiều giai đoạn. Vị trí hiện tại:

- **Giai đoạn 0 — XONG** (commit `2bdbba7`, `8cd7558`). Đã chốt bộ mẫu 30 công ty làm
  đường mốc so sánh. File: `docs/implementation/work-items/stage0-baseline.md`.
- **Giai đoạn 1 — CHƯA BẮT ĐẦU.** Gồm 3 work item. **Bạn được giao đúng work item 3.**

Kế hoạch chi tiết nằm ở `docs/v2-stage1-critical-fixes-implementation-plan.md`.
Đọc **mục 6** (work item 3) và **mục 8, 9** (cổng kiểm tra, định nghĩa hoàn thành).
Không cần đọc mục 4 và 5 — đó là hai work item khác, không giao cho bạn.

---

## 3. Phạm vi: được làm gì, cấm làm gì

### 3.1 ĐƯỢC GIAO — Work item 3: gộp toàn bộ logic thử lại về một chỗ

Hiện tại có **sáu chỗ** trong code tự quyết định "gọi lại API lần nữa", chồng lên nhau.
Hậu quả: cấu hình ghi "thử 3 lần" nhưng thực tế bắn 9 request thật (3 lớp trên × 3 lớp
dưới), tốn gấp ba tiền mà không ai biết.

Việc của bạn: tạo một bộ thử lại duy nhất, các chỗ còn lại gọi vào nó.

### 3.2 CẤM — không được đụng vào, kể cả khi thấy "tiện tay"

| Cấm | Lý do |
|---|---|
| **Mọi lệnh gọi API thật** (Firecrawl, Gemini) | Tốn tiền thật. Work item này chạy 100% bằng mock. Nếu bạn nghĩ cần gọi thật → dừng, báo người dùng, đừng tự quyết |
| **Work item 1** — sửa `waitFor: 3000`, `DELAY_SECONDS` | Bị chặn bởi phép đo A/B ở mục 4.1b, phép đo đó tốn credit Firecrawl và cần người dùng duyệt riêng |
| **Work item 2** — cache hit, unique index, script migrate | Phải sao lưu database production 1,98 GB trước, cần người dùng duyệt riêng |
| **Mọi thao tác ghi vào `data/*.db`** | Work item này không cần đụng database. Không `UPDATE`, không `DELETE`, không `CREATE INDEX` |
| **`git merge` vào nhánh gốc** | `AGENTS.md` mục 5: chỉ merge sau khi người dùng nói rõ đồng ý |
| **`git push`, mở pull request** | Không được, trừ khi người dùng yêu cầu |
| **Tắt / sửa / vòng qua hook `.claude/hooks/precommit-doc-sync.sh`** | Hook đó chặn commit khi tài liệu chưa cập nhật. Nếu bị chặn → sửa tài liệu, không phải sửa hook |

---

## 4. Luật sửa code của dự án — bắt buộc theo

Trích từ `AGENTS.md` mục 5–8.

### 4.1 Nhánh làm việc

```bash
cd /home/ubuntu/workspaces2/projects/auto_search_company
git status          # PHẢI sạch. Nếu có thay đổi lạ không phải của bạn → DỪNG, hỏi người dùng
git branch --show-current   # ghi lại tên này — đây là nhánh gốc, sau này merge về đây
git checkout -b refactor/stage1-retry-executor
```

Nhánh gốc hiện tại là `snapshot/ban-lasted-20260730` — **không phải `main`**. Merge về
đúng nhánh gốc, không phải `main`.

### 4.2 Commit theo bước, không dồn một cục

Kế hoạch mục 7 quy định thứ tự commit. Phần thuộc work item 3:

| # | Commit message | Nội dung |
|---|---|---|
| 1 | `docs: record Stage 1 retry work item` | Tạo `docs/implementation/work-items/stage1-retry.md` |
| 2 | `test: lock retry regressions` | Test đỏ — viết test trước, để nó fail, chứng minh lỗi có thật |
| 3 | `fix: retry failed API operations with exact attempts` | Sửa code cho test xanh |
| 4 | `chore: delete the dead multi-page AI batching helper` | Xóa hàm chết `_batch_short_pages` |

Commit 4 tách riêng, **không gộp** vào commit 3 — để lỡ có vấn đề thì revert độc lập được.

### 4.3 Tài liệu là một phần của commit, không phải việc làm sau

`AGENTS.md` mục 7 — bảng tra cứu:

| Bạn sửa gì | Bắt buộc cập nhật |
|---|---|
| Thêm/đổi tên class hoặc hàm public | chạy lại `./scripts/gen-symbols.sh` |
| Hợp đồng retry, giá trị `companies.status`, mã lỗi | `docs/architecture/MAP.md` — chỉ phần liên quan |
| File nào chịu trách nhiệm việc gì, test nào phủ cái gì | `docs/architecture/INDEX.md` |
| Bất cứ thứ gì | `docs/implementation/STATUS.md` |

`STATUS.md` viết theo `AGENTS.md` mục 9: **ghi đè, không nối thêm**, dưới ~40 dòng, chỉ
trả lời "đang làm gì / vừa quyết gì / việc chạy được tiếp theo là gì / đang kẹt gì".
Việc đã xong thuộc về git history, không nhét vào đây.

### 4.4 Kiểm tra

```bash
venv/bin/python -m pytest tests/ -q
```

**Đường mốc đã biết (2026-08-17): 190 passed, 1 failed.** Cái fail đó là
`test_dashboard_import_filters.py::test_runner_restart_worker_starts_new_process_after_terminating_runtime_workers`
(`KeyError: 'stopped_pids'`) — có sẵn từ trước, không phải lỗi của bạn.

**Bất kỳ test nào fail thêm ngoài cái đó là do bạn gây ra.** Không được báo "xong" khi
còn fail thêm.

Bộ test hẹp cho work item này (chạy nhanh trong lúc làm):

```bash
venv/bin/python -m pytest -q tests/test_scrape_module.py tests/test_search_module.py tests/test_company_run.py tests/test_connection_pool.py tests/test_retry.py
```

Lưu ý `tests/test_retry.py` **chưa tồn tại** — chính bạn tạo nó ở commit 2.

Trước khi commit:

```bash
bash scripts/check-doc-sync.sh
```

---

## 5. Nội dung công việc — chi tiết

### 5.1 Sáu chỗ đang tự thử lại (đã xác minh trên code ngày 2026-08-17)

| # | File:dòng | Đang làm gì | Sau khi sửa |
|---|---|---|---|
| 1 | `src/connection_pool.py:75-78` | urllib3 `Retry(total=..., status_forcelist=[500,502,504])` — **thiếu 503** | Tắt thử lại theo mã HTTP. Chỉ giữ quản lý kết nối và timeout |
| 2 | `src/search_module.py:606-679` | vòng lặp riêng, `max_retries=3`, gặp 429 thì ngủ cứng 60 giây | Gọi vào executor |
| 3 | `src/scrape_module.py:235` và `:462` | **hai** vòng lặp riêng biệt, `max_retries=3` | Gọi vào executor |
| 4 | `src/ai_extractor.py:371-545` | vòng lặp riêng + nhánh 503 ngủ 60 giây, kết thúc trả `{"status":"failed","reason":"max_retries"}` — **lỗi trông như thành công** | Gọi vào executor; không được biến lỗi thành dict giả vờ hợp lệ |
| 5 | `src/company_run.py:59` | thử lại **nguyên cả công ty**, `max_retries=2` | Bỏ vai trò thử lại. Xử lý theo mục 5.4 dưới đây |
| 6 | `src/rate_limiter.py` (`AdaptiveRateLimiter`) | Điều tiết tốc độ, **không phải** thử lại: 429 → gấp đôi thời gian chờ; 403/503 → nhảy lên mức chờ tối đa + nghỉ 5 phút | **Giữ nguyên.** Chỉ xác nhận nó nằm ngoài đường thử lại |

**Bỏ sót bất kỳ chỗ nào trong sáu chỗ trên là hỏng cả work item** — vì hai lớp thử lại
lồng nhau sẽ nhân số request lên.

### 5.2 Mâu thuẫn phải giải quyết: một lỗi 503 đang được xử lý ba kiểu cùng lúc

Đây mới là phần lõi của công việc, không phải việc dọn code cho gọn:

- `src/ai_extractor.py` → ngủ 60 giây rồi thử lại
- `src/connection_pool.py` → bỏ qua, không thử lại (503 không có trong `status_forcelist`)
- `src/rate_limiter.py` → coi là tín hiệu quá tải, nghỉ 5 phút

Ba hành vi này cùng chạy trên một sự kiện. Phải thống nhất về một quy tắc duy nhất, và
ghi quy tắc đó vào `MAP.md`.

### 5.3 File cần sửa

| File | Việc |
|---|---|
| `src/v2/runtime/retry.py` | **TẠO MỚI.** Thư mục `src/v2/` hiện chưa tồn tại — bạn tạo. Nơi duy nhất giữ: đếm lần thử, tính thời gian chờ tăng dần (backoff), thêm nhiễu ngẫu nhiên (jitter), quyết định dừng, ghi log |
| `src/errors.py` | Phân loại lỗi: tạm thời (đáng thử lại) và vĩnh viễn (thử lại vô ích) |
| `src/config.py:180` | Thêm `MAX_ATTEMPTS`. `MAX_RETRIES` cũ giữ làm tên gọi thay thế, in cảnh báo khi ai còn dùng. **Chú ý ngữ nghĩa: `MAX_ATTEMPTS=3` nghĩa là 1 lần đầu + 2 lần thử lại**, không phải 4 |
| `src/connection_pool.py` | Tắt thử lại theo mã HTTP |
| `src/firecrawl_deep_search.py` | Đang trả `[]` khi gặp 429/5xx/lỗi mạng — phải để lỗi nổi lên, vì `[]` bị hiểu nhầm thành "tìm thấy 0 kết quả" |
| `src/search_module.py` | Dùng bộ phân loại lỗi chung |
| `src/scrape_module.py` | Đang nuốt `RetryableError` trong `except Exception` trần — bỏ |
| `src/gemini_quick_search.py` | Để lỗi tạm thời nổi lên, đừng trả kết quả rỗng |
| `src/ai_extractor.py` | Bỏ vòng lặp thử lại riêng sau khi chuyển sang executor |
| `src/company_run.py:57-81` | Bỏ thử lại nguyên công ty ở dòng 59. Xử lý theo mục 5.4 |
| `dashboard/` (phần cấu hình) | Đổi nhãn "Max Retries" → "Max Attempts" |

### 5.4 Khi một thao tác hết số lần thử → `companies.status` là gì

Bảng này quan trọng nhất trong cả work item. Mỗi dòng phải có test riêng, và test phải
kiểm **giá trị `companies.status` cuối cùng**, không phải chỉ kiểm "có ném ra exception":

| Thao tác cạn lượt | `companies.status` | Vì sao |
|---|---|---|
| Search hoặc scrape | `failed` | Chạy lại từ đầu bước đó. Các dòng `scraped_pages` đã có vẫn giữ và dùng lại |
| Trích xuất bằng AI | **giữ nguyên `ai_extract_pending`** | Tiền scrape đã tiêu và dữ liệu đã lưu. Tuyệt đối không lùi qua điểm lưu này, lùi là mất tiền đã trả |
| `CriticalError` (401, 402, vỡ ràng buộc DB) | giữ nguyên điểm lưu hiện tại, dừng cả batch | Giống V1, không đổi |

### 5.5 Xóa hàm chết

`src/ai_extractor.py:285` — hàm `_batch_short_pages`, không còn ai gọi. Xóa ở commit
riêng (commit 4). Trước khi xóa, `grep -rn "_batch_short_pages" src/ tests/ dashboard/`
để chắc chắn thật sự không ai dùng.

---

## 6. Định nghĩa "xong"

Chưa xong nếu còn thiếu bất kỳ mục nào:

- [ ] Làm trên nhánh riêng `refactor/stage1-retry-executor`, **chưa merge**
- [ ] Đủ 4 commit theo thứ tự mục 4.2, commit xóa hàm chết tách riêng
- [ ] Test đỏ được viết **trước** phần sửa, và có bằng chứng nó từng fail
- [ ] `venv/bin/python -m pytest tests/ -q` → không fail thêm ngoài 1 cái đã biết
- [ ] Mỗi dòng trong bảng 5.4 có một test kiểm `companies.status`
- [ ] Cả sáu chỗ ở bảng 5.1 đã xử lý — **liệt kê rõ từng chỗ đã làm gì** khi báo cáo
- [ ] Quy tắc xử lý 503 thống nhất, đã ghi vào `MAP.md`
- [ ] `./scripts/gen-symbols.sh` đã chạy lại (vì có class/hàm public mới)
- [ ] `MAP.md`, `INDEX.md`, `STATUS.md` cập nhật trong cùng commit với code
- [ ] `bash scripts/check-doc-sync.sh` → pass
- [ ] **Không có lệnh gọi API thật nào được thực hiện**

---

## 7. Báo cáo lại thế nào

Làm xong thì **dừng lại, báo cáo, không merge**. Báo đúng những mục sau — bằng chữ, không
chỉ nói "đã xong":

1. **Kết quả test, dán nguyên văn dòng cuối của pytest.** Nếu có fail thêm → nói thẳng,
   đừng giấu, đừng sửa vòng quanh cho qua.
2. **Sáu chỗ ở bảng 5.1**: từng chỗ đã xử lý ra sao. Chỗ nào không đụng tới thì nói rõ
   vì sao.
3. **Quy tắc 503 cuối cùng** đã chọn là gì, và vì sao chọn thế.
4. **Danh sách file đã sửa** + 4 mã commit.
5. **Chỗ nào bạn không chắc**, hoặc phải tự suy đoán vì kế hoạch không nói rõ. Cứ nói ra,
   phần này quan trọng hơn bạn nghĩ — người kiểm sẽ soi đúng vào đó.
6. Xác nhận: **không gọi API thật, không ghi vào `data/*.db`, không merge, không push.**

Nếu giữa chừng phát hiện kế hoạch mâu thuẫn với code thật: **dừng và báo**, đừng tự chọn
một bên rồi đi tiếp.
