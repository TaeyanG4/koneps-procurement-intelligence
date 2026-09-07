#!/usr/bin/env python3
"""Deterministic dry-run planner for KONEPS 1-year historical collection.

Produces aggregate planning metrics (date range, windows by feed/category,
total logical windows, minimum request count, projected API calls, projected
storage, estimated curated scale) for the period 2025-09-01 through 2026-08-31.

Makes ZERO API calls. All projections are labeled ESTIMATED.

Usage:
    python scripts/plan_historical_collection.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
    python scripts/plan_historical_collection.py --json  # output raw JSON to stdout

Reference (from August 2026 pilot empirical data):
    bids: 32,895 tenders / month → ~32,895 * 12 = ~394,740 tenders/year
    awards: 2,107,948 submissions / month → ~25.3M/year
    contracts: 115,945 contracts / month → ~1.39M/year
    Total raw Parquet ~12× pilot ~= 1.4 GiB/year
    Curated ~12× pilot 115.67 MiB ~= 1.35 GiB/year (ESTIMATED)
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.endpoints import BUSINESS_DIVISIONS, FEEDS
from koneps_intel.parsers import feed_windows


def plan_historical_collection(
    start: date,
    end: date,
    page_size: int = 500,
) -> Dict[str, Any]:
    """Compute aggregate planning metrics for historical collection. Zero API calls."""

    total_logical_windows = 0
    total_api_calls_lower = 0  # minimum (assuming all pages full, i.e. 1 API call per window)
    feed_breakdown: Dict[str, Any] = {}

    for feed_name, spec in FEEDS.items():
        codes = list(BUSINESS_DIVISIONS.keys()) if spec.needs_business_division else [None]
        windows = list(feed_windows(spec, start, end))
        num_windows = len(windows)
        num_codes = len(codes)
        logical_windows = num_windows * num_codes
        # Lower bound: at minimum 1 API call per logical window (could be 0 rows)
        min_api_calls = logical_windows  # actual >= this
        total_logical_windows += logical_windows
        total_api_calls_lower += min_api_calls

        # Detail breakdown
        feed_breakdown[feed_name] = {
            "window_type": "monthly" if spec.monthly else f"{spec.window_days}_day",
            "num_calendar_windows": num_windows,
            "num_division_codes": num_codes,
            "logical_windows": logical_windows,
            "min_api_calls_estimated": min_api_calls,
            "window_examples": [
                {"start": str(ws), "end": str(we)}
                for ws, we in windows[:3]
            ] + (["..."] if num_windows > 3 else []),
        }

    # Empirical basis from August 2026 pilot
    PILOT_MONTHS = 1
    pilot_empirical = {
        "bids_tenders": 32895,
        "awards_submissions": 2107948,
        "contracts": 115945,
        "suppliers": 143842,
        "agencies": 14091,
        "curated_mib": 115.67,
        "raw_compressed_mib_approx": 200,  # rough estimate
    }

    plan_months = (end.year - start.year) * 12 + (end.month - start.month) + 1

    # Scale estimates (ESTIMATED - real seasonality will vary)
    estimated_tenders = pilot_empirical["bids_tenders"] * plan_months
    estimated_submissions = pilot_empirical["awards_submissions"] * plan_months
    estimated_contracts = pilot_empirical["contracts"] * plan_months
    estimated_curated_mib = round(pilot_empirical["curated_mib"] * plan_months, 1)

    return {
        "plan_type": "historical_dry_run",
        "note": "All projections are ESTIMATED based on August 2026 pilot. Actual counts depend on API data density and seasonality.",
        "api_calls_made": 0,
        "date_range": {
            "start": str(start),
            "end": str(end),
            "plan_months": plan_months,
            "total_days": (end - start).days + 1,
        },
        "feed_breakdown": feed_breakdown,
        "totals": {
            "total_logical_windows": total_logical_windows,
            "min_api_calls_estimated": total_api_calls_lower,
            "note": "Actual API calls >= min estimate; depends on rows/page and pagination depth",
        },
        "projected_scale_estimated": {
            "basis": "August 2026 pilot empirical data (1 month)",
            "plan_months": plan_months,
            "est_tenders": estimated_tenders,
            "est_bidder_submissions": estimated_submissions,
            "est_contracts": estimated_contracts,
            "est_curated_mib": estimated_curated_mib,
            "est_curated_gib": round(estimated_curated_mib / 1024, 2),
            "caveat": "ESTIMATED: assumes uniform monthly density; real data has seasonal variation",
        },
        "page_size": page_size,
        "empirical_pilot_basis": pilot_empirical,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Plan 1-year historical KONEPS collection (zero API calls)"
    )
    parser.add_argument("--start", default="2025-09-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-08-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--page-size", type=int, default=500, help="Assumed page size for estimates")
    parser.add_argument("--json", action="store_true", help="Output raw JSON to stdout")
    args = parser.parse_args()

    from koneps_intel.parsers import parse_date
    start = parse_date(args.start)
    end = parse_date(args.end)

    if start > end:
        parser.error("--start must be <= --end")

    plan = plan_historical_collection(start, end, page_size=args.page_size)

    if args.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print("KONEPS 1-Year Historical Collection Plan (DRY RUN)")
        print(f"{'='*60}")
        print(f"Date range: {plan['date_range']['start']} → {plan['date_range']['end']}")
        print(f"Plan months: {plan['date_range']['plan_months']}")
        print(f"API calls made: {plan['api_calls_made']} (zero, this is a dry run)")
        print()
        print("Feed breakdown:")
        for feed, info in plan["feed_breakdown"].items():
            print(f"  {feed:12s}: {info['logical_windows']:6d} logical windows "
                  f"({info['num_calendar_windows']} × {info['num_division_codes']} codes), "
                  f"min {info['min_api_calls_estimated']} API calls")
        print()
        totals = plan["totals"]
        print(f"Total logical windows: {totals['total_logical_windows']}")
        print(f"Min API calls (ESTIMATED): {totals['min_api_calls_estimated']}")
        print()
        proj = plan["projected_scale_estimated"]
        print("Projected scale (ESTIMATED from August 2026 pilot):")
        print(f"  Tenders:            ~{proj['est_tenders']:>12,}")
        print(f"  Bidder submissions: ~{proj['est_bidder_submissions']:>12,}")
        print(f"  Contracts:          ~{proj['est_contracts']:>12,}")
        print(f"  Curated size:       ~{proj['est_curated_mib']:>12,.1f} MiB (~{proj['est_curated_gib']:.2f} GiB)")
        print()
        print(f"Note: {proj['caveat']}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
