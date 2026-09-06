"""Robust API client for KONEPS standard open data service."""
from __future__ import annotations

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
        if hasattr(self.session, "headers") and isinstance(self.session.headers, dict):
            self.session.headers.update({"User-Agent": "koneps-intel/0.1.0"})
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

                # Transient HTTP server errors
                if resp.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)

                resp.raise_for_status()

                # Parse JSON or fallback to XML
                try:
                    payload = resp.json()
                    items, total, code, msg = extract_response(payload)
                except Exception:
                    # Often data.go.kr returns an XML error body even when type=json was requested
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

                raise KonepsApiError(f"API returned error code {code}: {msg}")

            except (requests.RequestException, KonepsApiError) as exc:
                last_error = exc
                if isinstance(exc, (AuthenticationError, QuotaExceededError)):
                    raise

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
