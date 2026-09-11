#!/usr/bin/env python3
"""Streaming QA for the 12-month KONEPS historical build."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.historical_audit import run_historical_audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a large KONEPS historical build without full-table concatenation")
    parser.add_argument("--start", required=True, help="Scope start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Scope end date (YYYY-MM-DD)")
    parser.add_argument("--raw", default="data/raw", help="Raw data root")
    parser.add_argument("--processed", required=True, help="Historical processed build root")
    parser.add_argument("--output", default=None, help="QA JSON output path")
    args = parser.parse_args()

    processed = Path(args.processed)
    output = Path(args.output) if args.output else processed / "historical_qa.json"
    result = run_historical_audit(Path(args.raw), processed, args.start, args.end, output)

    summary = result["summary"]
    print("=== KONEPS HISTORICAL QA ===")
    print(f"scope              : {args.start} .. {args.end}")
    print(f"canonical windows  : {summary['canonical_windows']:,}")
    print(f"canonical raw rows : {summary['canonical_raw_rows']:,}")
    print(f"processed rows     : {summary['processed_rows']:,}")
    print(f"parquet files      : {summary['processed_parquet_files']:,}")
    print(f"processed bytes    : {summary['processed_bytes']:,}")
    print(f"passed             : {summary['passed']}")
    if summary["critical_failures"]:
        for failure in summary["critical_failures"]:
            print(f"FAIL: {failure}")
        raise SystemExit(1)
    print(f"report             : {output}")


if __name__ == "__main__":
    main()
