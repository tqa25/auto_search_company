# Debug Task 02: AI Company Name in Prompt

**Model:** Gemini 3 Flash | **File:** `src/ai_extractor.py`

## Mục tiêu kiểm tra
Verify prompt gửi cho Gemini AI có chứa tên công ty target.

## Lệnh kiểm tra
```bash
# 1. Check placeholder trong template
grep -n "company_name" src/ai_extractor.py

# 2. Check instruction "CHỈ trích xuất"
grep -n "CHỈ trích xuất" src/ai_extractor.py

# 3. Check company lookup trong extract_from_page
grep -A3 "get_company\|original_name" src/ai_extractor.py
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `{company_name}` not replaced | Quên `.replace()` hoặc `.format()` | Check dòng tạo prompt |
| `KeyError: original_name` | Company record không có field đó | Dùng `.get("original_name", "")` |
| Prompt quá dài | Company name + markdown vượt limit | Không ảnh hưởng — prompt chỉ thêm ~50 chars |

## Debug steps
1. Thêm `print(prompt[:200])` tạm vào `extract_from_page()` → verify company name xuất hiện
2. Check JSONL log xem AI response có chính xác hơn không (so sánh trước/sau)
