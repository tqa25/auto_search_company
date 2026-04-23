# KẾ HOẠCH CHI TIẾT — GIAI ĐOẠN 3 & 4
## Phân chia nhiệm vụ theo từng Agent

**Tài liệu tham chiếu:** [AUTO_COMPANY_SEARCH_PROJECT_PLAN.md](./AUTO_COMPANY_SEARCH_PROJECT_PLAN.md)  
**Tài liệu tiền nhiệm:** [PHASE_1_2_DETAILED_PLAN.md](./PHASE_1_2_DETAILED_PLAN.md)  
**Ngày lập:** 15/04/2026  

---

## HƯỚNG DẪN SỬ DỤNG TÀI LIỆU NÀY

Tài liệu này tiếp nối [PHASE_1_2_DETAILED_PLAN.md](./PHASE_1_2_DETAILED_PLAN.md), chia nhỏ Giai đoạn 3 & 4 thành **các nhiệm vụ độc lập**, mỗi nhiệm vụ được giao cho **1 agent (phiên AI riêng biệt)**.

### Điều kiện tiên quyết
Trước khi bắt đầu GĐ3, toàn bộ GĐ1 & GĐ2 phải hoàn thành:
- ✅ Database SQLite hoạt động (`data/company_data.db`) — 6 bảng
- ✅ Excel I/O hoạt động (`ExcelReader`, `ExcelWriter`)
- ✅ Logging system hoạt động (`PipelineLogger`)
- ✅ Search + Filter + Scrape modules hoạt động
- ✅ Pipeline orchestrator (`pipeline.py`) đã test 10 công ty thành công
- ✅ Dữ liệu `scraped_pages` cho 10 công ty pilot đã có trong DB

### Quy ước (giữ nguyên từ GĐ1&2)
- 🟦 = Task có thể chạy song song với task khác
- 🟥 = Task phải chờ task trước hoàn thành
- 📋 = Prompt copy-paste cho agent
- ✅ = Tiêu chí nghiệm thu (Definition of Done)

---

## TỔNG QUAN TASK MAP

```
GIAI ĐOẠN 3: TÍCH HỢP TRÍ TUỆ NHÂN TẠO (8 ngày)
├── 🟥 Agent 3A: AI Extraction Module — Gemini (sau khi GĐ2 xong)
├── 🟥 Agent 3B: Result Aggregator & Excel Export (sau khi 3A xong)
├── 🟥 Agent 3C: Full Pipeline Test 10 cty (sau khi 3A + 3B xong)
└── 🟥 Agent 3D: Evaluation & Prompt Tuning (sau khi 3C xong)

GIAI ĐOẠN 4: VẬN HÀNH CHÍNH THỨC (10 ngày)
├── 🟥 Agent 4A: Resume System & Robustness (sau khi 3D xong)
├── 🟦 Agent 4B: Performance Optimization (song song với 4A)
├── 🟥 Agent 4C: Batch Run 100 công ty (sau khi 4A + 4B xong)
├── 🟥 Agent 4D: Batch Run 1.000 công ty (sau khi 4C xong)
└── 🟥 Agent 4E: Full Run 6.000+ công ty (sau khi 4D xong)
```

---
---

# GIAI ĐOẠN 3: TÍCH HỢP TRÍ TUỆ NHÂN TẠO

**💰 Chi phí Firecrawl:** ~50 credits (test 10 công ty MỚI) — Sử dụng gói Free (còn dư ~425 credits)  
**💰 Chi phí Gemini AI:** ~$0 (nằm trong gói miễn phí Google AI Studio)

---

## AGENT 3A — AI Extraction Module (Gemini) 🟥
**Độ ưu tiên:** Rất Cao — Module cốt lõi của GĐ3  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** GĐ2 hoàn thành (cần có data trong `scraped_pages`)  
**⚠️ Cần GEMINI_API_KEY**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi có bảng "scraped_pages" trong SQLite chứa nội dung Markdown đã thu thập từ nhiều 
trang web cho mỗi công ty. Giờ tôi cần gửi nội dung này cho Google Gemini AI để 
trích xuất thông tin liên hệ có cấu trúc.

Mỗi công ty có 2–5 trang đã scrape (từ masothue, topcv, yellowpages, website chính chủ...).
AI cần đọc từng trang và nhặt ra: địa chỉ, SĐT, email, website, fax, người đại diện.
Quan trọng: GHI RÕ NGUỒN GỐC TỪNG THÔNG TIN (lấy từ trang nào).

ĐÃ CÓ SẴN (KHÔNG CẦN TẠO):
- src/database.py: DatabaseManager — có method:
  - get_scraped_pages_for_company(company_id) → list[dict] với các key:
    id, filtered_link_id, company_id, url, source_type, markdown_content,
    content_length, scrape_status, credits_used, error_message
  - insert_extracted_contact(company_id, scraped_page_id, source_type, source_url,
    address, phone, email, website, fax, representative, raw_ai_response, confidence_score)
- src/logger.py: PipelineLogger — ghi log mỗi bước
- Bảng extracted_contacts trong DB (schema bên dưới)

BẢNG extracted_contacts:
  id, company_id, scraped_page_id, source_type, source_url,
  address, phone, email, website, fax, representative,
  raw_ai_response, confidence_score, created_at

NHIỆM VỤ:
Tạo file: src/ai_extractor.py

