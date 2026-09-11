"""Build the flat, one-row-per-tender Kaggle quickstart CSV.

The canonical public release remains relational.  This module adds a deliberately
small convenience derivative so a Kaggle user can start EDA without understanding
or joining the seven canonical Parquet tables first.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd


QUICKSTART_FILENAME = "00_quickstart_tender_summary.csv"

TENDER_COLUMNS = [
    "bid_notice_no",
    "bid_notice_round",
    "bid_title_ko",
    "bid_notice_date",
    "business_div_name_ko",
    "contract_method_ko",
    "notice_agency_code",
    "notice_agency_name_ko",
    "demand_agency_code",
    "demand_agency_name_ko",
    "assigned_budget_krw",
    "estimated_price_krw",
    "is_electronic_bid",
    "is_international_bid",
    "is_region_limited",
    "is_industry_limited",
]

AWARD_COLUMNS = [
    "bid_notice_no",
    "bid_notice_round",
    "tender_in_scope",
    "award_rate",
    "award_date",
]

BRIDGE_COLUMNS = [
    "bid_notice_no",
    "bid_notice_round",
    "tender_in_scope",
    "unified_contract_no",
    "contract_date",
]

QUICKSTART_COLUMNS = [
    "bid_notice_no",
    "bid_notice_round",
    "bid_title_ko",
    "bid_notice_date",
    "business_div_name_ko",
    "business_division_en",
    "contract_method_ko",
    "contract_method_group_en",
    "notice_agency_code",
    "notice_agency_name_ko",
    "demand_agency_code",
    "demand_agency_name_ko",
    "assigned_budget_krw",
    "estimated_price_krw",
    "is_electronic_bid",
    "is_international_bid",
    "is_region_limited",
    "is_industry_limited",
    "has_selected_award",
    "selected_award_count",
    "valid_award_rate_count",
    "median_award_rate_pct",
    "mean_award_rate_pct",
    "first_award_date",
    "last_award_date",
    "has_linked_contract",
    "linked_contract_count",
    "first_contract_date",
    "last_contract_date",
]

QUICKSTART_KAGGLE_TYPES = {
    "bid_notice_no": "string",
    "bid_notice_round": "string",
    "bid_title_ko": "string",
    "bid_notice_date": "datetime",
    "business_div_name_ko": "string",
    "business_division_en": "string",
    "contract_method_ko": "string",
    "contract_method_group_en": "string",
    "notice_agency_code": "string",
    "notice_agency_name_ko": "string",
    "demand_agency_code": "string",
    "demand_agency_name_ko": "string",
    "assigned_budget_krw": "number",
    "estimated_price_krw": "number",
    "is_electronic_bid": "boolean",
    "is_international_bid": "boolean",
    "is_region_limited": "boolean",
    "is_industry_limited": "boolean",
    "has_selected_award": "boolean",
    "selected_award_count": "integer",
    "valid_award_rate_count": "integer",
    "median_award_rate_pct": "number",
    "mean_award_rate_pct": "number",
    "first_award_date": "datetime",
    "last_award_date": "datetime",
    "has_linked_contract": "boolean",
    "linked_contract_count": "integer",
    "first_contract_date": "datetime",
    "last_contract_date": "datetime",
}


def _normalize_label(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value).strip())


def business_division_en(value: Any) -> str:
    """Map common KONEPS Korean business divisions to stable English labels."""
    normalized = _normalize_label(value)
    if not normalized:
        return "Unknown"
    for token, label in (
        ("용역", "Services"),
        ("공사", "Construction"),
        ("물품", "Goods"),
        ("외자", "Foreign supplies"),
    ):
        if token in normalized:
            return label
    return str(value).strip()


def contract_method_group_en(value: Any) -> str:
    """Map common KONEPS contract methods while preserving unknown source labels."""
    normalized = _normalize_label(value)
    if not normalized:
        return "Unknown"
    if "수의" in normalized:
        return "Direct / negotiated"
    if ("제한" in normalized) and ("경쟁" in normalized):
        return "Restricted competition"
    if ("일반" in normalized) and ("경쟁" in normalized):
        return "Open competition"
    if ("지명" in normalized) and ("경쟁" in normalized):
        return "Selective competition"
    return str(value).strip()


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_quickstart_csv(
    release_dir: Path | str,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a flat tender-level CSV from the canonical public Parquet tables."""
    release_dir = Path(release_dir)
    output = Path(output_path) if output_path else release_dir / QUICKSTART_FILENAME

    tenders = pd.read_parquet(release_dir / "01_tenders.parquet", columns=TENDER_COLUMNS)
    tender_keys = ["bid_notice_no", "bid_notice_round"]
    if tenders.duplicated(tender_keys).any():
        raise ValueError("Quickstart requires one canonical tender row per notice/round key")

    awards = pd.read_parquet(release_dir / "03_award_outcomes.parquet", columns=AWARD_COLUMNS)
    awards = awards.loc[awards["tender_in_scope"].fillna(False)].copy()
    awards["valid_award_rate"] = awards["award_rate"].where(
        awards["award_rate"].between(0, 100, inclusive="both")
    )
    award_summary = (
        awards.groupby(tender_keys, as_index=False, dropna=False)
        .agg(
            selected_award_count=("award_rate", "size"),
            valid_award_rate_count=("valid_award_rate", "count"),
            median_award_rate_pct=("valid_award_rate", "median"),
            mean_award_rate_pct=("valid_award_rate", "mean"),
            first_award_date=("award_date", "min"),
            last_award_date=("award_date", "max"),
        )
    )

    bridge = pd.read_parquet(
        release_dir / "07_tender_contract_bridge.parquet", columns=BRIDGE_COLUMNS
    )
    bridge = bridge.loc[bridge["tender_in_scope"].fillna(False)].copy()
    contract_summary = (
        bridge.groupby(tender_keys, as_index=False, dropna=False)
        .agg(
            linked_contract_count=("unified_contract_no", "nunique"),
            first_contract_date=("contract_date", "min"),
            last_contract_date=("contract_date", "max"),
        )
    )

    result = tenders.merge(award_summary, on=tender_keys, how="left", validate="one_to_one")
    result = result.merge(contract_summary, on=tender_keys, how="left", validate="one_to_one")
    result.insert(
        result.columns.get_loc("business_div_name_ko") + 1,
        "business_division_en",
        result["business_div_name_ko"].map(business_division_en),
    )
    result.insert(
        result.columns.get_loc("contract_method_ko") + 1,
        "contract_method_group_en",
        result["contract_method_ko"].map(contract_method_group_en),
    )

    for name in ("selected_award_count", "valid_award_rate_count", "linked_contract_count"):
        result[name] = result[name].fillna(0).astype("int64")
    result.insert(
        result.columns.get_loc("selected_award_count"),
        "has_selected_award",
        result["selected_award_count"].gt(0),
    )
    result.insert(
        result.columns.get_loc("linked_contract_count"),
        "has_linked_contract",
        result["linked_contract_count"].gt(0),
    )
    result = result[QUICKSTART_COLUMNS]

    if len(result) != len(tenders) or result.duplicated(tender_keys).any():
        raise ValueError("Quickstart tender grain changed during aggregation/join")
    if any("supplier" in name.lower() for name in result.columns):
        raise ValueError("Quickstart CSV must not expose supplier identifiers")
    if int(result["selected_award_count"].sum()) != len(awards):
        raise ValueError("Quickstart selected-award counts do not reconcile to in-scope awards")
    valid_award_rows = int(awards["valid_award_rate"].notna().sum())
    if int(result["valid_award_rate_count"].sum()) != valid_award_rows:
        raise ValueError("Quickstart valid award-rate counts do not reconcile")
    expected_contract_links = len(
        bridge[tender_keys + ["unified_contract_no"]].drop_duplicates()
    )
    if int(result["linked_contract_count"].sum()) != expected_contract_links:
        raise ValueError("Quickstart linked-contract counts do not reconcile")

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    result.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\n")
    tmp.replace(output)
    return {
        "file": output.name,
        "rows": len(result),
        "columns": len(result.columns),
        "bytes": output.stat().st_size,
        "sha256": _sha256_file(output),
        "tenders_with_selected_awards": int(result["has_selected_award"].sum()),
        "tenders_with_linked_contracts": int(result["has_linked_contract"].sum()),
        "selected_award_rows_reconciled": len(awards),
        "valid_award_rate_rows_reconciled": valid_award_rows,
        "distinct_tender_contract_links_reconciled": expected_contract_links,
    }
