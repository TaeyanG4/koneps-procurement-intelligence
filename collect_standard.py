#!/usr/bin/env python3
"""Compatibility wrapper for collect_standard.py."""
import sys
from pathlib import Path

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from koneps_intel.parsers import extract_response, fixed_windows, month_windows
from scripts.collect_standard import main

__all__ = ["main", "extract_response", "fixed_windows", "month_windows"]

if __name__ == "__main__":
    main()
