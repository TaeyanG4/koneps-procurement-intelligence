"""Generate complete Kaggle dataset metadata for the public KONEPS release."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict

import pyarrow as pa
import pyarrow.parquet as pq

from koneps_intel.release import PUBLIC_DIMENSION_FILES, PUBLIC_FACT_FILES


DATASET_TITLE = "KONEPS Public Procurement Intelligence"
DATASET_SUBTITLE = "South Korea tenders, 35.9M bids, awards and contracts"
DEFAULT_SLUG = "koneps-public-procurement-intelligence"

FILE_DESCRIPTIONS = {
    "01_tenders.parquet": "One row per KONEPS tender notice and notice round in the Sep 2025-Aug 2026 release scope.",
    "02_bidder_submissions.parquet": "One row per bidder submission/opening record. Supplier identity is pseudonymized; company names and business registration numbers are excluded.",
    "03_award_outcomes.parquet": "Selected-winner subset of bidder submissions, with final award values and pricing context where available.",
    "04_contracts.parquet": "One row per unified KONEPS contract record, including contract value, agencies, dates, methods and pseudonymized contractor reference.",
    "05_suppliers.parquet": "Global 12-month supplier dimension keyed only by HMAC-SHA256 supplier_id, with full-window activity snapshots and no company names or business numbers.",
    "06_agencies.parquet": "Global public-agency dimension with agency codes, latest observed Korean agency names, role flags and 12-month activity snapshots.",
    "07_tender_contract_bridge.parquet": "Relationship bridge from contracts carrying tender references to tender notice keys, with full-release tender_in_scope membership.",
}

COLUMN_DESCRIPTIONS = {
    "agency_code": "Official public-agency identifier used as the agency dimension key.",
    "agency_name_ko": "Latest observed official Korean name for the public agency within the release scope.",
    "assigned_budget_krw": "Budget assigned to the tender, in South Korean won (KRW).",
    "award_amount_krw": "Final award amount reported by KONEPS, in KRW; source nulls are preserved.",
    "award_date": "Date of the final award/selection decision when reported.",
    "award_lower_limit_rate": "Lower-bound award/bid rate threshold reported by KONEPS, in percent.",
    "award_method_ko": "Original Korean label for the winning-bidder determination method.",
    "award_outcome_id": "Deterministic public surrogate key for a selected award outcome (AWD_ prefix).",
    "award_rate": "Final award rate reported by KONEPS, in percent.",
    "base_amount_krw": "Base reference amount used in procurement pricing, in KRW.",
    "bid_amount_krw": "Submitted bid amount, in KRW; source anomalies such as negative values are preserved.",
    "bid_begin_date": "Tender submission window start date.",
    "bid_begin_time": "Tender submission window start time when available.",
    "bid_close_date": "Tender submission deadline date.",
    "bid_close_time": "Tender submission deadline time when available.",
    "bid_notice_date": "Date the tender notice was published.",
    "bid_notice_no": "KONEPS tender announcement number.",
    "bid_notice_round": "Tender announcement revision/round sequence.",
    "bid_notice_time": "Tender notice publication time when available.",
    "bid_notice_url": "KONEPS URL associated with the tender notice when reported.",
    "bid_rate": "Submitted bid rate reported by KONEPS, in percent.",
    "bid_submission_date": "Date the bidder submission was made when reported.",
    "bid_submission_id": "Deterministic public surrogate key for a bidder submission (BID_ prefix).",
    "bid_submission_time": "Bid submission time used as part of the lossless submission grain.",
    "bid_title_ko": "Original Korean tender title.",
    "bidder_supplier_id": "Pseudonymized HMAC-SHA256 supplier reference for the bidder; blank when no valid 10-digit business identifier was available.",
    "business_div_name_ko": "Original Korean procurement business division label, such as goods, foreign supplies, construction or services.",
    "contract_agency_code": "Official code of the contracting agency.",
    "contract_agency_name_ko": "Original Korean name of the contracting agency.",
    "contract_amount_krw": "Signed amount for the contract record/installment, in KRW; source negative values are preserved.",
    "contract_date": "Date the contract was concluded.",
    "contract_info_url": "KONEPS URL for contract information when reported.",
    "contract_method_ko": "Original Korean label for the procurement/contract conclusion method.",
    "contract_no": "Agency contract number associated with the unified contract record.",
    "contract_period": "Contract duration/period text as reported by KONEPS.",
    "contract_round": "Contract modification or round sequence.",
    "contract_status_ko": "Original Korean contract conclusion/status label.",
    "contract_title_ko": "Original Korean contract title.",
    "contractor_supplier_id": "Pseudonymized HMAC-SHA256 supplier reference for the contractor; blank when no valid business identifier was available.",
    "data_base_date": "Source-system data base/reference date reported by KONEPS.",
    "demand_agency_code": "Official identifier of the end-demand public agency.",
    "demand_agency_name_ko": "Original Korean name of the end-demand public agency.",
    "disqualification_reason_ko": "Original Korean bidder disqualification reason, if any.",
    "estimated_price_krw": "Estimated procurement price reported by KONEPS, in KRW.",
    "is_bidder": "True if the pseudonymized supplier submitted at least one bid in the release scope.",
    "is_contract_agency": "True if the agency appeared as a contracting agency in the release scope.",
    "is_contractor": "True if the pseudonymized supplier appeared as a contractor in the release scope.",
    "is_demand_agency": "True if the agency appeared as an end-demand agency in the release scope.",
    "is_domestic_corp": "KONEPS indicator that the contractor is a domestic corporation.",
    "is_electronic_bid": "KONEPS indicator that the tender uses electronic bidding.",
    "is_industry_limited": "KONEPS indicator that industry/license restrictions apply.",
    "is_international_bid": "KONEPS indicator that the tender is international.",
    "is_joint_contract": "KONEPS indicator for joint/common contracting.",
    "is_notice_agency": "True if the agency appeared as a tender notice publisher in the release scope.",
    "is_pps_notice": "KONEPS indicator that the Public Procurement Service manages the notice.",
    "is_region_limited": "KONEPS indicator that regional participation restrictions apply.",
    "is_selected_winner": "True when the bidder submission was selected as a winner.",
    "is_winner": "True if the pseudonymized supplier was selected as a winner at least once in the release scope.",
    "long_term_contract_div_ko": "Original Korean long-term/continuing-contract classification.",
    "match_type": "Rule/category describing how the contract was linked to the tender key.",
    "notice_agency_code": "Official identifier of the public agency that published the tender notice.",
    "notice_agency_name_ko": "Original Korean name of the tender notice publishing agency.",
    "opening_date": "Bid opening date.",
    "opening_place_ko": "Original Korean text describing the bid opening place.",
    "opening_rank": "Rank reported at bid opening; lower values generally indicate higher placement.",
    "opening_result_status_ko": "Original Korean opening-result status label.",
    "opening_time": "Bid opening time when reported.",
    "private_contract_reason_ko": "Original Korean reason text for a private/direct contract when reported.",
    "ref_notice_no": "Referenced or preceding tender notice number when reported.",
    "ref_notice_round": "Referenced tender notice round when reported.",
    "scheduled_price_krw": "Final scheduled/reference price reported for bid evaluation, in KRW.",
    "snapshot_total_bids_in_scope": "Supplier bid count aggregated over the complete 12-month release scope; not a leak-free historical feature.",
    "snapshot_total_contract_amount_krw": "Supplier contract amount aggregated over the complete 12-month release scope; not a leak-free historical feature.",
    "snapshot_total_contracts_in_scope": "Contract count aggregated over the complete 12-month release scope; not a leak-free historical feature.",
    "snapshot_total_tenders_in_scope": "Agency tender count aggregated over the complete 12-month release scope; not a leak-free historical feature.",
    "snapshot_total_wins_in_scope": "Supplier selected-win count aggregated over the complete 12-month release scope; not a leak-free historical feature.",
    "supplier_id": "Stable pseudonymized supplier key generated with HMAC-SHA256 and a private project secret.",
    "tender_in_scope": "True when the referenced tender key exists in the complete Sep 2025-Aug 2026 public tender table.",
    "total_contract_amount_krw": "Cumulative total contract amount reported by KONEPS, in KRW; source negative values are preserved.",
    "unified_contract_no": "National unified contract identifier and public contract-table key.",
    "winner_supplier_id": "Pseudonymized HMAC-SHA256 supplier reference for the selected winner.",
}


def _kaggle_type(data_type: pa.DataType) -> str:
    if pa.types.is_boolean(data_type):
        return "boolean"
    if pa.types.is_integer(data_type):
        return "integer"
    if pa.types.is_floating(data_type) or pa.types.is_decimal(data_type):
        return "number"
    if pa.types.is_date(data_type) or pa.types.is_timestamp(data_type):
        return "datetime"
    return "string"


def _validate_owner(owner: str) -> str:
    value = owner.strip()
    if not value or "/" in value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Kaggle owner must be a username/organization slug without slashes")
    return value


def build_dataset_metadata(
    release_dir: Path | str,
    owner: str,
    slug: str = DEFAULT_SLUG,
    output_path: Path | str | None = None,
) -> Dict[str, Any]:
    release_dir = Path(release_dir)
    owner = _validate_owner(owner)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,49}", slug):
        raise ValueError("Kaggle dataset slug must be 3-50 lowercase alphanumeric/hyphen characters")

    resources = []
    release_files = list(PUBLIC_FACT_FILES + PUBLIC_DIMENSION_FILES)
    for filename in release_files:
        path = release_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        schema = pq.ParquetFile(path).schema_arrow
        unknown = [field.name for field in schema if field.name not in COLUMN_DESCRIPTIONS]
        if unknown:
            raise ValueError(f"Missing Kaggle column descriptions for {filename}: {unknown}")
        resources.append(
            {
                "path": filename,
                "description": FILE_DESCRIPTIONS[filename],
                "schema": {
                    "fields": [
                        {
                            "name": field.name,
                            "description": COLUMN_DESCRIPTIONS[field.name],
                            "type": _kaggle_type(field.type),
                        }
                        for field in schema
                    ]
                },
            }
        )

    metadata: Dict[str, Any] = {
        "title": DATASET_TITLE,
        "subtitle": DATASET_SUBTITLE,
        "description": (
            "Research-ready relational public procurement data from South Korea's KONEPS, covering "
            "2025-09-01 through 2026-08-31. The release contains 470,937 tenders, 35.9 million bidder "
            "submissions, 305,995 selected award outcomes, 1.89 million contracts, pseudonymized "
            "suppliers, public agencies, and a tender-contract bridge. Supplier company names and raw "
            "or masked business registration numbers are excluded; supplier identity uses stable "
            "HMAC-SHA256 IDs. Source: Public Procurement Service via data.go.kr KONEPS Public Data "
            "Open Standard Service. The source service page was re-verified on 2026-09-11 and lists "
            "its scope of license as unrestricted: https://www.data.go.kr/en/data/15023678/standard.do"
        ),
        "id": f"{owner}/{slug}",
        "licenses": [{"name": "other"}],
        "resources": resources,
        "keywords": ["government", "economics", "business", "south korea", "public policy"],
    }

    target = Path(output_path) if output_path else release_dir / "dataset-metadata.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    tmp.replace(target)
    return metadata


def configured_kaggle_owner() -> str | None:
    """Return a user-managed Kaggle owner from environment, if configured."""
    value = os.getenv("KAGGLE_USERNAME", "").strip()
    return value or None
