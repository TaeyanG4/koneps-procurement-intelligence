"""Unit and integration tests for the pilot audit engine, deduplication forensics, and relational grains."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

from koneps_intel.audit import run_audit, clean_biz_no
from koneps_intel.config import PROJECT_ROOT
from koneps_intel.privacy import generate_supplier_id
from koneps_intel.schemas import DEDUPLICATION_KEYS

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "audit"
DOCS_METRICS_PATH = PROJECT_ROOT / "docs" / "metrics" / "pilot_2026_08.json"


def test_clean_biz_no():
    """Verify business registration number normalization."""
    s = pd.Series(["123-45-67890", "1234567890", "  987-65-43210  ", None, ""])
    cleaned = clean_biz_no(s)
    assert cleaned.iloc[0] == "1234567890"
    assert cleaned.iloc[1] == "1234567890"
    assert cleaned.iloc[2] == "9876543210"
    assert cleaned.iloc[3] == ""
    assert cleaned.iloc[4] == ""


def test_supplier_public_id_policy():
    """Verify non-enumerable supplier ID generation with HMAC-SHA256."""
    fake_key = b"test_secret_salt_key_12345"
    id1 = generate_supplier_id("123-45-67890", fake_key)
    id2 = generate_supplier_id("1234567890", fake_key)
    id3 = generate_supplier_id("987-65-43210", fake_key)

    assert id1.startswith("SUP_")
    assert len(id1) == 36  # "SUP_" (4) + 32 hex chars
    assert id1 == id2, "Normalized biz nos must produce identical supplier IDs"
    assert id1 != id3, "Different biz nos must produce distinct supplier IDs"
    # Invalid or incomplete inputs must return empty string
    assert generate_supplier_id("", fake_key) == ""
    assert generate_supplier_id(None, fake_key) == ""
    assert generate_supplier_id("12345", fake_key) == "", "Less than 10 digits must be rejected"
    assert generate_supplier_id("12345678901", fake_key) == "", "More than 10 digits must be rejected"
    assert generate_supplier_id("abcdefghij", fake_key) == "", "Non-numeric must be rejected"


def test_deterministic_json_metrics_output(tmp_path: Path):
    """Verify that run_audit with fixed generation_timestamp produces byte-for-byte identical output."""
    out_file1 = tmp_path / "metrics_run1.json"
    out_file2 = tmp_path / "metrics_run2.json"

    # Setup isolated test workspace
    mock_raw = tmp_path / "raw"
    mock_raw.mkdir()
    (mock_raw / "manifest.json").write_text("[]", encoding="utf-8")
    mock_processed = tmp_path / "processed"
    mock_processed.mkdir()

    fixed_ts = "2026-08-31T23:59:59.000000+00:00"
    m1 = run_audit(
        start="2026-08-01",
        end="2026-08-31",
        raw_dir=mock_raw,
        processed_dir=mock_processed,
        output_path=out_file1,
        generation_timestamp=fixed_ts,
    )
    m2 = run_audit(
        start="2026-08-01",
        end="2026-08-31",
        raw_dir=mock_raw,
        processed_dir=mock_processed,
        output_path=out_file2,
        generation_timestamp=fixed_ts,
    )

    assert out_file1.read_bytes() == out_file2.read_bytes(), "Audit runs with fixed timestamp must be byte-for-byte identical"
    assert m1["metadata"]["generated_at"] == fixed_ts


def test_audit_excludes_september_records():
    """Verify that August-scoped audit strictly excludes September 1 smoke records."""
    assert DOCS_METRICS_PATH.exists(), f"Committed public snapshot missing: {DOCS_METRICS_PATH}"

    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    # In collection: bids has 1 window (August only, 32895 rows, excluding Sep 1 1564 rows)
    assert metrics["collection"]["feeds"]["bids"]["windows"] == 1
    assert metrics["collection"]["feeds"]["bids"]["raw_rows"] == 32895

    # Contracts has 5 windows (115945 rows, excluding Sep 1 6269 rows)
    assert metrics["collection"]["feeds"]["contracts"]["windows"] == 5
    assert metrics["collection"]["feeds"]["contracts"]["raw_rows"] == 115945

    # Awards has 124 windows (excluding Sep 1 4 windows)
    assert metrics["collection"]["feeds"]["awards"]["windows"] == 124
    assert metrics["collection"]["feeds"]["awards"]["raw_rows"] == 2120108

    # Processed contracts rows must be exactly 115,945 (excluding 6,269 Sep 1 rows)
    assert metrics["processed_summary"]["contracts_rows"] == 115945
    assert metrics["cardinality"]["contracts_untyCntrctNo_integrity"]["total_rows"] == 115945
    assert metrics["cardinality"]["contracts_untyCntrctNo_integrity"]["is_strictly_unique"] is True


def test_dedup_collision_classification_logic():
    """Test forensic collision classification on current 7-key vs legacy 5-key."""
    curr_key = DEDUPLICATION_KEYS["awards"]
    assert curr_key == ["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn", "bidprcAmt", "bidprcTm"]

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
    assert df1.duplicated(subset=curr_key).sum() == 1

    # Case 2: Genuine distinct bidder event (different amount and time)
    # Must NOT be duplicate under current 7-key!
    rec2_diff_amt = dict(base_record, bidprcAmt="120000", bidprcTm="10:05")
    df2 = pd.DataFrame([base_record, rec2_diff_amt])
    assert df2.duplicated(subset=curr_key).sum() == 0, "Different submission amount/time must be preserved"
    # But legacy 5-key incorrectly collapsed it:
    legacy_key = ["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn"]
    assert df2.duplicated(subset=legacy_key).sum() == 1, "Legacy 5-key collapsed multi-lot bids"


def test_bidder_submission_candidate_grains():
    """Test that Candidate B (omitting opengRank) collapses anonymous/negotiation bids, whereas Candidate A preserves them."""
    # Case: negotiation bids where bizno and amount are blank, but opening ranks 1 and 2 are assigned
    bids = [
        {"bidNtceNo": "T_NEG", "bidNtceOrd": "000", "bidprcCorpBizrno": "", "opengRank": "1", "dqlfctnRsn": "", "bidprcAmt": "", "bidprcTm": ""},
        {"bidNtceNo": "T_NEG", "bidNtceOrd": "000", "bidprcCorpBizrno": "", "opengRank": "2", "dqlfctnRsn": "", "bidprcAmt": "", "bidprcTm": ""},
    ]
    df = pd.DataFrame(bids)

    cand_A = ["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn", "bidprcAmt", "bidprcTm"]
    cand_B = ["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "bidprcTm", "bidprcAmt"]

    assert df.duplicated(subset=cand_A).sum() == 0, "Candidate A preserves distinct ranks"
    assert df.duplicated(subset=cand_B).sum() == 1, "Candidate B incorrectly collapses distinct ranked bidders"


def test_synthetic_audit_fixtures_execution():
    """Verify that synthetic audit fixtures execute properly and prove cardinality semantics."""
    assert FIXTURES_DIR.exists(), "Fixtures directory must exist"

    bids_aug = pd.read_parquet(FIXTURES_DIR / "aug_bids.parquet")
    bids_sep = pd.read_parquet(FIXTURES_DIR / "sep_bids.parquet")
    awards_aug = pd.read_parquet(FIXTURES_DIR / "aug_awards.parquet")
    contracts_aug = pd.read_parquet(FIXTURES_DIR / "aug_contracts.parquet")

    # 1. Tender PK uniqueness
    assert bids_aug.duplicated(subset=["bid_notice_no", "bid_notice_round"]).sum() == 0

    # 2. Winner cardinality (0, 1, 2+ winners)
    winners = awards_aug[awards_aug["is_selected_winner"] == True]
    win_counts = winners.groupby(["bid_notice_no", "bid_notice_round"]).size()
    all_tenders = bids_aug[["bid_notice_no", "bid_notice_round"]].drop_duplicates()
    zero_win = len(all_tenders) - len(win_counts)
    one_win = (win_counts == 1).sum()
    multi_win = (win_counts > 1).sum()

    assert zero_win == 1, "TEST_TENDER_001 has 0 winners"
    assert one_win == 1, "TEST_TENDER_002 has 1 winner"
    assert multi_win == 1, "TEST_TENDER_003 has 2 winners (multi-lot)"

    # 3. Contract PK uniqueness
    assert contracts_aug["unified_contract_no"].is_unique

    # 4. Tender-Contract relations (unlinked vs 1 vs N)
    has_notice = contracts_aug[contracts_aug["bid_notice_no"].str.strip() != ""]
    unlinked = contracts_aug[contracts_aug["bid_notice_no"].str.strip() == ""]
    assert len(unlinked) == 1, "CNT_004 is unlinked private contract"
    assert unlinked["contract_method_ko"].iloc[0] == "수의계약"

    notice_cnt_counts = has_notice.groupby(["bid_notice_no", "bid_notice_round"]).size()
    assert notice_cnt_counts.get(("TEST_TENDER_002", "000")) == 1
    assert notice_cnt_counts.get(("TEST_TENDER_003", "000")) == 2, "TEST_TENDER_003 has 2 contracts (Tender 1:N Contract relation)"


def test_pagination_verification_semantics():
    """Verify that all pagination metrics have explicit status (VERIFIED or NOT_RETROACTIVELY_VERIFIABLE)."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    pag = metrics.get("pagination", {})
    for metric_name, details in pag.items():
        if metric_name == "future_observability_status":
            assert details["page_receipts_hook_implemented"] is True
            continue
        assert "status" in details, f"Pagination metric {metric_name} must have status"
        assert details["status"] in {"VERIFIED", "NOT_RETROACTIVELY_VERIFIABLE", "SKIPPED"}


