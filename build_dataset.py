#!/usr/bin/env python3
"""Compatibility wrapper for build_dataset.py."""
import sys
from pathlib import Path

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from scripts.build_dataset import main

if __name__ == "__main__":
    main()
