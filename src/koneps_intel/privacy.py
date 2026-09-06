"""Privacy and pseudonymization utilities for public dataset release."""
from __future__ import annotations

import hashlib
import hmac


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
        hmac_key: Secret project salt key (must remain local and private).
        prefix: Canonical prefix for the generated identifier.

    Returns:
        Pseudonymous string identifier (e.g. 'SUP_a1b2c3d4e5f60718') or empty string if input is blank.
    """
    clean = str(biz_no or "").replace("-", "").strip()
    if not clean:
        return ""
    digest = hmac.new(hmac_key, clean.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}{digest[:16]}"