def test_public_metrics_snapshot_reconciliation():
    """Verify that committed public metrics snapshot reconciles mathematically."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    dedup = m["deduplication"]["summary"]
    assert dedup["deduplication_accounting_reconciled"] is True
    assert dedup["total_removed_rows"] == dedup["total_exact_duplicates"] + dedup["total_non_exact_collisions"]
    assert dedup["total_preserved_distinct_submissions_vs_legacy"] == 1067

    # Collision classes have 0 unresolved
    classes = dedup["collision_classification_overall"]
    assert classes.get("DISTINCT_SUBMISSION", 0) == 0
    assert classes.get("DISTINCT_CLASSIFICATION_OR_LOT", 0) == 0
    assert classes.get("UNRESOLVED", 0) == 0

    # Ensure no PII or raw sample data in snapshot
    json_text = json.dumps(m)
    for pii_marker in ["주식회사", "사업자등록번호", "대표자", "010-"]:
        assert pii_marker not in json_text
    # Ensure sample_cases with real tender IDs or raw bid amounts was removed
    assert "sample_cases" not in json_text
    assert "R26BK" not in json_text, "Real tender notice IDs must not appear in public snapshot"


def test_contract_method_explicit_mapping_and_reconciliation():
    """Verify that contract methods are mapped explicitly without frequency heuristics and subtotal reconciles."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    bids_cnt = m["cardinality"]["bids_to_contracts"]
    assert bids_cnt["unlinked_contract_method_subtotal_reconciled"] is True

    breakdown = bids_cnt["unlinked_contract_method_breakdown"]
    # All keys must have descriptive English labels in parentheses
    for key in breakdown.keys():
        assert "(" in key and ")" in key, f"Contract method {key} must have explicit standard mapping"

    # Subtotal must match exactly
    assert sum(breakdown.values()) == bids_cnt["contracts_without_tender_link"]
    # Total contracts must reconcile
    assert bids_cnt["contracts_with_tender_link"] + bids_cnt["contracts_without_tender_link"] == bids_cnt["total_contracts_rows"]


