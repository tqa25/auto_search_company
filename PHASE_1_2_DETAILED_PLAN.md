# KẾ HOẠCH CHI TIẾT — GIAI ĐOẠN 1 & 2
## Phân chia nhiệm vụ theo từng Agent

**Tài liệu tham chiếu:** [AUTO_COMPANY_SEARCH_PROJECT_PLAN.md](./AUTO_COMPANY_SEARCH_PROJECT_PLAN.md)  
**Ngày lập:** 13/04/2026  

---

## HƯỚNG DẪN SỬ DỤNG TÀI LIỆU NÀY

Tài liệu này chia nhỏ Giai đoạn 1 & 2 thành **các nhiệm vụ độc lập**, mỗi nhiệm vụ được giao cho **1 agent (phiên AI riêng biệt)**. Mỗi agent chỉ cần đọc phần prompt dành cho nó, **không cần biết toàn bộ dự án**, nhờ đó:
- Agent không bị quá tải context → giảm hallucination
- Mỗi task có input/output rõ ràng → dễ kiểm tra
- Có thể chạy song song nếu task không phụ thuộc nhau

### Quy ước
- 🟦 = Task có thể chạy song song với task khác
- 🟥 = Task phải chờ task trước hoàn thành
- 📋 = Prompt copy-paste cho agent
- ✅ = Tiêu chí nghiệm thu (Definition of Done)

---

## TỔNG QUAN TASK MAP

```
GIAI ĐOẠN 1: NỀN TẢNG (6 ngày)
├── 🟦 Agent 1A: Database Schema Design
├── 🟦 Agent 1B: Excel I/O Module 
├── 🟥 Agent 1C: Logging System (sau khi 1A xong)
└── 🟥 Agent 1D: Integration Test GĐ1 (sau khi 1A + 1B + 1C xong)

GIAI ĐOẠN 2: THỬ NGHIỆM TÌM KIẾM & THU THẬP (8 ngày)
├── 🟥 Agent 2A: Search Module + Bilingual Strategy (sau khi 1D xong)
├── 🟥 Agent 2B: Link Filter Module (sau khi 2A xong)
├── 🟥 Agent 2C: Scrape Module (sau khi 2B xong)
└── 🟥 Agent 2D: Pipeline Test 10 cty (sau khi 2A + 2B + 2C xong)
```

---
---

# GIAI ĐOẠN 1: NỀN TẢNG

---

## AGENT 1A — Database Schema Design 🟦
**Độ ưu tiên:** Cao — Là nền tảng cho mọi module khác  
**Thời gian ước tính:** 1 ngày  
**Phụ thuộc:** Không (chạy đầu tiên hoặc song song với 1B)

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi đang xây dựng hệ thống tự động thu thập thông tin liên hệ doanh nghiệp. 
Hệ thống có 4 bước xử lý tuần tự cho mỗi công ty:
1. SEARCH: Tìm kiếm Google → lấy 10 link kết quả
2. FILTER: Lọc link → giữ lại link thuộc 9 trang web mục tiêu hoặc website chính chủ
3. SCRAPE: Vào từng link đã lọc → lấy nội dung text (Markdown)
4. AI_EXTRACT: Gửi text cho AI → trích xuất thông tin liên hệ có cấu trúc

NHIỆM VỤ:
Tạo database SQLite tại đường dẫn: data/company_data.db
Yêu cầu:
- Tạo file Python: src/database.py
- Thiết kế các bảng sau:

1. Bảng "companies" (danh sách công ty đầu vào):
   - id: INTEGER PRIMARY KEY AUTOINCREMENT
   - original_name: TEXT NOT NULL (tên tiếng Anh từ Excel)
   - vietnamese_name: TEXT (tên tiếng Việt do AI dịch, có thể NULL)
   - tax_code: TEXT (mã số thuế, có thể NULL)
   - status: TEXT DEFAULT 'pending' (pending/searching/scraping/extracting/done/failed)
   - created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   - updated_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

2. Bảng "search_results" (kết quả tìm kiếm Google):
   - id: INTEGER PRIMARY KEY AUTOINCREMENT
   - company_id: INTEGER REFERENCES companies(id)
   - search_query: TEXT NOT NULL (câu search thực tế đã dùng)
   - search_type: TEXT (english/vietnamese/tax_code) — loại tìm kiếm
   - result_rank: INTEGER (thứ tự 1-10)
   - url: TEXT NOT NULL
   - title: TEXT
   - snippet: TEXT (đoạn mô tả ngắn)
   - credits_used: REAL DEFAULT 0
   - created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

3. Bảng "filtered_links" (link đã phân loại):
   - id: INTEGER PRIMARY KEY AUTOINCREMENT
   - search_result_id: INTEGER REFERENCES search_results(id)
   - company_id: INTEGER REFERENCES companies(id)
   - url: TEXT NOT NULL
   - source_type: TEXT NOT NULL (masothue/yellowpages/thuvienphapluat/hosocongty/vietnamworks/topcv/vietcareer/facebook/linkedin/official_website/other)
   - should_scrape: BOOLEAN DEFAULT TRUE
   - reason: TEXT (lý do lọc vào hoặc bỏ qua)

