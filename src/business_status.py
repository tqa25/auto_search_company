import re
from typing import Optional


ACTIVE = "active"
INACTIVE_STOP = "inactive_stop"
INACTIVE_ADDRESS = "inactive_address"
UNKNOWN = "unknown"

STATUS_LABEL_RE = re.compile(
    r"(Tình trạng hoạt động|Tình trạng|Trạng thái hoạt động|Trạng thái)\s*"
    r"(?:[:|\-]|\s)*\s*([^\n#]{0,260})",
    re.IGNORECASE,
)

BRACKET_STATUS_RE = re.compile(
    r"(Tình trạng hoạt động|Tình trạng|Trạng thái hoạt động|Trạng thái)\s*"
    r"(?:[:|\-]|\s)*\s*\[([^\]]+)\]",
    re.IGNORECASE,
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip(" |:-")


def classify_business_status(status_text: str | None) -> str:
    text = _compact(status_text).lower()
    if not text:
        return UNKNOWN

    if "không hoạt động tại địa chỉ" in text or "không hoạt động tại nơi đăng ký" in text:
        return INACTIVE_ADDRESS

    stop_patterns = (
        "tạm ngừng",
        "tạm dừng",
        "ngừng hoạt động",
        "ngừng hđ",
        "chấm dứt hiệu lực mst",
        "đã đóng mst",
        "chờ làm thủ tục phá sản",
    )
    if any(pattern in text for pattern in stop_patterns):
        return INACTIVE_STOP

    if "đang hoạt động" in text:
        return ACTIVE

    return UNKNOWN


def extract_business_status(markdown: str | None) -> Optional[dict]:
    """Extract a labelled business status from scraped markdown."""
    if not markdown:
        return None

    candidates = []
    for regex in (BRACKET_STATUS_RE, STATUS_LABEL_RE):
        for match in regex.finditer(markdown):
            label = _compact(match.group(1))
            value = _compact(match.group(2))
            if not value:
                continue
            if re.search(r"tất cả trạng thái|windows|thiết bị máy tính|zalo đang hoạt động", value, re.IGNORECASE):
                continue
            category = classify_business_status(value)
            if category != UNKNOWN:
                candidates.append({
                    "business_status": value,
                    "business_status_category": category,
                    "business_status_label": label,
                })

    return candidates[0] if candidates else None
