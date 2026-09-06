"""Parsing utilities for date windows and API response structures."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple

from koneps_intel.endpoints import FeedSpec


def parse_date(value: str) -> date:
    """Parse YYYY-MM-DD date string."""
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def month_windows(start: date, end: date) -> Iterable[Tuple[date, date]]:
    """Generate calendar month slices between start and end inclusive."""
    cur = start
    while cur <= end:
        if cur.month == 12:
            next_month = date(cur.year + 1, 1, 1)
        else:
            next_month = date(cur.year, cur.month + 1, 1)
        win_end = min(end, next_month - timedelta(days=1))
        yield cur, win_end
        cur = win_end + timedelta(days=1)


def fixed_windows(start: date, end: date, days: int) -> Iterable[Tuple[date, date]]:
    """Generate fixed-day interval slices between start and end inclusive."""
    cur = start
    while cur <= end:
        win_end = min(end, cur + timedelta(days=days - 1))
        yield cur, win_end
        cur = win_end + timedelta(days=1)


def format_boundary(d: date, fmt: str, is_end: bool) -> str:
    """Format date for API query parameters according to endpoint format."""
    if fmt == "%Y%m%d%H%M":
        suffix = "2359" if is_end else "0000"
        return d.strftime("%Y%m%d") + suffix
    return d.strftime(fmt)


def feed_windows(spec: FeedSpec, start: date, end: date) -> Iterable[Tuple[date, date]]:
    """Yield appropriate date windows based on FeedSpec configuration."""
    if spec.monthly:
        yield from month_windows(start, end)
    elif spec.window_days:
        yield from fixed_windows(start, end, spec.window_days)
    else:
        yield start, end


def extract_response(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int, str, str]:
    """Extract list of items, total record count, resultCode, and resultMsg from JSON."""
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object payload, got {type(payload).__name__}")

    if "response" not in payload and "header" not in payload:
        raise ValueError(f"Unexpected JSON schema: missing 'response' or 'header' in {list(payload.keys())}")

    response = payload.get("response", payload)
    if not isinstance(response, dict):
        raise ValueError(f"Expected dict for 'response', got {type(response).__name__}")

    header = response.get("header", {}) or {}
    body = response.get("body", {}) or {}
    code = str(header.get("resultCode", ""))
    msg = str(header.get("resultMsg", ""))

    items = body.get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if items is None:
        items = []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected items shape: {type(items).__name__}")

    total = body.get("totalCount", len(items))
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(items)
    return items, total, code, msg


def parse_xml_response(text: str) -> Tuple[List[Dict[str, Any]], int, str, str]:
    """Fallback parser for XML response or XML error messages from data.go.kr."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Failed to parse XML response: {text[:200]}") from exc

    # Check for cmmMsgHeader (common data.go.kr error envelope)
    cmm_header = root.find("cmmMsgHeader")
    if cmm_header is not None:
        code = (cmm_header.findtext("returnReasonCode") or "").strip()
        msg = (cmm_header.findtext("returnAuthMsg") or cmm_header.findtext("errMsg") or "").strip()
        return [], 0, code, msg

    # Standard XML response envelope
    header = root.find("header")
    code = (header.findtext("resultCode") if header is not None else "") or ""
    msg = (header.findtext("resultMsg") if header is not None else "") or ""

    body = root.find("body")
    items_list: List[Dict[str, Any]] = []
    total = 0

    if body is not None:
        total_str = body.findtext("totalCount")
        if total_str and total_str.isdigit():
            total = int(total_str)

        items_elem = body.find("items")
        if items_elem is not None:
            for item in items_elem.findall("item"):
                item_dict = {child.tag: (child.text or "").strip() for child in item}
                items_list.append(item_dict)
        if not total:
            total = len(items_list)

    return items_list, total, code, msg
