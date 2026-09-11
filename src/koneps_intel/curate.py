"""Relational curation engine for KONEPS procurement intelligence datasets.

Transforms cleaned and typed monthly Parquet data into 7 normalized,
relational curated tables with deterministic surrogate PKs, temporal FK tracking,
strict privacy preservation (no raw PII/biz nos), and mathematical reconciliation gates.

Privacy policy: raw business registration numbers and direct contact fields are
excluded from all publishable curated output. Supplier public identity is
supplier_id only. Company names may remain in curated tables only after final
privacy and licensing review prior to Kaggle publication.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from koneps_intel.audit import clean_biz_no
from koneps_intel.config import PROCESSED_DIR
from koneps_intel.privacy import generate_supplier_id
from koneps_intel.utils import get_logger

CURATED_SCHEMA_VERSION = "1.1.0"
logger = get_logger("koneps_intel.curate")


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that safely serializes numpy scalar types produced by pandas."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return super().default(obj)


# ---------------------------------------------------------------------------
# Forbidden column patterns: raw biz-reg-no, direct contact, representative
# ---------------------------------------------------------------------------
_FORBIDDEN_COLUMN_PATTERNS = [
    # Raw business registration number columns (the raw un-masked number itself)
    re.compile(r"(?<![a-z_])business_registration_no", re.IGNORECASE),
    re.compile(r"(?<![a-z_])biz_no$", re.IGNORECASE),
    re.compile(r"(?<![a-z_])bizno$", re.IGNORECASE),
    re.compile(r"^biz_reg", re.IGNORECASE),
    # Direct phone/email/fax/mobile contact fields
    re.compile(r"^phone_|^tel_|^fax_|^mobile_|^email_", re.IGNORECASE),
    re.compile(r"_phone$|_tel$|_fax$|_mobile$|_email$", re.IGNORECASE),
    # Representative / CEO name fields (not "contractor" which is a business role)
    re.compile(r"^representative_name|^ceo_name|^president_name", re.IGNORECASE),
    # masked_biz_no is also excluded from publishable output
    re.compile(r"^masked_biz_no$", re.IGNORECASE),
]

# Identifier columns that must remain string dtype; monetary columns that must be numeric
_IDENTIFIER_COLUMNS = {
    "bid_submission_id", "award_outcome_id", "supplier_id", "agency_code",
    "unified_contract_no", "bid_notice_no", "bid_notice_round", "contract_no",
    "bidder_supplier_id", "winner_supplier_id", "contractor_supplier_id",
}
_MONETARY_COLUMNS = {
    "bid_amount_krw", "award_amount_krw", "contract_amount_krw",
    "total_contract_amount_krw", "assigned_budget_krw", "estimated_price_krw",
    "scheduled_price_krw", "base_amount_krw", "total_contract_amount_krw",
}

# Snapshot statistics in supplier/agency dimensions — time-window aggregates only,
# NOT stable identity attributes. Must not be used as leak-free historical ML features.
SUPPLIER_SNAPSHOT_STATS = [
    "snapshot_total_bids_in_scope",
    "snapshot_total_wins_in_scope",
    "snapshot_total_contracts_in_scope",
    "snapshot_total_contract_amount_krw",
]
AGENCY_SNAPSHOT_STATS = [
    "snapshot_total_tenders_in_scope",
    "snapshot_total_contracts_in_scope",
]


def mask_biz_no(biz_no: str) -> str:
    """Mask a 10-digit Korean business registration number (e.g. 123-45-*****)."""
    clean = str(biz_no or "").replace("-", "").strip()
    if len(clean) == 10 and clean.isdigit():
        return f"{clean[:3]}-{clean[3:5]}-*****"
    return ""


# ---------------------------------------------------------------------------
# Canonical surrogate key serialization
# Replaces ambiguous pipe-concatenation. Same semantic row → same ID always.
# ---------------------------------------------------------------------------

def _canonical_json(d: Dict[str, Any]) -> bytes:
    """Serialize a dict to a deterministic UTF-8 JSON bytes with sorted keys."""
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def generate_bid_submission_id(
    bid_notice_no: str,
    bid_notice_round: str,
    bidder_supplier_id: str,
    opening_rank: Any,
    disqualification_reason: Any,
    bid_amount_krw: Any,
    bid_submission_time: Any,
) -> str:
    """Generate deterministic BID_<32 hex> surrogate primary key.

    Uses structured canonical JSON serialization so that same semantic row always
    produces the same ID regardless of field order or future separator changes.
    NULL sentinel is the explicit string "__NULL__" to distinguish from empty string.
    """
    def _num_or_null(v: Any, fmt: str) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "__NULL__"
        try:
            return fmt % float(v)
        except (TypeError, ValueError):
            s = str(v).strip()
            return s if s else "__NULL__"

    record = {
        "entity": "bid_submission",
        "version": 1,
        "bid_notice_no": str(bid_notice_no or "").strip() or "__NULL__",
        "bid_notice_round": str(bid_notice_round or "").strip() or "__NULL__",
        "bidder_supplier_id": str(bidder_supplier_id or "").strip() or "__NULL__",
        "opening_rank": _num_or_null(opening_rank, "%.0f"),
        "disqualification_reason": str(disqualification_reason or "").strip() if disqualification_reason else "__NULL__",
        "bid_amount_krw": _num_or_null(bid_amount_krw, "%.2f"),
        "bid_submission_time": str(bid_submission_time or "").strip() or "__NULL__",
    }
    digest = hashlib.sha256(_canonical_json(record)).hexdigest()
    return f"BID_{digest[:32]}"


def compute_bid_submission_ids(
    df: pd.DataFrame,
    bidder_supplier_ids: pd.Series,
) -> pd.Series:
    """Vectorized computation of deterministic BID_<32 hex> surrogate primary keys."""

    def _num_or_null_scalar(v: Any, fmt: str) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "__NULL__"
        try:
            return fmt % float(v)
        except (TypeError, ValueError):
            s = str(v).strip()
            return s if s else "__NULL__"

    def _str_or_null(v: Any) -> str:
        s = str(v).strip() if v is not None and not (isinstance(v, float) and np.isnan(v)) else ""
        return s if s else "__NULL__"

    h = hashlib.sha256
    ids = []
    rank_col = df["opening_rank"] if "opening_rank" in df.columns else pd.Series([None] * len(df), index=df.index)
    disq_col = df["disqualification_reason_ko"] if "disqualification_reason_ko" in df.columns else pd.Series([None] * len(df), index=df.index)
    amt_col = df["bid_amount_krw"] if "bid_amount_krw" in df.columns else pd.Series([None] * len(df), index=df.index)
    time_col = df["bid_submission_time"] if "bid_submission_time" in df.columns else pd.Series([None] * len(df), index=df.index)

    # Iterating arrays directly avoids millions of pandas ``iloc`` calls while
    # preserving the exact canonical-json/SHA-256 identifier contract.
    rows = zip(
        df["bid_notice_no"].array,
        df["bid_notice_round"].array,
        bidder_supplier_ids.array,
        rank_col.array,
        disq_col.array,
        amt_col.array,
        time_col.array,
    )
    for ntce_no, ntce_ord, supplier_id, rank, disq, amount, submission_time in rows:
        record = {
            "entity": "bid_submission",
            "version": 1,
            "bid_notice_no": _str_or_null(ntce_no),
            "bid_notice_round": _str_or_null(ntce_ord),
            "bidder_supplier_id": _str_or_null(supplier_id),
            "opening_rank": _num_or_null_scalar(rank, "%.0f"),
            "disqualification_reason": _str_or_null(disq),
            "bid_amount_krw": _num_or_null_scalar(amount, "%.2f"),
            "bid_submission_time": _str_or_null(submission_time),
        }
        ids.append("BID_" + h(_canonical_json(record)).hexdigest()[:32])
    return pd.Series(ids, index=df.index)


def generate_award_outcome_id(
    bid_notice_no: str,
    bid_notice_round: str,
    winner_supplier_id: str,
    award_amount_krw: Any,
    bid_submission_time: Any,
) -> str:
    """Generate deterministic AWD_<32 hex> surrogate primary key.

    Uses structured canonical JSON serialization.
    """
    def _num_or_null(v: Any, fmt: str) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "__NULL__"
        try:
            return fmt % float(v)
        except (TypeError, ValueError):
            s = str(v).strip()
            return s if s else "__NULL__"

    def _str_or_null(v: Any) -> str:
        s = str(v or "").strip()
        return s if s else "__NULL__"

    record = {
        "entity": "award_outcome",
        "version": 1,
        "bid_notice_no": _str_or_null(bid_notice_no),
        "bid_notice_round": _str_or_null(bid_notice_round),
        "winner_supplier_id": _str_or_null(winner_supplier_id),
        "award_amount_krw": _num_or_null(award_amount_krw, "%.2f"),
        "bid_submission_time": _str_or_null(bid_submission_time),
    }
    digest = hashlib.sha256(_canonical_json(record)).hexdigest()
    return f"AWD_{digest[:32]}"


def compute_award_outcome_ids(
    df: pd.DataFrame,
    winner_supplier_ids: pd.Series,
) -> pd.Series:
    """Vectorized computation of deterministic AWD_<32 hex> surrogate primary keys."""

    def _num_or_null_scalar(v: Any, fmt: str) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "__NULL__"
        try:
            return fmt % float(v)
        except (TypeError, ValueError):
            s = str(v).strip()
            return s if s else "__NULL__"

    def _str_or_null(v: Any) -> str:
        s = str(v).strip() if v is not None and not (isinstance(v, float) and np.isnan(v)) else ""
        return s if s else "__NULL__"

    h = hashlib.sha256
    ids = []
    amt_col = df["award_amount_krw"] if "award_amount_krw" in df.columns else pd.Series([None] * len(df), index=df.index)
    time_col = df["bid_submission_time"] if "bid_submission_time" in df.columns else pd.Series([None] * len(df), index=df.index)

    rows = zip(
        df["bid_notice_no"].array,
        df["bid_notice_round"].array,
        winner_supplier_ids.array,
        amt_col.array,
        time_col.array,
    )
    for ntce_no, ntce_ord, supplier_id, amount, submission_time in rows:
        record = {
            "entity": "award_outcome",
            "version": 1,
            "bid_notice_no": _str_or_null(ntce_no),
            "bid_notice_round": _str_or_null(ntce_ord),
            "winner_supplier_id": _str_or_null(supplier_id),
            "award_amount_krw": _num_or_null_scalar(amount, "%.2f"),
            "bid_submission_time": _str_or_null(submission_time),
        }
        ids.append("AWD_" + h(_canonical_json(record)).hexdigest()[:32])
    return pd.Series(ids, index=df.index)


def _supplier_ids_from_business_numbers(series: pd.Series, hmac_key: bytes) -> pd.Series:
    """Map business numbers to stable supplier IDs while hashing each unique value once."""
    clean = clean_biz_no(series)
    valid_mask = clean.str.len().eq(10) & clean.str.isdigit()
    valid = clean[valid_mask]
    unique_values = valid.drop_duplicates().tolist()
    id_map = {biz_no: generate_supplier_id(biz_no, hmac_key) for biz_no in unique_values}
    return clean.map(id_map).fillna("")


def _valid_business_numbers(series: pd.Series) -> pd.Series:
    """Return canonical 10-digit business numbers accepted by supplier pseudonymization."""
    clean = clean_biz_no(series)
    return clean[clean.str.len().eq(10) & clean.str.isdigit()]


# ---------------------------------------------------------------------------
# Name resolution helpers: most-frequent, whitespace-normalised, lex tiebreak
# ---------------------------------------------------------------------------

def _normalize_name(name: Any) -> str:
    """Trim and collapse internal whitespace in a name string."""
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return ""
    s = " ".join(str(name).split())
    return s


def _resolve_names_most_frequent(
    keys: pd.Series,
    names: pd.Series,
) -> Tuple[Dict[str, str], int]:
    """For each key, choose the most frequent non-blank normalized name.

    Returns a (key→name) dict and the total number of name conflicts detected.
    A conflict is any key with >1 distinct non-blank name observed.
    Tiebreak: lexicographically smallest name among most-frequent candidates.
    """
    # Build frequency counts per (key, normalized_name)
    freq: Dict[str, Counter] = {}
    for k, n in zip(keys, names):
        k_str = str(k).strip() if k is not None else ""
        if not k_str:
            continue
        n_norm = _normalize_name(n)
        if not n_norm:
            continue
        if k_str not in freq:
            freq[k_str] = Counter()
        freq[k_str][n_norm] += 1

    result: Dict[str, str] = {}
    conflict_count = 0
    for k, counter in freq.items():
        distinct = list(counter.keys())
        if len(distinct) > 1:
            conflict_count += 1
        max_count = max(counter.values())
        top = sorted([nm for nm, cnt in counter.items() if cnt == max_count])
        result[k] = top[0]  # lex smallest among most-frequent
    return result, conflict_count


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

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
    # Deterministic sort
    return res.sort_values(["bid_notice_no", "bid_notice_round"]).reset_index(drop=True)


def build_curated_bidder_submissions(
    df_awards: pd.DataFrame,
    hmac_key: bytes,
    tender_keys: Set[Tuple[str, str]],
) -> pd.DataFrame:
    """Build 02_bidder_submissions table with surrogate PK bid_submission_id."""
    bidder_supplier_ids = _supplier_ids_from_business_numbers(
        df_awards["bidder_business_registration_no"], hmac_key
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
    # Deterministic sort
    return res.sort_values(["bid_submission_id"]).reset_index(drop=True)


def build_curated_award_outcomes(
    df_awards: pd.DataFrame,
    hmac_key: bytes,
    tender_keys: Set[Tuple[str, str]],
) -> pd.DataFrame:
    """Build 03_award_outcomes table with surrogate PK award_outcome_id."""
    winners_mask = df_awards["is_selected_winner"] == True
    winners_df = df_awards[winners_mask].copy()

    winner_supplier_ids = _supplier_ids_from_business_numbers(
        winners_df["winner_business_registration_no"], hmac_key
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
    # Deterministic sort
    return res.sort_values(["award_outcome_id"]).reset_index(drop=True)


def build_curated_contracts(
    df_contracts: pd.DataFrame,
    hmac_key: bytes,
) -> pd.DataFrame:
    """Build 04_contracts table with PK unified_contract_no."""
    contractor_supplier_ids = _supplier_ids_from_business_numbers(
        df_contracts["contractor_business_registration_no"], hmac_key
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
    # Deterministic sort
    return res.sort_values(["unified_contract_no"]).reset_index(drop=True)


def build_curated_suppliers(
    df_awards: pd.DataFrame,
    df_contracts: pd.DataFrame,
    hmac_key: bytes,
) -> Tuple[pd.DataFrame, int]:
    """Build 05_suppliers dimension table with PK supplier_id.

    Returns (DataFrame, name_conflict_count) where name_conflict_count is the
    number of biz_nos that had >1 distinct name observed (aggregate metric only).
    Snapshot statistics are prefixed with 'snapshot_' to signal they must NOT be
    used as stable identity or leak-free ML features.
    Public supplier identity = supplier_id only. masked_biz_no is excluded.
    Company names remain but require final privacy/license review before Kaggle publication.
    """
    bidder_biz = clean_biz_no(df_awards["bidder_business_registration_no"]) if not df_awards.empty else pd.Series([], dtype=str)
    winner_biz = clean_biz_no(df_awards[df_awards["is_selected_winner"] == True]["winner_business_registration_no"]) if not df_awards.empty else pd.Series([], dtype=str)
    cnt_biz = clean_biz_no(df_contracts["contractor_business_registration_no"]) if not df_contracts.empty else pd.Series([], dtype=str)

    bidders_10 = set(bidder_biz[bidder_biz.str.len().eq(10) & bidder_biz.str.isdigit()])
    winners_10 = set(winner_biz[winner_biz.str.len().eq(10) & winner_biz.str.isdigit()])
    contractors_10 = set(cnt_biz[cnt_biz.str.len().eq(10) & cnt_biz.str.isdigit()])

    all_10 = sorted(list(bidders_10 | winners_10 | contractors_10))

    # Collect names from all sources, then resolve via most-frequent / lex-tiebreak
    all_keys: List[str] = []
    all_names: List[str] = []

    if not df_contracts.empty:
        c_names = df_contracts["contractor_name_ko"] if "contractor_name_ko" in df_contracts.columns else pd.Series([""] * len(df_contracts), index=df_contracts.index)
        for b, n in zip(cnt_biz, c_names):
            b_clean = str(b).strip() if b else ""
            if len(b_clean) == 10 and b_clean.isdigit():
                all_keys.append(b_clean)
                all_names.append(str(n) if n is not None else "")

    if not df_awards.empty:
        w_df = df_awards[df_awards["is_selected_winner"] == True]
        w_names = w_df["winner_name_ko"] if "winner_name_ko" in w_df.columns else pd.Series([""] * len(w_df), index=w_df.index)
        for b, n in zip(clean_biz_no(w_df["winner_business_registration_no"]), w_names):
            b_clean = str(b).strip() if b else ""
            if len(b_clean) == 10 and b_clean.isdigit():
                all_keys.append(b_clean)
                all_names.append(str(n) if n is not None else "")

        b_names = df_awards["bidder_name_ko"] if "bidder_name_ko" in df_awards.columns else pd.Series([""] * len(df_awards), index=df_awards.index)
        for b, n in zip(bidder_biz, b_names):
            b_clean = str(b).strip() if b else ""
            if len(b_clean) == 10 and b_clean.isdigit():
                all_keys.append(b_clean)
                all_names.append(str(n) if n is not None else "")

    name_map, conflict_count = _resolve_names_most_frequent(
        pd.Series(all_keys), pd.Series(all_names)
    )

    # Pre-calculate snapshot statistics (time-window aggregates)
    bid_valid = bidder_biz.str.len().eq(10) & bidder_biz.str.isdigit()
    win_valid = winner_biz.str.len().eq(10) & winner_biz.str.isdigit()
    contract_valid = cnt_biz.str.len().eq(10) & cnt_biz.str.isdigit()
    bid_counts = bidder_biz[bid_valid].value_counts().to_dict()
    win_counts = winner_biz[win_valid].value_counts().to_dict()
    contract_counts = cnt_biz[contract_valid].value_counts().to_dict()

    contract_amt_dict: Dict[str, float] = {}
    if not df_contracts.empty and "contract_amount_krw" in df_contracts.columns:
        valid_mask = cnt_biz.str.len().eq(10) & cnt_biz.str.isdigit()
        grp = df_contracts[valid_mask].groupby(cnt_biz[valid_mask])["contract_amount_krw"].sum()
        contract_amt_dict = grp.to_dict()

    rows = []
    for b in all_10:
        sid = generate_supplier_id(b, hmac_key)
        rows.append({
            "supplier_id": sid,
            "supplier_name_ko": name_map.get(b, ""),
            # NOTE: masked_biz_no removed from publishable output (no demonstrated analytical requirement).
            # supplier_id is the sole public identity.
            "is_bidder": b in bidders_10,
            "is_winner": b in winners_10,
            "is_contractor": b in contractors_10,
            # Snapshot statistics: time-window aggregates, NOT stable identity attributes.
            # Must NOT be used as leak-free historical ML features.
            "snapshot_total_bids_in_scope": int(bid_counts.get(b, 0)),
            "snapshot_total_wins_in_scope": int(win_counts.get(b, 0)),
            "snapshot_total_contracts_in_scope": int(contract_counts.get(b, 0)),
            "snapshot_total_contract_amount_krw": float(contract_amt_dict.get(b, 0.0)),
        })

    df = pd.DataFrame(rows)
    # Deterministic sort
    if not df.empty:
        df = df.sort_values(["supplier_id"]).reset_index(drop=True)
    return df, conflict_count


def build_curated_agencies(
    df_bids: pd.DataFrame,
    df_contracts: pd.DataFrame,
) -> Tuple[pd.DataFrame, int]:
    """Build 06_agencies dimension table with PK agency_code.

    Returns (DataFrame, name_conflict_count).
    Snapshot statistics are prefixed with 'snapshot_' to signal they must NOT
    be used as stable identity or leak-free historical ML features.
    """
    # Collect all code/name pairs from all sources
    all_keys: List[str] = []
    all_names: List[str] = []

    def _collect(codes: pd.Series, names: pd.Series) -> None:
        for c, n in zip(codes.fillna("").astype(str), names.fillna("").astype(str)):
            c_clean = c.strip()
            if c_clean:
                all_keys.append(c_clean)
                all_names.append(n.strip())

    bids_ntce: Set[str] = set()
    bids_dmnd: Set[str] = set()
    cnt_inst: Set[str] = set()
    cnt_dmnd: Set[str] = set()

    if not df_bids.empty:
        if "notice_agency_code" in df_bids.columns:
            bids_ntce = set(df_bids["notice_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
        if "demand_agency_code" in df_bids.columns:
            bids_dmnd = set(df_bids["demand_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
        if "notice_agency_code" in df_bids.columns and "notice_agency_name_ko" in df_bids.columns:
            _collect(df_bids["notice_agency_code"], df_bids["notice_agency_name_ko"])
        if "demand_agency_code" in df_bids.columns and "demand_agency_name_ko" in df_bids.columns:
            _collect(df_bids["demand_agency_code"], df_bids["demand_agency_name_ko"])

    if not df_contracts.empty:
        if "contract_agency_code" in df_contracts.columns:
            cnt_inst = set(df_contracts["contract_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
        if "demand_agency_code" in df_contracts.columns:
            cnt_dmnd = set(df_contracts["demand_agency_code"].dropna().astype(str).str.strip().loc[lambda x: x != ""])
        if "contract_agency_code" in df_contracts.columns and "contract_agency_name_ko" in df_contracts.columns:
            _collect(df_contracts["contract_agency_code"], df_contracts["contract_agency_name_ko"])
        if "demand_agency_code" in df_contracts.columns and "demand_agency_name_ko" in df_contracts.columns:
            _collect(df_contracts["demand_agency_code"], df_contracts["demand_agency_name_ko"])

    name_map, conflict_count = _resolve_names_most_frequent(
        pd.Series(all_keys), pd.Series(all_names)
    )

    all_codes = sorted(list(bids_ntce | bids_dmnd | cnt_inst | cnt_dmnd))

    # Snapshot statistics
    bids_cnt: Dict[str, int] = {}
    cnt_cnt: Dict[str, int] = {}
    if not df_bids.empty and "notice_agency_code" in df_bids.columns:
        bids_cnt = df_bids["notice_agency_code"].dropna().astype(str).str.strip().value_counts().to_dict()
    if not df_contracts.empty and "contract_agency_code" in df_contracts.columns:
        cnt_cnt = df_contracts["contract_agency_code"].dropna().astype(str).str.strip().value_counts().to_dict()

    rows = []
    for c in all_codes:
        rows.append({
            "agency_code": c,
            "agency_name_ko": name_map.get(c, ""),
            "is_notice_agency": c in bids_ntce,
            "is_demand_agency": (c in bids_dmnd) or (c in cnt_dmnd),
            "is_contract_agency": c in cnt_inst,
            # Snapshot statistics: time-window aggregates, NOT stable identity attributes.
            "snapshot_total_tenders_in_scope": int(bids_cnt.get(c, 0)),
            "snapshot_total_contracts_in_scope": int(cnt_cnt.get(c, 0)),
        })

    df = pd.DataFrame(rows)
    # Deterministic sort
    if not df.empty:
        df = df.sort_values(["agency_code"]).reset_index(drop=True)
    return df, conflict_count


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
    # Deterministic sort
    return res.sort_values(["unified_contract_no"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validation gates
# ---------------------------------------------------------------------------

def _check_forbidden_columns(name: str, df: pd.DataFrame) -> List[str]:
    """Return list of forbidden column violations in a table."""
    violations = []
    for col in df.columns:
        for pat in _FORBIDDEN_COLUMN_PATTERNS:
            if pat.search(col):
                violations.append(f"{name}.{col}")
                break
    return violations


def _check_dtype_constraints(name: str, df: pd.DataFrame) -> List[str]:
    """Return list of dtype constraint violations."""
    violations = []
    for col in df.columns:
        if col in _IDENTIFIER_COLUMNS:
            if not pd.api.types.is_string_dtype(df[col]) and not pd.api.types.is_object_dtype(df[col]):
                violations.append(f"{name}.{col}: expected string dtype, got {df[col].dtype}")
        if col in _MONETARY_COLUMNS:
            if not pd.api.types.is_numeric_dtype(df[col]):
                violations.append(f"{name}.{col}: expected numeric dtype, got {df[col].dtype}")
    return violations


def validate_curated_tables(
    tables: Dict[str, pd.DataFrame],
    raw_counts: Dict[str, int],
    supplier_set: Optional[Set[str]] = None,
    agency_set: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Enforce all reconciliation + FK + privacy gates and return status metrics.

    Temporal FK mismatches are labeled TEMPORAL_SCOPE_UNMATCHED and are NOT
    treated as data-quality failures. Out-of-scope rows arise from the split
    between opening-date-scoped awards and notice-date-scoped tenders.
    """
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

    # Gate 3: Temporal FK reporting (TEMPORAL_SCOPE_UNMATCHED = expected, not failure)
    tender_key_set = set(zip(tenders["bid_notice_no"], tenders["bid_notice_round"]))

    def _temporal_fk_metrics(df: pd.DataFrame, key_set: Set[Tuple[str, str]]) -> Dict[str, Any]:
        in_scope = df.apply(
            lambda row: (str(row.get("bid_notice_no", "")), str(row.get("bid_notice_round", ""))) in key_set,
            axis=1,
        )
        return {
            "TEMPORAL_SCOPE_MATCHED": int(in_scope.sum()),
            "TEMPORAL_SCOPE_UNMATCHED": int((~in_scope).sum()),
            "coverage_ratio": round(float(in_scope.mean()), 4) if len(df) else 0.0,
        }

    submissions_temporal = _temporal_fk_metrics(submissions, tender_key_set)
    awards_temporal = _temporal_fk_metrics(awards, tender_key_set)
    bridge_temporal = _temporal_fk_metrics(bridge, tender_key_set)

    # Gate 4: FK referential integrity (supplier_id → suppliers, agency_code → agencies)
    supplier_id_set = set(suppliers["supplier_id"].dropna())
    agency_code_set = set(agencies["agency_code"].dropna())
    contract_no_set = set(contracts["unified_contract_no"].dropna())

    def _fk_coverage(fk_col: pd.Series, target_set: Set[str], skip_empty: bool = True) -> Dict[str, Any]:
        non_null = fk_col.dropna()
        if skip_empty:
            non_null = non_null[non_null.astype(str).str.strip() != ""]
        total = len(non_null)
        if total == 0:
            return {"total": 0, "matched": 0, "unmatched": 0, "coverage_ratio": 1.0}
        matched = non_null.astype(str).isin(target_set).sum()
        return {
            "total": total,
            "matched": int(matched),
            "unmatched": int(total - matched),
            "coverage_ratio": round(matched / total, 4),
        }

    fk_metrics: Dict[str, Any] = {}
    # bidder_supplier_id → suppliers
    if "bidder_supplier_id" in submissions.columns:
        fk_metrics["submissions_bidder_supplier_id_to_suppliers"] = _fk_coverage(
            submissions["bidder_supplier_id"], supplier_id_set
        )
    # winner_supplier_id → suppliers
    if "winner_supplier_id" in awards.columns:
        fk_metrics["awards_winner_supplier_id_to_suppliers"] = _fk_coverage(
            awards["winner_supplier_id"], supplier_id_set
        )
    # contractor_supplier_id → suppliers
    if "contractor_supplier_id" in contracts.columns:
        fk_metrics["contracts_contractor_supplier_id_to_suppliers"] = _fk_coverage(
            contracts["contractor_supplier_id"], supplier_id_set
        )
    # notice agency codes → agencies
    for tbl_name, df in [("tenders", tenders), ("submissions", submissions)]:
        if "notice_agency_code" in df.columns:
            fk_metrics[f"{tbl_name}_notice_agency_code_to_agencies"] = _fk_coverage(
                df["notice_agency_code"], agency_code_set
            )
    # demand agency codes → agencies
    for tbl_name, df in [("tenders", tenders), ("submissions", submissions), ("contracts", contracts)]:
        if "demand_agency_code" in df.columns:
            fk_metrics[f"{tbl_name}_demand_agency_code_to_agencies"] = _fk_coverage(
                df["demand_agency_code"], agency_code_set
            )
    # contract_agency_code → agencies
    if "contract_agency_code" in contracts.columns:
        fk_metrics["contracts_contract_agency_code_to_agencies"] = _fk_coverage(
            contracts["contract_agency_code"], agency_code_set
        )
    # bridge.unified_contract_no → contracts
    if "unified_contract_no" in bridge.columns:
        fk_metrics["bridge_unified_contract_no_to_contracts"] = _fk_coverage(
            bridge["unified_contract_no"], contract_no_set, skip_empty=False
        )

    # Gate 5: Forbidden column checks
    all_forbidden_violations: List[str] = []
    for tbl_name, df in tables.items():
        all_forbidden_violations.extend(_check_forbidden_columns(tbl_name, df))

    # Gate 6: Dtype constraints
    all_dtype_violations: List[str] = []
    for tbl_name, df in tables.items():
        all_dtype_violations.extend(_check_dtype_constraints(tbl_name, df))

    # Gate 7: Bridge assertions – tender keys non-null, linked contracts only
    bridge_notice_non_null = (bridge["bid_notice_no"].fillna("").astype(str).str.strip() != "").all() if len(bridge) else True

    gate_privacy = len(all_forbidden_violations) == 0
    gate_dtype = len(all_dtype_violations) == 0
    gate_bridge_assertions = bridge_notice_non_null

    all_passed = bool(
        gate_bids and gate_awards and gate_winners and gate_contracts and
        gate_bridge and gate_unlinked and gate_suppliers and gate_agencies and
        pk_tenders_valid and pk_submissions_valid and pk_awards_valid and
        pk_contracts_valid and pk_suppliers_valid and pk_agencies_valid and
        pk_bridge_valid and gate_privacy and gate_dtype and gate_bridge_assertions
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
        if not gate_privacy: mismatches.append(f"forbidden columns: {all_forbidden_violations}")
        if not gate_dtype: mismatches.append(f"dtype violations: {all_dtype_violations}")
        if not gate_bridge_assertions: mismatches.append("bridge contains rows with null/empty bid_notice_no")
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
        "forbidden_column_gate_passed": gate_privacy,
        "dtype_constraint_gate_passed": gate_dtype,
        "bridge_assertions_passed": gate_bridge_assertions,
        "temporal_fk": {
            "submissions": submissions_temporal,
            "award_outcomes": awards_temporal,
            "bridge": bridge_temporal,
        },
        "fk_coverage": fk_metrics,
    }


