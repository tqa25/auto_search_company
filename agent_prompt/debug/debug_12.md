# Debug Task 12: Schemas Validation

**Model:** Gemini 3 Flash | **File:** `src/schemas.py`

## Kiểm tra
```bash
grep -n "class.*Result\|class.*Link\|def validate_" src/schemas.py
grep -rn "from src.schemas" src/search_module.py src/filter_module.py
```

## Test
```python
from src.schemas import validate_search_result
validate_search_result({"url": "https://example.com"})  # OK
validate_search_result({"title": "No URL"})  # ValueError
```

## Lỗi thường gặp
- ImportError → check file path
- validate không raise → check validation logic
- TypeError → filter extra dict keys trước khi pass to dataclass
