#!/usr/bin/env python3
"""CLI script to ingest official bidder outcome reports (CSV, XLS, XLSX) into Parquet."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src is on python path for direct CLI script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.config import PROCESSED_DIR
from koneps_intel.normalize import ingest_bidder_report
from koneps_intel.utils import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert official KONEPS bidder report to Parquet")
    parser.add_argument("input", help="Path to exported CSV, XLS, or XLSX file")
    parser.add_argument(
        "--output",
        default=str(PROCESSED_DIR / "bidder_outcomes" / "bidder_outcomes.parquet"),
        help="Target Parquet output path",
    )
    args = parser.parse_args()

    logger = get_logger("koneps_bidder_ingest")
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file does not exist: %s", input_path)
        raise SystemExit(1)

    output_path = Path(args.output)
    try:
        df = ingest_bidder_report(input_path=input_path, output_path=output_path)
        logger.info("Successfully ingested %d rows, %d columns into %s", len(df), len(df.columns), output_path)
    except Exception as exc:
        logger.exception("Failed to ingest bidder report: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