4. Bảng "scraped_pages" (nội dung đã thu thập):
   - id: INTEGER PRIMARY KEY AUTOINCREMENT
   - filtered_link_id: INTEGER REFERENCES filtered_links(id)
   - company_id: INTEGER REFERENCES companies(id)
   - url: TEXT NOT NULL
   - source_type: TEXT NOT NULL
   - markdown_content: TEXT (nội dung Markdown đầy đủ — ĐÂY LÀ TÀI SẢN QUAN TRỌNG NHẤT)
   - content_length: INTEGER
   - scrape_status: TEXT (success/failed/timeout/blocked)
   - credits_used: REAL DEFAULT 0
   - error_message: TEXT
   - created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

5. Bảng "extracted_contacts" (kết quả AI trích xuất):
   - id: INTEGER PRIMARY KEY AUTOINCREMENT
   - company_id: INTEGER REFERENCES companies(id)
   - scraped_page_id: INTEGER REFERENCES scraped_pages(id)
   - source_type: TEXT NOT NULL (nguồn dữ liệu)
   - source_url: TEXT
   - address: TEXT
   - phone: TEXT
   - email: TEXT
   - website: TEXT
   - fax: TEXT
   - representative: TEXT (người đại diện)
   - raw_ai_response: TEXT (lưu response gốc của AI — để debug)
   - confidence_score: REAL (0-1, độ tin cậy AI tự đánh giá)
   - created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

6. Bảng "pipeline_logs" (nhật ký xử lý):
   - id: INTEGER PRIMARY KEY AUTOINCREMENT
   - company_id: INTEGER REFERENCES companies(id)
   - step: TEXT NOT NULL (search/filter/scrape/ai_extract)
   - status: TEXT NOT NULL (started/success/partial/failed/skipped)
   - started_at: TIMESTAMP
   - finished_at: TIMESTAMP
   - duration_seconds: REAL
   - source_url: TEXT
   - source_name: TEXT
   - credits_used: REAL DEFAULT 0
   - error_message: TEXT
   - data_saved: BOOLEAN DEFAULT FALSE
   - metadata_json: TEXT (thông tin bổ sung dạng JSON)

YÊU CẦU BẮT BUỘC:
- Tạo class DatabaseManager trong src/database.py
- Có method init_db() để tạo tất cả bảng (dùng IF NOT EXISTS)
- Có method riêng cho từng thao tác CRUD cơ bản cho mỗi bảng
- Bảng pipeline_logs PHẢI có index trên (company_id, step) để query nhanh
- Tạo thư mục data/ nếu chưa tồn tại
- Có docstring tiếng Anh đầy đủ cho mỗi method
- Viết test cơ bản trong tests/test_database.py: tạo DB, insert, query

CẤU TRÚC THƯ MỤC (chỉ tạo file liên quan):
project_root/
├── src/
│   └── database.py
├── data/           (thư mục chứa DB file)
├── tests/
│   └── test_database.py
└── requirements.txt  (thêm: sqlite3 có sẵn, không cần gì thêm)
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/database.py` tồn tại và có class `DatabaseManager`
- [ ] Chạy `python -c "from src.database import DatabaseManager; db = DatabaseManager(); db.init_db(); print('OK')"` thành công
- [ ] File `data/company_data.db` được tạo ra với đầy đủ 6 bảng
- [ ] Test file `tests/test_database.py` chạy all pass
- [ ] Có index trên bảng `pipeline_logs`

---

## AGENT 1B — Excel I/O Module 🟦
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 1 ngày  
**Phụ thuộc:** Không (chạy song song với 1A)

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi có 1 file Excel đầu vào chứa danh sách hơn 6.000 công ty.
File mẫu hiện tại: "PIC 수집 시도_글투실_20260409.xlsx" (tiếng Hàn)
Cấu trúc file có thể thay đổi, nhưng luôn có ít nhất:
  - Cột tên công ty (tiếng Anh)
  - Một số dòng có thêm cột mã số thuế

Tôi cần 2 module:
A) Module ĐỌC Excel đầu vào → trả về danh sách [{name, tax_code}]
B) Module GHI Excel đầu ra → xuất kết quả thu thập thành file Excel chuẩn

NHIỆM VỤ:
Tạo file: src/excel_handler.py

A) CLASS ExcelReader:
   - Method: read_company_list(file_path) -> list[dict]
   - Tự động phát hiện cột tên công ty (tên tiếng Anh) và cột mã số thuế
   - Xử lý edge cases: dòng trống, dòng header, dòng merged cells
   - Trả về list of dict: [{"name": "ABC Corp", "tax_code": "0123456789"}, ...]
   - tax_code = None nếu không có
   - Ghi log tổng số dòng đọc được, số dòng bỏ qua (empty), số dòng có MST

B) CLASS ExcelWriter:
   - Method: write_results(output_path, results: list[dict])
   - Cột output: STT | Tên công ty | Mã số thuế | Nguồn | Địa chỉ | SĐT | Email | Website | Fax | Người đại diện | Ngày thu thập
   - 1 công ty có thể chiếm NHIỀU DÒNG (mỗi nguồn 1 dòng) — xem ví dụ:
     Dòng 1: Công ty A | 0123456789 | masothue  | 123 Nguyễn Huệ | — | — | — | — | Nguyễn Văn A
     Dòng 2: Công ty A | —          | website   | 123 Nguyễn Huệ  | 028-1234 | info@a.com | ...
     Dòng 3: Công ty A | —          | topcv     | Q1, HCM        | 0901-234 | hr@a.com   | ...
   - Format đẹp: header bold, border, auto-width, freeze pane ở hàng đầu
   - Sheet name: "Kết quả thu thập"

THƯ VIỆN SỬ DỤNG: openpyxl (thêm vào requirements.txt)

CẤU TRÚC THƯ MỤC:
project_root/
├── src/
│   └── excel_handler.py
├── tests/
│   └── test_excel_handler.py  (tạo file Excel giả để test đọc/ghi)
└── requirements.txt  (thêm: openpyxl)

LƯU Ý:
- KHÔNG CẦN biết về database hay pipeline — chỉ làm đúng phần Excel.
- Tập trung vào xử lý unicode (tiếng Việt, tiếng Hàn) đúng cách.
- File test phải tự tạo Excel giả rồi đọc lại để verify.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/excel_handler.py` tồn tại, có class `ExcelReader` và `ExcelWriter`
- [ ] Đọc được file Excel mẫu thực tế (PIC 수집 시도_글투실_20260409.xlsx) không lỗi
- [ ] Ghi được file Excel output đẹp, đúng format, hỗ trợ unicode VN/KR
- [ ] Test `tests/test_excel_handler.py` all pass
- [ ] `requirements.txt` có `openpyxl`

