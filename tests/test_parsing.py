from collect_standard import extract_response, fixed_windows, month_windows
from datetime import date


def test_extract_list_items():
    p = {"response": {"header": {"resultCode": "00", "resultMsg": "OK"}, "body": {"items": [{"a": 1}], "totalCount": 1}}}
    items, total, code, msg = extract_response(p)
    assert items == [{"a": 1}]
    assert total == 1
    assert code == "00"


def test_extract_nested_item():
    p = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": {"a": 1}}, "totalCount": "1"}}}
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
    assert w[-1] == (date(2026, 1, 15), date(2026, 1, 16))
