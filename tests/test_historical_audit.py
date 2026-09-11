import pandas as pd

from koneps_intel.historical_audit import audit_processed_feed, canonical_raw_plan


def test_audit_processed_feed_detects_clean_scoped_bids(tmp_path):
    processed = tmp_path / "processed"
    out_dir = processed / "bids" / "year=2026" / "month=08"
    out_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "bidNtceNo": ["A", "B"],
            "bidNtceOrd": ["00", "00"],
            "bid_notice_date": pd.to_datetime(["2026-08-01", "2026-08-02"]),
            "assigned_budget_krw": [100, 200],
            "_source_file": ["bids_all_20260801_20260831.jsonl.gz"] * 2,
            "_window_start": ["2026-08-01"] * 2,
            "_window_end": ["2026-08-31"] * 2,
        }
    )
    df.to_parquet(out_dir / "part.parquet", index=False)

    result = audit_processed_feed(processed, "bids", "2026-08-01", "2026-08-31", processed / ".tmp")
    assert result["rows"] == 2
    assert result["effective_deduplication_keys"] == ["bidNtceNo", "bidNtceOrd"]
    assert result["global_key_duplicate_hashes"] == 0
    assert result["source_window_violations"] == 0
    assert result["critical_failures"] == []


def test_canonical_raw_plan_reports_expected_single_month_bid_file(tmp_path):
    raw = tmp_path / "raw"
    for feed in ("bids", "awards", "contracts"):
        (raw / feed).mkdir(parents=True)

    # This test only needs to prove a missing plan is surfaced deterministically.
    (raw / "manifest.json").write_text("[]", encoding="utf-8")
    result = canonical_raw_plan(raw, "2026-08-01", "2026-08-31")
    assert result["complete"] is False
    assert result["canonical_windows"] == 130
    assert "bids_all_20260801_20260831.jsonl.gz" in result["missing_manifest_entries"]
    assert "bids_all_20260801_20260831.jsonl.gz" in result["missing_raw_files"]


def test_negative_contract_amount_is_source_warning_not_integrity_failure(tmp_path):
    processed = tmp_path / "processed"
    out_dir = processed / "contracts" / "year=2026" / "month=06"
    out_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "untyCntrctNo": ["C-1"],
            "cntrctNo": ["C"],
            "cntrctOrd": ["02"],
            "contract_date": pd.to_datetime(["2026-06-22"]),
            "contract_amount_krw": [-5000],
            "total_contract_amount_krw": [-5000],
            "_source_file": ["contracts_all_20260622_20260628.jsonl.gz"],
            "_window_start": ["2026-06-22"],
            "_window_end": ["2026-06-28"],
        }
    )
    df.to_parquet(out_dir / "part.parquet", index=False)

    result = audit_processed_feed(
        processed,
        "contracts",
        "2026-06-22",
        "2026-06-28",
        processed / ".tmp",
    )

    assert result["negative_monetary_counts"] == {
        "contract_amount_krw": 1,
        "total_contract_amount_krw": 1,
    }
    assert result["critical_failures"] == []
    assert len(result["data_warnings"]) == 1
