# KẾ HOẠCH DỰ ÁN
# Hệ thống tự động thu thập thông tin doanh nghiệp

**Ngày lập:** 13/04/2026  
**Phiên bản:** 3.0 — Phương án Firecrawl + Google Gemini AI  

---

## I. TÓM TẮT DỰ ÁN (Dành cho Ban Lãnh đạo)

### Mục tiêu
Xây dựng công cụ tự động tìm kiếm và thu thập thông tin liên hệ (địa chỉ, số điện thoại, email, website, người đại diện) của **hơn 6.000 doanh nghiệp** từ internet, thay thế quy trình tra cứu thủ công hiện tại.

### Quy trình tổng quát

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUY TRÌNH THU THẬP DỮ LIỆU                  │
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│   │  BƯỚC 1  │───▶│  BƯỚC 2  │───▶│  BƯỚC 3  │───▶│  BƯỚC 4  │  │
│   │ Đọc danh │    │ Tìm kiếm │    │ Thu thập │    │ AI phân  │  │
│   │ sách từ  │    │ trên     │    │ nội dung │    │ tích và  │  │
│   │  Excel   │    │ Google   │    │ các trang│    │ phân loại│  │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                                       │         │
│                                                       ▼         │
│                                                 ┌──────────┐    │
│                                                 │  BƯỚC 5  │    │
│                                                 │ Xuất kết │    │
│                                                 │ quả ra   │    │
│                                                 │  Excel   │    │
│                                                 └──────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Giải thích từng bước 

| Bước | Tên gọi | Giải thích đơn giản |
|------|---------|---------------------|
| **Bước 1** | Đọc danh sách | Hệ thống mở file Excel chứa tên 6.000+ công ty, đọc từng tên một |
| **Bước 2** | Tìm kiếm tự động | Với mỗi công ty, hệ thống lên Google gõ tên công ty đó và lấy về 10 đường link kết quả đầu tiên. Giống hệt việc bạn tự gõ Google bằng tay, nhưng máy làm thay. **Kết quả 10 link này được lưu lại ngay lập tức** |
| **Bước 3** | Thu thập nội dung | Hệ thống kiểm tra 10 link đó: nếu link nào dẫn đến 1 trong 9 trang web mục tiêu hoặc dẫn đến website chính chủ của công ty, hệ thống sẽ tự vào trang đó và chép lại toàn bộ nội dung chữ (đã lọc quảng cáo). **Nội dung mỗi trang được lưu lại riêng biệt** |
| **Bước 4** | AI phân tích & phân loại | Trí tuệ nhân tạo Google Gemini đọc các bản chép nội dung ở Bước 3 và nhặt ra: địa chỉ, SĐT, email, fax, website, người đại diện. **Kết quả được ghi rõ nguồn gốc** (thông tin này lấy từ masothue, thông tin kia lấy từ website chính chủ...) |
| **Bước 5** | Xuất báo cáo | Toàn bộ kết quả được ghi vào file Excel. Mỗi công ty hiển thị **tất cả thông tin thu thập được từ mọi nguồn**, phân loại rõ ràng để người xem dễ nắm bắt |

---

## II. 9 TRANG WEB MỤC TIÊU

| STT | Trang web | Thông tin chính | Phân loại |
|-----|-----------|----------------|-----------|
| 1 | **masothue.com** | Mã số thuế, địa chỉ pháp lý, người đại diện | 🟢 Nguồn chính |
| 2 | **yellowpages.vn** | Danh bạ doanh nghiệp, SĐT, địa chỉ | 🟢 Nguồn chính |
| 3 | **thuvienphapluat.vn** | Thông tin pháp lý, giấy phép | 🟢 Nguồn chính |
| 4 | **hosocongty.vn** | Hồ sơ doanh nghiệp tổng hợp | 🟢 Nguồn chính |
| 5 | **vietnamworks.com** | Địa chỉ VP, SĐT HR, email tuyển dụng | 🟢 Nguồn chính |
| 6 | **topcv.vn** | Tương tự VietnamWorks | 🟢 Nguồn chính |
| 7 | **vietcareer.vn** | Tương tự VietnamWorks | 🟢 Nguồn chính |
| 8 | **facebook.com** | Fanpage: SĐT, địa chỉ, email | 🟡 Nguồn bổ sung (*) |
| 9 | **linkedin.com** | Quy mô, trụ sở, website | 🟡 Nguồn bổ sung (*) |
| +1 | **Website chính chủ** (nếu có) | Trang "Liên hệ" / "About us" của chính công ty đó | 🟢 Nguồn chính |

