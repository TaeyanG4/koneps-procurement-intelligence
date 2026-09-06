#!/usr/bin/env python3
"""CLI script to collect KONEPS standard open-data feeds (bids, awards, contracts)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Ensure src is on python path for direct CLI script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.api import AuthenticationError, KonepsClient, QuotaExceededError
from koneps_intel.collector import Collector
from koneps_intel.config import RAW_DIR, get_service_key, mask_key
from koneps_intel.endpoints import DEFAULT_PAGE_SIZE, FEEDS
from koneps_intel.parsers import parse_date
from koneps_intel.utils import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect KONEPS standard open-data API feeds")
    parser.add_argument(
        "--dataset",
        choices=["all", *FEEDS.keys()],
        default="all",
        help="Dataset feed to collect (default: all)",
    )
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument("--out", default=str(RAW_DIR), help="Output directory for raw compressed files")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Page size (1..999)")
    parser.add_argument("--force", action="store_true", help="Overwrite already collected date windows")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without making real API calls")
    parser.add_argument("--pause", type=float, default=0.08, help="Pacing sleep between successful calls (seconds)")
    args = parser.parse_args()

    logger = get_logger("koneps_collector")

    if not 1 <= args.page_size <= 999:
        parser.error("--page-size must be between 1 and 999")

    try:
        start = parse_date(args.start)
        end = parse_date(args.end)
    except ValueError as e:
        parser.error(f"Invalid date format: {e}")

    if start > end:
        parser.error("--start must be <= --end")

    try:
        service_key = get_service_key(required=not args.dry_run)
    except RuntimeError as err:
        logger.error("%s", err)
        sys.exit(1)

    if not args.dry_run:
        logger.info("Using authenticated service key: %s", mask_key(service_key))

    client = KonepsClient(service_key=service_key, pause=args.pause, logger=logger)
    collector = Collector(client=client, out_dir=Path(args.out), logger=logger)

    try:
        stats = collector.collect(
            dataset=args.dataset,
            start=start,
            end=end,
            page_size=args.page_size,
            force=args.force,
            dry_run=args.dry_run,
        )
        logger.info(
            "COMPLETED: total_rows=%d, api_calls=%d, windows_saved=%d, windows_skipped=%d",
            stats.total_rows,
            stats.total_calls,
            stats.completed_windows,
            stats.skipped_windows,
        )
    except AuthenticationError as e:
        logger.error("Authentication Failure: %s", e)
        sys.exit(2)
    except QuotaExceededError as e:
        logger.warning("Quota Limit Reached: %s", e)
        sys.exit(3)
    except Exception as e:
        logger.exception("Unexpected error during collection: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