CLASS AIExtractor:
  __init__(self, db: DatabaseManager, logger: PipelineLogger, gemini_api_key: str)
    - Khởi tạo Google Gemini client (dùng google-generativeai SDK)
    - Model mặc định: gemini-2.5-flash-preview-04-17

  CONSTANT: EXTRACTION_PROMPT_TEMPLATE (prompt gửi cho Gemini)
    Prompt phải yêu cầu AI:
    1. Đọc nội dung Markdown được cung cấp
    2. Trích xuất CHÍNH XÁC các trường sau (nếu tìm thấy):
       - address: Địa chỉ đầy đủ (bao gồm quận/huyện, tỉnh/thành phố)
       - phone: Số điện thoại (có thể nhiều số, phân cách bằng dấu phẩy)
       - email: Địa chỉ email (có thể nhiều, phân cách bằng dấu phẩy)
       - website: URL website chính thức  
       - fax: Số fax
       - representative: Tên người đại diện / Giám đốc / CEO
    3. Trả về dạng JSON thuần túy (không có markdown code block)
    4. Nếu không tìm thấy trường nào → để null
    5. Thêm trường "confidence": 0.0-1.0 (AI tự đánh giá độ tin cậy)
    
    LƯU Ý TRONG PROMPT:
    - Yêu cầu AI xử lý đặc biệt cho nội dung tiếng Việt
    - Phân biệt số điện thoại cố định vs di động
    - Không nhầm SĐT hotline quảng cáo với SĐT liên hệ chính
    - Địa chỉ phải là địa chỉ trụ sở/văn phòng, không phải địa chỉ kho hàng

  Method: extract_from_page(scraped_page_id: int) -> dict
    1. Đọc scraped_page từ DB (lấy markdown_content, source_type, url)
    2. KIỂM TRA TRƯỚC: page này đã extract rồi chưa? (check extracted_contacts)
       → Nếu rồi → skip, trả về data cũ (KHÔNG GỌI AI LẠI — tiết kiệm quota)
    3. Chuẩn bị prompt: điền markdown_content vào EXTRACTION_PROMPT_TEMPLATE
    4. Gọi Gemini API:
       - Dùng google.generativeai SDK
       - model.generate_content(prompt)
       - Parse JSON response
    5. Lưu kết quả vào bảng extracted_contacts:
       - source_type = lấy từ scraped_page
       - source_url = lấy từ scraped_page
       - raw_ai_response = response gốc (string, cho debug)
       - confidence_score = từ JSON response
    6. Ghi log (PipelineLogger)
    7. Trả về dict {status, extracted_fields, confidence}

  Method: extract_for_company(company_id: int, delay_seconds: float = 1.0) -> list[dict]
    1. Đọc tất cả scraped_pages cho company_id (chỉ lấy scrape_status='success')
    2. Sắp xếp ưu tiên: masothue > thuvienphapluat > yellowpages > hosocongty > 
       official_website > vietnamworks > topcv > vietcareer > facebook > linkedin
    3. Gọi extract_from_page tuần tự, delay giữa các request
    4. Update companies.status = 'extracting' → 'done'
    5. Trả về tổng hợp kết quả
    
  Method: extract_batch(company_ids: list[int], delay_seconds: float = 1.0)
    - Xử lý tuần tự, in progress
    - Nếu 1 company lỗi → log, tiếp tục company tiếp theo

  Method: get_extraction_stats() -> dict
    - total_extracted, total_pages_processed,
      avg_confidence_score, fields_coverage (% có address, % có phone, ...),
      source_distribution

ERROR HANDLING:
- Gemini API rate limit (429): chờ 60 giây rồi thử lại (tối đa 3 lần)
- Gemini API quota exceeded: DỪNG ngay, in cảnh báo
- JSON parse error: lưu raw_ai_response, ghi confidence=0, log warning
- Content quá dài (>30.000 ký tự): cắt giữ 30.000 ký tự đầu, ghi note trong metadata

THƯ VIỆN: google-generativeai (thêm vào requirements.txt)
API KEY: Đọc từ biến môi trường GEMINI_API_KEY hoặc file .env

CẤU TRÚC:
project_root/
├── src/
│   ├── database.py       (đã có — không sửa)
│   ├── logger.py         (đã có — không sửa)
│   └── ai_extractor.py   (TẠO MỚI)
├── tests/
│   └── test_ai_extractor.py (mock Gemini API, test parse logic)
└── requirements.txt      (thêm: google-generativeai)

LƯU Ý QUAN TRỌNG:
- KHÔNG sửa database.py và logger.py, chỉ import và sử dụng.
- Mỗi lần gọi Gemini = miễn phí (gói Google AI Studio), nhưng có rate limit 15 RPM
  cho model miễn phí → delay ít nhất 4 giây giữa các request.
- PHẢI lưu raw_ai_response vào DB — đây là tài sản để debug và cải thiện prompt.
- Ưu tiên tuyệt đối việc KHÔNG EXTRACT TRÙNG (idempotent) — nếu đã extract rồi thì skip.
- Khi test, dùng mock/fixture để không tốn quota thật.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/ai_extractor.py` tồn tại, có class `AIExtractor`
- [ ] Prompt template trích xuất đủ 6 trường: address, phone, email, website, fax, representative
- [ ] Có cơ chế skip page đã extract (idempotent)
- [ ] Parse JSON response chính xác, xử lý edge case (AI trả format sai)
- [ ] Lưu đầy đủ vào bảng `extracted_contacts` kèm `raw_ai_response`
- [ ] Xử lý rate limit (429) và quota exceeded đúng cách
- [ ] Mock test `tests/test_ai_extractor.py` all pass
- [ ] Test thật với 2-3 scraped pages từ DB pilot → verify kết quả hợp lý

---

## AGENT 3B — Result Aggregator & Excel Export 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** Agent 3A hoàn thành (cần có data trong `extracted_contacts`)

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi có bảng "extracted_contacts" trong SQLite chứa thông tin liên hệ đã được AI 
trích xuất từ nhiều nguồn khác nhau cho mỗi công ty. Mỗi công ty có thể có 2–5 bản ghi 
(mỗi bản ghi từ 1 nguồn: masothue, topcv, website chính chủ...).

Nguyên tắc trình bày:
- HIỂN THỊ TẤT CẢ thông tin thu thập được từ MỌI NGUỒN — KHÔNG lọc bỏ trùng lặp
- Phân loại rõ ràng theo nguồn — người xem biết ngay thông tin nào đến từ đâu
- Mỗi nguồn dữ liệu = 1 dòng riêng trong Excel
- Công ty không tìm thấy thông tin → vẫn hiện 1 dòng với ghi chú "(không tìm thấy)"

ĐÃ CÓ SẴN (KHÔNG CẦN TẠO):
- src/database.py: DatabaseManager — có method:
  - get_all_companies() → list[dict]
  - get_extracted_contacts_for_company(company_id) → list[dict] với các key:
    id, company_id, scraped_page_id, source_type, source_url,
    address, phone, email, website, fax, representative,
    raw_ai_response, confidence_score
  - get_scraped_pages_for_company(company_id) → list[dict]
  - get_pipeline_logs_for_company(company_id) → list[dict]
- src/excel_handler.py: ExcelWriter — đã có method write_results()
  → Tuy nhiên, ExcelWriter hiện tại CHƯA tối ưu cho output cuối cùng.
  Agent 3B cần NÂNG CẤP ExcelWriter hoặc tạo class mới.
- src/logger.py: PipelineLogger

NHIỆM VỤ:
Tạo file: src/result_aggregator.py

CLASS ResultAggregator:
  __init__(self, db: DatabaseManager)

  Method: aggregate_company(company_id: int) -> dict
    Tổng hợp TOÀN BỘ thông tin cho 1 công ty:
    1. Đọc company info (tên, MST)
    2. Đọc extracted_contacts cho company_id
    3. Nhóm theo source_type
    4. Trả về dict:
       {
         "company_name": "...",
         "tax_code": "...",
         "sources": [
           {
             "source_type": "masothue",
             "source_url": "https://masothue.com/...",
             "address": "123 Nguyễn Huệ, Q1, HCM",
             "phone": "028-1234-5678",
             "email": null,
             "website": null,
             "fax": null,
             "representative": "Nguyễn Văn A",
             "confidence": 0.95
           },
           {
             "source_type": "official_website",
             ...
           }
         ],
         "has_data": True,
         "total_sources": 2,
         "collection_date": "2026-04-20"
       }

  Method: aggregate_all(company_ids: list[int] = None) -> list[dict]
    - Tổng hợp cho tất cả (hoặc danh sách chỉ định)
    - In progress khi chạy

  Method: generate_summary_stats(aggregated_data: list[dict]) -> dict
    Thống kê tổng quát:
    - total_companies: int
    - companies_with_data: int
    - companies_no_data: int
    - coverage_rate: float (% tìm được thông tin)
    - field_coverage: dict (% có address, % có phone, % có email...)
    - source_distribution: dict (masothue: 35%, topcv: 20%, ...)
    - avg_sources_per_company: float
    - avg_confidence: float

CẬP NHẬT FILE: src/excel_handler.py

NÂNG CẤP CLASS ExcelWriter — thêm method mới:
  Method: write_final_report(output_path: str, aggregated_data: list[dict], 
                              summary_stats: dict)
    
    SHEET 1: "Kết quả thu thập" (dữ liệu chi tiết)
    Cột: STT | Tên công ty | Mã số thuế | Nguồn | Địa chỉ | SĐT | Email | Website | 
         Fax | Người đại diện | Độ tin cậy | Ngày thu thập
    
    Format:
    - Mỗi công ty có thể chiếm NHIỀU dòng (mỗi nguồn 1 dòng)
    - Conditional formatting: confidence >= 0.8 → xanh, 0.5-0.8 → vàng, < 0.5 → đỏ
    - Dòng công ty không tìm thấy: highlight xám nhạt, ghi "(không tìm thấy)"
    
    SHEET 2: "Thống kê tổng quát" (summary)
    - Hiển thị summary_stats dưới dạng bảng đẹp
    - Danh sách công ty không tìm thấy thông tin
    
    Format chung:
    - Header bold, border, auto-width, freeze pane
    - Font: Calibri 11pt
    - Encoding: UTF-8 (hỗ trợ tiếng Việt, Hàn)

CẤU TRÚC:
project_root/
├── src/
│   ├── database.py           (đã có — không sửa)
│   ├── excel_handler.py      (SỬA — thêm method write_final_report)
│   └── result_aggregator.py  (TẠO MỚI)
├── tests/
│   ├── test_result_aggregator.py  (TẠO MỚI)
│   └── test_excel_final.py        (TẠO MỚI — test Excel output cuối cùng)

LƯU Ý:
- Khi sửa excel_handler.py: KHÔNG xóa code cũ, chỉ THÊM method mới.
- Xử lý unicode (tiếng Việt, tiếng Hàn) đúng cách.
- Excel output phải đáp ứng yêu cầu "người xem dễ so sánh thông tin từ nhiều nguồn".
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/result_aggregator.py` tồn tại, có class `ResultAggregator`
- [ ] `aggregate_company()` trả về dict đúng format, bao gồm tất cả nguồn
- [ ] `generate_summary_stats()` tính đúng các chỉ số thống kê
- [ ] `excel_handler.py` có thêm method `write_final_report()`
- [ ] Excel output có 2 sheets: chi tiết + thống kê
- [ ] Conditional formatting confidence hoạt động (xanh/vàng/đỏ)
- [ ] Công ty không có data vẫn hiển thị dòng "(không tìm thấy)"
- [ ] Test all pass
- [ ] Tạo được file Excel mẫu với data giả → mở bằng Excel/LibreOffice đẹp

