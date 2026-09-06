"""Unit tests for response parsers and date window generators."""
from datetime import date
from koneps_intel.endpoints import FEEDS
from koneps_intel.parsers import (
    extract_response,
    feed_windows,
    fixed_windows,
    format_boundary,
    month_windows,
    parse_xml_response,
)


def test_extract_list_items():
    p = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {"items": [{"a": 1}], "totalCount": 1},
        }
    }
    items, total, code, msg = extract_response(p)
    assert items == [{"a": 1}]
    assert total == 1
    assert code == "00"


def test_extract_nested_item():
    p = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {"items": {"item": {"a": 1}}, "totalCount": "1"},
        }
    }
    items, total, _, _ = extract_response(p)
    assert items == [{"a": 1}]
    assert total == 1


def test_month_windows():
    w = list(month_windows(date(2026, 1, 15), date(2026, 3, 2)))
    assert w == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 2)),
    ]


def test_fixed_windows():
    w = list(fixed_windows(date(2026, 1, 1), date(2026, 1, 16), 7))
    assert w[0] == (date(2026, 1, 1), date(2026, 1, 7))
    assert w[-1] == (date(2026, 1, 15), date(2026, 1, 16))


def test_format_boundary():
    d = date(2026, 9, 1)
    assert format_boundary(d, "%Y%m%d%H%M", is_end=False) == "202609010000"
    assert format_boundary(d, "%Y%m%d%H%M", is_end=True) == "202609012359"
    assert format_boundary(d, "%Y%m%d", is_end=False) == "20260901"


def test_feed_windows_bids():
    spec = FEEDS["bids"]
    windows = list(feed_windows(spec, date(2026, 8, 15), date(2026, 9, 10)))
    assert len(windows) == 2
    assert windows[0] == (date(2026, 8, 15), date(2026, 8, 31))
    assert windows[1] == (date(2026, 9, 1), date(2026, 9, 10))


def test_feed_windows_awards_one_day_splitting():
    spec = FEEDS["awards"]
    assert spec.window_days == 1
    windows = list(feed_windows(spec, date(2026, 9, 1), date(2026, 9, 3)))
    assert windows == [
        (date(2026, 9, 1), date(2026, 9, 1)),
        (date(2026, 9, 2), date(2026, 9, 2)),
        (date(2026, 9, 3), date(2026, 9, 3)),
    ]



def test_parse_xml_error():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <OpenAPI_ServiceResponse>
      <cmmMsgHeader>
        <errMsg>SERVICE ERROR</errMsg>
        <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
        <returnReasonCode>30</returnReasonCode>
      </cmmMsgHeader>
    </OpenAPI_ServiceResponse>"""
    items, total, code, msg = parse_xml_response(xml)
    assert code == "30"
    assert msg == "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
    assert items == []
    assert total == 0