---

## AGENT 1C — Logging System 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 1 ngày  
**Phụ thuộc:** Agent 1A phải hoàn thành trước (cần dùng bảng `pipeline_logs`)

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi có hệ thống xử lý dữ liệu công ty theo pipeline gồm 4 bước:
search → filter → scrape → ai_extract

Tôi cần hệ thống ghi nhật ký (logging) cho pipeline này với 2 yêu cầu đặc biệt:
1. LOG PHẢI ĐỌC ĐƯỢC BỞI AI: format chuẩn hóa, cấu trúc nhất quán, 
   để sau này tôi có thể cho AI agent đọc log và phân tích lỗi tự động.
2. LOG LƯU VÀO CẢ DATABASE VÀ FILE: DB cho query nhanh, file cho đọc trực tiếp.

NHIỆM VỤ:
Tạo file: src/logger.py

CLASS PipelineLogger:

Đã có sẵn (KHÔNG CẦN TẠO):
- src/database.py với class DatabaseManager
- Bảng "pipeline_logs" trong SQLite DB có các cột:
  id, company_id, step, status, started_at, finished_at, duration_seconds,
  source_url, source_name, credits_used, error_message, data_saved, metadata_json

CẦN TẠO:
1. Method: log_step_start(company_id, step, source_url=None, source_name=None)
   → Ghi record mới với status='started', started_at=now()
   → Trả về log_id (để dùng khi log_step_end)

2. Method: log_step_end(log_id, status, credits_used=0, error_message=None, 
                         data_saved=False, metadata=None)
   → Update record: finished_at=now(), tính duration_seconds, cập nhật status

3. Method: get_daily_summary() -> dict
   → Trả về dict chứa:
     - total_processed_today: int
     - total_processed_all: int  
     - total_companies: int (từ bảng companies)
     - progress_percent: float (total_processed_all / total_companies * 100)
     - success_rate: float (% công ty có ít nhất 1 thông tin)
     - total_credits_used: float
     - avg_time_per_company: float (giây)
     - top_5_errors: list[dict] (error_message + count)
     - source_distribution: dict (masothue: 35%, topcv: 20%, ...)

4. Method: export_log_to_csv(output_path)
   → Xuất toàn bộ pipeline_logs ra file CSV

5. Method: export_summary_to_excel(output_path)
   → Xuất daily_summary ra file Excel đẹp (dùng openpyxl)

6. Method: get_last_processed_company_id() -> int
   → Trả về company_id cuối cùng đã xử lý xong (dùng cho resume)

CONSOLE LOG FORMAT (in ra terminal khi chạy):
Dùng Python logging module, format sau:
[2026-04-20 09:15:23] [CMP-0001] [SEARCH] [SUCCESS] 2 credits | 3.2s | "ABC Corp" → 10 links found
[2026-04-20 09:15:45] [CMP-0001] [SCRAPE] [SUCCESS] 1 credit  | 2.1s | masothue.com → 4532 chars saved
[2026-04-20 09:15:48] [CMP-0001] [SCRAPE] [FAILED]  0 credits | 5.0s | facebook.com → Timeout
[2026-04-20 09:16:10] [CMP-0001] [AI_EXT] [SUCCESS] 0 credits | 1.8s | Extracted: phone, email, address

