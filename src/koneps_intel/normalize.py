"""Data normalization and Parquet conversion pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from koneps_intel.schemas import (
    AWARDS_API_ALIASES,
    BIDDER_REPORT_ALIASES,
    BIDS_API_ALIASES,
    CONTRACTS_API_ALIASES,
    CONTROLLED_CATEGORIES,
    DEDUPLICATION_KEYS,
)
from koneps_intel.storage import RawStorage
from koneps_intel.utils import get_logger

FEED_ALIASES: Dict[str, Dict[str, str]] = {
    "bids": BIDS_API_ALIASES,
    "awards": AWARDS_API_ALIASES,
    "contracts": CONTRACTS_API_ALIASES,
}


def clean_numeric(series: pd.Series) -> pd.Series:
    """Clean monetary amounts, ranks, and percentages into numeric values."""
    if series.empty:
        return series
    return pd.to_numeric(
        series.astype("string")
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


def clean_boolean(series: pd.Series) -> pd.Series:
    """Map Korean/English boolean indicators to boolean series."""
    mapping = CONTROLLED_CATEGORIES["boolean_yn"]
    cleaned = series.astype("string").str.strip().map(mapping)
    return cleaned == "true"


def dedupe_frame(df: pd.DataFrame, feed: str) -> Tuple[pd.DataFrame, List[str]]:
    """Deduplicate records based on candidate grain keys or full row fingerprint."""
    keys = [c for c in DEDUPLICATION_KEYS.get(feed, []) if c in df.columns]
    if keys:
        return df.drop_duplicates(subset=keys, keep="last"), keys
    if len(df):
        fingerprints = df.astype(str).agg("\x1f".join, axis=1)
        df = df.loc[~fingerprints.duplicated(keep="last")]
    return df, []


def normalize_feed_frame(df: pd.DataFrame, feed: str) -> pd.DataFrame:
    """Apply canonical English aliases and type coercions while preserving Korean columns."""
    aliases = FEED_ALIASES.get(feed, {})
    for src_col, alias in aliases.items():
        if src_col in df.columns and alias not in df.columns:
            df[alias] = df[src_col]

    # Numeric amount columns to coerce
    numeric_cols = [
        "allocated_budget_krw", "assigned_budget_krw", "estimated_price_krw",
        "base_amount_krw", "scheduled_price_krw", "opening_rank", "bid_amount_krw",
        "bid_rate", "award_amount_krw", "award_rate", "award_lower_limit_rate",
        "contract_amount_krw", "total_contract_amount_krw", "current_contract_amount_krw",
        "asignBdgtAmt", "presmPtce", "bsisAmt", "sucsfbidAmt", "sucsfbidRate",
        "cntrctAmt", "totCntrctAmt",
    ]
    for col in df.columns:
        if col in numeric_cols or col.endswith("_krw") or col.endswith("_rate"):
            df[col] = clean_numeric(df[col])

    # Ensure registration numbers and codes remain clean strings with leading zeros
    str_cols = [
        "bidNtceNo", "bid_notice_no", "bizno", "winner_business_registration_no",
        "contractor_business_registration_no", "bidder_business_registration_no",
        "ntceInsttCd", "notice_agency_code", "dminsttCd", "demand_agency_code",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()

    return df


def build_feed_parquet(
    raw_root: Path,
    processed_root: Path,
    feed: str,
    force: bool = False,
    partition_by_date: bool = True,
) -> Dict[str, Any]:
    """Convert raw window JSONL archives to typed, partitioned Parquet datasets."""
    logger = get_logger("koneps_intel.normalize")
    files = sorted((raw_root / feed).glob("*.jsonl.gz"))
    base_out = processed_root / feed
    base_out.mkdir(parents=True, exist_ok=True)

    total_before = total_after = 0
    columns_seen: set[str] = set()
    parts_written = 0

    for path in files:
        meta, rows = RawStorage.read_window(path)
        if not rows:
            continue

        win_start = meta.get("window_start", "")
        year = win_start[:4] if len(win_start) >= 4 else "unknown"
        month = win_start[5:7] if len(win_start) >= 7 else "01"

        if partition_by_date:
            out_dir = base_out / f"year={year}" / f"month={month}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / path.name.replace(".jsonl.gz", ".parquet")
        else:
            out_file = base_out / path.name.replace(".jsonl.gz", ".parquet")

        if out_file.exists() and not force:
            parts_written += 1
            continue

        df = pd.DataFrame(rows)
        total_before += len(df)
        df, _ = dedupe_frame(df, feed)
        df = normalize_feed_frame(df, feed)
        total_after += len(df)
        columns_seen.update(map(str, df.columns))

        df["_source_file"] = path.name
        df["_window_start"] = meta.get("window_start")
        df["_window_end"] = meta.get("window_end")
        df["_business_code"] = meta.get("business_code")

        df.to_parquet(out_file, index=False, compression="zstd")
        parts_written += 1
        logger.info("WRITE %s (rows=%d)", out_file, len(df))

    return {
        "feed": feed,
        "raw_files": len(files),
        "parquet_parts": parts_written,
        "rows_before_dedupe": total_before,
        "rows_after_dedupe": total_after,
        "columns_seen": sorted(columns_seen),
        "output_directory": str(base_out),
    }


def ingest_bidder_report(
    input_path: Path,
    output_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Robustly ingest official KONEPS bidder outcome reports in CSV or Excel format."""
    logger = get_logger("koneps_intel.bidder_report")
    suffix = input_path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(input_path, dtype=str)
    elif suffix == ".csv":
        df = None
        for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
            try:
                df = pd.read_csv(input_path, dtype=str, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise RuntimeError(f"Could not decode CSV file {input_path} with standard Korean encodings.")
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .csv, .xlsx, .xls")

    # Clean header whitespace and newlines
    df.columns = [str(c).replace("\r", "").replace("\n", "").strip() for c in df.columns]

    # Map aliases
    missing_expected = [ko for ko in BIDDER_REPORT_ALIASES if ko not in df.columns]
    for ko, en in BIDDER_REPORT_ALIASES.items():
        if ko in df.columns:
            df[en] = df[ko]

    # Numeric cleaning
    numeric_aliases = [
        "allocated_budget_krw", "estimated_price_krw", "base_amount_krw", "scheduled_price_krw",
        "opening_rank", "bid_amount_krw", "bid_rate", "current_contract_amount_krw", "total_contract_amount_krw",
    ]
    for col in df.columns:
        if col in numeric_aliases or col.endswith("_krw") or col.endswith("_rate"):
            df[col] = clean_numeric(df[col])

    # Clean boolean flags
    boolean_aliases = ["is_failed_bid", "is_selected_winner", "is_disqualified", "is_it_project", "is_urgent_notice"]
    for col in boolean_aliases:
        if col in df.columns:
            df[col] = clean_boolean(df[col])

    # Ensure biz registration no is string
    if "bidder_business_registration_no" in df.columns:
        df["bidder_business_registration_no"] = df["bidder_business_registration_no"].astype("string").str.strip()

    out_file = output_path or Path("data/processed/bidder_outcomes/bidder_outcomes.parquet")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_file, index=False, compression="zstd")

    logger.info("INGEST Bidder report saved to %s (rows=%d, cols=%d)", out_file, len(df), len(df.columns))
    if missing_expected:
        logger.warning("%d expected Korean columns were not in export: %s", len(missing_expected), missing_expected[:5])

    return df