---

## AGENT 3C — Full Pipeline Test 10 công ty (Kịch bản B) 🟥
**Độ ưu tiên:** Rất cao — Đây là bài kiểm tra end-to-end đầu tiên  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** Agent 3A + 3B hoàn thành  
**⚠️ Tiêu tốn ~50 Firecrawl credits thật + Gemini AI quota**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi đã có hệ thống hoàn chỉnh với tất cả module:
- src/database.py: DatabaseManager
- src/excel_handler.py: ExcelReader + ExcelWriter (đã nâng cấp)
- src/logger.py: PipelineLogger
- src/search_module.py: SearchModule
- src/filter_module.py: LinkFilter
- src/scrape_module.py: ScrapeModule
- src/ai_extractor.py: AIExtractor (MỚI — GĐ3)
- src/result_aggregator.py: ResultAggregator (MỚI — GĐ3)
- src/pipeline.py: Pipeline orchestrator (cần NÂNG CẤP)

Giờ tôi cần:
1. Nâng cấp Pipeline để tích hợp bước AI Extract
2. Chạy thử TOÀN BỘ pipeline end-to-end cho 10 công ty MỚI (khác 10 cty pilot GĐ2)
3. Xuất báo cáo đầy đủ

NHIỆM VỤ:

PHẦN 1: CẬP NHẬT src/pipeline.py
  - Thêm bước 4 (AI Extract) vào pipeline run():
    1. SEARCH → lưu 10 link vào DB
    2. FILTER → lọc link, lưu vào DB
    3. SCRAPE → thu thập nội dung, lưu vào DB
    4. AI_EXTRACT → Gemini trích xuất thông tin, lưu vào DB  ← MỚI
  - Import và khởi tạo AIExtractor + ResultAggregator
  - Cập nhật method generate_report():
    + Dùng ResultAggregator.aggregate_all() thay vì logic tạm thời cũ
    + Dùng ExcelWriter.write_final_report() thay vì write_results()
  - KHÔNG XÓA code cũ — thêm code mới, giữ backward compatibility

PHẦN 2: TẠO scripts/run_pilot_10_full.py
  Script main cho Kịch bản B (full pipeline bao gồm AI):
  1. Đọc .env lấy FIRECRAWL_API_KEY + GEMINI_API_KEY
  2. Đọc Excel file → lấy 10 công ty TIẾP THEO (bỏ qua 10 cty đã test ở GĐ2)
     → Cụ thể: lấy company ID 11–20 (hoặc offset 10–19 trong danh sách)
  3. Insert vào DB (nếu chưa có)
  4. Chạy Pipeline.run(limit=10) — bao gồm cả AI Extract
  5. In summary chi tiết:
     - Bao nhiêu cty thành công / thất bại
     - Tổng credits Firecrawl đã dùng
     - Tổng lần gọi Gemini AI
     - % công ty tìm được thông tin
     - Breakdown theo nguồn dữ liệu
  6. Xuất báo cáo:
     - output/pilot_10_full_report.xlsx (Excel cuối cùng, 2 sheets)
     - output/pilot_10_full_log.csv (log chi tiết)
  7. Hỏi xác nhận trước khi chạy: "Sẽ sử dụng ~50 credits + Gemini AI. Tiếp tục? (y/n)"

PHẦN 3: TẠO scripts/run_extract_only.py
  Script chạy RIÊNG bước AI Extract cho data đã scrape (không tốn Firecrawl credit):
  1. Đọc .env lấy GEMINI_API_KEY
  2. Tìm tất cả công ty có status='scraped' (đã scrape nhưng chưa extract)
  3. Chạy AIExtractor.extract_batch() cho các công ty này
  4. Xuất báo cáo kết quả
  → MỤC ĐÍCH: Chạy AI extract cho 10 công ty pilot GĐ2 mà không tốn thêm Firecrawl credits