THƯ MỤC:
project_root/
├── src/
│   ├── database.py  (đã có — không sửa)
│   └── logger.py    (TẠO MỚI)
├── logs/            (thư mục chứa log files)
├── tests/
│   └── test_logger.py
└── requirements.txt

LƯU Ý:
- Import DatabaseManager từ src.database
- KHÔNG sửa database.py, chỉ sử dụng nó
- Console log phải có màu (dùng colorama hoặc ANSI codes): 
  xanh=SUCCESS, đỏ=FAILED, vàng=SKIPPED
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/logger.py` tồn tại, có class `PipelineLogger`
- [ ] Console output format đúng và có màu sắc
- [ ] `get_daily_summary()` trả về dict với đầy đủ key
- [ ] `export_log_to_csv()` tạo được file CSV hợp lệ
- [ ] `get_last_processed_company_id()` hoạt động cho resume
- [ ] Test `tests/test_logger.py` all pass

---

## AGENT 1D — Integration Test GĐ1 🟥
**Độ ưu tiên:** Trung bình  
**Thời gian ước tính:** 0.5 ngày  
**Phụ thuộc:** Agent 1A, 1B, 1C tất cả phải hoàn thành

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi đã có 3 module đã hoàn thành:
1. src/database.py — DatabaseManager (quản lý SQLite)
2. src/excel_handler.py — ExcelReader + ExcelWriter (đọc/ghi Excel)
3. src/logger.py — PipelineLogger (ghi nhật ký)

NHIỆM VỤ:
Viết 1 script integration test: tests/test_integration_phase1.py

Script này kiểm tra 3 module làm việc cùng nhau:
1. Tạo DB mới (DatabaseManager.init_db)
2. Đọc file Excel thật: "PIC 수집 시도_글투실_20260409.xlsx"
   → In ra: "Đọc được X công ty, Y công ty có MST"
3. Insert tất cả công ty đọc được vào bảng companies
4. Simulate pipeline log cho 3 công ty đầu tiên:
   - Log search started → search success
   - Log scrape started → scrape success  
   - Log AI extract started → extract success with fake data
5. Gọi get_daily_summary() → in ra kết quả
6. Gọi ExcelWriter.write_results() với dữ liệu giả → tạo file output test
7. Gọi export_log_to_csv() → tạo file CSV test

KIỂM TRA:
- Không có exception nào
- File DB, Excel output, CSV log đều được tạo
- In summary: "GĐ1 INTEGRATION TEST: ALL PASSED ✅"

CẤU TRÚC:
project_root/
├── tests/
│   └── test_integration_phase1.py
└── output/   (thư mục chứa file Excel và CSV output test)
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] Chạy `python tests/test_integration_phase1.py` không lỗi
- [ ] In ra "GĐ1 INTEGRATION TEST: ALL PASSED ✅"
- [ ] File `output/` chứa file Excel test và CSV log

---
---

# GIAI ĐOẠN 2: THỬ NGHIỆM TÌM KIẾM & THU THẬP

---

## AGENT 2A — Search Module + Bilingual Strategy 🟥
**Độ ưu tiên:** Rất Cao — Module cốt lõi  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** Agent 1D hoàn thành (cần DB + Logger sẵn sàng)  
**⚠️ Cần Firecrawl API key**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi đang xây module TÌM KIẾM (Search) cho hệ thống thu thập thông tin doanh nghiệp.
Input: Tên công ty tiếng Anh (VD: "ABC Software Solutions Co., Ltd")
Output: 10 link kết quả Google cho mỗi công ty, lưu vào DB

⚠️ VẤN ĐỀ QUAN TRỌNG - RÀO CẢN NGÔN NGỮ:
Danh sách đầu vào chỉ có tên tiếng Anh, nhưng nhiều trang web mục tiêu (masothue.com, 
thuvienphapluat.vn...) chỉ index tên pháp lý TIẾNG VIỆT.
→ Nếu chỉ search tiếng Anh sẽ bỏ sót rất nhiều kết quả quan trọng!

CHIẾN LƯỢC TÌM KIẾM SONG NGỮ (Bilingual Search Strategy):
Mỗi công ty sẽ được tìm kiếm theo 3 chiến lược, ưu tiên từ trên xuống:

① NẾU CÓ MÃ SỐ THUẾ (tax_code không NULL):
   → Search query: "{mã_số_thuế}"
   → search_type = "tax_code"
   → Đây là cách chính xác nhất, ưu tiên tuyệt đối

② SEARCH VỚI TỪ KHÓA MỎ NEO (luôn thực hiện):
   → Search query: "{tên tiếng Anh}" AND ("mã số thuế" OR "công ty TNHH" OR "công ty cổ phần" OR "giấy phép kinh doanh")
   → search_type = "english"
   → Ép Google trả về kết quả từ các trang danh bạ nội địa Việt Nam

③ SEARCH BẰNG TÊN TIẾNG VIỆT (option, dùng Gemini AI dịch):
   → Gọi Gemini AI: "Dịch tên công ty sau sang tên pháp lý tiếng Việt: {tên EN}"
   → VD: "Joint Stock Company" → "Công ty Cổ phần"
   → Search query: "{tên tiếng Việt đã dịch}"
   → search_type = "vietnamese"
   → Lưu tên VN vào bảng companies.vietnamese_name

   LƯU Ý: Bước ③ chỉ thực hiện nếu bước ② không trả về kết quả từ masothue hoặc 
   thuvienphapluat. Nếu ② đã đủ kết quả tốt thì bỏ qua ③ để tiết kiệm thời gian.

ĐÃ CÓ SẴN (KHÔNG CẦN TẠO):
- src/database.py: DatabaseManager — lưu/đọc DB
- src/logger.py: PipelineLogger — ghi log mỗi bước
- Bảng search_results trong DB (xem schema bên dưới)

BẢNG search_results:
  id, company_id, search_query, search_type, result_rank, 
  url, title, snippet, credits_used, created_at

BẢNG companies:
  id, original_name, vietnamese_name, tax_code, status, created_at, updated_at

NHIỆM VỤ:
Tạo file: src/search_module.py

CLASS SearchModule:
  __init__(self, db: DatabaseManager, logger: PipelineLogger, firecrawl_api_key: str)

  Method: search_company(company_id: int) -> list[dict]
    1. Đọc thông tin company từ DB (tên, MST)
    2. Thực hiện chiến lược search theo thứ tự ①→②→③ như trên
    3. Dùng Firecrawl Search API:
       POST https://api.firecrawl.dev/v1/search
       Headers: {"Authorization": "Bearer {api_key}"}
       Body: {"query": "...", "limit": 10}
    4. Lưu TẤT CẢ kết quả vào bảng search_results (kể cả kết quả trùng)
    5. Ghi log qua PipelineLogger: log_step_start → ... → log_step_end
    6. Update companies.status = 'searching' → 'searched'
    7. Trả về list kết quả đã lưu

  Method: search_batch(company_ids: list[int], delay_seconds: float = 2.0)
    - Chạy search_company cho từng company, cách nhau delay_seconds
    - Có try-except: nếu 1 company lỗi → log lỗi, tiếp tục company sau
    - In progress: "Đang xử lý: 5/10 công ty..."

  Method: get_search_stats() -> dict
    - Trả về: total_searched, total_results, avg_results_per_company,
              search_type_distribution, credits_used_total

THƯ VIỆN: requests (thêm vào requirements.txt)
API KEY: Đọc từ biến môi trường FIRECRAWL_API_KEY hoặc file .env

CẤU TRÚC:
project_root/
├── src/
│   ├── database.py       (đã có — không sửa)
│   ├── logger.py         (đã có — không sửa)
│   └── search_module.py  (TẠO MỚI)
├── tests/
│   └── test_search_module.py (mock API, test logic)
├── .env.example          (FIRECRAWL_API_KEY=fc-xxx)
└── requirements.txt      (thêm: requests, python-dotenv)

LƯU Ý QUAN TRỌNG:
- KHÔNG sửa database.py và logger.py, chỉ import và sử dụng.
- Mỗi lần gọi Firecrawl Search = 2 credits. Tracking credits cẩn thận.
- Rate limit: chờ ít nhất 2 giây giữa các request.
- Khi test, dùng mock/fixture để không tốn credit thật.
- Xử lý HTTP errors: 429 (rate limit), 402 (hết credit), 500 (server error)
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/search_module.py` tồn tại, có class `SearchModule`
- [ ] Chiến lược Bilingual Search đầy đủ 3 nhánh (MST → Anchor → VN name)
- [ ] Kết quả lưu đúng vào bảng `search_results` với `search_type` chính xác
- [ ] `search_batch()` có delay, error handling, progress tracking
- [ ] Mock test trong `tests/test_search_module.py` all pass
- [ ] Test thật với 1-2 công ty (consume ~4 credits) → verify kết quả hợp lý