> **(*) Lưu ý đặc biệt về Facebook & LinkedIn:**  
> Phần lớn các trang công ty trên Facebook và LinkedIn đều ở chế độ **không công khai**. Chỉ một số ít công ty công khai đầy đủ thông tin trên các nền tảng này. Do đó, việc thu thập từ Facebook/LinkedIn được xác định là bước **"chống sót"** (thu thập bổ sung), **KHÔNG phải chức năng cốt lõi** của hệ thống. Hệ thống sẽ cố gắng lấy nếu có thể, nhưng nếu không lấy được cũng không ảnh hưởng đến kết quả chung.

---

## III. KẾ HOẠCH TRIỂN KHAI

> **Ghi chú:** Mỗi "ngày" tương đương 1 ngày làm việc. Thời gian đã được ước tính dư ra để tính cho khả năng phát sinh.

---

### GIAI ĐOẠN 1: NỀN TẢNG
**Thời lượng: 6 ngày**  
**💰 Chi phí Firecrawl: $0** (không sử dụng Firecrawl trong giai đoạn này)

| Ngày | Hạng mục | Mô tả công việc | Sản phẩm bàn giao |
|------|----------|------------------|--------------------|
| 1–2 | Cấu trúc dữ liệu | Thiết kế "kho chứa" dữ liệu (SQLite) để lưu trữ toàn bộ kết quả. Thiết kế các bảng: Công ty, Kết quả tìm kiếm, Kết quả thu thập, Kết quả AI phân tích. **Lưu trữ tất cả dữ liệu thô sau mỗi bước** để tránh lãng phí tài nguyên thông tin — nếu cần phân tích lại sẽ không phải trả phí Firecrawl lần nữa | Cơ sở dữ liệu sẵn sàng, có khả năng lưu dữ liệu thô ở mọi giai đoạn |
| 3–4 | Đọc/ghi Excel | Xây module đọc danh sách công ty từ file Excel đầu vào và module ghi kết quả ra file Excel đầu ra | Có thể đọc file Excel 6.000+ dòng và ghi file kết quả |
| 5–6 | Hệ thống ghi nhật ký (Log) | Xây hệ thống nhật ký chi tiết, tuân theo format chuẩn để **AI có thể đọc hiểu và thao tác dữ liệu log** (xem mục IV). Ghi lại: thời gian xử lý từng bước, trạng thái, credit tiêu thụ, lỗi phát sinh. Xuất log ra file Excel / CSV để báo cáo | Mỗi lần chạy đều có báo cáo nhật ký chi tiết, có thể dùng AI để phân tích log |

---

### GIAI ĐOẠN 2: THỬ NGHIỆM TÌM KIẾM & THU THẬP — Test 10 công ty
**Thời lượng: 8 ngày**  
**💰 Chi phí Firecrawl: ~50 credits — Sử dụng gói Free (không tốn tiền)**

> **Cách tính:** 10 công ty × (2đ Search + ~3 trang khớp × 1đ Scrape) = 10 × 5 = **~50 credits**  
> *(Giả định trung bình mỗi công ty có ~3 link trong 10 kết quả trùng với 9 trang mục tiêu hoặc website chính chủ)*  
> Tài khoản miễn phí hiện có **525 credits** → Đủ dùng, còn dư ~475 credits cho giai đoạn 3.

| Ngày | Hạng mục | Mô tả công việc | Sản phẩm bàn giao |
|------|----------|------------------|--------------------|
| 7–8 | Module tìm kiếm (Search) | Xây module tự động gõ Google qua Firecrawl. Mỗi công ty lấy 10 kết quả. **Lưu toàn bộ 10 link + tiêu đề + đoạn mô tả ngắn (snippet) vào kho dữ liệu ngay lập tức** — dữ liệu này có giá trị và không nên bỏ phí. ⚠️ **Xem thêm: Chiến lược Tìm kiếm Song ngữ bên dưới** | Chạy thử 10 công ty, mỗi công ty có 10 link đã lưu |

