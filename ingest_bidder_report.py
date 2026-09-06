#!/usr/bin/env python3
"""Compatibility wrapper for ingest_bidder_report.py."""
import sys
from pathlib import Path

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from scripts.ingest_bidder_report import main

if __name__ == "__main__":
    main()