---

## AGENT 2B — Link Filter Module 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 1 ngày  
**Phụ thuộc:** Agent 2A hoàn thành (cần có data trong search_results)

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi có bảng "search_results" trong SQLite chứa 10 link Google cho mỗi công ty.
Giờ tôi cần LỌC link: chỉ giữ lại link dẫn đến 9 trang web mục tiêu hoặc 
website chính chủ của công ty. Bỏ qua link rác (quảng cáo, wiki, báo chí...).

9 TRANG WEB MỤC TIÊU:
  masothue.com, yellowpages.vn, thuvienphapluat.vn, hosocongty.vn,
  vietnamworks.com, topcv.vn, vietcareer.vn, facebook.com, linkedin.com

+ Website chính chủ (official_website): là domain KHÔNG thuộc 9 trang trên, 
  KHÔNG phải trang phổ biến (google, wikipedia, youtube, baomoi...), 
  và CÓ THỂ là website riêng của công ty.

ĐÃ CÓ SẴN (KHÔNG CẦN TẠO):
- src/database.py: DatabaseManager
- src/logger.py: PipelineLogger
- Bảng filtered_links:
  id, search_result_id, company_id, url, source_type, should_scrape, reason

NHIỆM VỤ:
Tạo file: src/filter_module.py

CLASS LinkFilter:
  __init__(self, db: DatabaseManager, logger: PipelineLogger)

  DANH SÁCH DOMAIN MỤC TIÊU (hardcode):
  TARGET_DOMAINS = {
      "masothue.com": "masothue",
      "yellowpages.vn": "yellowpages", 
      "thuvienphapluat.vn": "thuvienphapluat",
      "hosocongty.vn": "hosocongty",
      "vietnamworks.com": "vietnamworks",
      "topcv.vn": "topcv",
      "vietcareer.vn": "vietcareer",
      "facebook.com": "facebook",
      "linkedin.com": "linkedin"
  }

  DANH SÁCH DOMAIN BỎ QUA (blacklist):
  SKIP_DOMAINS = [
      "google.com", "youtube.com", "wikipedia.org", "baomoi.com",
      "vnexpress.net", "bing.com", "twitter.com", "tiktok.com",
      "pinterest.com", "amazon.com", "shopee.vn", "lazada.vn"
  ]

  Method: classify_url(url: str, company_name: str) -> dict
    Trả về: {"source_type": "masothue"|...|"official_website"|"other",
             "should_scrape": True/False,
             "reason": "Matched target domain: masothue.com"}
    
    Logic:
    1. Trích domain từ URL
    2. Nếu domain thuộc TARGET_DOMAINS → source_type = tương ứng, should_scrape = True
    3. Nếu domain thuộc SKIP_DOMAINS → source_type = "other", should_scrape = False
    4. Nếu domain KHÔNG thuộc cả 2 danh sách → CÓ THỂ là website chính chủ
       → source_type = "official_website", should_scrape = True
       → reason ghi: "Possible official website: {domain}"

  Method: filter_company_links(company_id: int) -> list[dict]
    1. Đọc tất cả search_results của company_id từ DB
    2. classify_url cho từng link
    3. Loại bỏ link trùng lặp (cùng domain chỉ giữ 1)
    4. Lưu kết quả vào bảng filtered_links
    5. Ghi log

  Method: filter_batch(company_ids: list[int])
    - Xử lý tuần tự, có summary cuối cùng

