#!/usr/bin/env python3
"""Build the flat tender-level CSV convenience artifact for Kaggle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.quickstart import build_quickstart_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Build KONEPS quickstart tender summary CSV")
    parser.add_argument(
        "--release-dir",
        default="data/processed/kaggle_release_202509_202608",
    )
    args = parser.parse_args()
    report = build_quickstart_csv(Path(args.release_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
