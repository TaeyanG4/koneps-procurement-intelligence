#!/usr/bin/env python3
"""CLI runner for KONEPS pilot dataset audit.

Accepts explicit scope arguments (--start, --end) to eliminate period contamination
and produces a deterministic metrics JSON artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure package import if run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.audit import main

if __name__ == "__main__":
    main()