CẤU TRÚC:
project_root/
├── src/
│   ├── filter_module.py  (TẠO MỚI)
├── tests/
│   └── test_filter_module.py (test phân loại URL)

LƯU Ý:
- Import từ urllib.parse để xử lý URL đúng cách
- Xử lý edge case: URL bị redirect, URL có subdomain (m.facebook.com)
- facebook.com và linkedin.com: should_scrape = True nhưng ghi note "secondary source"
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/filter_module.py` tồn tại
- [ ] Phân loại đúng URL thuộc 9 trang mục tiêu
- [ ] Nhận diện được website chính chủ (không reject nhầm)
- [ ] Loại bỏ trùng lặp domain
- [ ] Test all pass

---

## AGENT 2C — Scrape Module 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** Agent 2B hoàn thành (cần có data trong filtered_links)  
**⚠️ Cần Firecrawl API key**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi có bảng "filtered_links" trong SQLite chứa danh sách URL đã lọc — chỉ
những trang web đáng thu thập nội dung. Giờ tôi cần vào từng URL đó, lấy 
nội dung chữ (Markdown), lưu vào DB.

ĐÂY LÀ BƯỚC TỐN NHIỀU FIRECRAWL CREDITS NHẤT: mỗi trang = 1 credit.
Dữ liệu thu thập ở bước này là TÀI SẢN QUAN TRỌNG NHẤT của dự án.

ĐÃ CÓ SẴN (KHÔNG CẦN TẠO):
- src/database.py: DatabaseManager
- src/logger.py: PipelineLogger
- Bảng scraped_pages:
  id, filtered_link_id, company_id, url, source_type, markdown_content,
  content_length, scrape_status, credits_used, error_message, created_at

NHIỆM VỤ:
Tạo file: src/scrape_module.py

CLASS ScrapeModule:
  __init__(self, db: DatabaseManager, logger: PipelineLogger, firecrawl_api_key: str)

  Method: scrape_url(filtered_link_id: int) -> dict
    1. Đọc URL và source_type từ filtered_links
    2. KIỂM TRA TRƯỚC: URL này đã scrape rồi chưa? (check scraped_pages)
       → Nếu rồi & status=success → skip, trả về data cũ (KHÔNG TỐN CREDIT)
    3. Gọi Firecrawl Scrape API:
       POST https://api.firecrawl.dev/v1/scrape
       Headers: {"Authorization": "Bearer {api_key}"}
       Body: {
         "url": "...",
         "formats": ["markdown"],
         "timeout": 30000,
         "waitFor": 3000
       }
    4. Lưu markdown_content vào bảng scraped_pages
    5. Ghi log (bao gồm content_length)
    6. Trả về dict {status, content_length, source_type}

  Method: scrape_company(company_id: int, delay_seconds: float = 2.0) -> list[dict]
    1. Đọc tất cả filtered_links với should_scrape=True cho company_id
    2. Sắp xếp ưu tiên: masothue > yellowpages > thuvienphapluat > ... > facebook > linkedin
       (Scrape nguồn chính trước, nguồn bổ sung sau)
    3. Scrape tuần tự, có delay giữa các request
    4. Nếu 1 URL lỗi → log, tiếp tục URL tiếp theo (KHÔNG dừng cả pipeline)
    5. Update companies.status = 'scraping' → 'scraped'

  Method: scrape_batch(company_ids: list[int], delay_seconds: float = 2.0)
    - Xử lý tuần tự từng company
    - In progress, tổng credits đã dùng

  Method: get_scrape_stats() -> dict
    - total_pages_scraped, total_chars_collected, 
      avg_content_length, success_rate, credits_used_total,
      source_breakdown (bao nhiêu trang từ mỗi nguồn)

TIMEOUT & ERROR HANDLING:
- Mỗi request timeout sau 30 giây
- HTTP 429 (rate limit): chờ 60 giây rồi thử lại (tối đa 3 lần)
- HTTP 402 (hết credit): DỪNG ngay, in cảnh báo, ghi log
- Facebook/LinkedIn timeout: ghi "skipped - secondary source", tiếp tục

CẤU TRÚC:
project_root/
├── src/
│   ├── scrape_module.py  (TẠO MỚI)
├── tests/
│   └── test_scrape_module.py (mock API)
└── requirements.txt

LƯU Ý:
- KHÔNG sửa file nào đã có.
- Ưu tiên tuyệt đối việc KHÔNG SCRAPE TRÙNG (idempotent) → tiết kiệm credit.
- Mỗi scraped page cần lưu TOÀN BỘ Markdown, không cắt xén.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/scrape_module.py` tồn tại
- [ ] Có cơ chế skip URL đã scrape (idempotent)
- [ ] Xử lý lỗi HTTP 429, 402 đúng cách
- [ ] Ưu tiên nguồn chính trước nguồn bổ sung
- [ ] Lưu đầy đủ Markdown content vào DB
- [ ] Mock test all pass