CẤU TRÚC:
project_root/
├── src/
│   └── pipeline.py               (SỬA — thêm bước AI Extract)
├── scripts/
│   ├── run_pilot_10.py            (đã có — không sửa)
│   ├── run_pilot_10_full.py       (TẠO MỚI — Kịch bản B)
│   └── run_extract_only.py        (TẠO MỚI — chạy riêng AI)
├── output/
│   ├── pilot_10_full_report.xlsx  (kết quả 10 cty full pipeline)
│   └── pilot_10_full_log.csv     (log)
└── .env                           (cần thêm GEMINI_API_KEY)

LƯU Ý:
- Khi sửa pipeline.py: giữ lại TẤT CẢ code cũ, chỉ thêm logic mới.
- Delay giữa các Gemini API call: ít nhất 4 giây (rate limit 15 RPM free tier).
- CHẠY scripts/run_extract_only.py TRƯỚC cho 10 cty GĐ2 để test AI mà không tốn credit.
- Sau đó mới chạy scripts/run_pilot_10_full.py cho 10 cty MỚI.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] `src/pipeline.py` đã cập nhật có bước AI Extract
- [ ] `scripts/run_pilot_10_full.py` và `scripts/run_extract_only.py` tồn tại
- [ ] Chạy `run_extract_only.py` cho 10 công ty GĐ2 → extracted_contacts có data
- [ ] Chạy `run_pilot_10_full.py` hoàn thành 10 công ty MỚI, end-to-end
- [ ] File `output/pilot_10_full_report.xlsx` được tạo, có 2 sheets, chứa data thật
- [ ] File `output/pilot_10_full_log.csv` ghi đầy đủ log
- [ ] Tổng Firecrawl credits ≤ 60 (dự phòng 20%)
- [ ] Pipeline có resume capability (chạy lại không bị trùng)

---

## AGENT 3D — Evaluation & Prompt Tuning 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** Agent 3C hoàn thành (cần có kết quả thật để đánh giá)

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi đã chạy xong pipeline hoàn chỉnh (Search → Filter → Scrape → AI Extract) 
cho 20 công ty (10 cty GĐ2 + 10 cty GĐ3). Giờ tôi cần:
1. Đánh giá chất lượng kết quả AI trích xuất
2. So sánh dữ liệu từ nhiều nguồn cho cùng 1 công ty
3. Tinh chỉnh prompt AI nếu cần
4. Tạo báo cáo đánh giá chính thức

ĐÃ CÓ SẴN:
- Database chứa extracted_contacts cho 20 công ty
- src/result_aggregator.py: ResultAggregator
- src/ai_extractor.py: AIExtractor

NHIỆM VỤ:
Tạo 2 file:
1. src/evaluator.py — Module đánh giá chất lượng
2. scripts/run_evaluation.py — Script chạy đánh giá

FILE 1: src/evaluator.py

CLASS QualityEvaluator:
  __init__(self, db: DatabaseManager)

  Method: evaluate_extraction_quality(company_id: int) -> dict
    Cho 1 công ty, phân tích:
    1. Số nguồn có dữ liệu vs số nguồn đã scrape
    2. Các trường nào được extract (address? phone? email?)
    3. So sánh chéo giữa các nguồn:
       - Địa chỉ từ masothue có giống website chính chủ không?
       - SĐT có nhất quán giữa các nguồn không?
    4. Confidence score trung bình
    5. Trạng thái: "excellent" (>=3 trường, >=2 nguồn) / "good" (>=2 trường) / 
       "partial" (1 trường) / "no_data"
    
    Trả về:
    {
      "company_id": 1,
      "company_name": "ABC Corp",
      "quality_grade": "excellent",
      "total_sources": 3,
      "fields_found": ["address", "phone", "email", "representative"],
      "fields_missing": ["fax", "website"],
      "cross_source_consistency": {
        "address_match": True,
        "phone_match": False
      },
      "avg_confidence": 0.87,
      "issues": ["Phone mismatch between masothue and topcv"]
    }

  Method: evaluate_batch(company_ids: list[int] = None) -> dict
    Đánh giá toàn bộ, trả về:
    - grade_distribution: {"excellent": 5, "good": 8, "partial": 4, "no_data": 3}
    - overall_quality_score: float (0-100)
    - common_issues: list[str] (top 5 vấn đề phổ biến)
    - recommendations: list[str] (đề xuất cải thiện)

  Method: generate_evaluation_report(output_path: str, eval_results: dict)
    Xuất báo cáo đánh giá ra Excel:
    - Sheet 1: "Đánh giá chi tiết" (từng công ty 1 dòng)
    - Sheet 2: "Thống kê chất lượng" (tổng quát)
    - Sheet 3: "Vấn đề cần xử lý" (danh sách issues)

FILE 2: scripts/run_evaluation.py
  1. Đọc toàn bộ extracted_contacts từ DB
  2. Chạy QualityEvaluator.evaluate_batch()
  3. In summary ra console
  4. Xuất báo cáo: output/evaluation_report.xlsx
  5. In recommendations

BONUS — PROMPT TUNING:
  Tạo file: src/prompt_versions.py
  - Chứa dictionary các phiên bản prompt (v1, v2, v3...)
  - Mỗi phiên bản ghi rõ: ngày tạo, changelog, kết quả test
  - AIExtractor có thể load prompt version cụ thể để A/B test
  → MỤC ĐÍCH: theo dõi quá trình cải thiện prompt

CẤU TRÚC:
project_root/
├── src/
│   ├── evaluator.py          (TẠO MỚI)
│   └── prompt_versions.py    (TẠO MỚI)
├── scripts/
│   └── run_evaluation.py     (TẠO MỚI)
├── output/
│   └── evaluation_report.xlsx

LƯU Ý:
- KHÔNG sửa file nào trong src/ ngoài các file tạo mới.
- Cross-source consistency: so sánh đơn giản (substring match) — KHÔNG CẦN quá phức tạp.
- Đây là bước quan trọng trước khi chạy quy mô lớn (GĐ4).
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] File `src/evaluator.py` tồn tại, có class `QualityEvaluator`
- [ ] `evaluate_extraction_quality()` phân loại đúng quality grade
- [ ] `evaluate_batch()` tạo được tổng kết quality cho 20 công ty
- [ ] File `output/evaluation_report.xlsx` được tạo, có 3 sheets
- [ ] File `src/prompt_versions.py` tồn tại với ít nhất prompt v1
- [ ] Có recommendations rõ ràng cho việc cải thiện (nếu cần)
- [ ] Test all pass

---
---

# GIAI ĐOẠN 4: VẬN HÀNH CHÍNH THỨC

**⚠️ GĐ4 bắt đầu SAU KHI đánh giá GĐ3 đạt chất lượng chấp nhận được.**  
**Nếu quality_score < 60% → quay lại GĐ3 tinh chỉnh trước.**

---

