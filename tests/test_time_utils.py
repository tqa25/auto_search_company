from datetime import datetime, timezone

from src.time_utils import parse_timestamp_as_vn, vn_cache_expiry, vn_date_str, vn_timestamp, VN_TZ


def test_vn_date_and_timestamp_use_vn_timezone():
    dt = datetime(2026, 6, 24, 20, 30, tzinfo=timezone.utc)
    assert vn_date_str(dt) == "2026-06-25"
    assert vn_timestamp(dt) == "2026-06-25 03:30:00"


def test_vn_cache_expiry_adds_days_in_vn_time():
    dt = datetime(2026, 6, 25, 23, 15, tzinfo=VN_TZ)
    assert vn_cache_expiry(2, dt) == "2026-06-27 23:15:00"


def test_parse_timestamp_as_vn_treats_naive_values_as_vn_local():
    parsed = parse_timestamp_as_vn("2026-06-25 09:45:00")
    assert parsed is not None
    assert parsed.tzinfo == VN_TZ
    assert parsed.isoformat() == "2026-06-25T09:45:00+07:00"
