
## 🚀 Phương án Khuyến nghị

### Bước 1: Query “rẻ” trước (Coarse Search)
Chạy 1 query kiểu PA1 nhưng được tinh lọc để lấy top 5–10 URL:
`("company_en" OR "company_vi") AND ("liên hệ" OR "contact" OR "email" OR "phone") 

### Bước 2: URL Filtering (Cực kỳ quan trọng)
Chỉ giữ lại các URL có dấu hiệu uy tín:
- Chứa slug: `/lien-he`, `/contact`, `/contact-us`, `/about`.
- Thuộc **Domain chính thức** (trùng hoặc chứa tên công ty).

### Bước 3: Fallback thông minh
Chỉ chạy PA2 (Multi-query) khi:
- Không tìm được URL hợp lệ ở Bước 1.
- Nội dung crawl từ Bước 1 không trích xuất được Email/Số điện thoại.
*Giúp giảm ~60–70% số lượng query so với việc chạy brute-force ngay từ đầu.*


## ⚡ Bonus: Tối ưu nâng cao

1.  **Sử dụng Pattern thay vì Keyword:**
    Dùng `inurl:contact OR inurl:lien-he` để tăng mạnh độ chính xác.
2.  **Ưu tiên Domain nội địa:**
    Thêm toán tử `site:.vn` nếu đối tượng là doanh nghiệp Việt Nam.
3.  **Chiến thuật Detect Domain trước:**
    - **Nhánh A:** Tìm website chính thức của công ty.
    - **Nhánh B:** Sau khi có website, chỉ crawl trực tiếp các trang con (`/contact`, `/about`) thay vì search dạo.
