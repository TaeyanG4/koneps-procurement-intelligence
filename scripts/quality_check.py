#!/usr/bin/env python3
"""CLI script for dataset quality checks and cardinality profiling."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src is on python path for direct CLI script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.config import PROCESSED_DIR
from koneps_intel.quality import run_quality_checks
from koneps_intel.utils import get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile Parquet datasets and verify quality")
    parser.add_argument("paths", nargs="+", help="Paths to Parquet files or directories to check")
    parser.add_argument(
        "--output",
        default=str(PROCESSED_DIR / "quality_report.json"),
        help="Path to output JSON report",
    )
    parser.add_argument("--strict", action="store_true", help="Exit with non-zero status on critical issues")
    args = parser.parse_args()

    logger = get_logger("koneps_quality")
    target_files: list[Path] = []
    for p in args.paths:
        path_obj = Path(p)
        if path_obj.is_dir():
            target_files.extend(sorted(path_obj.glob("**/*.parquet")))
        elif path_obj.exists():
            target_files.append(path_obj)
        else:
            # Maybe glob pattern on Windows shell
            parent = path_obj.parent if path_obj.parent != Path("") else Path(".")
            target_files.extend(sorted(parent.glob(path_obj.name)))

    if not target_files:
        logger.error("No valid Parquet files found matching specified paths.")
        sys.exit(1)

    out_path = Path(args.output)
    reports, has_critical = run_quality_checks(
        paths=target_files,
        output_report_path=out_path,
        fail_on_critical=args.strict,
    )

    print(json.dumps(reports, ensure_ascii=False, indent=2))
    logger.info("Checked %d files. Critical issues detected: %s", len(target_files), has_critical)
    logger.info("Full quality report written to %s", out_path.resolve())

    if has_critical and args.strict:
        logger.error("Quality verification failed with critical anomalies.")
        sys.exit(1)


if __name__ == "__main__":
    main()
