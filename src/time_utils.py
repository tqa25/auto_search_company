from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
DB_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
FILENAME_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def vn_now() -> datetime:
    return datetime.now(VN_TZ)


def vn_date_str(dt: datetime | None = None) -> str:
    return (dt or vn_now()).astimezone(VN_TZ).strftime("%Y-%m-%d")


def vn_timestamp(dt: datetime | None = None) -> str:
    return (dt or vn_now()).astimezone(VN_TZ).strftime(DB_TIMESTAMP_FORMAT)


def vn_iso(dt: datetime | None = None, timespec: str = "seconds") -> str:
    return (dt or vn_now()).astimezone(VN_TZ).isoformat(timespec=timespec)


def vn_filename_timestamp(dt: datetime | None = None) -> str:
    return (dt or vn_now()).astimezone(VN_TZ).strftime(FILENAME_TIMESTAMP_FORMAT)


def vn_cache_expiry(days: int, dt: datetime | None = None) -> str:
    return vn_timestamp((dt or vn_now()).astimezone(VN_TZ) + timedelta(days=days))


def parse_timestamp_as_vn(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text) if "T" in text else datetime.strptime(text[:19], DB_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=VN_TZ)
    return parsed.astimezone(VN_TZ)