def test_awards_category_explicit_mapping():
    """Verify awards categories are mapped without size heuristics."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    by_cat = m["cardinality"]["bids_to_awards"]["bidders_per_tender_by_category"]
    expected_categories = {"construction", "goods", "service", "foreign"}
    assert set(by_cat.keys()) == expected_categories


def test_award_outcomes_pk_validation_metrics():
    """Verify award_outcomes PK candidate has 0 duplicates and strictly unique."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    aw_val = m.get("award_outcomes_pk_validation", {})
    assert aw_val["is_strictly_unique"] is True
    assert aw_val["candidate_key_duplicate_count"] == 0
    assert aw_val["candidate_key_distinct_count"] == aw_val["award_outcome_rows"]
    # Core identifiers must have 0 nulls
    nulls = aw_val["candidate_key_null_component_counts"]
    assert nulls["bid_notice_no"] == 0
    assert nulls["bid_notice_round"] == 0
    assert nulls["winner_business_registration_no"] == 0
    assert nulls["bid_submission_time"] == 0


def test_tender_contract_bridge_cardinality():
    """Verify Tender 1:N Contract relationship semantics."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    bridge = m["cardinality"]["tender_contract_bridge_cardinality"]
    assert bridge["contracts_linked_to_2plus_tenders"] == 0
    assert bridge["relationship_type"] == "Tender (1) : Contract (0..N)"
    assert bridge["bridge_primary_key"] == "unified_contract_no"
    assert bridge["contracts_linked_to_1_tender"] == 40677
    assert bridge["contracts_linked_to_0_tenders"] == 75268


def test_storage_footprint_exact_bytes_and_units():
    """Verify storage measurements explicitly separate MiB and MB."""
    with open(DOCS_METRICS_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)

    storage = m["storage"]
    assert storage["raw_jsonl_gz_bytes"] == 131322271
    assert storage["raw_jsonl_gz_mib"] == 125.24
    assert storage["raw_jsonl_gz_mb"] == 131.32
    assert storage["processed_parquet_bytes"] == 148156166
    assert storage["processed_parquet_mib"] == 141.29
    assert storage["processed_parquet_mb"] == 148.16

