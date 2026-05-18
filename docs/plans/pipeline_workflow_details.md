# Tài Liệu Chi Tiết Quy Trình Hoạt Động (System Workflow Details)

Hệ thống **Auto Search Company** được thiết kế theo kiến trúc **Sequential Fallback** (Dự phòng tuần tự) và **Early Stop** (Dừng sớm thông minh). Mục tiêu là tối đa hoá tỷ lệ tìm thấy thông tin liên hệ (đặc biệt là Số điện thoại) với chi phí API thấp nhất.

Quy trình bao gồm 5 bước cốt lõi, bám sát vào cấu trúc vận hành ổn định và hiệu quả nhất (đã được kiểm chứng qua đợt test 13 công ty).

---

## 1. Bước 1: Khởi tạo dữ liệu (Input & Initialization)

**Nhiệm vụ:** Đưa danh sách công ty thô vào hệ thống và khởi tạo quy trình theo dõi.

*   **Input:** File Excel do người dùng tải lên chứa danh sách tên công ty tiếng Anh hoặc tiếng Việt.
*   **Process:**
    *   Hệ thống đọc file và đẩy vào cơ sở dữ liệu (SQLite `companies`).
    *   Trạng thái ban đầu: `status = 'pending'`.
    *   **Cơ chế Resumable**: Nếu hệ thống bị tắt đột ngột, lần chạy sau sẽ tiếp tục từ công ty đang bị dở dang thay vì chạy lại từ đầu.
*   **Output:** Hàng đợi các công ty chờ xử lý trong DB.

---

## 2. Bước 2: Khảo sát nhanh (AI Quick Search / Grounding)

**Nhiệm vụ:** Dùng AI gọi công cụ tìm kiếm thực tế để "chốt nhanh" các công ty dễ tìm.

*   **Input:** Tên công ty thô.
*   **Process:**
    *   Gửi prompt cho mô hình AI (hỗ trợ Search Grounding) để thực hiện search Google theo thời gian thực.
    *   AI đọc các đoạn trích dẫn (snippet) để suy luận và trả về định dạng JSON gồm: `core_name_vi` (Tên pháp lý), `tax_code` (Mã số thuế), `phone`, `address`, `website` và `confidence` (độ tin cậy).
    *   **Early Stop:** Nếu có Số điện thoại và `confidence` đủ cao, hệ thống chốt công ty này thành `done` và bỏ qua các bước sau.
*   **Output:** 
    *   *Thành công:* Lưu liên hệ vào DB. Chuyển sang công ty tiếp theo.
    *   *Thất bại (Thiếu dữ liệu):* Cập nhật Tên tiếng Việt và Mã số thuế vào DB làm "vốn" cho các bước sau.

---

## 3. Bước 3: Tìm kiếm Địa điểm (Google Maps via Serper)

**Nhiệm vụ:** Tra cứu thông tin trên bản đồ. Dữ liệu trên Maps thường do chính chủ doanh nghiệp cung cấp nên độ tin cậy cực cao.

*   **Input:** Tên công ty (ưu tiên Tên pháp lý tiếng Việt lấy từ Bước 2).
*   **Process:**
    *   Gọi API Serper Places (Google Maps).
    *   Phân tích kết quả trả về để tìm `phoneNumber`, `address`, `website`.
    *   **Early Stop:** Nếu tìm thấy `phoneNumber`, chốt kết quả và kết thúc công ty này.
    *   **Tận dụng tối đa:** Nếu Maps *không* có số điện thoại nhưng *có Website*, hệ thống lập tức lưu Website này vào hàng đợi cạo dữ liệu (`should_scrape = 1`) với điểm ưu tiên rất cao.
*   **Output:**
    *   *Thành công:* Số điện thoại lưu vào DB.
    *   *Thất bại:* Chuyển sang Bước 4 (mang theo URL Website từ Maps nếu có).

---

## 4. Bước 4: Tìm kiếm Chuyên sâu (Deep Search - 4-Step Strategy)

**Nhiệm vụ:** Đây là chiến thuật cốt lõi (Module `SearchModule`). Thay vì search mù quáng, hệ thống đi qua 4 công đoạn tinh vi để thu thập URL, ưu tiên tiết kiệm API credit.

### 4.1. Contact Query (Tìm kiếm liên hệ)
*   **Query:** `("{Tên tiếng Anh}" OR "{Tên tiếng Việt}") AND ("liên hệ" OR "contact")`
*   **Mục tiêu:** Bắn thẳng vào các trang có khả năng chứa số điện thoại nhất.
*   *Early Stop check:* Đánh giá ngay các URL tìm được. Nếu đủ link xịn, dừng luôn để tiết kiệm credit.

### 4.2. Infer VN Data (Suy luận dữ liệu pháp lý)
*   *Chỉ chạy nếu Bước 2 chưa tìm ra Mã số thuế hoặc Tên tiếng Việt.*
*   **Process:** Hệ thống lướt qua các URL vừa tìm được ở 4.1. Lọc ra các trang thuộc đuôi uy tín (`.gov.vn`, `masothue`, v.v.). Đọc nội dung snippet (hoặc cạo thử 1-2 trang) để dùng Regex ép lấy bằng được Tên pháp lý chuẩn và Mã số thuế.

### 4.3. Tax Code Query (Tìm bằng Mã số thuế)
*   *Chỉ chạy nếu đã có Mã số thuế.*
*   **Query:** `"{Mã số thuế}"`
*   **Mục tiêu:** Mã số thuế là định danh duy nhất. Search MST sẽ lòi ra các danh bạ doanh nghiệp uy tín nhất.
*   *Early Stop check:* Đánh giá URL, nếu đủ link xịn, dừng tìm kiếm.

### 4.4. Bare Query (Tìm kiếm rộng)
*   **Query:** `"{Tên tiếng Anh}" OR "{Tên tiếng Việt}"`
*   **Mục tiêu:** Bước vét máng cuối cùng nếu các bước trên chưa tìm đủ URL.

**Đầu ra của Bước 4:** Một tập hợp các URL chất lượng cao, đã được loại bỏ trùng lặp (dedup) và chấm điểm (`score`), sẵn sàng để cạo.

---

## 5. Bước 5: Cạo dữ liệu & Trích xuất AI (Scrape + Extract)

**Nhiệm vụ:** Vào sâu bên trong các URL đã lọc để "bắt" liên hệ.

### 5.1. Firecrawl Scrape
*   **Process:** Gọi Firecrawl API để cào nội dung HTML của các URL đạt chuẩn, chuyển hóa chúng thành văn bản Markdown sạch sẽ.

### 5.2. AI Extractor
*   **Process:** 
    *   Quét sơ bộ (Regex): Nếu văn bản không có cụm số nào giống SĐT, vứt bỏ ngay lập tức để tiết kiệm tiền AI.
    *   Nếu có tín hiệu khả quan, đẩy vào AI để yêu cầu trích xuất JSON: `phone`, `email`, `address`, `representative`.
    *   **Xử lý xung đột:** Nếu tìm được nhiều số điện thoại từ các trang web khác nhau, hệ thống tự động so sánh điểm `confidence` (độ tin cậy) do AI đánh giá và giữ lại số điện thoại có điểm cao nhất.
*   **Output:** Chốt hạ kết quả, đổi `status = 'done'` và xuất Excel báo cáo (bao gồm cả sheet chi tiết tracking đường đi của dữ liệu).
