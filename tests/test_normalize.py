"""Unit tests for normalization, aliasing, and Parquet creation."""
import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from koneps_intel.normalize import (
    build_feed_parquet,
    clean_boolean,
    clean_datetime,
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


def test_clean_boolean_nullable():
    s = pd.Series(["Y", "N", "여", "부", "1", "0", None, "", "invalid", "TRUE", "false"])
    cleaned = clean_boolean(s)
    assert cleaned.dtype.name == "boolean"
    assert cleaned.iloc[0] is True or cleaned.iloc[0] == True
    assert cleaned.iloc[1] is False or cleaned.iloc[1] == False
    assert cleaned.iloc[2] is True or cleaned.iloc[2] == True
    assert cleaned.iloc[3] is False or cleaned.iloc[3] == False
    assert cleaned.iloc[4] is True or cleaned.iloc[4] == True
    assert cleaned.iloc[5] is False or cleaned.iloc[5] == False
    assert pd.isna(cleaned.iloc[6])
    assert pd.isna(cleaned.iloc[7])
    assert pd.isna(cleaned.iloc[8])
    assert cleaned.iloc[9] is True or cleaned.iloc[9] == True
    assert cleaned.iloc[10] is False or cleaned.iloc[10] == False


def test_clean_datetime():
    s = pd.Series(["2026-09-01 10:00:00", "2026-09-01", "20260901", None, "", "invalid"])
    cleaned = clean_datetime(s)
    assert pd.api.types.is_datetime64_any_dtype(cleaned)
    assert cleaned.iloc[0] == pd.Timestamp("2026-09-01 10:00:00")
    assert cleaned.iloc[1] == pd.Timestamp("2026-09-01 00:00:00")
    assert cleaned.iloc[2] == pd.Timestamp("2026-09-01 00:00:00")
    assert pd.isna(cleaned.iloc[3])
    assert pd.isna(cleaned.iloc[4])
    assert pd.isna(cleaned.iloc[5])


def test_build_feed_parquet_cross_month_partitioning(tmp_path):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    bids_raw = raw_dir / "bids"
    bids_raw.mkdir(parents=True, exist_ok=True)
    sample_file = bids_raw / "bids_goods_20260829_20260904.jsonl.gz"

    meta = {"window_start": "2026-08-29", "window_end": "2026-09-04", "business_code": "1"}
    # One item in August, one item in September
    item_aug = {
        "bidNtceNo": "20260831001",
        "bidNtceOrd": "00",
        "bidClsfcNo": "01",
        "rbidNo": "0",
        "bidNtceDt": "2026-08-31 10:00:00",
        "bidNtceNm": "August Bid",
    }
    item_sep = {
        "bidNtceNo": "20260901001",
        "bidNtceOrd": "00",
        "bidClsfcNo": "01",
        "rbidNo": "0",
        "bidNtceDt": "2026-09-01 09:30:00",
        "bidNtceNm": "September Bid",
    }

    with gzip.open(sample_file, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"__collector_meta__": meta}) + "\n")
        f.write(json.dumps(item_aug) + "\n")
        f.write(json.dumps(item_sep) + "\n")

    report = build_feed_parquet(raw_dir, processed_dir, "bids", partition_by_date=True)
    assert report["parquet_parts"] == 2
    assert report["rows_after_dedupe"] == 2

    aug_parquet = processed_dir / "bids" / "year=2026" / "month=08" / "bids_goods_20260829_20260904.parquet"
    sep_parquet = processed_dir / "bids" / "year=2026" / "month=09" / "bids_goods_20260829_20260904.parquet"

    assert aug_parquet.exists()
    assert sep_parquet.exists()

    df_aug = pd.read_parquet(aug_parquet)
    assert len(df_aug) == 1
    assert df_aug["bid_notice_no"].iloc[0] == "20260831001"

    df_sep = pd.read_parquet(sep_parquet)
    assert len(df_sep) == 1
    assert df_sep["bid_notice_no"].iloc[0] == "20260901001"


def test_ingest_bidder_report_xlsx(tmp_path):
    # Create sample xlsx
    data = {
        "입찰공고번호": ["20260901001"],
        "공고명": ["테스트 입찰공고"],
        "업체명": ["(주)테스트"],
        "투찰금액": ["500,000,000"],
        "낙찰자선정여부": ["Y"],
        "투찰일자": ["2026-09-01 10:00:00"],
    }
    df_raw = pd.DataFrame(data)
    xlsx_path = tmp_path / "sample_report.xlsx"
    df_raw.to_excel(xlsx_path, index=False)

    out_parquet = tmp_path / "out.parquet"
    df_out = ingest_bidder_report(xlsx_path, out_parquet)

    assert out_parquet.exists()
    assert len(df_out) == 1
    assert df_out["bidder_name_ko"].iloc[0] == "(주)테스트"
    assert df_out["bid_amount_krw"].iloc[0] == 500000000.0
    assert df_out["is_selected_winner"].iloc[0] is True or df_out["is_selected_winner"].iloc[0] == True
    assert pd.api.types.is_datetime64_any_dtype(df_out["bid_submission_date"])


def test_ingest_bidder_report_real_xls(tmp_path):
    xls_file = FIXTURES_DIR / "sample_bidder_report.xls"
    out_parquet = tmp_path / "real_xls_out.parquet"

    df = ingest_bidder_report(xls_file, out_parquet)
    assert out_parquet.exists()
    assert len(df) == 2

    # Canonical aliases generated
    assert "bid_notice_no" in df.columns
    assert "opening_date" in df.columns
    assert "bidder_name_ko" in df.columns
    assert "bid_amount_krw" in df.columns
    assert "is_selected_winner" in df.columns

    # opening_date normalized to datetime64[ns]
    assert pd.api.types.is_datetime64_any_dtype(df["opening_date"])
    assert df["opening_date"].iloc[0] == pd.Timestamp("2026-09-01")

    # Numeric and boolean types correctly coerced
    assert df["bid_amount_krw"].iloc[0] == 850000000
    assert df["is_selected_winner"].dtype.name == "boolean"
    assert bool(df["is_selected_winner"].iloc[0]) is True
    assert bool(df["is_selected_winner"].iloc[1]) is False

    # Parquet round-trip preserves datetime-compatible type
    df_pq = pd.read_parquet(out_parquet)
    assert pd.api.types.is_datetime64_any_dtype(df_pq["opening_date"])
    assert df_pq["opening_date"].iloc[0] == pd.Timestamp("2026-09-01")