> ### ⚠️ LƯU Ý ĐẶC BIỆT: CHIẾN LƯỢC TÌM KIẾM SONG NGỮ (Bilingual Search)
>
> **Vấn đề:** Danh sách đầu vào chỉ có tên công ty bằng **tiếng Anh** (VD: *ABC Software Solutions Co., Ltd*). Nhưng nhiều trang danh bạ nội địa Việt Nam (masothue.com, thuvienphapluat.vn, hosocongty.vn...) chỉ lưu tên pháp lý bằng **tiếng Việt** (VD: *Công ty TNHH Giải Pháp Phần Mềm ABC*). Nếu chỉ tìm kiếm bằng tên tiếng Anh → **bỏ sót rất nhiều kết quả từ các nguồn quan trọng nhất**.
>
> **Giải pháp kết hợp (được áp dụng trong Module Search):**
>
> **① Từ khóa mỏ neo (Anchor Keywords)** — Không tốn thêm chi phí:
> - Thay vì search đơn giản: `"ABC Software Solutions"`
> - Search nâng cao: `"ABC Software Solutions" AND ("mã số thuế" OR "công ty TNHH" OR "công ty cổ phần")`
> - Hiệu quả: ép Google trả về kết quả từ các trang danh bạ nội địa Việt Nam
>
> **② Khai thác Mã số thuế (nếu có)** — Độ chính xác 100%:
> - Nếu dòng Excel có cột mã số thuế → **ưu tiên dùng MST để tìm kiếm trước**, bỏ qua tên.
> - MST là duy nhất, không phụ thuộc ngôn ngữ, không sợ trùng tên.
>
> **③ AI dịch tên (bổ sung cho trường hợp khó):**
> - Dùng Gemini AI (miễn phí) dịch tên tiếng Anh thành dạng tên pháp lý tiếng Việt trước khi search.
> - VD: AI tự biết `Joint Stock Company` = `Công ty Cổ phần`, `Company Limited` = `Công ty TNHH`.
> - Search 2 lần: 1 lần bằng tên gốc tiếng Anh + 1 lần bằng tên tiếng Việt do AI suy luận.
| 9–10 | Bộ lọc link thông minh | Xây bộ lọc: so sánh 10 link với 9 trang web mục tiêu. Đánh dấu link nào cần thu thập. Tự nhận diện website chính chủ của công ty | Mỗi công ty có danh sách "link đáng thu thập" |
| 11–12 | Module thu thập (Scrape) | Xây module tự vào từng link đã lọc, lấy nội dung chữ sạch (Markdown). **Lưu toàn bộ nội dung văn bản vào kho dữ liệu** — đây là tài sản thông tin, sau này có thể phân tích lại bằng AI khác mà không tốn credit Firecrawl | Mỗi công ty có 2–5 file văn bản nội dung đã lưu |
| 13–14 | Chạy thử Kịch bản A | Chạy pipeline Search → Lọc → Scrape cho **10 công ty mẫu**. Kiểm tra kết quả. Đo thời gian & credit tiêu thụ | Báo cáo thử nghiệm Kịch bản A (10 công ty) |

---

### GIAI ĐOẠN 3: TÍCH HỢP TRÍ TUỆ NHÂN TẠO (AI) — Test 10 công ty
**Thời lượng: 8 ngày**  
**💰 Chi phí Firecrawl: ~50 credits — Sử dụng gói Free (không tốn tiền)**  
**💰 Chi phí Gemini AI: ~$0** (nằm trong gói miễn phí của Google AI Studio)

> **Cách tính Firecrawl:** Tương tự GĐ2, test 10 công ty mới × 5đ = ~50 credits.  
> Tổng tích lũy GĐ2 + GĐ3: ~100 credits / 525 credits miễn phí → **Vẫn đủ dùng, còn dư ~425 credits.**  
> **Gemini AI:** 10 công ty × ~3 trang/cty = 30 lần gọi AI, mỗi lần xử lý ~2.000 từ. Tổng ~60.000 từ — nằm hoàn toàn trong giới hạn miễn phí của Google (1.500 lần gọi/ngày).

