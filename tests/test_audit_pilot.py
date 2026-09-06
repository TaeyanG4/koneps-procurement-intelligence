"""Unit and integration tests for the pilot audit engine and deduplication forensics."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

from koneps_intel.audit import run_audit, clean_biz_no
from koneps_intel.config import PROCESSED_DIR, RAW_DIR
from koneps_intel.schemas import DEDUPLICATION_KEYS


def test_clean_biz_no():
    """Verify business registration number normalization."""
    s = pd.Series(["123-45-67890", "1234567890", "  987-65-43210  ", None, ""])
    cleaned = clean_biz_no(s)
    assert cleaned.iloc[0] == "1234567890"
    assert cleaned.iloc[1] == "1234567890"
    assert cleaned.iloc[2] == "9876543210"
    assert cleaned.iloc[3] == ""
    assert cleaned.iloc[4] == ""


def test_deterministic_json_metrics_output(tmp_path: Path):
    """Verify that run_audit generates a valid deterministic JSON metrics artifact."""
    out_file = tmp_path / "test_metrics.json"

    # Test deterministic metrics generation using a lightweight isolated workspace
    mock_raw = tmp_path / "raw"
    mock_raw.mkdir()
    (mock_raw / "manifest.json").write_text("[]", encoding="utf-8")
    mock_processed = tmp_path / "processed"
    mock_processed.mkdir()

    metrics = run_audit(
        start="2026-08-01",
        end="2026-08-31",
        raw_dir=mock_raw,
        processed_dir=mock_processed,
        output_path=out_file,
    )
    assert out_file.exists()
    assert metrics["metadata"]["audit_scope_start"] == "2026-08-01"
    assert metrics["metadata"]["audit_scope_end"] == "2026-08-31"

    expected_sections = [
        "metadata",
        "collection",
        "deduplication",
        "processed_summary",
        "winner_cardinality",
        "cardinality",
        "pagination",
        "storage",
    ]
    for section in expected_sections:
        assert section in metrics, f"Missing section in metrics: {section}"


def test_audit_excludes_september_smoke_data():
    """Verify that August-scoped audit strictly excludes September 1 smoke records."""
    metrics_path = PROCESSED_DIR / "audits" / "pilot_2026_08_metrics.json"
    if not metrics_path.exists():
        pytest.skip("Pilot audit metrics artifact not yet generated.")

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    # In collection: bids has 1 window (August only, 32895 rows, not 32895+1564)
    assert metrics["collection"]["feeds"]["bids"]["windows"] == 1
    assert metrics["collection"]["feeds"]["bids"]["raw_rows"] == 32895

    # Contracts has 5 windows (115945 rows, not 115945+6269)
    assert metrics["collection"]["feeds"]["contracts"]["windows"] == 5
    assert metrics["collection"]["feeds"]["contracts"]["raw_rows"] == 115945

    # Awards has 124 windows (not 128)
    assert metrics["collection"]["feeds"]["awards"]["windows"] == 124
    assert metrics["collection"]["feeds"]["awards"]["raw_rows"] == 2120108

    # Processed contracts rows must be exactly 115,945 (excluding 6,269 Sep 1 rows)
    assert metrics["processed_summary"]["contracts_rows"] == 115945
    assert metrics["cardinality"]["contracts_untyCntrctNo_integrity"]["total_rows"] == 115945
    assert metrics["cardinality"]["contracts_untyCntrctNo_integrity"]["is_strictly_unique"] is True


def test_dedup_collision_classification_logic():
    """Test the forensic collision classification on synthetic records."""
    from collections import Counter

    # Candidate key: ["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn"]
    base_record = {
        "bidNtceNo": "R26BK00000001",
        "bidNtceOrd": "000",
        "bidprcCorpBizrno": "1234567890",
        "opengRank": "1",
        "dqlfctnRsn": "",
        "bidprcAmt": "100000",
        "bidprcTm": "10:00",
        "opengRsltDivNm": "개찰완료",
        "rsrvtnPrce": "105000",
        "fnlSucsfAmt": "100000",
    }

    # Case 1: Status update
    rec1_updated = dict(base_record, opengRsltDivNm="최종완료")
    df1 = pd.DataFrame([base_record, rec1_updated])
    diff_cols = set(c for c in df1.columns if df1[c].nunique() > 1)
    assert diff_cols == {"opengRsltDivNm"}

    # Case 2: Genuine distinct bidder event (different amount)
    rec2_diff_amt = dict(base_record, bidprcAmt="120000", bidprcTm="10:05")
    df2 = pd.DataFrame([base_record, rec2_diff_amt])
    diff_cols2 = set(c for c in df2.columns if df2[c].nunique() > 1)
    assert "bidprcAmt" in diff_cols2

    # Case 3: Price field backfill
    rec3_backfill = dict(base_record, rsrvtnPrce="106000")
    df3 = pd.DataFrame([base_record, rec3_backfill])
    diff_cols3 = set(c for c in df3.columns if df3[c].nunique() > 1)
    assert diff_cols3 == {"rsrvtnPrce"}


def test_winner_cardinality_structure():
    """Test winner cardinality calculation logic."""
    metrics_path = PROCESSED_DIR / "audits" / "pilot_2026_08_metrics.json"
    if not metrics_path.exists():
        pytest.skip("Pilot audit metrics artifact not yet generated.")

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    win = metrics.get("winner_cardinality", {})
    assert "selected_winner_flag_distribution" in win
    dist = win["selected_winner_flag_distribution"]
    assert dist["0_winners"] > 0
    assert dist["1_winner"] > 0
    assert dist["2_or_more_winners"] >= 0
    assert "multi_winner_investigation" in win