---

## AGENT 2D — Pipeline Integration Test (10 công ty) 🟥
**Độ ưu tiên:** Rất cao — Đây là bài kiểm tra thực tế đầu tiên  
**Thời gian ước tính:** 1 ngày  
**Phụ thuộc:** Agent 2A, 2B, 2C tất cả phải hoàn thành  
**⚠️ Tiêu tốn ~50 Firecrawl credits thật**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi đã có hệ thống hoàn chỉnh với các module:
- src/database.py: DatabaseManager (quản lý SQLite)
- src/excel_handler.py: ExcelReader + ExcelWriter (đọc/ghi Excel)
- src/logger.py: PipelineLogger (ghi nhật ký)
- src/search_module.py: SearchModule (tìm kiếm Google qua Firecrawl)
- src/filter_module.py: LinkFilter (lọc link mục tiêu)
- src/scrape_module.py: ScrapeModule (thu thập nội dung trang web)

Giờ tôi cần chạy thử TOÀN BỘ pipeline cho 10 công ty đầu tiên từ file Excel thật.

NHIỆM VỤ:
Tạo 2 file:
1. src/pipeline.py  — Orchestrator điều phối toàn bộ pipeline
2. scripts/run_pilot_10.py — Script chạy thử 10 công ty

FILE 1: src/pipeline.py

CLASS Pipeline:
  __init__(self, config: dict)
    - config chứa: firecrawl_api_key, input_excel_path, output_dir, 
                    delay_seconds, batch_size
    - Khởi tạo tất cả module: DB, Logger, Search, Filter, Scrape

  Method: run(company_ids: list[int] = None, limit: int = None)
    Pipeline cho MỖI công ty theo thứ tự:
    1. SEARCH → lưu 10 link vào DB
    2. FILTER → lọc link, lưu vào DB
    3. SCRAPE → thu thập nội dung, lưu vào DB
    (Bước 4 AI Extract sẽ làm ở Giai đoạn 3)
    
    Xử lý đặc biệt:
    - Nếu company đã có status='scraped' hoặc 'done' → SKIP (resume capability)
    - Có try-except bao quanh mỗi company: 1 cty lỗi không ảnh hưởng cty khác
    - Sau mỗi company xong → print summary ngắn
    - Sau tất cả xong → print summary tổng

  Method: resume()
    - Tìm last_processed_company_id từ logger
    - Tiếp tục chạy từ company tiếp theo

  Method: generate_report(output_path: str)
    - Xuất báo cáo: tổng hợp kết quả (chưa có AI Extract)
    - Bao gồm: danh sách link đã thu thập cho mỗi cty,
      content_length mỗi trang, stats tổng thể

FILE 2: scripts/run_pilot_10.py

Script main:
  1. Đọc .env lấy API key
  2. Đọc Excel file → lấy 10 công ty đầu tiên
  3. Insert vào DB
  4. Chạy Pipeline.run(limit=10)
  5. In summary: bao nhiêu cty OK, bao nhiêu fail, tổng credits
  6. Xuất báo cáo ra output/pilot_10_report.xlsx
  7. Xuất log ra output/pilot_10_log.csv

