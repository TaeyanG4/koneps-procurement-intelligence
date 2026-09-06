"""Unit tests for KonepsClient API requests and error handling."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from koneps_intel.api import (
    AuthenticationError,
    KonepsApiError,
    KonepsClient,
    PermanentApiError,
    QuotaExceededError,
)
from koneps_intel.config import mask_key
from koneps_intel.utils import redact_sensitive

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_session():
    s = MagicMock(spec=requests.Session)
    s.headers = {}
    return s


def test_mask_key():
    assert mask_key("short") == "********"
    assert mask_key("abcdef1234567890xyz") == "abcd********0xyz"
    assert mask_key(None) == "<none>"


def test_redact_sensitive():
    url = "https://apis.data.go.kr/1230000/PubDataOpnStdService/getData?serviceKey=SECRET_KEY_123&type=json"
    clean = redact_sensitive(url)
    assert "SECRET_KEY_123" not in clean
    assert "serviceKey=[REDACTED]" in clean


def test_client_normal_response(mock_session):
    with open(FIXTURES_DIR / "sample_bids_response.json", "r", encoding="utf-8") as f:
        mock_data = json.load(f)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data
    mock_session.get.return_value = mock_resp

    client = KonepsClient(service_key="test_key_123456", pause=0.0, session=mock_session)
    items, total = client.get_page("getDataSetOpnStdBidPblancInfo", {"pageNo": 1, "numOfRows": 10})

    assert len(items) == 2
    assert total == 2
    assert items[0]["bidNtceNo"] == "20260901001"


def test_client_empty_response(mock_session):
    with open(FIXTURES_DIR / "sample_empty_response.json", "r", encoding="utf-8") as f:
        mock_data = json.load(f)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data
    mock_session.get.return_value = mock_resp

    client = KonepsClient(service_key="test_key_123456", pause=0.0, session=mock_session)
    items, total = client.get_page("getDataSetOpnStdBidPblancInfo", {})

    assert items == []
    assert total == 0


def test_client_auth_failure_xml(mock_session):
    xml_text = (FIXTURES_DIR / "sample_auth_error.xml").read_text(encoding="utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Not JSON")
    mock_resp.text = xml_text
    mock_session.get.return_value = mock_resp

    client = KonepsClient(service_key="bad_key", pause=0.0, session=mock_session)
    with pytest.raises(AuthenticationError) as exc_info:
        client.get_page("getDataSetOpnStdBidPblancInfo", {})

    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(exc_info.value)


def test_client_quota_exceeded(mock_session):
    with open(FIXTURES_DIR / "sample_quota_error.json", "r", encoding="utf-8") as f:
        mock_data = json.load(f)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_data
    mock_session.get.return_value = mock_resp

    client = KonepsClient(service_key="test_key_123456", pause=0.0, session=mock_session)
    with pytest.raises(QuotaExceededError):
        client.get_page("getDataSetOpnStdBidPblancInfo", {})


def test_client_retry_server_error(mock_session):
    err_resp = MagicMock()
    err_resp.status_code = 500

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"response": {"header": {"resultCode": "00"}, "body": {"items": [{"id": 1}], "totalCount": 1}}}

    mock_session.get.side_effect = [
        requests.HTTPError("500 Server Error", response=err_resp),
        ok_resp,
    ]

    client = KonepsClient(service_key="test_key_123456", timeout=5, max_retries=3, pause=0.0, session=mock_session)
    with patch("time.sleep"):
        items, total = client.get_page("test_op", {})

    assert len(items) == 1
    assert total == 1
    assert client.calls == 2


def test_client_client_error_no_retry(mock_session):
    err_resp = MagicMock()
    err_resp.status_code = 404
    mock_session.get.side_effect = requests.HTTPError("404 Not Found", response=err_resp)

    client = KonepsClient(service_key="test_key_123456", max_retries=3, pause=0.0, session=mock_session)
    with pytest.raises(PermanentApiError):
        client.get_page("test_op", {})

    assert client.calls == 1
    assert mock_session.get.call_count == 1


def test_client_json_schema_error_no_xml_fallback(mock_session):
    # Valid JSON, but missing standard response envelope
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error_code": "INVALID_PARAMS"}
    mock_resp.text = '{"error_code": "INVALID_PARAMS"}'
    mock_session.get.return_value = mock_resp

    client = KonepsClient(service_key="test_key_123456", max_retries=1, pause=0.0, session=mock_session)
    with pytest.raises(PermanentApiError) as exc_info:
        client.get_page("test_op", {})

    assert "Unexpected JSON schema" in str(exc_info.value)
    assert client.calls == 1


def test_client_application_error_code_no_retry(mock_session):
    # Application error code (e.g. 02: Invalid Request Parameter)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": {
            "header": {"resultCode": "02", "resultMsg": "INVALID_REQUEST_PARAMETER_ERROR"}
        }
    }
    mock_session.get.return_value = mock_resp

    client = KonepsClient(service_key="test_key_123456", max_retries=3, pause=0.0, session=mock_session)
    with pytest.raises(PermanentApiError) as exc_info:
        client.get_page("test_op", {})

    assert "INVALID_REQUEST_PARAMETER_ERROR" in str(exc_info.value)
    assert client.calls == 1


def test_client_user_agent_header():
    client = KonepsClient(service_key="test_key_123456")
    assert "User-Agent" in client.session.headers
    assert client.session.headers["User-Agent"].startswith("koneps-procurement-intelligence/")