## AGENT 4A — Resume System & Robustness 🟥
**Độ ưu tiên:** Rất Cao — Bắt buộc có trước khi chạy quy mô lớn  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** GĐ3 hoàn thành + đánh giá đạt  

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi chuẩn bị chạy hệ thống cho hàng ngàn công ty. Trước khi chạy quy mô lớn,
hệ thống CẦN:
1. Resume capability: tự động tiếp tục từ điểm dừng nếu bị gián đoạn
2. Checkpointing: lưu trạng thái sau mỗi công ty
3. Graceful shutdown: dừng an toàn khi nhận signal SIGINT (Ctrl+C)
4. Data integrity: không bao giờ mất dữ liệu đã thu thập
5. Error recovery: tự động retry các công ty bị lỗi

ĐÃ CÓ SẴN:
- src/pipeline.py: Pipeline (có method resume() cơ bản — cần nâng cấp)
- src/database.py: DatabaseManager
- src/logger.py: PipelineLogger (có get_last_processed_company_id())
- Toàn bộ module Search, Filter, Scrape, AI Extract

NHIỆM VỤ:

PHẦN 1: NÂNG CẤP src/pipeline.py — Hệ thống Resume mạnh mẽ

  CẬP NHẬT method run():
  1. Trước khi bắt đầu:
     - Check status từng company trong DB
     - Skip company có status = 'done'
     - Retry company có status = 'failed' (tối đa 2 lần retry)
     - Tiếp tục company đang ở giữa chừng (VD: đã search nhưng chưa scrape)
       → Xác định bước cuối cùng hoàn thành, tiếp tục từ bước tiếp theo
  
  2. Checkpoint sau mỗi bước/công ty:
     - Sau SEARCH xong → update status = 'searched'
     - Sau FILTER xong → status vẫn = 'searched' (filter không tốn credit, rất nhanh)
     - Sau SCRAPE xong → update status = 'scraped'
     - Sau AI EXTRACT xong → update status = 'done'
     → Nếu system crash giữa SCRAPE → resume sẽ không search lại (đã có data)

  3. Graceful shutdown:
     - Bắt signal SIGINT / SIGTERM
     - Khi nhận signal: hoàn thành công ty HIỆN TẠI, rồi mới dừng
     - In: "Đang dừng an toàn... Hoàn thành công ty hiện tại trước khi thoát"
     - Lưu trạng thái cuối cùng vào DB

  THÊM method: get_resumable_companies() -> list[dict]
    Trả về danh sách công ty chưa hoàn thành, kèm trạng thái hiện tại:
    [
      {"company_id": 15, "status": "searched", "next_step": "filter"},
      {"company_id": 16, "status": "pending", "next_step": "search"},
      {"company_id": 17, "status": "failed", "retry_count": 1, "next_step": "search"}
    ]

  THÊM method: retry_failed(max_retries: int = 2)
    - Tìm tất cả company status='failed'
    - Retry từ đầu, tối đa max_retries lần
    - Nếu vẫn fail → status = 'permanently_failed', ghi lý do

PHẦN 2: TẠO src/health_monitor.py — Giám sát sức khỏe hệ thống

CLASS HealthMonitor:
  __init__(self, db: DatabaseManager, logger: PipelineLogger)

  Method: check_credits_remaining(firecrawl_api_key: str) -> dict
    - Tính toán từ DB: total credits_used ở search_results + scraped_pages
    - Cảnh báo nếu credit sắp hết

  Method: estimate_completion_time(remaining_companies: int) -> dict
    - Dựa trên avg_time_per_company từ data đã chạy
    - Ước tính: thời gian còn lại, thời điểm hoàn thành
    - Ước tính: credit cần thiết

  Method: get_system_status() -> dict
    Tổng hợp:
    {
      "total_companies": 6000,
      "completed": 20,
      "failed": 2,
      "pending": 5978,
      "progress_percent": 0.33,
      "estimated_hours_remaining": 150,
      "estimated_credits_needed": 29890,
      "current_plan": "Standard ($99/mo, 100k credits)",
      "credit_sufficient": True
    }

  Method: print_dashboard()
    In bảng thông tin tổng quát ra console (có format đẹp, có màu)

PHẦN 3: TẠO scripts/run_batch.py — Script chạy batch tổng quát

  Script main cho vận hành chính thức:
  Argument: python scripts/run_batch.py --limit 100 --offset 20 --delay 3.0
  
  Options:
  --limit N       : Số công ty tối đa để xử lý (bắt buộc)
  --offset N      : Bỏ qua N công ty đầu (mặc định 0)
  --delay SECONDS : Delay giữa các request (mặc định 3.0)
  --resume        : Tiếp tục từ điểm dừng (bỏ qua offset)
  --retry-failed  : Retry các công ty đã fail
  --dry-run       : Chỉ in kế hoạch, không chạy thật
  
  Luồng xử lý:
  1. Load config từ .env
  2. Khởi tạo Pipeline + HealthMonitor
  3. In dashboard (HealthMonitor.print_dashboard())
  4. Nếu --dry-run → in kế hoạch rồi thoát
  5. Hỏi xác nhận: "Sẽ xử lý N công ty, ước tính ~X credits. Tiếp tục? (y/n)"
  6. Chạy Pipeline.run(limit=N, offset=M)
  7. Sau khi xong → in summary + xuất báo cáo

CẤU TRÚC:
project_root/
├── src/
│   ├── pipeline.py           (SỬA — nâng cấp resume + graceful shutdown)
│   └── health_monitor.py     (TẠO MỚI)
├── scripts/
│   └── run_batch.py          (TẠO MỚI — script chạy batch tổng quát)
├── tests/
│   ├── test_resume.py        (TẠO MỚI — test resume logic)
│   └── test_health_monitor.py (TẠO MỚI)

LƯU Ý:
- Khi sửa pipeline.py: giữ backward compatibility. run_pilot_10.py phải vẫn chạy được.
- Signal handling: dùng module signal của Python (signal.SIGINT, signal.SIGTERM).
- QUAN TRỌNG: hệ thống resume PHẢI hoạt động đúng — đây là bảo hiểm cho toàn bộ GĐ4.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] Resume hoạt động: chạy 5 cty → Ctrl+C → chạy lại → tiếp tục từ cty dở dang
- [ ] Không scrape/search trùng khi resume (verify bằng credits_used)
- [ ] Graceful shutdown dừng đúng cách (hoàn thành cty hiện tại)
- [ ] `retry_failed()` hoạt động cho các công ty lỗi
- [ ] `HealthMonitor.get_system_status()` trả về đúng số liệu
- [ ] `scripts/run_batch.py --dry-run` in được kế hoạch mà không chạy thật
- [ ] Test resume logic all pass

---

