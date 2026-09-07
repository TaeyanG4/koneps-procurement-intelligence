"""Relational curation engine for KONEPS procurement intelligence datasets.

Transforms cleaned and typed monthly Parquet data into 7 normalized,
relational curated tables with deterministic surrogate PKs, temporal FK tracking,
strict privacy preservation (no raw PII/biz nos), and mathematical reconciliation gates.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from koneps_intel.audit import clean_biz_no
from koneps_intel.config import PROCESSED_DIR
from koneps_intel.privacy import generate_supplier_id
from koneps_intel.utils import get_logger

CURATED_SCHEMA_VERSION = "1.0.0"
logger = get_logger("koneps_intel.curate")


def mask_biz_no(biz_no: str) -> str:
    """Mask a 10-digit Korean business registration number (e.g. 123-45-*****)."""
    clean = str(biz_no or "").replace("-", "").strip()
    if len(clean) == 10 and clean.isdigit():
        return f"{clean[:3]}-{clean[3:5]}-*****"
    return ""


def generate_bid_submission_id(
    bid_notice_no: str,
    bid_notice_round: str,
    bidder_supplier_id: str,
    opening_rank: Any,
    disqualification_reason: Any,
    bid_amount_krw: Any,
    bid_submission_time: Any,
) -> str:
    """Generate deterministic BID_<32 hex> surrogate primary key from public-safe reconciliation grain."""
    rank_str = f"{float(opening_rank):.0f}" if pd.notna(opening_rank) and str(opening_rank).strip() != "" else "NULL"
    amt_str = f"{float(bid_amount_krw):.2f}" if pd.notna(bid_amount_krw) and str(bid_amount_krw).strip() != "" else "NULL"
    parts = [
        str(bid_notice_no or "").strip(),
        str(bid_notice_round or "").strip(),
        str(bidder_supplier_id or "").strip(),
        rank_str,
        str(disqualification_reason or "").strip(),
        amt_str,
        str(bid_submission_time or "").strip(),
    ]
    canonical = "|".join(parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"BID_{digest[:32]}"


def compute_bid_submission_ids(
    df: pd.DataFrame,
    bidder_supplier_ids: pd.Series,
) -> pd.Series:
    """Vectorized computation of deterministic BID_<32 hex> surrogate primary keys."""
    rank_str = df["opening_rank"].apply(
        lambda x: f"{float(x):.0f}" if pd.notna(x) and str(x).strip() != "" else "NULL"
    )
    amt_str = df["bid_amount_krw"].apply(
        lambda x: f"{float(x):.2f}" if pd.notna(x) and str(x).strip() != "" else "NULL"
    )
    disq_str = df["disqualification_reason_ko"].fillna("").astype(str).str.strip() if "disqualification_reason_ko" in df.columns else pd.Series([""] * len(df), index=df.index)
    time_str = df["bid_submission_time"].fillna("").astype(str).str.strip() if "bid_submission_time" in df.columns else pd.Series([""] * len(df), index=df.index)

    canonical = (
        df["bid_notice_no"].fillna("").astype(str).str.strip() + "|" +
        df["bid_notice_round"].fillna("").astype(str).str.strip() + "|" +
        bidder_supplier_ids.fillna("").astype(str).str.strip() + "|" +
        rank_str + "|" +
        disq_str + "|" +
        amt_str + "|" +
        time_str
    )
    h = hashlib.sha256
    return pd.Series(
        ["BID_" + h(x.encode("utf-8")).hexdigest()[:32] for x in canonical],
        index=df.index,
    )


def generate_award_outcome_id(
    bid_notice_no: str,
    bid_notice_round: str,
    winner_supplier_id: str,
    award_amount_krw: Any,
    bid_submission_time: Any,
) -> str:
    """Generate deterministic AWD_<32 hex> surrogate primary key from public-safe reconciliation grain."""
    amt_str = f"{float(award_amount_krw):.2f}" if pd.notna(award_amount_krw) and str(award_amount_krw).strip() != "" else "NULL"
    parts = [
        str(bid_notice_no or "").strip(),
        str(bid_notice_round or "").strip(),
        str(winner_supplier_id or "").strip(),
        amt_str,
        str(bid_submission_time or "").strip(),
    ]
    canonical = "|".join(parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"AWD_{digest[:32]}"


def compute_award_outcome_ids(
    df: pd.DataFrame,
    winner_supplier_ids: pd.Series,
) -> pd.Series:
    """Vectorized computation of deterministic AWD_<32 hex> surrogate primary keys."""
    amt_str = df["award_amount_krw"].apply(
        lambda x: f"{float(x):.2f}" if pd.notna(x) and str(x).strip() != "" else "NULL"
    )
    time_str = df["bid_submission_time"].fillna("").astype(str).str.strip() if "bid_submission_time" in df.columns else pd.Series([""] * len(df), index=df.index)

    canonical = (
        df["bid_notice_no"].fillna("").astype(str).str.strip() + "|" +
        df["bid_notice_round"].fillna("").astype(str).str.strip() + "|" +
        winner_supplier_ids.fillna("").astype(str).str.strip() + "|" +
        amt_str + "|" +
        time_str
    )
    h = hashlib.sha256
    return pd.Series(
        ["AWD_" + h(x.encode("utf-8")).hexdigest()[:32] for x in canonical],
        index=df.index,
    )


def build_curated_tenders(df_bids: pd.DataFrame) -> pd.DataFrame:
    """Build 01_tenders table with natural PK (bid_notice_no, bid_notice_round)."""
    cols = [
        "bid_notice_no",
        "bid_notice_round",
        "bid_title_ko",
        "notice_agency_code",
        "notice_agency_name_ko",
        "demand_agency_code",
        "demand_agency_name_ko",
        "business_div_name_ko",
        "contract_method_ko",
        "contract_status_ko",
        "award_method_ko",
        "assigned_budget_krw",
        "estimated_price_krw",
        "bid_notice_date",
        "bid_notice_time",
        "bid_begin_date",
        "bid_begin_time",
        "bid_close_date",
        "bid_close_time",
        "opening_date",
        "opening_time",
        "opening_place_ko",
        "ref_notice_no",
        "ref_notice_round",
        "bid_notice_url",
        "is_joint_contract",
        "is_electronic_bid",
        "is_international_bid",
        "is_pps_notice",
        "is_region_limited",
        "is_industry_limited",
        "data_base_date",
    ]
    present_cols = [c for c in cols if c in df_bids.columns]
    res = df_bids[present_cols].copy()
    res["bid_notice_no"] = res["bid_notice_no"].astype(str).str.strip()
    res["bid_notice_round"] = res["bid_notice_round"].astype(str).str.strip()
    return res


def build_curated_bidder_submissions(
    df_awards: pd.DataFrame,
    hmac_key: bytes,
    tender_keys: Set[Tuple[str, str]],
) -> pd.DataFrame:
    """Build 02_bidder_submissions table with surrogate PK bid_submission_id."""
    clean_biz = clean_biz_no(df_awards["bidder_business_registration_no"])
    bidder_supplier_ids = pd.Series(
        [generate_supplier_id(b, hmac_key) if len(b) == 10 and b.isdigit() else "" for b in clean_biz],
        index=df_awards.index,
    )

    submission_ids = compute_bid_submission_ids(df_awards, bidder_supplier_ids)

    # Determine temporal FK scope
    ntce_no = df_awards["bid_notice_no"].fillna("").astype(str).str.strip()
    ntce_ord = df_awards["bid_notice_round"].fillna("").astype(str).str.strip()
    in_scope = [k in tender_keys for k in zip(ntce_no, ntce_ord)]

    res = pd.DataFrame({
        "bid_submission_id": submission_ids,
        "bid_notice_no": ntce_no,
        "bid_notice_round": ntce_ord,
        "bidder_supplier_id": bidder_supplier_ids,
        "tender_in_scope": in_scope,
        "opening_rank": df_awards["opening_rank"] if "opening_rank" in df_awards.columns else np.nan,
        "disqualification_reason_ko": df_awards["disqualification_reason_ko"].fillna("") if "disqualification_reason_ko" in df_awards.columns else "",
        "bid_amount_krw": df_awards["bid_amount_krw"] if "bid_amount_krw" in df_awards.columns else np.nan,
        "bid_rate": df_awards["bid_rate"] if "bid_rate" in df_awards.columns else np.nan,
        "bid_submission_date": df_awards["bid_submission_date"] if "bid_submission_date" in df_awards.columns else None,
        "bid_submission_time": df_awards["bid_submission_time"].fillna("") if "bid_submission_time" in df_awards.columns else "",
        "is_selected_winner": df_awards["is_selected_winner"].fillna(False).astype(bool) if "is_selected_winner" in df_awards.columns else False,
        "bid_title_ko": df_awards["bid_title_ko"].fillna("") if "bid_title_ko" in df_awards.columns else "",
        "business_div_name_ko": df_awards["business_div_name_ko"].fillna("") if "business_div_name_ko" in df_awards.columns else "",
        "contract_method_ko": df_awards["contract_method_ko"].fillna("") if "contract_method_ko" in df_awards.columns else "",
        "award_method_ko": df_awards["award_method_ko"].fillna("") if "award_method_ko" in df_awards.columns else "",
        "notice_agency_code": df_awards["notice_agency_code"].fillna("") if "notice_agency_code" in df_awards.columns else "",
        "notice_agency_name_ko": df_awards["notice_agency_name_ko"].fillna("") if "notice_agency_name_ko" in df_awards.columns else "",
        "demand_agency_code": df_awards["demand_agency_code"].fillna("") if "demand_agency_code" in df_awards.columns else "",
        "demand_agency_name_ko": df_awards["demand_agency_name_ko"].fillna("") if "demand_agency_name_ko" in df_awards.columns else "",
        "bidder_name_ko": df_awards["bidder_name_ko"].fillna("") if "bidder_name_ko" in df_awards.columns else "",
        "opening_date": df_awards["opening_date"] if "opening_date" in df_awards.columns else None,
        "opening_time": df_awards["opening_time"].fillna("") if "opening_time" in df_awards.columns else "",
        "opening_result_status_ko": df_awards["opening_result_status_ko"].fillna("") if "opening_result_status_ko" in df_awards.columns else "",
        "scheduled_price_krw": df_awards["scheduled_price_krw"] if "scheduled_price_krw" in df_awards.columns else np.nan,
        "base_amount_krw": df_awards["base_amount_krw"] if "base_amount_krw" in df_awards.columns else np.nan,
        "estimated_price_krw": df_awards["estimated_price_krw"] if "estimated_price_krw" in df_awards.columns else np.nan,
        "award_lower_limit_rate": df_awards["award_lower_limit_rate"] if "award_lower_limit_rate" in df_awards.columns else np.nan,
        "data_base_date": df_awards["data_base_date"].fillna("") if "data_base_date" in df_awards.columns else "",
    })
    return res


def build_curated_award_outcomes(
    df_awards: pd.DataFrame,
    hmac_key: bytes,
    tender_keys: Set[Tuple[str, str]],
) -> pd.DataFrame:
    """Build 03_award_outcomes table with surrogate PK award_outcome_id."""
    winners_mask = df_awards["is_selected_winner"] == True
    winners_df = df_awards[winners_mask].copy()

    clean_biz = clean_biz_no(winners_df["winner_business_registration_no"])
    winner_supplier_ids = pd.Series(
        [generate_supplier_id(b, hmac_key) if len(b) == 10 and b.isdigit() else "" for b in clean_biz],
        index=winners_df.index,
    )

    outcome_ids = compute_award_outcome_ids(winners_df, winner_supplier_ids)

    ntce_no = winners_df["bid_notice_no"].fillna("").astype(str).str.strip()
    ntce_ord = winners_df["bid_notice_round"].fillna("").astype(str).str.strip()
    in_scope = [k in tender_keys for k in zip(ntce_no, ntce_ord)]

    res = pd.DataFrame({
        "award_outcome_id": outcome_ids,
        "bid_notice_no": ntce_no,
        "bid_notice_round": ntce_ord,
        "winner_supplier_id": winner_supplier_ids,
        "tender_in_scope": in_scope,
        "award_amount_krw": winners_df["award_amount_krw"] if "award_amount_krw" in winners_df.columns else np.nan,
        "award_rate": winners_df["award_rate"] if "award_rate" in winners_df.columns else np.nan,
        "award_date": winners_df["award_date"] if "award_date" in winners_df.columns else None,
        "bid_submission_time": winners_df["bid_submission_time"].fillna("") if "bid_submission_time" in winners_df.columns else "",
        "bid_amount_krw": winners_df["bid_amount_krw"] if "bid_amount_krw" in winners_df.columns else np.nan,
        "opening_rank": winners_df["opening_rank"] if "opening_rank" in winners_df.columns else np.nan,
        "winner_name_ko": winners_df["winner_name_ko"].fillna("") if "winner_name_ko" in winners_df.columns else "",
        "bid_title_ko": winners_df["bid_title_ko"].fillna("") if "bid_title_ko" in winners_df.columns else "",
        "business_div_name_ko": winners_df["business_div_name_ko"].fillna("") if "business_div_name_ko" in winners_df.columns else "",
        "contract_method_ko": winners_df["contract_method_ko"].fillna("") if "contract_method_ko" in winners_df.columns else "",
        "award_method_ko": winners_df["award_method_ko"].fillna("") if "award_method_ko" in winners_df.columns else "",
        "notice_agency_code": winners_df["notice_agency_code"].fillna("") if "notice_agency_code" in winners_df.columns else "",
        "notice_agency_name_ko": winners_df["notice_agency_name_ko"].fillna("") if "notice_agency_name_ko" in winners_df.columns else "",
        "demand_agency_code": winners_df["demand_agency_code"].fillna("") if "demand_agency_code" in winners_df.columns else "",
        "demand_agency_name_ko": winners_df["demand_agency_name_ko"].fillna("") if "demand_agency_name_ko" in winners_df.columns else "",
        "opening_date": winners_df["opening_date"] if "opening_date" in winners_df.columns else None,
        "scheduled_price_krw": winners_df["scheduled_price_krw"] if "scheduled_price_krw" in winners_df.columns else np.nan,
        "base_amount_krw": winners_df["base_amount_krw"] if "base_amount_krw" in winners_df.columns else np.nan,
        "estimated_price_krw": winners_df["estimated_price_krw"] if "estimated_price_krw" in winners_df.columns else np.nan,
        "award_lower_limit_rate": winners_df["award_lower_limit_rate"] if "award_lower_limit_rate" in winners_df.columns else np.nan,
        "data_base_date": winners_df["data_base_date"].fillna("") if "data_base_date" in winners_df.columns else "",
    })
    return res


def build_curated_contracts(
    df_contracts: pd.DataFrame,
    hmac_key: bytes,
) -> pd.DataFrame:
    """Build 04_contracts table with PK unified_contract_no."""
    clean_biz = clean_biz_no(df_contracts["contractor_business_registration_no"])
    contractor_supplier_ids = pd.Series(
        [generate_supplier_id(b, hmac_key) if len(b) == 10 and b.isdigit() else "" for b in clean_biz],
        index=df_contracts.index,
    )

    res = pd.DataFrame({
        "unified_contract_no": df_contracts["unified_contract_no"].astype(str).str.strip(),
        "contract_no": df_contracts["contract_no"].fillna("").astype(str).str.strip() if "contract_no" in df_contracts.columns else "",
        "contract_round": df_contracts["contract_round"].fillna("").astype(str).str.strip() if "contract_round" in df_contracts.columns else "",
        "contract_title_ko": df_contracts["contract_title_ko"].fillna("").astype(str).str.strip() if "contract_title_ko" in df_contracts.columns else "",
        "contract_date": df_contracts["contract_date"] if "contract_date" in df_contracts.columns else None,
        "contract_method_ko": df_contracts["contract_method_ko"].fillna("").astype(str).str.strip() if "contract_method_ko" in df_contracts.columns else "",
        "contract_status_ko": df_contracts["contract_status_ko"].fillna("").astype(str).str.strip() if "contract_status_ko" in df_contracts.columns else "",
        "contract_amount_krw": df_contracts["contract_amount_krw"] if "contract_amount_krw" in df_contracts.columns else np.nan,
        "total_contract_amount_krw": df_contracts["total_contract_amount_krw"] if "total_contract_amount_krw" in df_contracts.columns else np.nan,
        "contract_agency_code": df_contracts["contract_agency_code"].fillna("").astype(str).str.strip() if "contract_agency_code" in df_contracts.columns else "",
        "contract_agency_name_ko": df_contracts["contract_agency_name_ko"].fillna("").astype(str).str.strip() if "contract_agency_name_ko" in df_contracts.columns else "",
        "demand_agency_code": df_contracts["demand_agency_code"].fillna("").astype(str).str.strip() if "demand_agency_code" in df_contracts.columns else "",
        "demand_agency_name_ko": df_contracts["demand_agency_name_ko"].fillna("").astype(str).str.strip() if "demand_agency_name_ko" in df_contracts.columns else "",
        "contractor_supplier_id": contractor_supplier_ids,
        "contractor_name_ko": df_contracts["contractor_name_ko"].fillna("").astype(str).str.strip() if "contractor_name_ko" in df_contracts.columns else "",
        "bid_notice_no": df_contracts["bid_notice_no"].fillna("").astype(str).str.strip() if "bid_notice_no" in df_contracts.columns else "",
        "bid_notice_round": df_contracts["bid_notice_round"].fillna("").astype(str).str.strip() if "bid_notice_round" in df_contracts.columns else "",
        "contract_period": df_contracts["contract_period"].fillna("").astype(str).str.strip() if "contract_period" in df_contracts.columns else "",
        "long_term_contract_div_ko": df_contracts["long_term_contract_div_ko"].fillna("").astype(str).str.strip() if "long_term_contract_div_ko" in df_contracts.columns else "",
        "private_contract_reason_ko": df_contracts["private_contract_reason_ko"].fillna("").astype(str).str.strip() if "private_contract_reason_ko" in df_contracts.columns else "",
        "is_joint_contract": df_contracts["is_joint_contract"].fillna(False).astype(bool) if "is_joint_contract" in df_contracts.columns else False,
        "is_domestic_corp": df_contracts["is_domestic_corp"].fillna(False).astype(bool) if "is_domestic_corp" in df_contracts.columns else False,
        "contract_info_url": df_contracts["contract_info_url"].fillna("").astype(str).str.strip() if "contract_info_url" in df_contracts.columns else "",
        "bid_notice_url": df_contracts["bid_notice_url"].fillna("").astype(str).str.strip() if "bid_notice_url" in df_contracts.columns else "",
        "data_base_date": df_contracts["data_base_date"].fillna("").astype(str).str.strip() if "data_base_date" in df_contracts.columns else "",
    })
    return res


def build_curated_suppliers(
    df_awards: pd.DataFrame,
    df_contracts: pd.DataFrame,
    hmac_key: bytes,
) -> pd.DataFrame:
    """Build 05_suppliers dimension table with PK supplier_id."""
    bidder_biz = clean_biz_no(df_awards["bidder_business_registration_no"]) if not df_awards.empty else pd.Series([], dtype=str)
    winner_biz = clean_biz_no(df_awards[df_awards["is_selected_winner"] == True]["winner_business_registration_no"]) if not df_awards.empty else pd.Series([], dtype=str)
    cnt_biz = clean_biz_no(df_contracts["contractor_business_registration_no"]) if not df_contracts.empty else pd.Series([], dtype=str)

    bidders_10 = set(bidder_biz[bidder_biz.str.len() == 10])
    winners_10 = set(winner_biz[winner_biz.str.len() == 10])
    contractors_10 = set(cnt_biz[cnt_biz.str.len() == 10])

    all_10 = sorted(list(bidders_10 | winners_10 | contractors_10))

    # Collect best available name per biz_no
    name_map: Dict[str, str] = {}
    if not df_contracts.empty:
        c_names = df_contracts["contractor_name_ko"] if "contractor_name_ko" in df_contracts.columns else pd.Series([""] * len(df_contracts), index=df_contracts.index)
        for b, n in zip(cnt_biz, c_names.fillna("").astype(str)):
            b_clean = b.strip()
            n_clean = n.strip()
            if len(b_clean) == 10 and n_clean and b_clean not in name_map:
                name_map[b_clean] = n_clean

    if not df_awards.empty:
        w_df = df_awards[df_awards["is_selected_winner"] == True]
        w_names = w_df["winner_name_ko"] if "winner_name_ko" in w_df.columns else pd.Series([""] * len(w_df), index=w_df.index)
        for b, n in zip(clean_biz_no(w_df["winner_business_registration_no"]), w_names.fillna("").astype(str)):
            b_clean = b.strip()
            n_clean = n.strip()
            if len(b_clean) == 10 and n_clean and b_clean not in name_map:
                name_map[b_clean] = n_clean

        b_names = df_awards["bidder_name_ko"] if "bidder_name_ko" in df_awards.columns else pd.Series([""] * len(df_awards), index=df_awards.index)
        for b, n in zip(bidder_biz, b_names.fillna("").astype(str)):
            b_clean = b.strip()
            n_clean = n.strip()
            if len(b_clean) == 10 and n_clean and b_clean not in name_map:
                name_map[b_clean] = n_clean

    # Pre-calculate counts and totals
    bid_counts = bidder_biz[bidder_biz.str.len() == 10].value_counts().to_dict()
    win_counts = winner_biz[winner_biz.str.len() == 10].value_counts().to_dict()
    contract_counts = cnt_biz[cnt_biz.str.len() == 10].value_counts().to_dict()

    contract_amt_dict: Dict[str, float] = {}
    if not df_contracts.empty and "contract_amount_krw" in df_contracts.columns:
        valid_mask = cnt_biz.str.len() == 10
        grp = df_contracts[valid_mask].groupby(cnt_biz[valid_mask])["contract_amount_krw"].sum()
        contract_amt_dict = grp.to_dict()

    rows = []
    for b in all_10:
        sid = generate_supplier_id(b, hmac_key)
        rows.append({
            "supplier_id": sid,
            "supplier_name_ko": name_map.get(b, ""),
            "masked_biz_no": mask_biz_no(b),
            "is_bidder": b in bidders_10,
            "is_winner": b in winners_10,
            "is_contractor": b in contractors_10,
            "total_bids_in_scope": int(bid_counts.get(b, 0)),
            "total_wins_in_scope": int(win_counts.get(b, 0)),
            "total_contracts_in_scope": int(contract_counts.get(b, 0)),
            "total_contract_amount_krw": float(contract_amt_dict.get(b, 0.0)),
        })

    return pd.DataFrame(rows)


def build_curated_agencies(
    df_bids: pd.DataFrame,
    df_contracts: pd.DataFrame,
) -> pd.DataFrame:
    """Build 06_agencies dimension table with PK agency_code."""
    names: Dict[str, str] = {}

    def _ingest_pairs(codes: pd.Series, nms: pd.Series):
        for c, n in zip(codes.dropna().astype(str), nms.dropna().astype(str)):
            c_clean = c.strip()
            n_clean = n.strip()
            if c_clean and n_clean and c_clean not in names:
                names[c_clean] = n_clean

    bids_ntce = set(df_bids["notice_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""]) if not df_bids.empty and "notice_agency_code" in df_bids.columns else set()
    bids_dmnd = set(df_bids["demand_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""]) if not df_bids.empty and "demand_agency_code" in df_bids.columns else set()
    cnt_inst = set(df_contracts["contract_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""]) if not df_contracts.empty and "contract_agency_code" in df_contracts.columns else set()
    cnt_dmnd = set(df_contracts["demand_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""]) if not df_contracts.empty and "demand_agency_code" in df_contracts.columns else set()

    if not df_bids.empty:
        if "notice_agency_code" in df_bids.columns and "notice_agency_name_ko" in df_bids.columns:
            _ingest_pairs(df_bids["notice_agency_code"], df_bids["notice_agency_name_ko"])
        if "demand_agency_code" in df_bids.columns and "demand_agency_name_ko" in df_bids.columns:
            _ingest_pairs(df_bids["demand_agency_code"], df_bids["demand_agency_name_ko"])
    if not df_contracts.empty:
        if "contract_agency_code" in df_contracts.columns and "contract_agency_name_ko" in df_contracts.columns:
            _ingest_pairs(df_contracts["contract_agency_code"], df_contracts["contract_agency_name_ko"])
        if "demand_agency_code" in df_contracts.columns and "demand_agency_name_ko" in df_contracts.columns:
            _ingest_pairs(df_contracts["demand_agency_code"], df_contracts["demand_agency_name_ko"])

    all_codes = sorted(list(bids_ntce | bids_dmnd | cnt_inst | cnt_dmnd))

    # Compute activity counts
    bids_cnt = df_bids["notice_agency_code"].dropna().astype(str).str.strip().value_counts().to_dict() if not df_bids.empty else {}
    cnt_cnt = df_contracts["contract_agency_code"].dropna().astype(str).str.strip().value_counts().to_dict() if not df_contracts.empty else {}

    rows = []
    for c in all_codes:
        rows.append({
            "agency_code": c,
            "agency_name_ko": names.get(c, ""),
            "is_notice_agency": c in bids_ntce,
            "is_demand_agency": (c in bids_dmnd) or (c in cnt_dmnd),
            "is_contract_agency": c in cnt_inst,
            "total_tenders_in_scope": int(bids_cnt.get(c, 0)),
            "total_contracts_in_scope": int(cnt_cnt.get(c, 0)),
        })

    return pd.DataFrame(rows)


def build_curated_bridge(
    df_contracts: pd.DataFrame,
    tender_keys: Set[Tuple[str, str]],
) -> pd.DataFrame:
    """Build 07_tender_contract_bridge with LINKED CONTRACTS ONLY."""
    linked_mask = df_contracts["bid_notice_no"].fillna("").astype(str).str.strip() != ""
    linked = df_contracts[linked_mask].copy()

    unty_cnt = linked["unified_contract_no"].astype(str).str.strip()
    ntce_no = linked["bid_notice_no"].astype(str).str.strip()
    ntce_ord = linked["bid_notice_round"].fillna("").astype(str).str.strip()
    in_scope = [k in tender_keys for k in zip(ntce_no, ntce_ord)]

    res = pd.DataFrame({
        "unified_contract_no": unty_cnt,
        "bid_notice_no": ntce_no,
        "bid_notice_round": ntce_ord,
        "match_type": "DIRECT_NOTICE_MATCH",
        "tender_in_scope": in_scope,
        "contract_date": linked["contract_date"] if "contract_date" in linked.columns else None,
        "contract_amount_krw": linked["contract_amount_krw"] if "contract_amount_krw" in linked.columns else np.nan,
    })
    return res


def validate_curated_tables(
    tables: Dict[str, pd.DataFrame],
    raw_counts: Dict[str, int],
) -> Dict[str, Any]:
    """Enforce all reconciliation gates and return reconciliation status metrics."""
    tenders = tables["tenders"]
    submissions = tables["bidder_submissions"]
    awards = tables["award_outcomes"]
    contracts = tables["contracts"]
    suppliers = tables["suppliers"]
    agencies = tables["agencies"]
    bridge = tables["tender_contract_bridge"]

    # Gate 1: Row counts reconciliation
    gate_bids = len(tenders) == raw_counts["bids"]
    gate_awards = len(submissions) == raw_counts["awards"]
    gate_winners = len(awards) == raw_counts["winners"]
    gate_contracts = len(contracts) == raw_counts["contracts"]
    gate_bridge = len(bridge) == raw_counts["linked_contracts"]
    gate_unlinked = (len(contracts) - len(bridge)) == raw_counts["unlinked_contracts"]
    gate_suppliers = len(suppliers) == raw_counts["suppliers"]
    gate_agencies = len(agencies) == raw_counts["agencies"]

    # Gate 2: PK uniqueness & nullness
    pk_tenders_valid = (
        tenders.duplicated(subset=["bid_notice_no", "bid_notice_round"]).sum() == 0
        and tenders["bid_notice_no"].isna().sum() == 0
        and tenders["bid_notice_round"].isna().sum() == 0
    )
    pk_submissions_valid = submissions["bid_submission_id"].is_unique and submissions["bid_submission_id"].isna().sum() == 0
    pk_awards_valid = awards["award_outcome_id"].is_unique and awards["award_outcome_id"].isna().sum() == 0
    pk_contracts_valid = contracts["unified_contract_no"].is_unique and contracts["unified_contract_no"].isna().sum() == 0
    pk_suppliers_valid = suppliers["supplier_id"].is_unique and suppliers["supplier_id"].isna().sum() == 0
    pk_agencies_valid = agencies["agency_code"].is_unique and agencies["agency_code"].isna().sum() == 0
    pk_bridge_valid = bridge["unified_contract_no"].is_unique and bridge["unified_contract_no"].isna().sum() == 0

    all_passed = bool(
        gate_bids and gate_awards and gate_winners and gate_contracts and
        gate_bridge and gate_unlinked and gate_suppliers and gate_agencies and
        pk_tenders_valid and pk_submissions_valid and pk_awards_valid and
        pk_contracts_valid and pk_suppliers_valid and pk_agencies_valid and
        pk_bridge_valid
    )

    if not all_passed:
        mismatches = []
        if not gate_bids: mismatches.append(f"bids count {len(tenders)} != {raw_counts['bids']}")
        if not gate_awards: mismatches.append(f"awards count {len(submissions)} != {raw_counts['awards']}")
        if not gate_winners: mismatches.append(f"winners count {len(awards)} != {raw_counts['winners']}")
        if not gate_contracts: mismatches.append(f"contracts count {len(contracts)} != {raw_counts['contracts']}")
        if not gate_bridge: mismatches.append(f"bridge count {len(bridge)} != {raw_counts['linked_contracts']}")
        if not gate_unlinked: mismatches.append(f"unlinked count {len(contracts)-len(bridge)} != {raw_counts['unlinked_contracts']}")
        if not gate_suppliers: mismatches.append(f"suppliers count {len(suppliers)} != {raw_counts['suppliers']}")
        if not gate_agencies: mismatches.append(f"agencies count {len(agencies)} != {raw_counts['agencies']}")
        if not pk_tenders_valid: mismatches.append("tenders PK invalid")
        if not pk_submissions_valid: mismatches.append("submissions PK invalid")
        if not pk_awards_valid: mismatches.append("awards PK invalid")
        if not pk_contracts_valid: mismatches.append("contracts PK invalid")
        if not pk_suppliers_valid: mismatches.append("suppliers PK invalid")
        if not pk_agencies_valid: mismatches.append("agencies PK invalid")
        if not pk_bridge_valid: mismatches.append("bridge PK invalid")
        raise ValueError(f"Critical reconciliation gate failure: {'; '.join(mismatches)}")

    return {
        "bids_to_tenders_match": gate_bids,
        "awards_to_bidder_submissions_match": gate_awards,
        "winners_to_award_outcomes_match": gate_winners,
        "contracts_match": gate_contracts,
        "linked_contracts_to_bridge_match": gate_bridge,
        "unlinked_contracts_match": gate_unlinked,
        "suppliers_match": gate_suppliers,
        "agencies_match": gate_agencies,
        "all_pks_unique_and_non_null": True,
        "all_reconciliation_gates_passed": all_passed,
    }


def run_curation(
    start: str = "2026-08-01",
    end: str = "2026-08-31",
    processed_dir: Path | str = PROCESSED_DIR,
    out_dir: Optional[Path | str] = None,
    public_metrics_path: Optional[Path | str] = None,
    hmac_key: Optional[bytes] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Execute full relational curation pipeline and write curated Parquet tables and public metrics."""
    load_dotenv()
    if hmac_key is None:
        key_str = os.getenv("KONEPS_SUPPLIER_HMAC_KEY")
        if not key_str:
            raise ValueError(
                "KONEPS_SUPPLIER_HMAC_KEY must be provided via environment or parameter. "
                "Set KONEPS_SUPPLIER_HMAC_KEY in .env before running curation."
            )
        hmac_key = key_str.encode("utf-8")

    processed_dir = Path(processed_dir)
    dest_dir = Path(out_dir) if out_dir else (processed_dir / "curated" / f"{start.replace('-', '')[:6]}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = Path(public_metrics_path) if public_metrics_path else None

    target_filenames = [
        "01_tenders.parquet",
        "02_bidder_submissions.parquet",
        "03_award_outcomes.parquet",
        "04_contracts.parquet",
        "05_suppliers.parquet",
        "06_agencies.parquet",
        "07_tender_contract_bridge.parquet",
    ]
    if not force and all((dest_dir / fname).exists() for fname in target_filenames):
        logger.info("All curated tables already exist in %s and force=False. Skipping curation.", dest_dir)
        if metrics_path and metrics_path.exists():
            with open(metrics_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    logger.info("Starting relational curation for period %s ~ %s", start, end)

    # 1. Load processed Parquet feeds
    bids_files = list((processed_dir / "bids").glob("**/*.parquet"))
    awards_files = list((processed_dir / "awards").glob("**/*.parquet"))
    contracts_files = list((processed_dir / "contracts").glob("**/*.parquet"))

    bids_raw = pd.concat([pd.read_parquet(f) for f in bids_files], ignore_index=True)
    awards_raw = pd.concat([pd.read_parquet(f) for f in awards_files], ignore_index=True)
    contracts_raw = pd.concat([pd.read_parquet(f) for f in contracts_files], ignore_index=True)

    # Scope strictly by event date
    aug_bids = bids_raw[(bids_raw["bid_notice_date"].astype(str).str[:10] >= start) & (bids_raw["bid_notice_date"].astype(str).str[:10] <= end)].copy()
    aug_awards = awards_raw[(awards_raw["opening_date"].astype(str).str[:10] >= start) & (awards_raw["opening_date"].astype(str).str[:10] <= end)].copy()
    aug_contracts = contracts_raw[(contracts_raw["contract_date"].astype(str).str[:10] >= start) & (contracts_raw["contract_date"].astype(str).str[:10] <= end)].copy()

    # Calculate raw baselines
    aug_winners = aug_awards[aug_awards["is_selected_winner"] == True]
    linked_contracts = aug_contracts[aug_contracts["bid_notice_no"].fillna("").astype(str).str.strip() != ""]

    bidder_biz = clean_biz_no(aug_awards["bidder_business_registration_no"])
    winner_biz = clean_biz_no(aug_winners["winner_business_registration_no"])
    cnt_biz = clean_biz_no(aug_contracts["contractor_business_registration_no"])
    all_suppliers_set = set(bidder_biz[bidder_biz.str.len() == 10]) | set(winner_biz[winner_biz.str.len() == 10]) | set(cnt_biz[cnt_biz.str.len() == 10])

    bids_ntce = set(aug_bids["notice_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
    bids_dmnd = set(aug_bids["demand_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
    cnt_inst = set(aug_contracts["contract_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
    cnt_dmnd = set(aug_contracts["demand_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
    all_agencies_set = bids_ntce | bids_dmnd | cnt_inst | cnt_dmnd

    raw_baselines = {
        "bids": len(aug_bids),
        "awards": len(aug_awards),
        "winners": len(aug_winners),
        "contracts": len(aug_contracts),
        "linked_contracts": len(linked_contracts),
        "unlinked_contracts": len(aug_contracts) - len(linked_contracts),
        "suppliers": len(all_suppliers_set),
        "agencies": len(all_agencies_set),
    }

    # 2. Build Curated Tables
    tenders_df = build_curated_tenders(aug_bids)
    tender_keys = set(zip(tenders_df["bid_notice_no"], tenders_df["bid_notice_round"]))

    submissions_df = build_curated_bidder_submissions(aug_awards, hmac_key, tender_keys)
    awards_df = build_curated_award_outcomes(aug_awards, hmac_key, tender_keys)
    contracts_df = build_curated_contracts(aug_contracts, hmac_key)
    suppliers_df = build_curated_suppliers(aug_awards, aug_contracts, hmac_key)
    agencies_df = build_curated_agencies(aug_bids, aug_contracts)
    bridge_df = build_curated_bridge(aug_contracts, tender_keys)

    tables = {
        "tenders": tenders_df,
        "bidder_submissions": submissions_df,
        "award_outcomes": awards_df,
        "contracts": contracts_df,
        "suppliers": suppliers_df,
        "agencies": agencies_df,
        "tender_contract_bridge": bridge_df,
    }

    # 3. Enforce Reconciliation Gates
    gates_result = validate_curated_tables(tables, raw_baselines)

    # 4. Save Curated Tables as Parquet with ZSTD
    table_files = {
        "tenders": dest_dir / "01_tenders.parquet",
        "bidder_submissions": dest_dir / "02_bidder_submissions.parquet",
        "award_outcomes": dest_dir / "03_award_outcomes.parquet",
        "contracts": dest_dir / "04_contracts.parquet",
        "suppliers": dest_dir / "05_suppliers.parquet",
        "agencies": dest_dir / "06_agencies.parquet",
        "tender_contract_bridge": dest_dir / "07_tender_contract_bridge.parquet",
    }

    storage_metrics: Dict[str, Any] = {}
    total_bytes = 0
    for name, path in table_files.items():
        df = tables[name]
        df.to_parquet(path, compression="zstd", index=False)
        size_b = path.stat().st_size
        total_bytes += size_b
        storage_metrics[name] = {
            "file_name": path.name,
            "bytes": size_b,
            "mib": round(size_b / (1024 * 1024), 2),
            "mb": round(size_b / 1_000_000, 2),
        }
    storage_metrics["total_curated_bytes"] = total_bytes
    storage_metrics["total_curated_mib"] = round(total_bytes / (1024 * 1024), 2)
    storage_metrics["total_curated_mb"] = round(total_bytes / 1_000_000, 2)

    # 5. Compile Public Metrics Snapshot (Sanitized & Aggregate-Only)
    aw_null_cnt = int(awards_df["award_amount_krw"].isna().sum())
    aw_null_ratio = round(aw_null_cnt / len(awards_df), 6) if len(awards_df) else 0.0

    # Null forensics (pure aggregate categories, no PII/real IDs)
    null_sub = aug_winners[aug_winners["award_amount_krw"].isna()]
    rank_dist = {str(k): int(v) for k, v in null_sub["opening_rank"].value_counts().items()} if "opening_rank" in null_sub.columns else {}
    _METHOD_MAP: Dict[str, str] = {
        "적격심사": "qualification_review",
        "수의": "small_sum_private",
        "협상": "negotiation",
        "최저가": "lowest_price",
        "종합평가": "comprehensive_evaluation",
    }
    raw_method_counts = null_sub["award_method_ko"].value_counts().to_dict() if "award_method_ko" in null_sub.columns else {}
    mapped_method_dist: Dict[str, int] = {}
    for m_raw, cnt in raw_method_counts.items():
        label = next((v for k, v in _METHOD_MAP.items() if k in str(m_raw)), "other")
        mapped_method_dist[label] = mapped_method_dist.get(label, 0) + int(cnt)

    metrics = {
        "schema_version": CURATED_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "curation_scope_start": start,
        "curation_scope_end": end,
        "reconciliation_gates": gates_result,
        "table_metrics": {
            "tenders": {
                "row_count": len(tenders_df),
                "primary_key": "(bid_notice_no, bid_notice_round)",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
            },
            "bidder_submissions": {
                "row_count": len(submissions_df),
                "primary_key": "bid_submission_id",
                "surrogate_pk_prefix": "BID_",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
                "temporal_fk_in_scope_count": int(submissions_df["tender_in_scope"].sum()),
                "temporal_fk_out_of_scope_count": int((~submissions_df["tender_in_scope"]).sum()),
                "temporal_fk_coverage_ratio": round(float(submissions_df["tender_in_scope"].mean()), 4),
            },
            "award_outcomes": {
                "row_count": len(awards_df),
                "primary_key": "award_outcome_id",
                "surrogate_pk_prefix": "AWD_",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
                "temporal_fk_in_scope_count": int(awards_df["tender_in_scope"].sum()),
                "temporal_fk_out_of_scope_count": int((~awards_df["tender_in_scope"]).sum()),
                "temporal_fk_coverage_ratio": round(float(awards_df["tender_in_scope"].mean()), 4),
                "award_amount_krw_null_count": aw_null_cnt,
                "award_amount_krw_null_ratio": aw_null_ratio,
            },
            "contracts": {
                "row_count": len(contracts_df),
                "primary_key": "unified_contract_no",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
            },
            "suppliers": {
                "row_count": len(suppliers_df),
                "primary_key": "supplier_id",
                "surrogate_pk_prefix": "SUP_",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
                "bidders_count": int(suppliers_df["is_bidder"].sum()),
                "winners_count": int(suppliers_df["is_winner"].sum()),
                "contractors_count": int(suppliers_df["is_contractor"].sum()),
            },
            "agencies": {
                "row_count": len(agencies_df),
                "primary_key": "agency_code",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
                "notice_agencies_count": int(agencies_df["is_notice_agency"].sum()),
                "demand_agencies_count": int(agencies_df["is_demand_agency"].sum()),
                "contract_agencies_count": int(agencies_df["is_contract_agency"].sum()),
            },
            "tender_contract_bridge": {
                "row_count": len(bridge_df),
                "primary_key": "unified_contract_no",
                "pk_null_count": 0,
                "pk_duplicate_count": 0,
                "is_pk_unique": True,
                "temporal_fk_in_scope_count": int(bridge_df["tender_in_scope"].sum()),
                "temporal_fk_out_of_scope_count": int((~bridge_df["tender_in_scope"]).sum()),
                "temporal_fk_coverage_ratio": round(float(bridge_df["tender_in_scope"].mean()), 4),
            },
        },
        "award_amount_null_forensics": {
            "null_count": aw_null_cnt,
            "null_ratio": aw_null_ratio,
            "rank_distribution": rank_dist,
            "award_method_distribution": mapped_method_dist,
            "imputation_policy": "DO_NOT_IMPUTE: Preserved as NULL due to unfinalized post-opening adjudication in raw API snapshot.",
        },
        "storage": storage_metrics,
    }

    if metrics_path:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        logger.info("Wrote public curated metrics snapshot to %s", metrics_path)

    logger.info("Curated tables generation complete: %d total tables written to %s", len(tables), dest_dir)
    return metrics


def main() -> None:
    """CLI entrypoint for relational curated table generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Build relational curated tables for KONEPS pilot dataset")
    parser.add_argument("--start", default="2026-08-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-08-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--processed", default=str(PROCESSED_DIR), help="Input processed directory")
    parser.add_argument("--out", default=str(PROCESSED_DIR / "curated" / "2026_08"), help="Output curated directory")
    parser.add_argument("--public-metrics", default="docs/metrics/curated_2026_08.json", help="Path to write public metrics JSON")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if outputs exist")
    args = parser.parse_args()

    run_curation(
        start=args.start,
        end=args.end,
        processed_dir=Path(args.processed),
        out_dir=Path(args.out),
        public_metrics_path=Path(args.public_metrics),
        force=args.force,
    )


if __name__ == "__main__":
    main()


