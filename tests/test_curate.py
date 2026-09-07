"""Unit tests for KONEPS relational curated tables pipeline.

Tests surrogate key generation, null-safe canonical hashing, business number masking,
table construction, privacy guarantees, reconciliation gates, and metric sanitization.
Operates completely offline on synthetic fixtures with no network or credential dependencies.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import pytest

from koneps_intel.curate import (
    CURATED_SCHEMA_VERSION,
    build_curated_agencies,
    build_curated_award_outcomes,
    build_curated_bidder_submissions,
    build_curated_bridge,
    build_curated_contracts,
    build_curated_suppliers,
    build_curated_tenders,
    compute_award_outcome_ids,
    compute_bid_submission_ids,
    generate_award_outcome_id,
    generate_bid_submission_id,
    mask_biz_no,
    validate_curated_tables,
)
from koneps_intel.privacy import generate_supplier_id

TEST_HMAC_KEY = b"test_supplier_pseudonymization_key_0123456789"


# =====================================================================
# 1. Privacy and Masking Tests
# =====================================================================

def test_mask_biz_no_valid():
    assert mask_biz_no("1234567890") == "123-45-*****"
    assert mask_biz_no("123-45-67890") == "123-45-*****"
    assert mask_biz_no("  987-65-43210  ") == "987-65-*****"


def test_mask_biz_no_invalid():
    assert mask_biz_no("") == ""
    assert mask_biz_no(None) == ""
    assert mask_biz_no("12345") == ""
    assert mask_biz_no("12345678901") == ""
    assert mask_biz_no("abcdefghij") == ""


# =====================================================================
# 2. Surrogate Key Generation Tests
# =====================================================================

def test_generate_bid_submission_id_format_and_determinism():
    id1 = generate_bid_submission_id(
        bid_notice_no="20260800001",
        bid_notice_round="00",
        bidder_supplier_id="SUP_a1b2c3d4e5f60718293a4b5c6d7e8f90",
        opening_rank=1,
        disqualification_reason="",
        bid_amount_krw=1000000.0,
        bid_submission_time="2026-08-01 10:00:00",
    )
    assert id1.startswith("BID_")
    assert len(id1) == 36  # "BID_" (4) + 32 hex chars

    # Deterministic replay
    id2 = generate_bid_submission_id(
        bid_notice_no="20260800001",
        bid_notice_round="00",
        bidder_supplier_id="SUP_a1b2c3d4e5f60718293a4b5c6d7e8f90",
        opening_rank=1,
        disqualification_reason="",
        bid_amount_krw=1000000.0,
        bid_submission_time="2026-08-01 10:00:00",
    )
    assert id1 == id2

    # Different attribute produces distinct key
    id3 = generate_bid_submission_id(
        bid_notice_no="20260800001",
        bid_notice_round="00",
        bidder_supplier_id="SUP_a1b2c3d4e5f60718293a4b5c6d7e8f90",
        opening_rank=2,
        disqualification_reason="",
        bid_amount_krw=1000000.0,
        bid_submission_time="2026-08-01 10:00:00",
    )
    assert id1 != id3


def test_generate_bid_submission_id_null_safety():
    id_nulls = generate_bid_submission_id(
        bid_notice_no="20260800002",
        bid_notice_round="00",
        bidder_supplier_id="SUP_none",
        opening_rank=None,
        disqualification_reason=None,
        bid_amount_krw=np.nan,
        bid_submission_time=None,
    )
    assert id_nulls.startswith("BID_")
    assert len(id_nulls) == 36


def test_compute_bid_submission_ids_vectorized_match():
    df = pd.DataFrame({
        "bid_notice_no": ["N1", "N2"],
        "bid_notice_round": ["00", "01"],
        "opening_rank": [1, np.nan],
        "disqualification_reason_ko": ["", "서류 미비"],
        "bid_amount_krw": [50000.0, np.nan],
        "bid_submission_time": ["2026-08-01 09:00:00", "2026-08-02 14:30:00"],
    })
    sup_ids = pd.Series(["SUP_111", "SUP_222"])

    vectorized = compute_bid_submission_ids(df, sup_ids)
    assert len(vectorized) == 2

    expected0 = generate_bid_submission_id("N1", "00", "SUP_111", 1, "", 50000.0, "2026-08-01 09:00:00")
    expected1 = generate_bid_submission_id("N2", "01", "SUP_222", None, "서류 미비", None, "2026-08-02 14:30:00")

    assert vectorized.iloc[0] == expected0
    assert vectorized.iloc[1] == expected1


def test_generate_award_outcome_id_format_and_null_safety():
    id1 = generate_award_outcome_id(
        bid_notice_no="20260800003",
        bid_notice_round="00",
        winner_supplier_id="SUP_winner123",
        award_amount_krw=250000000.0,
        bid_submission_time="2026-08-05 11:20:00",
    )
    assert id1.startswith("AWD_")
    assert len(id1) == 36

    # Null award_amount_krw handled safely (forensic case: 24 null winners)
    id_null_amt = generate_award_outcome_id(
        bid_notice_no="20260800004",
        bid_notice_round="00",
        winner_supplier_id="SUP_winner456",
        award_amount_krw=None,
        bid_submission_time="2026-08-06 15:10:00",
    )
    assert id_null_amt.startswith("AWD_")
    assert len(id_null_amt) == 36
    assert id1 != id_null_amt


def test_compute_award_outcome_ids_vectorized_match():
    df = pd.DataFrame({
        "bid_notice_no": ["N10", "N20"],
        "bid_notice_round": ["00", "00"],
        "award_amount_krw": [np.nan, 999999.0],
        "bid_submission_time": ["2026-08-01 10:00:00", ""],
    })
    sup_ids = pd.Series(["SUP_AAA", "SUP_BBB"])

    vectorized = compute_award_outcome_ids(df, sup_ids)
    assert len(vectorized) == 2

    expected0 = generate_award_outcome_id("N10", "00", "SUP_AAA", None, "2026-08-01 10:00:00")
    expected1 = generate_award_outcome_id("N20", "00", "SUP_BBB", 999999.0, "")

    assert vectorized.iloc[0] == expected0
    assert vectorized.iloc[1] == expected1


# =====================================================================
# 3. Synthetic Pipeline Fixtures and Table Construction
# =====================================================================

@pytest.fixture
def synthetic_raw_feeds():
    """Build synthetic raw dataframes mimicking August pilot schema and semantics."""
    # 2 Tenders in scope
    tenders_df = pd.DataFrame({
        "bid_notice_no": ["20260800001", "20260800002"],
        "bid_notice_round": ["00", "00"],
        "bid_notice_date": ["2026-08-01", "2026-08-02"],
        "bid_notice_name_ko": ["용역 공고 1", "물품 공고 2"],
        "notice_agency_code": ["AG001", "AG002"],
        "notice_agency_name_ko": ["기관 A", "기관 B"],
        "demand_agency_code": ["AG001", "AG003"],
        "demand_agency_name_ko": ["기관 A", "기관 C"],
        "contract_method_ko": ["일반경쟁", "수의계약"],
        "bid_method_ko": ["전자입찰", "전자입찰"],
        "bid_start_date": ["2026-08-01", "2026-08-02"],
        "bid_end_date": ["2026-08-07", "2026-08-08"],
        "opening_date": ["2026-08-07", "2026-08-08"],
        "assigned_budget_krw": [100000000.0, 50000000.0],
        "estimated_price_krw": [90000000.0, 45000000.0],
        "industry_restriction_code": ["1234", None],
        "region_restriction_ko": ["전국", "서울특별시"],
    })

    # 3 Awards: 2 in scope notice, 1 referencing prior month notice
    # 2 are selected winners, 1 is bidder only
    awards_df = pd.DataFrame({
        "bid_notice_no": ["20260800001", "20260800001", "20260799999"],
        "bid_notice_round": ["00", "00", "01"],
        "opening_date": ["2026-08-07", "2026-08-07", "2026-08-10"],
        "bid_title_ko": ["용역 공고 1", "용역 공고 1", "7월 공고"],
        "notice_agency_code": ["AG001", "AG001", "AG004"],
        "notice_agency_name_ko": ["기관 A", "기관 A", "기관 D"],
        "demand_agency_code": ["AG001", "AG001", "AG004"],
        "demand_agency_name_ko": ["기관 A", "기관 A", "기관 D"],
        "opening_rank": [1, 2, 1],
        "bidder_business_registration_no": ["1112233333", "2223344444", "3334455555"],
        "bidder_name_ko": ["회사 1", "회사 2", "회사 3"],
        "bid_amount_krw": [85000000.0, 88000000.0, 15000000.0],
        "bid_rate_pct": [88.5, 91.2, 87.5],
        "is_selected_winner": [True, False, True],
        "winner_business_registration_no": ["1112233333", None, "3334455555"],
        "winner_name_ko": ["회사 1", None, "회사 3"],
        "award_amount_krw": [85000000.0, None, None],  # One winner has NULL award_amount
        "award_method_ko": ["적격심사", None, "적격심사"],
        "award_date": ["2026-08-08", None, "2026-08-11"],
        "disqualification_reason_ko": [None, None, None],
        "bid_submission_time": ["2026-08-07 09:30:00", "2026-08-07 09:45:00", "2026-08-10 10:00:00"],
    })

    # 3 Contracts: 1 linked to August tender, 1 linked to prior July tender, 1 unlinked
    contracts_df = pd.DataFrame({
        "unified_contract_no": ["CNT-2026-001", "CNT-2026-002", "CNT-2026-003"],
        "contract_date": ["2026-08-15", "2026-08-18", "2026-08-20"],
        "contract_title_ko": ["계약 1", "계약 2", "단독 계약 3"],
        "bid_notice_no": ["20260800001", "20260799999", None],
        "bid_notice_round": ["00", "01", None],
        "contract_agency_code": ["AG001", "AG004", "AG005"],
        "contract_agency_name_ko": ["기관 A", "기관 D", "기관 E"],
        "demand_agency_code": ["AG001", "AG004", "AG005"],
        "demand_agency_name_ko": ["기관 A", "기관 D", "기관 E"],
        "contract_method_ko": ["일반경쟁", "일반경쟁", "수의계약"],
        "contractor_business_registration_no": ["1112233333", "3334455555", "4445566666"],
        "contractor_name_ko": ["회사 1", "회사 3", "회사 4"],
        "contract_amount_krw": [85000000.0, 15000000.0, 5000000.0],
        "total_contract_amount_krw": [85000000.0, 15000000.0, 5000000.0],
        "contract_period_start": ["2026-08-15", "2026-08-18", "2026-08-20"],
        "contract_period_end": ["2026-12-31", "2026-11-30", "2026-09-30"],
    })

    return tenders_df, awards_df, contracts_df


def test_build_all_curated_tables_integrity(synthetic_raw_feeds):
    raw_bids, raw_awards, raw_contracts = synthetic_raw_feeds
    tender_keys = set(zip(raw_bids["bid_notice_no"], raw_bids["bid_notice_round"]))

    tenders = build_curated_tenders(raw_bids)
    submissions = build_curated_bidder_submissions(raw_awards, TEST_HMAC_KEY, tender_keys)
    awards = build_curated_award_outcomes(raw_awards, TEST_HMAC_KEY, tender_keys)
    contracts = build_curated_contracts(raw_contracts, TEST_HMAC_KEY)
    # build_curated_suppliers now returns (df, conflict_count)
    suppliers, sup_conflicts = build_curated_suppliers(raw_awards, raw_contracts, TEST_HMAC_KEY)
    # build_curated_agencies now returns (df, conflict_count)
    agencies, ag_conflicts = build_curated_agencies(raw_bids, raw_contracts)
    bridge = build_curated_bridge(raw_contracts, tender_keys)

    # 1. Tenders Table
    assert len(tenders) == 2
    assert tenders["bid_notice_no"].is_unique is False or len(tenders["bid_notice_round"].unique()) == 1
    assert set(zip(tenders["bid_notice_no"], tenders["bid_notice_round"])) == {("20260800001", "00"), ("20260800002", "00")}

    # 2. Submissions Table
    assert len(submissions) == 3
    assert submissions["bid_submission_id"].is_unique
    assert submissions["bid_submission_id"].str.startswith("BID_").all()
    assert "bidder_business_registration_no" not in submissions.columns
    # Temporal FK coverage: 2 in scope, 1 out of scope
    assert submissions["tender_in_scope"].sum() == 2
    assert (~submissions["tender_in_scope"]).sum() == 1

    # 3. Awards Table (only winners)
    assert len(awards) == 2
    assert awards["award_outcome_id"].is_unique
    assert awards["award_outcome_id"].str.startswith("AWD_").all()
    assert "winner_business_registration_no" not in awards.columns
    # 1 in scope, 1 out of scope
    assert awards["tender_in_scope"].sum() == 1
    assert (~awards["tender_in_scope"]).sum() == 1
    # Check NULL award amount safely preserved
    assert awards["award_amount_krw"].isna().sum() == 1

    # 4. Contracts Table
    assert len(contracts) == 3
    assert contracts["unified_contract_no"].is_unique
    assert "contractor_business_registration_no" not in contracts.columns

    # 5. Suppliers Table — masked_biz_no REMOVED, snapshot_ prefix for aggregates
    assert len(suppliers) == 4  # 1112233333, 2223344444, 3334455555, 4445566666
    assert suppliers["supplier_id"].is_unique
    assert suppliers["supplier_id"].str.startswith("SUP_").all()
    assert "business_registration_no" not in suppliers.columns
    # masked_biz_no is now excluded from publishable output
    assert "masked_biz_no" not in suppliers.columns
    # Snapshot stats use snapshot_ prefix
    assert "snapshot_total_bids_in_scope" in suppliers.columns
    assert "snapshot_total_wins_in_scope" in suppliers.columns
    # Old unprefixed column names must NOT be present
    assert "total_bids_in_scope" not in suppliers.columns
    # Conflict count is an int
    assert isinstance(sup_conflicts, int)
    assert sup_conflicts >= 0

    # Verify supplier roles by supplier_id lookup
    from koneps_intel.privacy import generate_supplier_id
    sid1 = generate_supplier_id("1112233333", TEST_HMAC_KEY)
    sup1 = suppliers[suppliers["supplier_id"] == sid1].iloc[0]
    assert sup1["is_bidder"] and sup1["is_winner"] and sup1["is_contractor"]

    sid2 = generate_supplier_id("2223344444", TEST_HMAC_KEY)
    sup2 = suppliers[suppliers["supplier_id"] == sid2].iloc[0]
    assert sup2["is_bidder"] and not sup2["is_winner"] and not sup2["is_contractor"]

    # 6. Agencies Table
    assert len(agencies) == 5  # AG001, AG002, AG003, AG004, AG005
    assert agencies["agency_code"].is_unique
    assert isinstance(ag_conflicts, int)
    # Snapshot stats use snapshot_ prefix
    assert "snapshot_total_tenders_in_scope" in agencies.columns
    assert "total_tenders_in_scope" not in agencies.columns

    # 7. Bridge Table (linked contracts only)
    assert len(bridge) == 2  # CNT-2026-001 (linked to Aug notice), CNT-2026-002 (linked to July notice)
    assert bridge["unified_contract_no"].is_unique
    assert bridge["tender_in_scope"].sum() == 1
    assert (~bridge["tender_in_scope"]).sum() == 1
    assert "CNT-2026-003" not in bridge["unified_contract_no"].values


def test_reconciliation_gates_validation(synthetic_raw_feeds):
    raw_bids, raw_awards, raw_contracts = synthetic_raw_feeds
    tender_keys = set(zip(raw_bids["bid_notice_no"], raw_bids["bid_notice_round"]))

    tables = {
        "tenders": build_curated_tenders(raw_bids),
        "bidder_submissions": build_curated_bidder_submissions(raw_awards, TEST_HMAC_KEY, tender_keys),
        "award_outcomes": build_curated_award_outcomes(raw_awards, TEST_HMAC_KEY, tender_keys),
        "contracts": build_curated_contracts(raw_contracts, TEST_HMAC_KEY),
        "suppliers": build_curated_suppliers(raw_awards, raw_contracts, TEST_HMAC_KEY)[0],
        "agencies": build_curated_agencies(raw_bids, raw_contracts)[0],
        "tender_contract_bridge": build_curated_bridge(raw_contracts, tender_keys),
    }

    raw_baselines = {
        "bids": 2,
        "awards": 3,
        "winners": 2,
        "contracts": 3,
        "linked_contracts": 2,
        "unlinked_contracts": 1,
        "suppliers": 4,
        "agencies": 5,
    }

    result = validate_curated_tables(tables, raw_baselines)
    assert result["all_reconciliation_gates_passed"] is True

    # Intentionally corrupt count and assert failure
    bad_baselines = dict(raw_baselines)
    bad_baselines["winners"] = 999
    with pytest.raises(ValueError, match="reconciliation gate failure"):
        validate_curated_tables(tables, bad_baselines)


def test_curated_schema_version():
    assert CURATED_SCHEMA_VERSION == "1.1.0"