## AGENT 4B — Performance Optimization 🟦
**Độ ưu tiên:** Trung bình  
**Thời gian ước tính:** 2 ngày  
**Phụ thuộc:** GĐ3 hoàn thành (cần data thật để benchmark)  
**Có thể chạy song song với Agent 4A**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Tôi chuẩn bị chạy hệ thống cho 6.000+ công ty. Hiện tại mỗi công ty mất ~25-40 giây.
Với 6.000 cty → ~42-67 giờ chạy liên tục. Tôi cần tối ưu tốc độ nhưng KHÔNG được 
bị chặn (rate limit / IP ban).

ĐÃ CÓ SẴN:
- Toàn bộ module trong src/
- Data thật từ 20 công ty đã xử lý

NHIỆM VỤ:
Tạo file: src/rate_limiter.py

CLASS AdaptiveRateLimiter:
  __init__(self, initial_delay: float = 3.0, min_delay: float = 1.0, max_delay: float = 30.0)

  Chiến lược điều chỉnh tốc độ tự động:
  1. Bắt đầu với delay = initial_delay (3 giây)
  2. Nếu request thành công liên tiếp 10 lần → giảm delay 0.5s (tối thiểu min_delay)
  3. Nếu nhận HTTP 429 (rate limit) → tăng delay gấp đôi (tối đa max_delay)
  4. Nếu nhận HTTP 403/503 (có thể bị chặn) → tăng delay lên max_delay, chờ 5 phút
  5. Log mọi thay đổi delay

  Method: wait()
  Method: report_success()
  Method: report_error(status_code: int)
  Method: get_stats() -> dict

TẠO file: src/connection_pool.py

CLASS ConnectionManager:
  __init__(self, firecrawl_api_key: str)
  
  - Dùng requests.Session() thay vì requests.get/post đơn lẻ
    → Reuse TCP connection → nhanh hơn ~20%
  - Tự động retry với backoff (retry 3 lần, delay 1s → 2s → 4s)
  - Timeout config riêng cho từng loại request:
    - Search: timeout=15s
    - Scrape: timeout=45s
  - Connection pooling: max 5 connections

CẬP NHẬT: src/search_module.py, src/scrape_module.py
  - Tích hợp AdaptiveRateLimiter thay cho fixed delay
  - Tích hợp ConnectionManager thay cho raw requests
  - KHÔNG thay đổi interface (các method public giữ nguyên signature)

BENCHMARK SCRIPT: scripts/benchmark.py
  1. Chạy pipeline cho 5 công ty với delay cũ (3.0s)
  2. Chạy pipeline cho 5 công ty với AdaptiveRateLimiter
  3. So sánh: thời gian trung bình, tổng thời gian, rate limit errors
  4. In bảng so sánh

CẤU TRÚC:
project_root/
├── src/
│   ├── rate_limiter.py       (TẠO MỚI)
│   ├── connection_pool.py    (TẠO MỚI)
│   ├── search_module.py      (SỬA — tích hợp rate limiter)
│   └── scrape_module.py      (SỬA — tích hợp rate limiter)
├── scripts/
│   └── benchmark.py          (TẠO MỚI)
├── tests/
│   ├── test_rate_limiter.py   (TẠO MỚI)
│   └── test_connection_pool.py (TẠO MỚI)

LƯU Ý:
- TUYỆT ĐỐI KHÔNG dùng concurrent/parallel requests cho Firecrawl
  → Tài khoản Free/Hobby chỉ cho 2-5 đồng thời, dễ bị ban.
- Ưu tiên: ỔN ĐỊNH hơn NHANH. Chạy chậm mà đủ 6.000 cty tốt hơn chạy nhanh mà bị ban.
- Khi sửa search_module.py / scrape_module.py: giữ backward compatibility.
  Nếu AdaptiveRateLimiter không được truyền vào → fallback về delay cũ.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] `AdaptiveRateLimiter` tự giảm delay khi ổn định, tự tăng khi gặp 429
- [ ] `ConnectionManager` dùng Session reuse, có retry + backoff
- [ ] `search_module.py` và `scrape_module.py` tích hợp đúng, backward compatible
- [ ] Benchmark cho thấy cải thiện ≥ 15% thời gian (so với delay cố định)
- [ ] Không có rate limit error trong quá trình benchmark
- [ ] Test all pass

---

## AGENT 4C — Batch Run 100 công ty 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 1 ngày  
**Phụ thuộc:** Agent 4A + 4B hoàn thành  
**⚠️ Tiêu tốn ~500 Firecrawl credits → Cần nâng lên gói Hobby ($19/tháng)**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Hệ thống đã sẵn sàng chạy quy mô trung bình. Đây là bước "stress test" đầu tiên
để phát hiện vấn đề chỉ xuất hiện ở quy mô lớn.

⚠️ TRƯỚC KHI BẮT ĐẦU:
- Xác nhận Firecrawl đã nâng lên gói Hobby ($19/tháng, 3.000 credits)
- Xác nhận resume system hoạt động (Agent 4A)
- Xác nhận rate limiter hoạt động (Agent 4B)

NHIỆM VỤ:

1. CHẠY DRY RUN trước:
   python scripts/run_batch.py --limit 100 --offset 20 --dry-run
   → Xác nhận kế hoạch đúng (100 cty, bỏ qua 20 cty đã test)

2. CHẠY THẬT:
   python scripts/run_batch.py --limit 100 --offset 20 --delay 3.0
   
   Trong quá trình chạy, GIÁM SÁT:
   - Console log: có bị 429 (rate limit) không?
   - Tốc độ: trung bình bao nhiêu giây / công ty?
   - Credits: đã dùng bao nhiêu? Còn bao nhiêu?
   - Lỗi: công ty nào fail? Lý do gì?

3. NẾU BỊ GIÁN ĐOẠN:
   python scripts/run_batch.py --resume

4. SAU KHI HOÀN THÀNH:
   - Chạy evaluation: python scripts/run_evaluation.py
   - Xuất báo cáo: output/batch_100_report.xlsx
   - Xuất log: output/batch_100_log.csv

5. PHÂN TÍCH KẾT QUẢ:
   Tạo file: output/batch_100_analysis.md
   Ghi nhận:
   - Tổng thời gian chạy
   - Tổng credits tiêu tốn (Firecrawl + Gemini)
   - Tỷ lệ thành công
   - Edge cases phát hiện
   - Đề xuất điều chỉnh cho batch 1.000

6. RETRY CÁC CÔNG TY FAIL:
   python scripts/run_batch.py --retry-failed

KHÔNG TẠO CODE MỚI — Chỉ chạy và phân tích kết quả.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] 100 công ty đã được xử lý
- [ ] File `output/batch_100_report.xlsx` tồn tại
- [ ] File `output/batch_100_analysis.md` ghi nhận edge cases + đề xuất
- [ ] Resume đã được test thực tế
- [ ] Credits tiêu tốn ≤ 600
- [ ] Tỷ lệ thành công ≥ 60%

---

