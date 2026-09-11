"""Restartable month-by-month curation for the historical KONEPS release.

The monthly runner deliberately reuses the verified relational curation gates while
bounding memory to one calendar month at a time. Each month is independently
materialized and accompanied by a sanitized metrics JSON, so interrupted runs can
resume without rebuilding completed months.
"""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from koneps_intel.curate import CURATED_SCHEMA_VERSION, run_curation
from koneps_intel.utils import get_logger


logger = get_logger("koneps_intel.historical_curate")


CURATED_FILENAMES = (
    "01_tenders.parquet",
    "02_bidder_submissions.parquet",
    "03_award_outcomes.parquet",
    "04_contracts.parquet",
    "05_suppliers.parquet",
    "06_agencies.parquet",
    "07_tender_contract_bridge.parquet",
)


def month_scopes(start: str, end: str) -> List[Tuple[str, str]]:
    """Split an inclusive date range into inclusive calendar-month scopes."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start must be on or before end")

    scopes: List[Tuple[str, str]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        first = date(year, month, 1)
        last = date(year, month, monthrange(year, month)[1])
        scoped_start = max(first, start_date)
        scoped_end = min(last, end_date)
        scopes.append((scoped_start.isoformat(), scoped_end.isoformat()))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return scopes


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _month_complete(out_dir: Path, metrics_path: Path) -> bool:
    return metrics_path.exists() and all((out_dir / name).exists() for name in CURATED_FILENAMES)


def run_historical_curation(
    start: str,
    end: str,
    processed_dir: Path | str,
    out_root: Optional[Path | str] = None,
    metrics_root: Optional[Path | str] = None,
    summary_path: Optional[Path | str] = None,
    max_months: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Build historical curated data month by month with resumable checkpoints."""
    if max_months is not None and max_months < 0:
        raise ValueError("max_months must be non-negative")

    processed_dir = Path(processed_dir)
    out_root = Path(out_root) if out_root else processed_dir / "curated_monthly"
    metrics_root = Path(metrics_root) if metrics_root else processed_dir / "curated_metrics"
    summary_path = (
        Path(summary_path)
        if summary_path
        else processed_dir / "historical_curated_summary.json"
    )

    planned = month_scopes(start, end)
    selected = planned if max_months is None else planned[:max_months]
    months: List[Dict[str, Any]] = []

    for scope_start, scope_end in selected:
        month_key = scope_start[:7]
        label = month_key.replace("-", "_")
        month_out = out_root / label
        month_metrics = metrics_root / f"curated_{label}.json"
        was_complete = _month_complete(month_out, month_metrics)

        logger.info("Historical curation month %s (%s .. %s)", month_key, scope_start, scope_end)
        metrics = run_curation(
            start=scope_start,
            end=scope_end,
            processed_dir=processed_dir,
            out_dir=month_out,
            public_metrics_path=month_metrics,
            force=force,
        )
        if not metrics and month_metrics.exists():
            with open(month_metrics, "r", encoding="utf-8") as handle:
                metrics = json.load(handle)

        table_metrics = metrics.get("table_metrics", {})
        storage = metrics.get("storage", {})
        months.append(
            {
                "month": month_key,
                "scope_start": scope_start,
                "scope_end": scope_end,
                "status": "reused" if was_complete and not force else "built",
                "all_reconciliation_gates_passed": metrics.get("reconciliation_gates", {}).get(
                    "all_reconciliation_gates_passed", False
                ),
                "tenders": table_metrics.get("tenders", {}).get("row_count", 0),
                "bidder_submissions": table_metrics.get("bidder_submissions", {}).get(
                    "row_count", 0
                ),
                "award_outcomes": table_metrics.get("award_outcomes", {}).get("row_count", 0),
                "contracts": table_metrics.get("contracts", {}).get("row_count", 0),
                "curated_bytes": storage.get("total_curated_bytes", 0),
            }
        )

        summary = {
            "schema_version": CURATED_SCHEMA_VERSION,
            "scope_start": start,
            "scope_end": end,
            "planned_months": len(planned),
            "selected_months_this_run": len(selected),
            "completed_months_in_summary": len(months),
            "all_selected_months_passed": all(
                item["all_reconciliation_gates_passed"] for item in months
            ),
            "totals": {
                "tenders": sum(item["tenders"] for item in months),
                "bidder_submissions": sum(item["bidder_submissions"] for item in months),
                "award_outcomes": sum(item["award_outcomes"] for item in months),
                "contracts": sum(item["contracts"] for item in months),
                "curated_bytes": sum(item["curated_bytes"] for item in months),
            },
            "months": months,
        }
        _atomic_write_json(summary_path, summary)

    if not selected:
        summary = {
            "schema_version": CURATED_SCHEMA_VERSION,
            "scope_start": start,
            "scope_end": end,
            "planned_months": len(planned),
            "selected_months_this_run": 0,
            "completed_months_in_summary": 0,
            "all_selected_months_passed": True,
            "totals": {
                "tenders": 0,
                "bidder_submissions": 0,
                "award_outcomes": 0,
                "contracts": 0,
                "curated_bytes": 0,
            },
            "months": [],
        }
        _atomic_write_json(summary_path, summary)
        return summary

    return summary

