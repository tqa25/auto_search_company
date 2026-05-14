# Task 02: AI Prompt — Thêm Company Name

**Model:** Gemini 3.1 Pro
**File:** `src/ai_extractor.py`
**Phụ thuộc:** Không

## Bối cảnh
`EXTRACTION_PROMPT_TEMPLATE` gửi markdown content cho Gemini AI nhưng **không kèm tên công ty**. AI có thể trích xuất nhầm thông tin liên hệ của website hosting, nhà tuyển dụng, hoặc công ty khác trên cùng trang.

## Thay đổi

### 1. Cập nhật `EXTRACTION_PROMPT_TEMPLATE`
Thêm 2 dòng vào đầu prompt:
```
Bạn đang trích xuất thông tin liên hệ của công ty: {company_name}
CHỈ trích xuất thông tin của công ty trên, KHÔNG lấy thông tin của các công ty khác được đề cập trên trang.
```

### 2. Cập nhật `extract_from_page()`
- Truy vấn `company_name` từ DB: `self.db.get_company(company_id)['original_name']`
- Thay `{company_name}` trong prompt trước khi gửi AI
- Lưu ý: hiện tại hàm đã có `company_id`, chỉ cần thêm lookup tên

## Input/Output
- **Input:** Không thay đổi — `extract_from_page(scraped_page_id: int)`
- **Output:** Không thay đổi — cùng JSON schema
- **Side effect:** AI sẽ chính xác hơn khi biết tên công ty target

## Tiêu chí hoàn thành
- [ ] Prompt template có placeholder `{company_name}`
- [ ] `extract_from_page()` lookup company name và inject vào prompt
- [ ] Instruction "CHỈ trích xuất" có trong prompt gửi đi
- [ ] Không thay đổi output JSON schema