## AGENT 4D — Batch Run 1.000 công ty 🟥
**Độ ưu tiên:** Cao  
**Thời gian ước tính:** 2 ngày (bao gồm monitoring time)  
**Phụ thuộc:** Agent 4C hoàn thành + kết quả chấp nhận được  
**⚠️ Tiêu tốn ~5.000 credits → Cần nâng lên gói Standard ($99/tháng, 100.000 credits)**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Đã xong batch 100 cty. Edge cases đã được xử lý. Giờ chạy lô lớn đầu tiên: 1.000 cty.

⚠️ TRƯỚC KHI BẮT ĐẦU:
- Xác nhận Firecrawl đã nâng lên gói Standard ($99/tháng, 100.000 credits)
- Review file output/batch_100_analysis.md để áp dụng bài học
- Đảm bảo máy tính có thể chạy liên tục 8-12 tiếng (hoặc dùng screen/tmux)

NHIỆM VỤ:

1. CHUẨN BỊ:
   - Kiểm tra disk space (dữ liệu scraped sẽ ~500MB-1GB)
   - Kiểm tra health monitor
   - Setup tmux/screen session

2. CHẠY THẬT (chia thành sub-batches 250 cty để an toàn):
   # Batch 1: công ty 121-370
   python scripts/run_batch.py --limit 250 --offset 120 --delay 3.0
   
   # Batch 2: công ty 371-620
   python scripts/run_batch.py --limit 250 --offset 370 --delay 3.0
   
   # Batch 3: công ty 621-870
   python scripts/run_batch.py --limit 250 --offset 620 --delay 3.0
   
   # Batch 4: công ty 871-1120
   python scripts/run_batch.py --limit 250 --offset 870 --delay 3.0
   
   Sau mỗi sub-batch:
   - Kiểm tra health monitor
   - Review log cho anomalies
   - Pause 5-10 phút

3. GIÁM SÁT LIÊN TỤC:
   - Credit usage, rate limit errors, memory/disk, database size

4. SAU KHI HOÀN THÀNH:
   - Retry failed: python scripts/run_batch.py --retry-failed
   - Evaluation: python scripts/run_evaluation.py
   - Báo cáo: output/batch_1000_report.xlsx
   - Analysis: output/batch_1000_analysis.md

5. PHÂN TÍCH CHUYÊN SÂU (output/batch_1000_analysis.md):
   - Thời gian tổng, thời gian trung bình / công ty
   - So sánh với batch 100
   - Phân bố nguồn dữ liệu
   - Đề xuất delay tối ưu cho batch 6.000
   - Database size và dự đoán size cuối cùng
   - Ước tính thời gian và chi phí cho 5.000+ công ty còn lại

KHÔNG TẠO CODE MỚI — Chỉ chạy, giám sát, và phân tích.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] 1.000 công ty đã được xử lý
- [ ] File `output/batch_1000_report.xlsx` tồn tại
- [ ] File `output/batch_1000_analysis.md` có phân tích chuyên sâu
- [ ] Không có vấn đề nghiêm trọng (bị ban IP, mất data, crash)
- [ ] Credits tiêu tốn ≤ 6.000
- [ ] Tỷ lệ thành công ≥ 60%
- [ ] Ước tính cho batch 6.000 đã được tính toán

---

## AGENT 4E — Full Run 6.000+ công ty 🟥
**Độ ưu tiên:** Cao — Đây là bước cuối cùng  
**Thời gian ước tính:** 3-5 ngày (bao gồm thời gian chạy + giám sát)  
**Phụ thuộc:** Agent 4D hoàn thành + phân tích ổn  
**💰 Chi phí: ~25.000 credits → Nằm trong gói Standard (100.000/tháng)**

### 📋 PROMPT CHO AGENT

```
BỐI CẢNH DỰ ÁN (chỉ phần liên quan):
Đã xong 1.120 công ty. Còn ~4.880+ công ty. Chạy nốt toàn bộ danh sách.

⚠️ TRƯỚC KHI BẮT ĐẦU:
- Review output/batch_1000_analysis.md để lấy delay tối ưu
- Xác nhận credit Standard đủ (100.000 credits/tháng, cần ~25.000)
- Setup monitoring: tmux session + health check mỗi 1-2 tiếng

NHIỆM VỤ:

1. CHIA BATCH:
   Chia thành sub-batches 500 công ty:
   
   for offset in 1120 1620 2120 2620 3120 3620 4120 4620 5120 5620:
     python scripts/run_batch.py --limit 500 --offset $offset --delay {tối ưu}
     # Pause 10-15 phút giữa các sub-batch
     # Check health monitor
     # Retry failed nếu > 5% fail rate

2. GIÁM SÁT (mỗi 2 tiếng):
   - Check health monitor
   - Check logs for anomalies
   - Check database integrity

3. SAU KHI HOÀN THÀNH TOÀN BỘ:
   a) Retry tất cả failed:
      python scripts/run_batch.py --retry-failed
   
   b) Evaluation toàn bộ:
      python scripts/run_evaluation.py
   
   c) Xuất BÁO CÁO CUỐI CÙNG:
      output/FINAL_REPORT_6000.xlsx  ← SẢN PHẨM CHÍNH CỦA DỰ ÁN
      output/FINAL_SUMMARY.xlsx
      output/FINAL_FAILED_LIST.xlsx
   
   d) Phân tích cuối cùng:
      output/FINAL_ANALYSIS.md

4. BÁO CÁO CUỐI CÙNG (output/FINAL_ANALYSIS.md):
   - Tổng số công ty đã xử lý
   - Tỷ lệ tìm được thông tin
   - Phân bố chất lượng (excellent/good/partial/no_data)
   - Tổng chi phí (Firecrawl + Gemini)
   - Thời gian tổng cộng
   - Bài học kinh nghiệm
   - Đề xuất cho phase tiếp theo (nếu có)

KHÔNG TẠO CODE MỚI — Chỉ chạy, giám sát, và xuất báo cáo cuối cùng.
```

### ✅ TIÊU CHÍ NGHIỆM THU
- [ ] Toàn bộ 6.000+ công ty đã được xử lý
- [ ] File `output/FINAL_REPORT_6000.xlsx` tồn tại — **SẢN PHẨM CUỐI CÙNG**
- [ ] File `output/FINAL_SUMMARY.xlsx` có thống kê tổng quát
- [ ] File `output/FINAL_FAILED_LIST.xlsx` liệt kê công ty không tìm thấy
- [ ] File `output/FINAL_ANALYSIS.md` có phân tích chi tiết
- [ ] Credits Firecrawl tổng ≤ 35.000 (tất cả giai đoạn)
- [ ] Tỷ lệ thành công ≥ 60% (target: 70-80%)

---
---

# PHỤ LỤC A: CẤU TRÚC THƯ MỤC CUỐI CÙNG SAU GĐ3 & GĐ4

