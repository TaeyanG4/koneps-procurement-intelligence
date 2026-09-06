"""Robust API client for KONEPS standard open data service."""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from koneps_intel.endpoints import (
    AUTH_CODES,
    BASE_URL,
    NO_DATA_CODES,
    QUOTA_CODES,
    SUCCESS_CODES,
)
from koneps_intel.parsers import extract_response, parse_xml_response
from koneps_intel.utils import get_logger, redact_sensitive


class KonepsApiError(Exception):
    """Base exception for KONEPS API communication failures."""


class AuthenticationError(KonepsApiError):
    """Raised when the API service key is invalid or unauthorized."""


class QuotaExceededError(KonepsApiError):
    """Raised when daily API request limits are exceeded."""


class PermanentApiError(KonepsApiError):
    """Raised when the request or API error is non-retryable (client error, invalid params)."""


class TransientApiError(KonepsApiError):
    """Raised for retryable server-side failures (429, 500, 502, 503, 504)."""

    def __init__(
        self,
        message: str,
        response: Optional[Any] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.response = response
        self.status_code = status_code or (response.status_code if response is not None else None)


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class KonepsClient:
    """Production-grade HTTP client for data.go.kr KONEPS APIs."""

    def __init__(
        self,
        service_key: str,
        timeout: int = 45,
        max_retries: int = 5,
        pause: float = 0.08,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.service_key = service_key.strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.pause = pause
        self.session = session or requests.Session()
        if hasattr(self.session, "headers") and hasattr(self.session.headers, "update"):
            self.session.headers.update({"User-Agent": "koneps-procurement-intelligence/0.1.1"})
        self.logger = logger or get_logger("koneps_intel.api")
        self.calls = 0

    def get_page(self, operation: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
        """Fetch a single page of records with retry and structured error handling."""
        url = f"{BASE_URL}/{operation}"
        request_params = {
            "serviceKey": self.service_key,
            "type": "json",
            **params,
        }
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                self.calls += 1
                resp = self.session.get(url, params=request_params, timeout=self.timeout)

                # Transient HTTP server errors (retryable)
                if resp.status_code in TRANSIENT_STATUS_CODES:
                    raise TransientApiError(f"Transient HTTP {resp.status_code}", response=resp)

                # Permanent HTTP client errors (non-retryable, e.g. 400, 401, 403, 404)
                if 400 <= resp.status_code < 500 and resp.status_code not in TRANSIENT_STATUS_CODES:
                    raise PermanentApiError(f"Permanent HTTP {resp.status_code}: {resp.text[:200]}")

                resp.raise_for_status()

                # Separate JSON decoding from schema validation
                is_json = False
                payload = None
                try:
                    payload = resp.json()
                    is_json = True
                except (ValueError, json.JSONDecodeError):
                    is_json = False

                if is_json:
                    # Valid JSON parsed - extract response directly.
                    # Schema errors must NOT fallback to XML parser.
                    try:
                        items, total, code, msg = extract_response(payload)
                    except Exception as schema_err:
                        raise PermanentApiError(f"Unexpected JSON schema: {schema_err}") from schema_err
                else:
                    # Non-JSON response (e.g. data.go.kr XML error envelope)
                    items, total, code, msg = parse_xml_response(resp.text)

                if code in SUCCESS_CODES or (not code and items):
                    time.sleep(self.pause)
                    return items, total

                if code in NO_DATA_CODES:
                    return [], 0

                if code in AUTH_CODES:
                    raise AuthenticationError(
                        f"Authentication failed ({code}: {msg}). "
                        "Check DATA_GO_KR_SERVICE_KEY and service approval on data.go.kr."
                    )

                if code in QUOTA_CODES:
                    raise QuotaExceededError(
                        f"Daily traffic quota exceeded ({code}: {msg}). "
                        "Collection halted cleanly. Resume tomorrow or request quota expansion."
                    )

                # Any other application error code from API is permanent (e.g. invalid parameters)
                raise PermanentApiError(f"API returned non-retryable error code {code}: {msg}")

            except (AuthenticationError, QuotaExceededError, PermanentApiError) as non_retryable:
                # Strictly do not retry permanent failures
                self.logger.error("Request failed with non-retryable error: %s", redact_sensitive(str(non_retryable)))
                raise

            except Exception as exc:
                # Permanent HTTP client errors (4xx) raised by requests session
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    status = exc.response.status_code
                    if 400 <= status < 500 and status not in TRANSIENT_STATUS_CODES:
                        self.logger.error("Request failed with non-retryable HTTP %d: %s", status, exc)
                        raise PermanentApiError(f"Permanent HTTP {status}: {exc}") from exc

                last_error = exc
                if attempt == self.max_retries - 1:
                    break

                sleep_for = min(30.0, (2 ** attempt) + random.uniform(0.1, 1.0))
                self.logger.warning(
                    "RETRY attempt %d/%d after %.1fs: %s",
                    attempt + 1,
                    self.max_retries,
                    sleep_for,
                    redact_sensitive(str(exc)),
                )
                time.sleep(sleep_for)

        sanitized_msg = redact_sensitive(str(last_error))
        raise KonepsApiError(f"Request failed after {self.max_retries} retries: {sanitized_msg}") from last_error
