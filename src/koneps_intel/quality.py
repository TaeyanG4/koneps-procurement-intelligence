"""Data quality, cardinality inspection, and integrity checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from koneps_intel.utils import get_logger


def profile_dataframe(df: pd.DataFrame, source_name: str) -> Dict[str, Any]:
    """Profile a DataFrame for quality metrics, cardinality, and anomalies."""
    rows = int(len(df))
    cols = int(len(df.columns))

    out: Dict[str, Any] = {
        "source": source_name,
        "rows": rows,
        "columns": cols,
        "duplicate_full_rows": int(df.astype(str).duplicated().sum()) if rows else 0,
        "key_candidates": {},
        "null_fraction_top20": {},
        "anomalies": {},
        "critical_failures": [],
    }

    if rows == 0:
        out["critical_failures"].append("Dataset contains 0 rows.")
        return out

    # Inspect key candidates
    key_fields = [
        "bidNtceNo", "bid_notice_no", "contract_no", "cntrctNo",
        "untyCntrctNo", "unified_contract_no", "bizno",
        "bidder_business_registration_no", "winner_business_registration_no",
    ]
    for key in key_fields:
        if key in df.columns:
            s = df[key].dropna()
            total_valid = int(len(s))
            n_unique = int(s.nunique())
            dup_count = int(s.duplicated().sum())
            out["key_candidates"][key] = {
                "non_null_count": total_valid,
                "null_ratio": round(float((rows - total_valid) / rows), 6),
                "unique_count": n_unique,
                "duplicate_count": dup_count,
            }

    # Null fractions
    nulls = df.isna().mean().sort_values(ascending=False).head(20)
    out["null_fraction_top20"] = {str(k): round(float(v), 6) for k, v in nulls.items()}

    # Anomaly checks on numeric amounts
    monetary_cols = [c for c in df.columns if any(m in c.lower() for m in ["amt", "price", "krw", "budget"])]
    negative_counts: Dict[str, int] = {}
    for col in monetary_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            neg = int((df[col] < 0).sum())
            if neg > 0:
                negative_counts[col] = neg
                out["critical_failures"].append(f"Column '{col}' has {neg} negative monetary amounts.")
    out["anomalies"]["negative_monetary_counts"] = negative_counts

    # Rate / percentage checks
    rate_cols = [c for c in df.columns if "rate" in c.lower() or "?" in c]
    invalid_rates: Dict[str, int] = {}
    for col in rate_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            # Bid rates typically between 50% and 150%, certainly >= 0
            bad = int(((df[col] < 0) | (df[col] > 500)).sum())
            if bad > 0:
                invalid_rates[col] = bad
                out["anomalies"]["invalid_rate_counts"] = invalid_rates

    return out


def profile_file(path: Path) -> Dict[str, Any]:
    """Read a Parquet file and profile its contents."""
    try:
        df = pd.read_parquet(path)
        return profile_dataframe(df, str(path))
    except Exception as exc:
        return {
            "source": str(path),
            "rows": 0,
            "columns": 0,
            "critical_failures": [f"Failed to read file {path.name}: {exc}"],
        }


def run_quality_checks(
    paths: List[Path],
    output_report_path: Optional[Path] = None,
    fail_on_critical: bool = True,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Run quality checks on multiple files and optionally output a report."""
    logger = get_logger("koneps_intel.quality")
    reports: List[Dict[str, Any]] = []
    has_critical = False

    for path in paths:
        rep = profile_file(path)
        reports.append(rep)
        if rep.get("critical_failures"):
            has_critical = True
            for failure in rep["critical_failures"]:
                logger.error("CRITICAL [%s]: %s", path.name, failure)

    if output_report_path:
        output_report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_report_path, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
        logger.info("Quality report saved to %s", output_report_path)

    return reports, has_critical