| Ngày | Hạng mục | Mô tả công việc | Sản phẩm bàn giao |
|------|----------|------------------|--------------------|
| 15–16 | Module AI Gemini | Xây module gửi văn bản thu thập được cho Google Gemini 2.5 Flash. AI đọc và trả về: địa chỉ, SĐT, email, website, người đại diện, fax. **Ghi rõ nguồn gốc từng thông tin** (lấy từ trang nào) | AI trích xuất chính xác thông tin kèm nguồn dữ liệu |
| 17–18 | Module xuất kết quả | Xây module tổng hợp kết quả từ tất cả nguồn. **Không lọc bỏ thông tin trùng lặp** — trình bày toàn bộ dữ liệu thu thập được cho mỗi công ty, phân loại rõ ràng theo nguồn để người xem tự đánh giá | Mỗi công ty hiển thị đầy đủ thông tin từ mọi nguồn |
| 19–20 | Chạy thử Kịch bản B | Chạy pipeline hoàn chỉnh Search → Lọc → Scrape → AI Extract cho **10 công ty mẫu**. Đối chiếu kết quả AI vs thực tế bằng tay | Báo cáo thử nghiệm Kịch bản B (10 công ty) |
| 21–22 | Đánh giá & tinh chỉnh | So sánh Kịch bản A và B. Tinh chỉnh câu lệnh AI (prompt) để tăng độ chính xác cho tên tiếng Việt, địa chỉ Việt Nam | Báo cáo đánh giá, chốt kịch bản chính thức |

---

### GIAI ĐOẠN 4: VẬN HÀNH CHÍNH THỨC
**Thời lượng: 10 ngày**

| Ngày | Hạng mục | Mô tả công việc | 💰 Chi phí Firecrawl | Sản phẩm bàn giao |
|------|----------|------------------|---------------------|--------------------|
| 23–24 | Hệ thống chạy lại (Resume) | Xây chức năng tự động tiếp tục từ điểm dừng nếu bị gián đoạn. Đảm bảo không mất dữ liệu | $0 (không cào thêm) | Hệ thống ổn định cho chạy dài |
| 25–26 | Tối ưu tốc độ | Điều chỉnh tốc độ cào để tránh bị chặn. Tối ưu xử lý song song để tăng tốc | $0 (không cào thêm) | Hệ thống chạy ổn định ở tốc độ tối ưu |
| 27–28 | Chạy thử **100 công ty** | Chạy hệ thống cho 100 công ty. Kiểm tra kết quả, sửa lỗi | **~500 credits** → Dùng hết Free credits, cần nâng lên **gói Hobby ($19/tháng)** | Báo cáo 100 công ty |
| 29–30 | Chạy batch **1.000 công ty** | Chạy lô đầu tiên 1.000 công ty. Giám sát liên tục | **~5.000 credits** → Gói Hobby (3.000đ/tháng) không đủ, cần nâng lên **gói Standard ($99/tháng)** | File Excel kết quả 1.000 công ty |
| 31–32 | Chạy toàn bộ **6.000+ công ty** | Chạy toàn bộ danh sách còn lại. Xuất file Excel cuối cùng | **~30.000 credits** → Nằm trong gói Standard (100.000đ/tháng), **không tốn thêm** | **File Excel kết quả 6.000+ công ty** |

### Tại sao phải chia số lượng test tăng dần (10 → 100 → 1.000 → 6.000)?

Việc tăng dần quy mô thử nghiệm là nguyên tắc bắt buộc trong các dự án tự động hóa, vì 3 lý do:

**1. Bảo vệ ngân sách (Kiểm soát chi phí)**

Nếu hệ thống có lỗi (ví dụ: cào nhầm trang web rác thay vì trang chính thức), việc chạy ngay 6.000 công ty sẽ tiêu hao toàn bộ credit chỉ trong vài giờ mà thu về dữ liệu rác. Chạy thử 10–100 công ty trước giúp đo lường chính xác chi phí thực tế trước khi xử lý lượng lớn.

**2. Phát hiện các trường hợp đặc biệt (Edge Cases)**

- **Mức 10 công ty:** Kiểm tra hệ thống có chạy đúng quy trình cơ bản không — tìm kiếm có trả kết quả, thu thập có lưu dữ liệu, AI có đọc đúng không.
- **Mức 100 công ty:** Các trường hợp "ngoài dự kiến" bắt đầu xuất hiện — công ty trùng tên, công ty chỉ có Fanpage Facebook chứ không có website, mã số thuế bị sai, trang web bảo trì... Ta quan sát để tinh chỉnh hệ thống.
- **Mức 1.000 công ty:** Phát hiện lỗi chỉ xảy ra khi chạy khối lượng lớn (ví dụ: trang web chặn IP do truy cập quá nhiều, bộ nhớ máy tính bị đầy).

