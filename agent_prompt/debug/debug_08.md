# Debug Task 08: Confidence Threshold

**Model:** Gemini 3 Flash | **Files:** `src/ai_extractor.py`, `src/config.py`

## Mục tiêu kiểm tra
Low confidence extractions được log, conflict resolution chọn source tốt nhất.

## Lệnh kiểm tra
```bash
# 1. Config
grep -n "MIN_CONFIDENCE_THRESHOLD" src/config.py

# 2. Low confidence log
grep "low_confidence" output/logs/pipeline_*.jsonl | head -3

# 3. Conflict resolution log
grep "contact_conflict_resolved" output/logs/pipeline_*.jsonl | head -3
```

## Lỗi thường gặp
| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Không có low_confidence events | Threshold quá thấp hoặc check không chạy | Verify threshold đúng 0.3 |
| Conflict resolution không log | Logic chưa implement trong extract_for_company | Thêm comparison loop |
| Tất cả bị filter | Threshold quá cao | Giảm MIN_CONFIDENCE_THRESHOLD |

## Debug steps
1. Query DB: `SELECT confidence_score FROM extracted_contacts ORDER BY confidence_score ASC LIMIT 10`
2. Nếu có scores < 0.3 → check log có warning không
3. Nếu 1 company có 2+ contacts → check conflict resolution log
