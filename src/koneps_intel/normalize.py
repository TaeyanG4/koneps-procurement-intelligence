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


DATETIME_COLUMNS = [
    "bid_notice_date",
    "bid_notice_begin_datetime",
    "bid_notice_end_datetime",
    "opening_datetime",
    "contract_date",
    "bid_submission_date",
    "opening_date",
    "award_date",
    "bidNtceDt",
    "bidNtceDate",
    "bidNtceBgnDate",
    "bidNtceEndDate",
    "bidBeginDate",
    "bidClseDate",
    "opengDate",
    "cntrctDate",
    "cntrctCnclsDate",
    "bidprcDate",
    "fnlSucsfDate",
]


def clean_datetime(series: pd.Series) -> pd.Series:
    """Convert string date/datetime series to datetime64[ns], coercing invalid formats to NaT."""
    if series.empty:
        return series
    cleaned_str = series.astype("string").str.strip()
    return pd.to_datetime(cleaned_str, format="mixed", errors="coerce")


def clean_boolean(series: pd.Series) -> pd.Series:
    """Map Korean/English boolean indicators to nullable boolean series (dtype='boolean')."""
    if series.empty:
        return series.astype("boolean")
    if isinstance(series.dtype, pd.BooleanDtype):
        return series

    bool_map = {
        "Y": True, "y": True, "1": True, "여": True, "TRUE": True, "True": True, "true": True,
        "N": False, "n": False, "0": False, "부": False, "FALSE": False, "False": False, "false": False,
    }
    cleaned_str = series.astype("string").str.strip()
    return cleaned_str.map(bool_map).astype("boolean")


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
        "asignBdgtAmt", "presmPtce", "presmptPrce", "bsisAmt", "bssAmt", "rsrvtnPrce",
        "sucsfbidAmt", "sucsfbidRate", "sucsfbidLwltRate", "sucsfLwstlmtRt",
        "fnlSucsfAmt", "fnlSucsfRt", "bidprcAmt", "bidprcRt", "cntrctAmt", "totCntrctAmt",
        "ttalCntrctAmt",
    ]
    for col in df.columns:
        if col in numeric_cols or col.endswith("_krw") or col.endswith("_rate"):
            df[col] = clean_numeric(df[col])
        elif col in DATETIME_COLUMNS or col.endswith("_datetime") or col.endswith("_date"):
            df[col] = clean_datetime(df[col])
        elif col.startswith("is_") or col.endswith("Yn") or col.endswith("_yn"):
            df[col] = clean_boolean(df[col])

    # Ensure registration numbers and codes remain clean strings with leading zeros
    str_cols = [
        "bidNtceNo", "bid_notice_no", "bizno", "winner_business_registration_no",
        "contractor_business_registration_no", "bidder_business_registration_no",
        "bidprcCorpBizrno", "fnlSucsfCorpBizrno", "rprsntCorpBizrno",
        "ntceInsttCd", "notice_agency_code", "dminsttCd", "demand_agency_code",
        "dmndInsttCd", "cntrctInsttCd", "contract_agency_code",
        "untyCntrctNo", "unified_contract_no", "cntrctNo", "contract_no",
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

    primary_date_cols = {
        "bids": ["bid_notice_date", "bidNtceDt", "bidNtceDate", "bid_notice_begin_datetime", "bidNtceBgnDate"],
        "awards": ["opening_datetime", "opengDate", "bid_notice_date", "bidNtceDt", "bidNtceDate"],
        "contracts": ["contract_date", "cntrctCnclsDate", "cntrctDate"],
    }

    for path in files:
        meta, rows = RawStorage.read_window(path)
        if not rows:
            continue

        win_start = str(meta.get("window_start", ""))
        default_year = win_start[:4] if len(win_start) >= 4 and win_start[:4].isdigit() else "unknown"
        default_month = win_start[5:7] if len(win_start) >= 7 and win_start[5:7].isdigit() else "01"

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

        if not partition_by_date:
            out_file = base_out / path.name.replace(".jsonl.gz", ".parquet")
            if not out_file.exists() or force:
                df.to_parquet(out_file, index=False, compression="zstd")
                parts_written += 1
                logger.info("WRITE %s (rows=%d)", out_file, len(df))
            else:
                parts_written += 1
            continue

        # Row-level event-date partitioning
        date_candidates = primary_date_cols.get(feed, [])
        event_col = None
        for c in date_candidates:
            if c in df.columns:
                event_col = c
                break

        if event_col:
            parsed_dates = pd.to_datetime(df[event_col], errors="coerce")
            row_years = parsed_dates.dt.year.fillna(-1).astype(int).apply(
                lambda y: f"{y:04d}" if y > 0 else default_year
            )
            row_months = parsed_dates.dt.month.fillna(-1).astype(int).apply(
                lambda m: f"{m:02d}" if m > 0 else default_month
            )
        else:
            row_years = pd.Series([default_year] * len(df), index=df.index)
            row_months = pd.Series([default_month] * len(df), index=df.index)

        df["_part_year"] = row_years
        df["_part_month"] = row_months

        for (year, month), sub_df in df.groupby(["_part_year", "_part_month"], sort=False):
            out_dir = base_out / f"year={year}" / f"month={month}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / path.name.replace(".jsonl.gz", ".parquet")

            if out_file.exists() and not force:
                parts_written += 1
                continue

            write_df = sub_df.drop(columns=["_part_year", "_part_month"])
            write_df.to_parquet(out_file, index=False, compression="zstd")
            parts_written += 1
            logger.info("WRITE %s (rows=%d)", out_file, len(write_df))

        df.drop(columns=["_part_year", "_part_month"], inplace=True)

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

    # Date cleaning
    date_aliases = ["bid_submission_date", "contract_date", "bid_notice_date", "opening_date", "opening_datetime"]
    for col in date_aliases:
        if col in df.columns:
            df[col] = clean_datetime(df[col])

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
