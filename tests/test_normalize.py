"""Unit tests for normalization, aliasing, and Parquet creation."""
import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from koneps_intel.normalize import (
    build_feed_parquet,
    clean_boolean,
    clean_numeric,
    ingest_bidder_report,
    normalize_feed_frame,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_clean_numeric():
    s = pd.Series(["1,000", " 250 ", "88.5%", "invalid", None])
    cleaned = clean_numeric(s)
    assert cleaned[0] == 1000.0
    assert cleaned[1] == 250.0
    assert cleaned[2] == 88.5
    assert pd.isna(cleaned[3])
    assert pd.isna(cleaned[4])


def test_clean_boolean():
    s = pd.Series(["Y", "N", "\uc5ec", "\ubd80", "1", "0"])
    cleaned = clean_boolean(s)
    assert cleaned.tolist() == [True, False, True, False, True, False]


def test_normalize_feed_frame():
    title = "\ube45\ub370\uc774\ud130 \ud50c\ub7ab\ud3fc \uad6c\ucd95"
    df = pd.DataFrame([
        {
            "bidNtceNo": "20260901001",
            "bidNtceNm": title,
            "asignBdgtAmt": "1,000,000,000",
            "presmPtce": "900,000,000",
        }
    ])
    norm = normalize_feed_frame(df, "bids")

    # Korean columns preserved
    assert norm["bidNtceNm"].iloc[0] == title
    # English aliases added
    assert norm["bid_title_ko"].iloc[0] == title
    assert norm["bid_notice_no"].iloc[0] == "20260901001"
    # Numeric values cleaned
    assert norm["assigned_budget_krw"].iloc[0] == 1000000000.0
    assert norm["estimated_price_krw"].iloc[0] == 900000000.0


def test_build_feed_parquet(tmp_path):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    # Create dummy raw window file
    bids_raw = raw_dir / "bids"
    bids_raw.mkdir(parents=True, exist_ok=True)
    sample_file = bids_raw / "bids_all_20260901_20260930.jsonl.gz"

    meta = {"window_start": "2026-09-01", "window_end": "2026-09-30", "business_code": None}
    item = {"bidNtceNo": "20260901001", "bidNtceOrd": "00", "bidClsfcNo": "01", "rbidNo": "0", "bidNtceNm": "test"}

    with gzip.open(sample_file, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"__collector_meta__": meta}) + "\n")
        f.write(json.dumps(item) + "\n")

    report = build_feed_parquet(raw_dir, processed_dir, "bids", partition_by_date=True)
    assert report["parquet_parts"] == 1
    assert report["rows_after_dedupe"] == 1

    expected_parquet = processed_dir / "bids" / "year=2026" / "month=09" / "bids_all_20260901_20260930.parquet"
    assert expected_parquet.exists()

    df = pd.read_parquet(expected_parquet)
    assert len(df) == 1
    assert df["bid_notice_no"].iloc[0] == "20260901001"


def test_ingest_bidder_report(tmp_path):
    csv_file = FIXTURES_DIR / "sample_bidder_report.csv"
    out_parquet = tmp_path / "bidder_outcomes.parquet"

    df = ingest_bidder_report(csv_file, out_parquet)
    assert out_parquet.exists()
    assert len(df) == 2
    assert "bidder_name_ko" in df.columns
    assert "bid_amount_krw" in df.columns
    assert df["bid_amount_krw"].iloc[0] == 1200000000.0
    assert bool(df["is_selected_winner"].iloc[0]) is True
    assert bool(df["is_selected_winner"].iloc[1]) is False
