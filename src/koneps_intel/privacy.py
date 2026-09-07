"""Privacy and pseudonymization utilities for public dataset release.

Supplier pseudonymization uses HMAC-SHA256 with a dedicated secret key
(``KONEPS_SUPPLIER_HMAC_KEY``), which is **separate** from the API authentication
key (``DATA_GO_KR_SERVICE_KEY``).

Key separation rationale:
- ``DATA_GO_KR_SERVICE_KEY``: API access only; can be rotated without affecting data.
- ``KONEPS_SUPPLIER_HMAC_KEY``: Supplier identity; must remain **stable across all
  public dataset releases** to preserve consistent supplier identifiers.

IMPORTANT: Once a dataset version is published, the supplier HMAC key must NEVER
change. Rotating it changes every ``supplier_id`` in the dataset.
"""
from __future__ import annotations

import hashlib
import hmac


_VALID_BIZ_NO_LEN = 10


def generate_supplier_id(
    biz_no: str,
    hmac_key: bytes,
    prefix: str = "SUP_",
) -> str:
    """Generate a pseudonymous, non-enumerable public supplier identifier using HMAC-SHA256.

    Prevents dictionary and brute-force precomputation attacks against the bounded
    10-digit Korean business registration number space.

    Args:
        biz_no: Raw or formatted 10-digit business registration number.
                Hyphens are stripped automatically (e.g. "123-45-67890" → "1234567890").
        hmac_key: Dedicated supplier pseudonymization secret (``KONEPS_SUPPLIER_HMAC_KEY``).
                  Must NOT be the API key (``DATA_GO_KR_SERVICE_KEY``).
        prefix: Canonical prefix for the generated identifier.

    Returns:
        Pseudonymous string identifier in the form ``SUP_<32 hex chars>``
        (128-bit HMAC prefix), or an empty string if the input is blank, None,
        or does not contain exactly 10 numeric digits after normalization.

    Raises:
        TypeError: If ``hmac_key`` is not bytes.
    """
    if not isinstance(hmac_key, bytes):
        raise TypeError("hmac_key must be bytes")
    # Normalize: strip hyphens, whitespace
    clean = str(biz_no or "").replace("-", "").strip()
    if not clean:
        return ""
    # Require exactly 10 numeric digits
    if len(clean) != _VALID_BIZ_NO_LEN or not clean.isdigit():
        return ""
    digest = hmac.new(hmac_key, clean.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}{digest[:32]}"

