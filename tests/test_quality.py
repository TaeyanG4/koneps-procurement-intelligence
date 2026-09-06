"""Unit tests for dataset quality validation and anomaly detection."""
from pathlib import Path
import pandas as pd
import pytest

from koneps_intel.quality import profile_dataframe, run_quality_checks


def test_profile_clean_dataframe():
    df = pd.DataFrame([
        {
            "bid_notice_no": "20260901001",
            "bid_amount_krw": 1000000.0,
            "bid_rate": 88.5,
            "is_winner": True,
        },
        {
            "bid_notice_no": "20260901002",
            "bid_amount_krw": 2000000.0,
            "bid_rate": 91.2,
            "is_winner": False,
        },
    ])
    prof = profile_dataframe(df, "clean_test")
    assert prof["rows"] == 2
    assert prof["columns"] == 4
    assert len(prof["critical_failures"]) == 0
    assert prof["key_candidates"]["bid_notice_no"]["unique_count"] == 2
    assert prof["key_candidates"]["bid_notice_no"]["duplicate_count"] == 0


def test_detect_negative_monetary_anomalies():
    df = pd.DataFrame([
        {
            "bid_notice_no": "20260901001",
            "bid_amount_krw": -50000.0,
            "bid_rate": 88.5,
        }
    ])
    prof = profile_dataframe(df, "bad_money_test")
    assert len(prof["critical_failures"]) > 0
    assert any("negative monetary amounts" in msg for msg in prof["critical_failures"])


def test_detect_impossible_rates():
    df = pd.DataFrame([
        {
            "bid_notice_no": "20260901001",
            "bid_rate": 999.0,  # Impossible percentage
        }
    ])
    prof = profile_dataframe(df, "bad_rate_test")
    assert "invalid_rate_counts" in prof["anomalies"]
    assert prof["anomalies"]["invalid_rate_counts"]["bid_rate"] == 1


def test_run_quality_checks_on_file(tmp_path):
    parquet_path = tmp_path / "test.parquet"
    df = pd.DataFrame([{"bid_notice_no": "B01", "estimated_price_krw": 10000.0}])
    df.to_parquet(parquet_path)

    report_out = tmp_path / "report.json"
    reports, has_critical = run_quality_checks([parquet_path], output_report_path=report_out)

    assert not has_critical
    assert len(reports) == 1
    assert report_out.exists()
