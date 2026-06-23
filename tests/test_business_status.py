from src.business_status import (
    ACTIVE,
    INACTIVE_ADDRESS,
    INACTIVE_STOP,
    classify_business_status,
    extract_business_status,
)


def test_classify_inactive_stop_statuses():
    assert classify_business_status("Tạm ngừng KD có thời hạn") == INACTIVE_STOP
    assert classify_business_status("NNT ngừng hoạt động nhưng chưa hoàn thành thủ tục chấm dứt hiệu lực MST") == INACTIVE_STOP
    assert classify_business_status("NNT ngừng hoạt động và đã hoàn thành thủ tục chấm dứt hiệu lực MST") == INACTIVE_STOP


def test_inactive_address_does_not_count_as_stop():
    assert classify_business_status("Không hoạt động tại địa chỉ đã đăng ký") == INACTIVE_ADDRESS


def test_extract_labelled_status_from_markdown():
    markdown = """
    | Tên doanh nghiệp | Công Ty TNHH Ricco Việt Nam |
    | Tình trạng hoạt động: | Doanh nghiệp tạm dừng hoạt động hoặc đã ngừng hoạt động từ ngày 2015-12-18 |
    """
    result = extract_business_status(markdown)
    assert result["business_status_category"] == INACTIVE_STOP
    assert "tạm dừng" in result["business_status"].lower()


def test_extract_active_status():
    markdown = "| Tình trạng | [Đang hoạt động](https://example.com) |"
    result = extract_business_status(markdown)
    assert result["business_status_category"] == ACTIVE