```
auto_search_company/
├── .env                              # API keys (KHÔNG push git)
├── .env.example                      # Template
├── .gitignore
├── requirements.txt                  # + google-generativeai
│
├── AUTO_COMPANY_SEARCH_PROJECT_PLAN.md
├── PHASE_1_2_DETAILED_PLAN.md
├── PHASE_3_4_DETAILED_PLAN.md        # File này
│
├── src/
│   ├── __init__.py
│   ├── database.py               # [Agent 1A] DatabaseManager
│   ├── excel_handler.py          # [Agent 1B + 3B] ExcelReader + ExcelWriter (nâng cấp)
│   ├── logger.py                 # [Agent 1C] PipelineLogger
│   ├── search_module.py          # [Agent 2A + 4B] SearchModule (+ rate limiter)
│   ├── filter_module.py          # [Agent 2B] LinkFilter
│   ├── scrape_module.py          # [Agent 2C + 4B] ScrapeModule (+ rate limiter)
│   ├── pipeline.py               # [Agent 2D + 3C + 4A] Pipeline (nâng cấp)
│   ├── ai_extractor.py           # [Agent 3A] AIExtractor — MỚI GĐ3
│   ├── result_aggregator.py      # [Agent 3B] ResultAggregator — MỚI GĐ3
│   ├── evaluator.py              # [Agent 3D] QualityEvaluator — MỚI GĐ3
│   ├── prompt_versions.py        # [Agent 3D] Quản lý prompt versions — MỚI GĐ3
│   ├── health_monitor.py         # [Agent 4A] HealthMonitor — MỚI GĐ4
│   ├── rate_limiter.py           # [Agent 4B] AdaptiveRateLimiter — MỚI GĐ4
│   └── connection_pool.py        # [Agent 4B] ConnectionManager — MỚI GĐ4
│
├── scripts/
│   ├── run_pilot_10.py           # [Agent 2D] Test 10 cty (Search+Scrape only)
│   ├── run_pilot_10_full.py      # [Agent 3C] Test 10 cty (full pipeline)
│   ├── run_extract_only.py       # [Agent 3C] Chạy riêng AI Extract
│   ├── run_evaluation.py         # [Agent 3D] Đánh giá chất lượng
│   ├── run_batch.py              # [Agent 4A] Script chạy batch (vận hành chính thức)
│   └── benchmark.py              # [Agent 4B] Benchmark performance
│
├── tests/
│   ├── test_database.py          # [Agent 1A]
│   ├── test_excel_handler.py     # [Agent 1B]
│   ├── test_logger.py            # [Agent 1C]
│   ├── test_integration_phase1.py # [Agent 1D]
│   ├── test_search_module.py     # [Agent 2A]
│   ├── test_filter_module.py     # [Agent 2B]
│   ├── test_scrape_module.py     # [Agent 2C]
│   ├── test_ai_extractor.py      # [Agent 3A] — MỚI
│   ├── test_result_aggregator.py  # [Agent 3B] — MỚI
│   ├── test_excel_final.py        # [Agent 3B] — MỚI
│   ├── test_resume.py            # [Agent 4A] — MỚI
│   ├── test_health_monitor.py    # [Agent 4A] — MỚI
│   ├── test_rate_limiter.py      # [Agent 4B] — MỚI
│   └── test_connection_pool.py   # [Agent 4B] — MỚI
│
├── data/
│   └── company_data.db           # SQLite database (~1-2GB khi đầy)
│
├── logs/
│   └── pipeline_YYYYMMDD.log    # Daily log files
│
└── output/
    ├── pilot_10_report.xlsx          # [GĐ2]
    ├── pilot_10_log.csv              # [GĐ2]
    ├── pilot_10_full_report.xlsx     # [GĐ3]
    ├── pilot_10_full_log.csv         # [GĐ3]
    ├── evaluation_report.xlsx        # [GĐ3]
    ├── batch_100_report.xlsx         # [GĐ4]
    ├── batch_100_analysis.md         # [GĐ4]
    ├── batch_1000_report.xlsx        # [GĐ4]
    ├── batch_1000_analysis.md        # [GĐ4]
    ├── FINAL_REPORT_6000.xlsx        # [GĐ4] 🏆 SẢN PHẨM CUỐI CÙNG
    ├── FINAL_SUMMARY.xlsx            # [GĐ4]
    ├── FINAL_FAILED_LIST.xlsx        # [GĐ4]
    └── FINAL_ANALYSIS.md             # [GĐ4]
```

---

# PHỤ LỤC B: TÓM TẮT THỨ TỰ THỰC HIỆN (GĐ3 & GĐ4)

| Thứ tự | Agent | Task | Phụ thuộc | Song song? | Ước tính | Loại |
|--------|-------|------|-----------|------------|----------|------|
| 1 | **3A** | AI Extraction Module | GĐ2 xong | 🟥 Chờ GĐ2 | 2 ngày | Code |
| 2 | **3B** | Result Aggregator + Excel | 3A xong | 🟥 Chờ 3A | 2 ngày | Code |
| 3 | **3C** | Full Pipeline Test 10 cty | 3A+3B xong | 🟥 Chờ cả hai | 2 ngày | Code + Run |
| 4 | **3D** | Evaluation & Prompt Tuning | 3C xong | 🟥 Chờ 3C | 2 ngày | Code + Analysis |
| 5 | **4A** | Resume & Robustness | 3D xong | 🟥 Chờ GĐ3 | 2 ngày | Code |
| 5 | **4B** | Performance Optimization | GĐ3 xong | 🟦 Song song 4A | 2 ngày | Code |
| 6 | **4C** | Batch Run 100 cty | 4A+4B xong | 🟥 Chờ cả hai | 1 ngày | Run + Analysis |
| 7 | **4D** | Batch Run 1.000 cty | 4C xong | 🟥 Chờ 4C | 2 ngày | Run + Analysis |
| 8 | **4E** | Full Run 6.000+ cty | 4D xong | 🟥 Chờ 4D | 3-5 ngày | Run + Analysis |

**Tổng thời gian tối thiểu (critical path):** ~16-18 ngày  
**Tổng thời gian dự phòng (theo Plan):** 18 ngày (GĐ3: 8d + GĐ4: 10d)

---

# PHỤ LỤC C: CHECKLIST NÂNG CẤP GÓI FIRECRAWL

| Thời điểm | Hành động | Lý do |
|-----------|-----------|-------|
| Trước Agent 4C | Nâng lên **Hobby** ($19/tháng) | Batch 100 cty cần ~500 credits, vượt Free |
| Trước Agent 4D | Nâng lên **Standard** ($99/tháng) | Batch 1.000 cty cần ~5.000 credits |
| Sau Agent 4E | **Hạ xuống Hobby hoặc hủy** | Đã xử lý xong, không cần nữa |

---

# PHỤ LỤC D: DEPENDENCIES MỚI (requirements.txt)

```
# === Đã có từ GĐ1 & GĐ2 ===
openpyxl
requests
python-dotenv
colorama

# === Thêm cho GĐ3 ===
google-generativeai    # Google Gemini AI SDK

# === Thêm cho GĐ4 (optional) ===
# urllib3               # Đã có trong requests, dùng cho connection pooling
# argparse              # Built-in Python, dùng cho run_batch.py CLI args
```
