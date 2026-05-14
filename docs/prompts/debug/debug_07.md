# Debug Task 07: AI Optimizations (3)

**Model:** Gemini 3 Flash | **File:** `src/ai_extractor.py`

## Mục tiêu kiểm tra
3 tối ưu: pre-filter skip, early stop extraction, batch pages.

## Lệnh kiểm tra
```bash
# 1. Pre-filter method
grep -n "_has_contact_signals" src/ai_extractor.py

# 2. Early stop extraction
grep -n "early_stop_extraction" src/ai_extractor.py

# 3. Batch method
grep -n "_batch_short_pages" src/ai_extractor.py

# 4. JSONL events
grep -c "ai_skipped" output/logs/pipeline_*.jsonl
grep -c "early_stop_extraction" output/logs/pipeline_*.jsonl
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| ai_skipped quá nhiều | Regex quá strict | Thêm keyword patterns (liên hệ, contact) |
| ai_skipped = 0 | Regex quá loose hoặc không được gọi | Check `_has_contact_signals` được gọi trước AI |
| early_stop không trigger | Confidence threshold quá cao | Check >= 0.8 condition |
| Batch parse error | Merged markdown confuses AI | Thêm separator rõ ràng giữa pages |
| Fewer extractions overall | Pre-filter quá aggressive | Giảm threshold: 1 pattern thay vì 2 |

## Debug steps
1. Compare API call count trước/sau optimization
2. Check `ai_skipped` reasons trong JSONL
3. Verify early_stop chỉ trigger khi 3+ fields found
4. Check batch: pages < 5k chars được gộp, pages > 5k không gộp
