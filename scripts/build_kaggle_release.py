#!/usr/bin/env python3
"""Build the seven-file public Kaggle release from verified historical curation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.release import build_kaggle_release


def main() -> None:
    parser = argparse.ArgumentParser(description="Build privacy-minimized KONEPS Kaggle release")
    parser.add_argument("--start", default="2025-09-01")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument(
        "--curated-root",
        default="data/processed/historical_202509_202608/curated_monthly",
    )
    parser.add_argument(
        "--out",
        default="data/processed/kaggle_release_202509_202608",
    )
    parser.add_argument(
        "--historical-summary",
        default="data/processed/historical_202509_202608/historical_curated_summary.json",
    )
    parser.add_argument(
        "--report",
        default="docs/metrics/release_202509_202608.json",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    report = build_kaggle_release(
        curated_root=Path(args.curated_root),
        out_dir=Path(args.out),
        start=args.start,
        end=args.end,
        historical_summary_path=Path(args.historical_summary),
        report_path=Path(args.report),
        force=args.force,
    )
    print("=== KONEPS KAGGLE RELEASE ===")
    print(f"scope       : {report['scope_start']} .. {report['scope_end']}")
    print(f"source months: {report['source_months']}")
    print(f"files       : {len(report['files'])}")
    print(f"bytes       : {report['total_release_bytes']:,}")
    print(f"passed      : {report['validation']['passed']}")


if __name__ == "__main__":
    main()