**3. Kiểm tra khả năng chịu tải và phục hồi**

Khi chạy liên tục hàng ngàn lượt truy cập, các trang web mục tiêu (như masothue) hoặc Google sẽ nghi ngờ là robot tấn công và bắt đầu chặn. Chạy ở mức 1.000 công ty giúp hệ thống tìm ra tốc độ tối ưu (đủ nhanh để hoàn thành nhưng đủ chậm để không bị chặn). Đồng thời kiểm tra chức năng "lưu điểm dừng" — nếu bị gián đoạn ở công ty số 850, hệ thống có tự tiếp tục từ công ty 851 hay phải chạy lại từ đầu.

**Tóm lại:** Sai ở quy mô nhỏ → sửa nhanh, tốn ít tiền. Sai ở quy mô 6.000 → mất nhiều ngày và nhiều tiền để khắc phục.

---

## IV. HỆ THỐNG GHI NHẬT KÝ (LOG)

Hệ thống nhật ký được thiết kế theo 2 nguyên tắc:
1. **Chi tiết & chuẩn hóa** — Format nhất quán để AI có thể đọc hiểu và thao tác dữ liệu log (lọc, thống kê, phân tích xu hướng).
2. **Bảo toàn dữ liệu thô** — Toàn bộ dữ liệu thu thập ở mỗi bước (link tìm kiếm, nội dung trang web, kết quả AI) đều được lưu trữ vĩnh viễn trong cơ sở dữ liệu, tránh lãng phí tài nguyên — nếu cần phân tích lại sẽ không phải trả phí Firecrawl lần nữa.

### Nhật ký theo từng công ty (Log chi tiết)

| Cột | Nội dung | Ví dụ |
|-----|----------|-------|
| company_id | Mã công ty (tự động tạo) | CMP-0001 |
| company_name | Tên công ty từ danh sách | Công ty TNHH ABC |
| step | Bước đang thực hiện | search / filter / scrape / ai_extract |
| started_at | Thời gian bắt đầu (chính xác đến giây) | 2026-04-20 09:15:23 |
| finished_at | Thời gian kết thúc | 2026-04-20 09:15:45 |
| duration_seconds | Thời lượng (giây) | 22 |
| source_url | Đường link đang xử lý | https://masothue.com/... |
| source_name | Tên nguồn dữ liệu | masothue / topcv / website_chính_chủ |
| credits_used | Số credit Firecrawl tiêu thụ | 3 |
| status | Trạng thái | success / partial / failed / skipped |
| error_message | Thông tin lỗi (nếu có) | Timeout after 30s |
| data_saved | Dữ liệu thô đã lưu chưa | true / false |

### Nhật ký tổng hợp 

| Chỉ số | Ý nghĩa |
|--------|---------|
| Tổng công ty đã xử lý hôm nay | Tiến độ trong ngày |
| Tổng công ty đã xử lý tích lũy | Tiến độ tổng thể (ví dụ: 2.340 / 6.000 = 39%) |
| Tỷ lệ thành công | Bao nhiêu % công ty tìm được thông tin (ví dụ: 78%) |
| Thời gian trung bình / công ty | Ước tính thời gian còn lại (ví dụ: 25 giây/công ty) |
| Tổng credit đã dùng / còn lại | Kiểm soát ngân sách |
| Phân bổ nguồn dữ liệu | Bao nhiêu % thông tin đến từ masothue, bao nhiêu từ topcv, v.v. |
| Top 5 lỗi thường gặp | Ưu tiên khắc phục |

---

## V. KẾT QUẢ ĐẦU RA — MẪU FILE EXCEL

### Nguyên tắc trình bày
- **Hiển thị TẤT CẢ thông tin** thu thập được từ mọi nguồn, không lọc bỏ trùng lặp.
- **Phân loại rõ ràng theo nguồn** — người xem biết ngay thông tin nào đến từ đâu.
- Mỗi công ty chiếm **1 dòng**, các nguồn dữ liệu khác nhau được phân biệt bằng **tiền tố nguồn** trong từng cột.

