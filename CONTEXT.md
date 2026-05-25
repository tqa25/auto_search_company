# Glossary

- **Export Record**: Một dòng (row) trong file CSV xuất ra. Đại diện cho một "Search Result URL" (tất cả các URL trả về từ Firecrawl /search hoặc các URL mà Gemini tham khảo qua Search Grounding), bất kể URL đó có trích xuất được thông tin liên hệ thành công hay không. Một công ty sẽ có số dòng bằng với tổng số URL tìm được.
- **Data Scope**: Mức độ tham chiếu của dữ liệu liên hệ trên một dòng URL. Có 2 giá trị:
  - `Company-Level`: Dữ liệu (phone, email...) là thông tin chung của công ty (thường lấy từ Gemini Quick Search), được lặp lại trên tất cả các URL tham khảo vì không xác định được đích xác URL nào chứa thông tin nào.
  - `URL-Level`: Dữ liệu được trích xuất chính xác từ nội dung (scrape) của chính URL đó.
