#!/usr/bin/env python3
"""Build the historical curated KONEPS release in resumable monthly units."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.historical_curate import run_historical_curation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build verified relational KONEPS tables month by month"
    )
    parser.add_argument("--start", default="2025-09-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-08-31", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--processed",
        default="data/processed/historical_202509_202608",
        help="Historical normalized Parquet root",
    )
    parser.add_argument("--out-root", help="Optional monthly curated output root")
    parser.add_argument("--metrics-root", help="Optional monthly sanitized metrics root")
    parser.add_argument("--summary", help="Optional cumulative summary JSON path")
    parser.add_argument(
        "--max-months",
        type=int,
        help="Bound this invocation to the first N months (useful for smoke tests)",
    )
    parser.add_argument("--force", action="store_true", help="Rebuild completed monthly outputs")
    args = parser.parse_args()

    result = run_historical_curation(
        start=args.start,
        end=args.end,
        processed_dir=Path(args.processed),
        out_root=Path(args.out_root) if args.out_root else None,
        metrics_root=Path(args.metrics_root) if args.metrics_root else None,
        summary_path=Path(args.summary) if args.summary else None,
        max_months=args.max_months,
        force=args.force,
    )

    totals = result["totals"]
    print("=== KONEPS HISTORICAL CURATION ===")
    print(f"scope              : {result['scope_start']} .. {result['scope_end']}")
    print(f"planned months     : {result['planned_months']}")
    print(f"months this run    : {result['selected_months_this_run']}")
    print(f"all passed         : {result['all_selected_months_passed']}")
    print(f"tenders            : {totals['tenders']:,}")
    print(f"bidder submissions : {totals['bidder_submissions']:,}")
    print(f"award outcomes     : {totals['award_outcomes']:,}")
    print(f"contracts          : {totals['contracts']:,}")
    print(f"curated bytes      : {totals['curated_bytes']:,}")


if __name__ == "__main__":
    main()