### Cấu trúc file Excel

| STT | Tên công ty | Mã số thuế | Nguồn | Địa chỉ | SĐT | Email | Website | Fax | Người đại diện | Ngày thu thập |
|-----|------------|------------|-------|---------|-----|-------|---------|-----|----------------|---------------|
| 1 | Công ty A | 0123456789 | **masothue** | 123 Nguyễn Huệ, Q1, HCM | — | — | — | — | Nguyễn Văn A | 01/05/2026 |
| 1 | Công ty A | — | **website** | 123 Nguyễn Huệ, Q1, TP.HCM | 028-1234-5678 | info@a.com | www.a.com | 028-1234-0000 | — | 01/05/2026 |
| 1 | Công ty A | — | **topcv** | Quận 1, HCM | 0901-234-567 | hr@a.com | — | — | — | 01/05/2026 |
| 2 | Công ty B | — | **yellowpages** | 45 Lý Thường Kiệt, HN | 024-9876-5432 | — | — | — | — | 01/05/2026 |
| 2 | Công ty B | — | **facebook** | Hà Nội | 024-9876-5432 | contact@b.com | fb.com/congtyb | — | — | 01/05/2026 |
| 3 | Công ty C | — | *(không tìm thấy)* | — | — | — | — | — | — | 01/05/2026 |

> **Cách đọc:** Công ty A có thông tin từ 3 nguồn (masothue, website chính chủ, topcv) — hiển thị trên 3 dòng riêng biệt. Người dùng có thể tự so sánh và chọn thông tin phù hợp nhất.

---

## VI. DỮ LIỆU LƯU TRỮ SAU MỖI BƯỚC

Toàn bộ dữ liệu "thô" được lưu giữ vĩnh viễn trong cơ sở dữ liệu, đảm bảo không lãng phí tài nguyên:

| Bước | Dữ liệu lưu trữ | Mục đích |
|------|-------------------|----------|
| Sau bước Search | 10 link + tiêu đề + đoạn mô tả (snippet) cho mỗi công ty | Có thể phân tích lại để tìm thêm nguồn mới mà không cần search lại (không tốn thêm credit) |
| Sau bước Filter | Danh sách link đã phân loại (thuộc trang nào, có phải website chính chủ không) | Kiểm tra lại logic lọc link, tinh chỉnh bộ lọc |
| Sau bước Scrape | Toàn bộ văn bản Markdown của mỗi trang web đã thu thập | **Tài sản quan trọng nhất** — có thể gửi cho AI khác phân tích lại theo hướng mới mà không tốn credit Firecrawl |
| Sau bước AI Extract | Kết quả trích xuất của AI (địa chỉ, SĐT, email...) kèm nguồn | Đối chiếu, kiểm tra độ chính xác AI, cải thiện prompt |

---

## VII. RỦI RO & BIỆN PHÁP

| Rủi ro | Mức độ | Biện pháp |
|--------|--------|-----------|
| ~20-30% công ty nhỏ không có thông tin trên mạng | Cao | Đánh dấu "Không tìm thấy", chuyển tra cứu thủ công |
| Facebook / LinkedIn chặn truy cập tự động | Trung bình | Đây chỉ là nguồn bổ sung "chống sót", không ảnh hưởng kết quả chung. Ưu tiên 7 trang chính + website chính chủ |
| Trang web mục tiêu (masothue, yellowpages) chặn truy cập do cào quá nhanh | Trung bình | Giảm tốc độ tự động, nghỉ giữa các lần truy cập. Phát hiện ở mức test 1.000 công ty |
| Gián đoạn khi chạy (mất mạng, lỗi hệ thống) | Thấp | Hệ thống tự lưu điểm dừng, chạy lại từ công ty dở dang. Dữ liệu thô đã thu thập không bị mất |
| Thông tin lỗi thời (công ty đã chuyển trụ sở) | Thấp | Ghi rõ ngày thu thập. Hiển thị thông tin từ nhiều nguồn để người dùng tự đối chiếu |
| AI đọc sai thông tin (nhầm SĐT, sai địa chỉ) | Thấp | Tinh chỉnh prompt AI ở giai đoạn thử nghiệm. Ghi rõ nguồn gốc để người dùng kiểm chứng |

---

