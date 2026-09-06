#!/usr/bin/env python3
"""CLI script to normalize raw JSONL feeds into partitioned Parquet datasets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src is on python path for direct CLI script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.config import PROCESSED_DIR, RAW_DIR
from koneps_intel.normalize import build_feed_parquet
from koneps_intel.utils import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert raw KONEPS JSONL to partitioned Parquet")
    parser.add_argument("--raw", default=str(RAW_DIR), help="Input raw directory")
    parser.add_argument("--processed", default=str(PROCESSED_DIR), help="Output processed directory")
    parser.add_argument("--feed", choices=["all", "bids", "awards", "contracts"], default="all")
    parser.add_argument("--force", action="store_true", help="Rebuild existing Parquet files")
    parser.add_argument("--no-partition", action="store_true", help="Do not partition by year/month")
    args = parser.parse_args()

    logger = get_logger("koneps_build")
    raw_root = Path(args.raw)
    processed_root = Path(args.processed)
    partition = not args.no_partition

    target_feeds = ["bids", "awards", "contracts"] if args.feed == "all" else [args.feed]
    reports = []

    for feed in target_feeds:
        logger.info("Processing feed: %s", feed)
        rep = build_feed_parquet(
            raw_root=raw_root,
            processed_root=processed_root,
            feed=feed,
            force=args.force,
            partition_by_date=partition,
        )
        reports.append(rep)
        logger.info(
            "Feed %s: %d parts written, %d rows after deduplication",
            feed,
            rep["parquet_parts"],
            rep["rows_after_dedupe"],
        )

    processed_root.mkdir(parents=True, exist_ok=True)
    report_file = processed_root / "build_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)
    logger.info("Build report written to %s", report_file)


if __name__ == "__main__":
    main()
