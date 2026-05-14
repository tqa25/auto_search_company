# Task 12: Schemas Validation

**Model:** Gemini 3.1 Pro
**File:** `src/schemas.py` [NEW]
**Phụ thuộc:** Không (nhưng nên sau Task 01-08 để biết data flow)

## Bối cảnh
Các module truyền `dict` không validate. Khi data bị corrupt (missing key, wrong type) → lỗi chỉ phát hiện ở bước sau, khó debug. Cần schema validation ở boundary.

## Tạo file `src/schemas.py`

Dùng `dataclasses` (không cần Pydantic — giữ lightweight):

```python
from dataclasses import dataclass, field, asdict
from typing import Optional

@dataclass
class SearchResult:
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    search_type: str = ""       # "coarse", "fallback_a", etc.
    cache_hit: bool = False
    credits_used: float = 0.0

@dataclass
class ScoredLink:
    url: str
    source_type: str = "unknown"
    relevance_score: float = 0.0
    should_scrape: bool = True
    breakdown: dict = field(default_factory=dict)
    reason: str = ""

@dataclass
class ScrapedContent:
    url: str
    markdown: str = ""
    content_length: int = 0
    scrape_status: str = "pending"
    credits_used: float = 0.0
    error_message: Optional[str] = None

@dataclass
class ExtractedContact:
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    fax: Optional[str] = None
    representative: Optional[str] = None
    confidence: float = 0.0
    source_type: str = ""
    source_url: str = ""
```

### Thêm validation helper:
```python
def validate_search_result(data: dict) -> SearchResult:
    """Validate và convert dict → SearchResult. Raise ValueError nếu thiếu url."""
    if "url" not in data or not data["url"]:
        raise ValueError(f"SearchResult missing required 'url': {data}")
    return SearchResult(**{k: v for k, v in data.items() if k in SearchResult.__dataclass_fields__})
```

Tương tự cho `validate_scored_link()`, `validate_scraped_content()`, `validate_extracted_contact()`.

### Tích hợp vào modules:
- **search_module.py**: Sau khi parse search results → validate qua `validate_search_result()`
- **filter_module.py**: Output của classify_url → validate qua `validate_scored_link()`
- **Không bắt buộc** cho tất cả modules ngay — thêm dần

## Tiêu chí hoàn thành
- [ ] `src/schemas.py` tồn tại với 4 dataclasses
- [ ] Mỗi dataclass có validate function
- [ ] Ít nhất search_module và filter_module dùng validation
- [ ] ValueError được raise khi data thiếu required fields