## VIII. BẢNG GIÁ FIRECRAWL & DỰ TOÁN CHI PHÍ

### Bảng giá gói dịch vụ Firecrawl (Nguồn: [firecrawl.dev/pricing](https://www.firecrawl.dev/pricing) & [docs.firecrawl.dev/billing](https://docs.firecrawl.dev/billing))

| Gói | Giá/tháng | Credits/tháng | Số trang xử lý đồng thời |
|-----|-----------|---------------|---------------------------|
| **Free** | $0 | 500 credits *(cấp 1 lần, không gia hạn)* | 2 |
| **Hobby** | $19 | 3.000 credits | 5 |
| **Standard** | $99 | 100.000 credits | 50 |
| **Growth** | $399 | 500.000 credits | 100 |

### Chi phí mỗi thao tác Firecrawl

| Thao tác | Chi phí | Giải thích |
|----------|---------|------------|
| Search (tìm kiếm) | **2 credits** / 10 kết quả | Gõ Google lấy 10 link = 2đ |
| Scrape (thu thập) | **1 credit** / trang | Vào 1 trang web, lấy nội dung chữ = 1đ |

### Công thức tính chi phí cho 1 công ty

```
Chi phí = 2đ (Search 10 link) + Số trang khớp × 1đ (Scrape)
```

> Giả định trung bình mỗi công ty có **~3 link** trong 10 kết quả trùng với 9 trang mục tiêu hoặc website chính chủ → **~5 credits / công ty**.

### Dự toán chi phí theo từng giai đoạn

| Giai đoạn | Số công ty | Credits cần | Credits tích lũy | Gói cần mua | 💰 Chi phí phát sinh |
|-----------|-----------|-------------|-------------------|-------------|---------------------|
| GĐ1: Nền tảng | 0 | 0 | 0 | Free | **$0** |
| GĐ2: Test Search+Scrape | 10 | ~50 | ~50 | Free (còn 475đ dư) | **$0** |
| GĐ3: Test AI Extract | 10 | ~50 | ~100 | Free (còn 425đ dư) | **$0** |
| GĐ4a: Chạy 100 cty | 100 | ~500 | ~600 | ⚠️ Hết Free → Nâng **Hobby** | **$19/tháng** |
| GĐ4b: Chạy 1.000 cty | 1.000 | ~5.000 | ~5.600 | ⚠️ Hết Hobby → Nâng **Standard** | **$99/tháng** |
| GĐ4c: Chạy 6.000+ cty | 5.000+ | ~25.000+ | ~30.600 | Standard (đủ dùng) | **Đã bao gồm** |

### Chi phí Gemini AI (Google)

| Giai đoạn | Số lần gọi AI | Chi phí |
|-----------|---------------|--------|
| GĐ3: Test 10 cty | ~30 lần | **$0** (miễn phí) |
| GĐ4a: 100 cty | ~300 lần | **$0** (miễn phí — Google cho 1.500 lần/ngày) |
| GĐ4b: 1.000 cty | ~3.000 lần | **~$0.5** (rất rẻ) |
| GĐ4c: 6.000+ cty | ~18.000 lần | **~$2–5** |

### Tổng chi phí dự toán toàn dự án

| Hạng mục | Chi phí |
|----------|---------|
| GĐ1–3 (Thử nghiệm) | **$0** |
| GĐ4 Firecrawl (gói Standard) | **$99/tháng** |
| GĐ4 Gemini AI | **~$2–5** (một lần) |
| **TỔNG CỘNG** | **~$101–104** |

> **Ghi chú:** Sau khi hoàn thành 6.000 công ty, có thể hạ gói Firecrawl xuống Hobby ($19) hoặc hủy đăng ký nếu không cần cào thêm.

---

## IX. TỔNG KẾT TIMELINE & CHI PHÍ

```
GĐ1: Nền tảng          ██████                              6 ngày   💰 $0
GĐ2: Test 10 cty (S+S)       ████████                      8 ngày   💰 $0 (Free)
GĐ3: Test 10 cty (S+AI)              ████████              8 ngày   💰 $0 (Free)
GĐ4: Vận hành chính thức                     ██████████   10 ngày   💰 $99
───────────────────────────────────────────────────────────────────
                        TỔNG CỘNG:  32 ngày làm việc    💰 ~$101
```

---

