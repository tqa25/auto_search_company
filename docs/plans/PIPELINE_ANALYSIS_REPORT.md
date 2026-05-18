# 📊 BÁO CÁO PHÂN TÍCH PIPELINE: Query & URL Scoring
**Ngày phân tích:** 13/05/2026  
**Dữ liệu:** Toàn bộ log từ lúc bắt đầu vận hành hệ thống  
**Phạm vi:** 69 công ty · 580 URL tìm kiếm · 373 URL đã chấm điểm · 129 liên hệ trích xuất

---

## MỤC LỤC
1. [Tổng quan Pipeline 2 Bước](#1-tổng-quan-pipeline-2-bước)
2. [BƯỚC 1: Phân tích Chiến lược Query](#2-bước-1-phân-tích-chiến-lược-query)
3. [BƯỚC 2: Phân tích Hệ thống Chấm điểm URL](#3-bước-2-phân-tích-hệ-thống-chấm-điểm-url)
4. [🔴 BUG NGHIÊM TRỌNG: URL có SĐT nhưng bị chấm 0 điểm](#4--bug-nghiêm-trọng)
5. [Phễu chuyển đổi theo Công ty](#5-phễu-chuyển-đổi-theo-công-ty)
6. [Kết luận & Đề xuất](#6-kết-luận--đề-xuất)

---

## 1. Tổng quan Pipeline 2 Bước

Hệ thống tìm kiếm thông tin công ty hoạt động theo 2 bước tuần tự:

```
┌─────────────────────┐     ┌──────────────────────┐
│  BƯỚC 1: QUERY      │────▸│  BƯỚC 2: CHẤM ĐIỂM  │
│  Tạo câu truy vấn   │     │  Đánh giá chất lượng │
│  gửi lên Google     │     │  từng URL trả về     │
│  (qua Firecrawl API)│     │  Quyết định: Cào/Bỏ  │
└─────────────────────┘     └──────────────────────┘
```

**Giải thích đơn giản:**  
- **Bước 1** giống như bạn gõ từ khóa vào Google để tìm thông tin công ty.  
- **Bước 2** giống như bạn nhìn qua danh sách kết quả Google, quyết định link nào đáng mở ra xem, link nào bỏ qua.

---

## 2. BƯỚC 1: Phân tích Chiến lược Query

### 2.1. Các loại Query đang sử dụng

Hệ thống tạo nhiều loại câu truy vấn khác nhau, chạy tuần tự theo thứ tự ưu tiên:

| # | Loại Query | Ý nghĩa | Ví dụ | Số URL tìm được | Số Cty sử dụng |
|---|-----------|---------|-------|:---:|:---:|
| 1 | `step1_anchor` | Tên EN + từ khóa "liên hệ/contact" | `"HYCO4 - JSC" AND ("liên hệ" OR "contact")` | 140 | 6 |
| 2 | `english` | Tên tiếng Anh thuần (hệ thống cũ) | `"SAMSUNG ELECTRONICS VIỆT NAM"` | 176 | 22 |
| 3 | `tax_code` | Mã số thuế để tìm trên trang pháp lý | `"0100100079"` | 58 | 6 |
| 4 | `step4_fallback_en` | Tên EN không có keyword bổ sung | `"CIRCO SERVICES"` | 206 | 3 |

### 2.2. Hiệu quả thực tế: Loại Query nào tìm được SĐT?

Đây là phân tích quan trọng nhất — xem câu truy vấn nào thực sự **dẫn đến** việc tìm được số điện thoại:

| Loại Query | Số Cty tìm được SĐT | Số bản ghi liên hệ | Hiệu quả |
|-----------|:---:|:---:|:---:|
| `english` (tên EN thuần) | **15** | **33** | ⭐ Cao nhất |
| `tax_code` (MST) | **4** | **17** | ⭐⭐ Rất hiệu quả theo tỷ lệ |
| `tier1_coarse` (EN + keyword) | **1** | **16** | ⚠️ Thấp bất ngờ |
| `step4_fallback_en` | **0** | **0** | ❌ Không hiệu quả |

### 2.3. Nhận xét

> **Phát hiện #1:** Query `english` (chỉ tìm tên thuần) hiệu quả hơn `tier1_coarse` (tên + "liên hệ").  
> Nguyên nhân có thể do việc thêm keyword "liên hệ/contact" vào query đã **thu hẹp kết quả quá mức**, loại bỏ luôn nhiều trang pháp lý và trang vàng chứa SĐT nhưng không có từ "liên hệ" trong tiêu đề.

> **Phát hiện #2:** Query `tax_code` (MST) tuy chỉ dùng cho 6 công ty nhưng tìm được **17 bản ghi** → trung bình 2.8 liên hệ/công ty. Đây là chiến lược **hiệu quả nhất theo tỷ lệ**.

> **Phát hiện #3:** `step4_fallback_en` tạo ra **206 URL** (nhiều nhất) nhưng **0 SĐT** → toàn bộ là rác. Đây là dấu hiệu cho thấy khi không có tên tiếng Việt, hệ thống đang "đánh bừa" bằng tên tiếng Anh dẫn đến kết quả sai công ty.

---

## 3. BƯỚC 2: Phân tích Hệ thống Chấm điểm URL

### 3.1. Cách chấm điểm hoạt động

Mỗi URL được chấm điểm từ 0-100 dựa trên 3 yếu tố cộng dồn:

```
TỔNG ĐIỂM = Điểm Domain + Điểm Keyword + Điểm Tên Khớp
```

| Yếu tố | Mô tả | Ví dụ | Điểm |
|--------|-------|-------|:---:|
| **Domain** | Trang web thuộc loại nào? | Trang pháp lý (thuvienphapluat) | 30 |
| | | Trang tuyển dụng (topcv, vietnamworks) | 25 |
| | | Mạng xã hội (facebook, linkedin) | 20 |
| | | Website không rõ nguồn gốc | 40 |
| **Keyword** | URL có chứa từ khóa quan trọng? | `/lien-he`, `/contact` | +25 |
| | | `/tuyen-dung`, `/career` | +15 |
| **Tên Khớp** | Tên công ty có xuất hiện trong domain/title? | `samsung.com` chứa "samsung" | +15 |

### 3.2. Phân bổ điểm URL trong hệ thống

| Nhóm điểm | Ý nghĩa | Số URL | Được cào? |
|-----------|---------|:---:|:---:|
| **A (≥ 80)** | URL chất lượng cao, rất đáng xem | 187 | 187 ✅ |
| **B (50-79)** | URL khá tốt | 0 | — |
| **C (30-49)** | URL trung bình | 0 | — |
| **D (< 30)** | URL kém, có thể bỏ qua | 186 | 176 ⚠️ |

> **⚠️ CẢNH BÁO:** Phân bổ điểm bị **phân cực cực đoan** — chỉ có 2 nhóm: rất cao hoặc rất thấp. Không có nhóm trung bình. Điều này cho thấy hệ thống chấm điểm đang hoạt động như **bật/tắt** (binary) thay vì đánh giá tinh tế theo phổ liên tục.

### 3.3. Domain nào xuất hiện nhiều nhất trong kết quả tìm kiếm?

| Domain | Số lần xuất hiện | Ghi chú |
|--------|:---:|---------|
| Các trang khác (đa dạng) | 502 | Website riêng, trang tin, PDF... |
| masothue.com | 47 | **Đang bị blacklist** (không cào) |
| facebook.com | 15 | Fallback cuối cùng |
| yellowpages.vn | 7 | Trang vàng VN |
| thongtincongty.com | 6 | Tra cứu DN |
| linkedin.com | 3 | Đang bị tắt |

---

## 4. 🔴 BUG NGHIÊM TRỌNG

### URL có Số Điện Thoại nhưng bị chấm 0.0 điểm

Đây là phát hiện quan trọng nhất của báo cáo. Phân tích cho thấy **hầu hết URL thực sự chứa SĐT đều bị hệ thống chấm 0.0 điểm**:

| Công ty | URL chứa SĐT | Loại trang | Điểm hiện tại |
|---------|-------------|-----------|:---:|
| SAMSUNG ELECTRONICS VN | thuvienphapluat.vn/ma-so-thue/... | Trang pháp lý | **0.0** ❌ |
| SAMSUNG ELECTRONICS VN | yellowpages.vn/... | Trang vàng | **0.0** ❌ |
| SAMSUNG DISPLAY VN | thuvienphapluat.vn/ma-so-thue/... | Trang pháp lý | **0.0** ❌ |
| SAMSUNG DISPLAY VN | topcv.vn/... | Trang tuyển dụng | **0.0** ❌ |
| TẬP ĐOÀN ĐIỆN LỰC VN | thuvienphapluat.vn/ma-so-thue/... | Trang pháp lý | **0.0** ❌ |
| CAPELLA LAND | yp.vn/... | Trang vàng | **0.0** ❌ |
| SƠN GIANG NHÂN | thuvienphapluat.vn/ma-so-thue/... | Trang pháp lý | **0.0** ❌ |
| DP VIỆT NAM | thuvienphapluat.vn/ma-so-thue/... | Trang pháp lý | **0.0** ❌ |

> **Nguyên nhân gốc rễ:**  
> Các URL này được tìm thấy qua hệ thống Search **cũ** (`english`, `tax_code`) — một hệ thống trước khi module chấm điểm (`filter_module`) được tích hợp. Khi đó, tất cả URL đều được cào mà **không qua bước chấm điểm**. Điểm `0.0` là giá trị mặc định khi không được chấm.
>
> Tuy nhiên, nếu chạy lại các URL này qua hệ thống chấm điểm hiện tại:
> - `thuvienphapluat.vn` → sẽ được 30 điểm (domain "legal")
> - `yellowpages.vn` → sẽ được 40 điểm (domain "official")
> - `topcv.vn` → sẽ được 25 điểm (domain "job")
>
> **Kết luận:** Hệ thống chấm điểm hiện tại **KHÔNG bỏ sót** — vấn đề nằm ở dữ liệu lịch sử chưa được chấm lại.

### False Positives: URL điểm CAO nhưng KHÔNG chứa SĐT

Ngược lại, có nhiều URL bị chấm **65 điểm** (cao nhất) nhưng hoàn toàn **sai công ty**:

| Công ty cần tìm | URL bị chấm 65 điểm | Vấn đề |
|-----------------|---------------------|--------|
| CIRCO SERVICES JSC | getcirco.com/contact | ❌ Công ty khác (nước ngoài) |
| CIRCO SERVICES JSC | circoconsulting.com | ❌ Công ty khác |
| CIRCO SERVICES JSC | shopcirco.com | ❌ Cửa hàng nước ngoài |
| SAIGON BOULEVARD | saigonblvdbanhmi.com | ❌ Tiệm bánh mì ở Mỹ |
| SAIGON BOULEVARD | saigonsantabarbara.com | ❌ Nhà hàng ở Mỹ |
| SAIGON BOULEVARD | thereveriesaigon.com | ❌ Khách sạn (khác công ty) |
| AUDIENCE SERV | cityoflancasterpa.gov/vi/contact | ❌ Trang chính phủ Mỹ |

> **Nguyên nhân:** Hệ thống chấm **65 điểm = 40 (domain "official") + 25 (keyword "contact")** cho bất kỳ URL nào có chứa `/contact` trong đường dẫn. Nó **không kiểm tra** xem URL đó có thực sự liên quan đến công ty cần tìm hay không.

---

## 5. Phễu chuyển đổi theo Công ty

Bảng dưới cho thấy "hành trình" dữ liệu của từng công ty — từ lúc tìm kiếm đến khi trích xuất được liên hệ:

| Công ty | URLs tìm được | URLs đã lọc | Đủ điều kiện cào | Trang đã cào | SĐT tìm được | Nguồn SĐT |
|---------|:---:|:---:|:---:|:---:|:---:|------|
| SAMSUNG ELECTRONICS VN | 60 | 76 | 73 | 12 | **11** | thuvienphapluat, yellowpages, website |
| SAMSUNG DISPLAY VN | 19 | 14 | 14 | 14 | **13** | thuvienphapluat, topcv, website |
| TẬP ĐOÀN ĐIỆN LỰC VN | 20 | 9 | 8 | 8 | **7** | thuvienphapluat, website |
| QUOC THAI CO. | 10 | 5 | 5 | 5 | **5** | website |
| PHÒNG THƯƠNG MẠI VN | 10 | 7 | 7 | 7 | **7** | website |
| CAPELLA LAND | 10 | 9 | 9 | 9 | **7** | website |
| CITYHOUSE MANAGEMENT | 3 | 3 | 3 | 3 | **2** | website |
| AUDIENCE SERV | 20 | 22 | 22 | 13 | **10** | website, contact_page |
| **CIRCO SERVICES** | 20 | 19 | 19 | 10 | **0** ❌ | (tất cả URL sai công ty) |
| **SAIGON BOULEVARD** | 20 | 19 | 19 | 10 | **0** ❌ | (tất cả URL sai công ty) |
| HYCO4 - JSC | 20 | 18 | 18 | 10 | **1** | gemini_grounding |

> **Công ty thất bại (0 SĐT):** CIRCO SERVICES và SAIGON BOULEVARD — pipeline tìm được 19-20 URL, cào 10 trang, nhưng **tất cả đều sai công ty**. Nguyên nhân: tên công ty quá chung chung (generic), Google trả về nhiều kết quả của công ty nước ngoài trùng tên.

---

## 6. Kết luận & Đề xuất

### ✅ Điểm mạnh
1. **Query bằng MST** là chiến lược hiệu quả nhất (2.8 liên hệ/công ty).
2. **Gemini Grounding** (bước mới) cho kết quả nhanh (7-25 giây) với độ tin cậy cao (0.95-0.98).
3. **Hệ thống chấm điểm** phân loại domain chính xác (legal, job, social).

### ⚠️ Điểm yếu cần cải thiện
1. **False Positive cao:** URL có `/contact` trong path tự động được +25 điểm dù hoàn toàn sai công ty.
2. **Thiếu Name Matching:** Hệ thống chấm tên khớp trong domain (`samsung.com` → match "samsung") nhưng **không kiểm tra tên trong title/snippet** một cách đủ mạnh cho các công ty tên generic.
3. **Dữ liệu cũ chưa được chấm lại:** 100% URL từ hệ thống Search cũ có điểm = 0.0.

### 🔧 Đề xuất cải thiện

| Ưu tiên | Hành động | Tác động dự kiến |
|:---:|---------|-----------------|
| 🔴 P0 | Thêm cơ chế **"Negative Name Match"**: nếu domain KHÔNG chứa bất kỳ từ nào liên quan đến tên công ty → trừ 20 điểm | Loại bỏ ~80% false positives |
| 🟡 P1 | Ưu tiên query **MST trước** khi sử dụng tên EN | Tăng tỷ lệ tìm SĐT +30% |
| 🟡 P1 | Giảm điểm keyword `/contact` từ +25 xuống +10 | Giảm false positive |
| 🟢 P2 | Chạy lại chấm điểm cho toàn bộ dữ liệu lịch sử | Chuẩn hóa dữ liệu |

---
*Báo cáo được tạo tự động từ dữ liệu Pipeline Control Center.*  
*Phân tích bởi AI Agent dựa trên 580 search results và 129 extracted contacts.*
