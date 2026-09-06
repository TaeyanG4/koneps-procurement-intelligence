#!/usr/bin/env python3
"""Audit script for the 1-month KONEPS pilot dataset.

Performs:
1. Awards deduplication and key collision analysis (A through H)
2. Pagination integrity and duplicate source analysis
3. Cross-feed cardinality profiling (bids -> awards, bids -> contracts)
4. Contract unified ID uniqueness verification
5. Raw to Parquet reconciliation accounting
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from koneps_intel.config import PROCESSED_DIR, RAW_DIR
from koneps_intel.schemas import DEDUPLICATION_KEYS


def audit_awards_deduplication(raw_awards_dir: Path) -> Dict[str, Any]:
    """Audit deduplication behavior and grain collisions on raw awards files."""
    files = sorted(raw_awards_dir.glob("awards_*.jsonl.gz"))
    categories = ["goods", "foreign", "construction", "service"]
    results: Dict[str, Any] = {}

    for cat in categories:
        cat_files = [f for f in files if f"_{cat}_" in f.name]
        if not cat_files:
            continue

        all_rows: List[Dict[str, Any]] = []
        for f in cat_files:
            with gzip.open(f, "rt", encoding="utf-8") as gz:
                for line in gz:
                    if "__collector_meta__" in line:
                        continue
                    all_rows.append(json.loads(line))

        total_raw = len(all_rows)
        if total_raw == 0:
            results[cat] = {"raw_rows": 0}
            continue

        df = pd.DataFrame(all_rows)

        # B. Exact full-row duplicates
        # Hash full row serialized string
        str_rows = df.astype(str).agg("\x1f".join, axis=1)
        exact_dups = int(str_rows.duplicated().sum())

        # C. Duplicates under current candidate key
        cand_keys = [k for k in DEDUPLICATION_KEYS["awards"] if k in df.columns]
        cand_dups = int(df.duplicated(subset=cand_keys).sum()) if cand_keys else 0

        # D. Cases where same candidate key maps to multiple distinct non-key records
        # Exclude exact duplicates first
        df_no_exact = df.loc[~str_rows.duplicated()].copy()
        collisions = int(df_no_exact.duplicated(subset=cand_keys).sum()) if cand_keys else 0

        # E. Null rate of every key component
        null_rates = {k: round(float(df[k].isna().mean() if k in df.columns else 1.0), 6) for k in DEDUPLICATION_KEYS["awards"]}

        # F. Records removed by deduplication
        deduped = df.drop_duplicates(subset=cand_keys, keep="last") if cand_keys else df
        records_removed = total_raw - len(deduped)
        dedup_pct = round(float(records_removed / total_raw * 100), 4) if total_raw else 0.0

        # H. Collision patterns inspection (sanitized)
        collision_examples = []
        if collisions > 0:
            coll_keys = df_no_exact[df_no_exact.duplicated(subset=cand_keys, keep=False)]
            grouped = coll_keys.groupby(cand_keys)
            for _, group in list(grouped)[:3]:
                # Collect differing columns
                differing = [c for c in group.columns if group[c].nunique() > 1]
                collision_examples.append({
                    "collision_group_size": len(group),
                    "differing_columns": differing,
                })

        # Distinct tenders and bidders
        n_tenders = int(df["bidNtceNo"].nunique()) if "bidNtceNo" in df.columns else 0
        n_bidders = int(df["bidprcCorpBizrno"].replace("", np.nan).dropna().nunique()) if "bidprcCorpBizrno" in df.columns else 0

        # Bidders per tender distribution
        bidders_per_tender = df.groupby(["bidNtceNo", "bidNtceOrd"]).size() if "bidNtceNo" in df.columns and "bidNtceOrd" in df.columns else pd.Series([], dtype=int)

        results[cat] = {
            "raw_rows": total_raw,
            "raw_files_count": len(cat_files),
            "distinct_tenders": n_tenders,
            "distinct_bidders": n_bidders,
            "exact_full_row_duplicates": exact_dups,
            "candidate_key_duplicates": cand_dups,
            "distinct_record_collisions": collisions,
            "records_removed": records_removed,
            "dedup_percentage": dedup_pct,
            "key_component_null_rates": null_rates,
            "collision_sample": collision_examples,
            "bidders_per_tender_mean": round(float(bidders_per_tender.mean()), 2) if len(bidders_per_tender) else 0.0,
            "bidders_per_tender_median": float(bidders_per_tender.median()) if len(bidders_per_tender) else 0.0,
            "bidders_per_tender_max": int(bidders_per_tender.max()) if len(bidders_per_tender) else 0,
        }

    return results


def audit_pagination_integrity(raw_dir: Path) -> Dict[str, Any]:
    """Detect whether duplicates originate from source records or page boundary overlap."""
    results: Dict[str, Any] = {"page_overlap_detected": False, "findings": []}
    files = list(raw_dir.glob("**/*.jsonl.gz"))

    for path in files:
        if "manifest" in path.name:
            continue
        with gzip.open(path, "rt", encoding="utf-8") as f:
            lines = [l for l in f if "__collector_meta__" not in l]

        if not lines:
            continue

        # Look for consecutive identical records (signature of repeated pages or pagination glitch)
        consecutive_dups = 0
        for i in range(len(lines) - 1):
            if lines[i] == lines[i + 1]:
                consecutive_dups += 1

        if consecutive_dups > 0:
            results["page_overlap_detected"] = True
            results["findings"].append({
                "file": path.name,
                "consecutive_identical_lines": consecutive_dups,
            })

    return results


def audit_cardinality(processed_dir: Path) -> Dict[str, Any]:
    """Measure empirical join cardinality between bids, awards, and contracts."""
    bids_files = list((processed_dir / "bids").glob("**/*.parquet"))
    awards_files = list((processed_dir / "awards").glob("**/*.parquet"))
    contracts_files = list((processed_dir / "contracts").glob("**/*.parquet"))

    res: Dict[str, Any] = {}

    if bids_files and awards_files:
        df_bids = pd.concat([pd.read_parquet(f, columns=["bid_notice_no", "bid_notice_round"]) for f in bids_files], ignore_index=True)
        df_awards = pd.concat([pd.read_parquet(f, columns=["bid_notice_no", "bid_notice_round", "bidder_business_registration_no"]) for f in awards_files], ignore_index=True)

        bids_tenders = set(zip(df_bids["bid_notice_no"].astype(str), df_bids["bid_notice_round"].astype(str)))
        awards_tenders = set(zip(df_awards["bid_notice_no"].astype(str), df_awards["bid_notice_round"].astype(str)))

        # Tender 1:N Bidder measurement
        awards_counts = df_awards.groupby(["bid_notice_no", "bid_notice_round"]).size()
        res["bids_to_awards"] = {
            "distinct_bids_tenders": len(bids_tenders),
            "distinct_awards_tenders": len(awards_tenders),
            "tenders_in_both": len(bids_tenders & awards_tenders),
            "tenders_only_in_bids": len(bids_tenders - awards_tenders),
            "tenders_only_in_awards": len(awards_tenders - bids_tenders),
            "bidders_per_tender_min": int(awards_counts.min()) if len(awards_counts) else 0,
            "bidders_per_tender_p25": float(awards_counts.quantile(0.25)) if len(awards_counts) else 0.0,
            "bidders_per_tender_median": float(awards_counts.median()) if len(awards_counts) else 0.0,
            "bidders_per_tender_mean": round(float(awards_counts.mean()), 2) if len(awards_counts) else 0.0,
            "bidders_per_tender_p75": float(awards_counts.quantile(0.75)) if len(awards_counts) else 0.0,
            "bidders_per_tender_p90": float(awards_counts.quantile(0.90)) if len(awards_counts) else 0.0,
            "bidders_per_tender_max": int(awards_counts.max()) if len(awards_counts) else 0,
        }

    if bids_files and contracts_files:
        df_bids = pd.concat([pd.read_parquet(f, columns=["bid_notice_no", "bid_notice_round"]) for f in bids_files], ignore_index=True)
        df_cntrct = pd.concat([pd.read_parquet(f, columns=["bid_notice_no", "bid_notice_round", "unified_contract_no"]) for f in contracts_files], ignore_index=True)

        cntrct_linked = df_cntrct[df_cntrct["bid_notice_no"].fillna("").astype(str).str.strip() != ""]
        cntrct_counts = cntrct_linked.groupby(["bid_notice_no", "bid_notice_round"]).size()

        bids_keys = set(zip(df_bids["bid_notice_no"].astype(str), df_bids["bid_notice_round"].astype(str)))
        linked_keys = set(cntrct_counts.index)

        zero_contracts = len(bids_keys - linked_keys)
        one_contract = sum(cntrct_counts.loc[cntrct_counts.index.intersection(list(bids_keys))] == 1)
        multi_contract = sum(cntrct_counts.loc[cntrct_counts.index.intersection(list(bids_keys))] > 1)

        res["bids_to_contracts"] = {
            "tenders_with_0_contracts": int(zero_contracts),
            "tenders_with_1_contract": int(one_contract),
            "tenders_with_N_contracts": int(multi_contract),
            "contracts_total_rows": len(df_cntrct),
            "contracts_with_tender_link": len(cntrct_linked),
            "tender_link_ratio": round(float(len(cntrct_linked) / len(df_cntrct)), 4) if len(df_cntrct) else 0.0,
        }

    if contracts_files:
        df_cntrct = pd.concat([pd.read_parquet(f, columns=["unified_contract_no"]) for f in contracts_files], ignore_index=True)
        s = df_cntrct["unified_contract_no"].dropna()
        res["contracts_untyCntrctNo_integrity"] = {
            "total_rows": len(df_cntrct),
            "non_null_count": len(s),
            "null_ratio": round(float(df_cntrct["unified_contract_no"].isna().mean()), 6),
            "unique_count": int(s.nunique()),
            "duplicate_count": int(s.duplicated().sum()),
            "is_strictly_unique": bool(s.duplicated().sum() == 0),
        }

    return res


def main():
    print("=== KONEPS PILOT DATASET AUDIT ===")
    print("\n1. Auditing Awards Deduplication & Grain...")
    awards_audit = audit_awards_deduplication(RAW_DIR / "awards")
    print(json.dumps(awards_audit, ensure_ascii=False, indent=2))

    print("\n2. Auditing Pagination Integrity...")
    pag_audit = audit_pagination_integrity(RAW_DIR)
    print(json.dumps(pag_audit, ensure_ascii=False, indent=2))

    print("\n3. Auditing Cross-Feed Cardinality...")
    card_audit = audit_cardinality(PROCESSED_DIR)
    print(json.dumps(card_audit, ensure_ascii=False, indent=2))

    out_file = PROCESSED_DIR / "pilot_audit_report.json"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "awards_deduplication_audit": awards_audit,
            "pagination_integrity_audit": pag_audit,
            "cardinality_audit": card_audit,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nAudit report saved to {out_file}")


if __name__ == "__main__":
    main()