CẤU TRÚC:
project_root/
├── src/
│   └── pipeline.py       (TẠO MỚI)
├── scripts/
│   └── run_pilot_10.py   (TẠO MỚI)
├── output/               (thư mục chứa kết quả)
├── .env                  (FIRECRAWL_API_KEY=fc-xxx)
└── requirements.txt

LƯU Ý QUAN TRỌNG:
- KHÔNG sửa bất kỳ file nào đã có trong src/
- Chỉ import và sử dụng các module đã có
- delay_seconds mặc định = 3.0 (an toàn hơn để không bị ban)
- ĐÂY LÀ PIPELINE THẬT → SẼ TỐN KHOẢNG 50 CREDITS
- Trước khi chạy thật, hỏi người dùng xác nhận: "Sẽ sử dụng ~50 credits. Tiếp tục? (y/n)"
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/pipeline.py` và `scripts/run_pilot_10.py` tồn tại
- [ ] Chạy `python scripts/run_pilot_10.py` hoàn thành 10 công ty
- [ ] DB chứa search_results, filtered_links, scraped_pages cho 10 cty
- [ ] File `output/pilot_10_report.xlsx` được tạo
- [ ] File `output/pilot_10_log.csv` được tạo
- [ ] Có cơ chế resume (chạy lại script không bị đè data cũ)
- [ ] Credits tiêu tốn ≤ 60 (dự phòng 20%)

---
---

# PHỤ LỤC: CẤU TRÚC THƯ MỤC CUỐI CÙNG SAU GĐ1 & GĐ2

```
auto_search_company/
├── .env                              # API keys (KHÔNG push lên git)
├── .env.example                      # Template API keys
├── .gitignore                        # Ignore .env, data/, output/, venv/
├── requirements.txt                  # openpyxl, requests, python-dotenv, colorama
│
├── AUTO_COMPANY_SEARCH_PROJECT_PLAN.md        # Kế hoạch tổng thể
├── AUTO_COMPANY_SEARCH_PROJECT_PLAN_KO.md     # Bản tiếng Hàn
├── PHASE_1_2_DETAILED_PLAN.md                 # File này
│
├── src/
│   ├── __init__.py
│   ├── database.py               # [Agent 1A] DatabaseManager
│   ├── excel_handler.py          # [Agent 1B] ExcelReader + ExcelWriter
│   ├── logger.py                 # [Agent 1C] PipelineLogger
│   ├── search_module.py          # [Agent 2A] SearchModule + Bilingual
│   ├── filter_module.py          # [Agent 2B] LinkFilter
│   ├── scrape_module.py          # [Agent 2C] ScrapeModule
│   └── pipeline.py              # [Agent 2D] Pipeline Orchestrator
│
├── scripts/
│   └── run_pilot_10.py           # [Agent 2D] Script chạy thử 10 cty
│
├── tests/
│   ├── test_database.py          # [Agent 1A]
│   ├── test_excel_handler.py     # [Agent 1B]
│   ├── test_logger.py            # [Agent 1C]
│   ├── test_integration_phase1.py # [Agent 1D]
│   ├── test_search_module.py     # [Agent 2A]
│   ├── test_filter_module.py     # [Agent 2B]
│   └── test_scrape_module.py     # [Agent 2C]
│
├── data/
│   └── company_data.db           # SQLite database
│
├── logs/
│   └── pipeline_YYYYMMDD.log     # Daily log files
│
└── output/
    ├── pilot_10_report.xlsx      # Báo cáo test 10 cty
    └── pilot_10_log.csv          # Log test 10 cty
```

---

# TÓM TẮT THỨ TỰ THỰC HIỆN

| Thứ tự | Agent | Task | Phụ thuộc | Song song? | Ước tính |
|--------|-------|------|-----------|------------|----------|
| 1 | **1A** | Database Schema | Không | 🟦 Có thể chạy song song với 1B | 1 ngày |
| 1 | **1B** | Excel I/O | Không | 🟦 Có thể chạy song song với 1A | 1 ngày |
| 2 | **1C** | Logging System | 1A xong | 🟥 Chờ 1A | 1 ngày |
| 3 | **1D** | Integration Test GĐ1 | 1A+1B+1C xong | 🟥 Chờ tất cả | 0.5 ngày |
| 4 | **2A** | Search + Bilingual | 1D xong | 🟥 Chờ GĐ1 | 2 ngày |
| 5 | **2B** | Link Filter | 2A xong | 🟥 Chờ 2A | 1 ngày |
| 6 | **2C** | Scrape Module | 2B xong | 🟥 Chờ 2B | 2 ngày |
| 7 | **2D** | Pipeline Test 10 cty | 2A+2B+2C xong | 🟥 Chờ tất cả | 1 ngày |

**Tổng thời gian tối thiểu (critical path):** ~8.5 ngày  
**Tổng thời gian dự phòng (theo Plan):** 14 ngày (GĐ1: 6d + GĐ2: 8d)