# ---------------------------------------------------------------------------
# Main curation pipeline
# ---------------------------------------------------------------------------

def _month_partitions_in_scope(start: str, end: str) -> List[Tuple[int, int]]:
    """Return inclusive ``(year, month)`` partitions intersecting a date scope."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start must be on or before end")

    result: List[Tuple[int, int]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        result.append((year, month))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return result


def select_processed_parquet_files(
    processed_dir: Path | str,
    feed: str,
    start: str,
    end: str,
) -> List[Path]:
    """Select only year/month Parquet partitions intersecting the curation scope.

    Historical builds can contain tens of millions of rows. Reading every Parquet
    file before applying the event-date filter defeats partitioning and can exhaust
    memory. This selector bounds each curation run to the requested month(s); the
    event-date filter in ``run_curation`` still provides exact day-level scoping.
    """
    root = Path(processed_dir) / feed
    selected: List[Path] = []
    for year, month in _month_partitions_in_scope(start, end):
        partition = root / f"year={year:04d}" / f"month={month:02d}"
        if partition.exists():
            selected.extend(sorted(partition.glob("*.parquet")))
    return sorted(selected)


def _read_parquet_scope(files: List[Path], feed: str) -> pd.DataFrame:
    if not files:
        raise FileNotFoundError(f"No processed Parquet files found for scoped {feed} curation")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


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
    outputs_complete = all((dest_dir / fname).exists() for fname in target_filenames)
    metrics_complete = metrics_path is None or metrics_path.exists()
    if not force and outputs_complete and metrics_complete:
        logger.info("All curated tables already exist in %s and force=False. Skipping curation.", dest_dir)
        if metrics_path and metrics_path.exists():
            with open(metrics_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    logger.info("Starting relational curation for period %s ~ %s", start, end)

    # 1. Load only processed year/month partitions intersecting this scope.
    bids_files = select_processed_parquet_files(processed_dir, "bids", start, end)
    awards_files = select_processed_parquet_files(processed_dir, "awards", start, end)
    contracts_files = select_processed_parquet_files(processed_dir, "contracts", start, end)

    logger.info(
        "Scoped input files: bids=%d awards=%d contracts=%d",
        len(bids_files),
        len(awards_files),
        len(contracts_files),
    )
    bids_raw = _read_parquet_scope(bids_files, "bids")
    awards_raw = _read_parquet_scope(awards_files, "awards")
    contracts_raw = _read_parquet_scope(contracts_files, "contracts")

    # Scope strictly by event date
    aug_bids = bids_raw[(bids_raw["bid_notice_date"].astype(str).str[:10] >= start) & (bids_raw["bid_notice_date"].astype(str).str[:10] <= end)].copy()
    aug_awards = awards_raw[(awards_raw["opening_date"].astype(str).str[:10] >= start) & (awards_raw["opening_date"].astype(str).str[:10] <= end)].copy()
    aug_contracts = contracts_raw[(contracts_raw["contract_date"].astype(str).str[:10] >= start) & (contracts_raw["contract_date"].astype(str).str[:10] <= end)].copy()

    # Calculate raw baselines
    aug_winners = aug_awards[aug_awards["is_selected_winner"] == True]
    linked_contracts = aug_contracts[aug_contracts["bid_notice_no"].fillna("").astype(str).str.strip() != ""]

    bidder_biz = _valid_business_numbers(aug_awards["bidder_business_registration_no"])
    winner_biz = _valid_business_numbers(aug_winners["winner_business_registration_no"])
    cnt_biz = _valid_business_numbers(aug_contracts["contractor_business_registration_no"])
    all_suppliers_set = set(bidder_biz) | set(winner_biz) | set(cnt_biz)

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
    suppliers_df, supplier_name_conflict_count = build_curated_suppliers(aug_awards, aug_contracts, hmac_key)
    agencies_df, agency_name_conflict_count = build_curated_agencies(aug_bids, aug_contracts)
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
        "deterministic_build": True,
        "surrogate_id_serialization": "canonical_json_v1",
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
                "temporal_fk_label": "TEMPORAL_SCOPE_UNMATCHED rows are expected cross-period records, not data errors",
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
                "temporal_fk_label": "TEMPORAL_SCOPE_UNMATCHED rows are expected cross-period records, not data errors",
                "award_amount_krw_null_count": aw_null_cnt,
                "award_amount_krw_null_ratio": aw_null_ratio,
                "award_amount_null_cause": (
                    f"OBSERVED: NULL present in raw API snapshot for {aw_null_cnt} selected-winner entries. "
                    "The missing values are preserved source-faithfully; no administrative cause is inferred from absence alone."
                ),
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
                "name_conflict_count": supplier_name_conflict_count,
                "name_resolution_policy": "most_frequent_normalized_name_with_lex_tiebreak",
                "snapshot_stats_note": "snapshot_total_* columns are time-window aggregates only; NOT stable identity; must NOT be used as leak-free historical ML features",
                "masked_biz_no_excluded": True,
                "privacy_note": "supplier_id is sole public identity; company names require final privacy/license review before Kaggle publication",
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
                "name_conflict_count": agency_name_conflict_count,
                "name_resolution_policy": "most_frequent_normalized_name_with_lex_tiebreak",
                "snapshot_stats_note": "snapshot_total_* columns are time-window aggregates only; NOT stable identity; must NOT be used as leak-free historical ML features",
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
                "temporal_fk_label": "TEMPORAL_SCOPE_UNMATCHED rows are expected cross-period records, not data errors",
            },
        },
        "award_amount_null_forensics": {
            "null_count": aw_null_cnt,
            "null_ratio": aw_null_ratio,
            "cause_classification": "OBSERVED",
            "rank_distribution": rank_dist,
            "award_method_distribution": mapped_method_dist,
            "imputation_policy": (
                "DO_NOT_IMPUTE: Preserve NULL exactly as observed in the source API snapshot unless an authoritative source supplies the value."
            ),
        },
        "storage": storage_metrics,
        "fk_coverage": gates_result.get("fk_coverage", {}),
        "name_resolution": {
            "supplier_name_conflict_count": supplier_name_conflict_count,
            "agency_name_conflict_count": agency_name_conflict_count,
        },
        "forbidden_column_validation": {
            "passed": True,
            "violations": [],
        },
    }

    if metrics_path:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2, cls=_NumpyEncoder)
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
