"""Configuration management for KONEPS Procurement Intelligence."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
PROCESSED_DIR = DATA_DIR / "processed"
LOGS_DIR = DATA_DIR / "logs"

# Ensure essential directories exist
for d in (RAW_DIR, STAGING_DIR, PROCESSED_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)


def mask_key(key: str | None) -> str:
    """Mask sensitive API service key for safe logging."""
    if not key:
        return "<none>"
    key = key.strip()
    if len(key) <= 8:
        return "********"
    return f"{key[:4]}********{key[-4:]}"


import urllib.parse


def get_service_key(required: bool = True) -> str:
    """Retrieve and validate the public data portal API key from environment."""
    load_dotenv()
    key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not key or key == "YOUR_DECODING_SERVICE_KEY_HERE":
        if required:
            raise RuntimeError(
                "Missing DATA_GO_KR_SERVICE_KEY. "
                "Copy .env.example to .env and set your data.go.kr decoding service key."
            )
        return ""
    # Normalize percent-encoded keys (e.g. from 'Encoding' portal key) so requests
    # does not double-encode special characters (%2B, %2F, %3D) when sending params.
    if "%" in key:
        key = urllib.parse.unquote(key)
    return key

