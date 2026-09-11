"""Build the public Kaggle release from verified monthly curated KONEPS tables.

The release intentionally exposes seven distinct relational grains as seven Parquet
files. Large fact tables are merged with PyArrow streaming so the 12-month build
does not require loading all bidder submissions into memory at once.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from koneps_intel.curate import CURATED_SCHEMA_VERSION, _FORBIDDEN_COLUMN_PATTERNS
from koneps_intel.historical_curate import CURATED_FILENAMES, month_scopes


PUBLIC_FACT_FILES = (
    "01_tenders.parquet",
    "02_bidder_submissions.parquet",
    "03_award_outcomes.parquet",
    "04_contracts.parquet",
    "07_tender_contract_bridge.parquet",
)

PUBLIC_DIMENSION_FILES = (
    "05_suppliers.parquet",
    "06_agencies.parquet",
)

COMPANY_NAME_COLUMNS = {
    "02_bidder_submissions.parquet": {"bidder_name_ko"},
    "03_award_outcomes.parquet": {"winner_name_ko"},
    "04_contracts.parquet": {"contractor_name_ko"},
    "05_suppliers.parquet": {"supplier_name_ko"},
}

# These fields vary between int64 and double across months because pandas uses
# floating representation when a monthly partition contains null/fractional data.
# The public release uses one stable, lossless numeric representation.
FLOAT64_OVERRIDES = {
    "04_contracts.parquet": {"contract_amount_krw", "total_contract_amount_krw"},
    "07_tender_contract_bridge.parquet": {"contract_amount_krw"},
}


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _month_dirs(curated_root: Path, start: str, end: str) -> List[Path]:
    result = []
    for scope_start, _ in month_scopes(start, end):
        result.append(curated_root / scope_start[:7].replace("-", "_"))
    return result


def _verify_month_inputs(month_dirs: Sequence[Path]) -> None:
    missing: List[str] = []
    for month_dir in month_dirs:
        for filename in CURATED_FILENAMES:
            path = month_dir / filename
            if not path.exists():
                missing.append(str(path))
    if missing:
        preview = ", ".join(missing[:5])
        suffix = " ..." if len(missing) > 5 else ""
        raise FileNotFoundError(f"Missing verified monthly curated files: {preview}{suffix}")


def _target_schema(input_files: Sequence[Path], filename: str) -> pa.Schema:
    base = pq.ParquetFile(input_files[0]).schema_arrow
    drop = COMPANY_NAME_COLUMNS.get(filename, set())
    overrides = FLOAT64_OVERRIDES.get(filename, set())
    fields = []
    for field in base:
        if field.name in drop:
            continue
        if field.name in overrides:
            fields.append(pa.field(field.name, pa.float64(), nullable=True))
        else:
            fields.append(field)
    return pa.schema(fields)


def _joined_tender_key(
    bid_notice_no: pa.Array | pa.ChunkedArray,
    bid_notice_round: pa.Array | pa.ChunkedArray,
) -> pa.Array | pa.ChunkedArray:
    """Build a version-stable composite tender key for Arrow set operations."""
    key_type = pa.string()
    return pc.binary_join_element_wise(
        pc.cast(bid_notice_no, key_type),
        pc.cast(bid_notice_round, key_type),
        pa.scalar("\x1f", type=key_type),
    )


def merge_fact_parquets(
    input_files: Sequence[Path],
    output_path: Path,
    filename: str,
    batch_size: int = 250_000,
    tender_key_values: pa.Array | pa.ChunkedArray | None = None,
) -> int:
    """Stream monthly fact files into one public Parquet and return row count."""
    if not input_files:
        raise ValueError("input_files must not be empty")
    target_schema = _target_schema(input_files, filename)
    columns = target_schema.names
    normalized_tender_key_values = (
        pc.cast(tender_key_values, pa.string()) if tender_key_values is not None else None
    )
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        tmp.unlink()

    row_count = 0
    writer = pq.ParquetWriter(
        tmp,
        target_schema,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
    )
    try:
        for path in input_files:
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
                table = pa.Table.from_batches([batch])
                if normalized_tender_key_values is not None and "tender_in_scope" in table.column_names:
                    joined_key = _joined_tender_key(
                        table["bid_notice_no"], table["bid_notice_round"]
                    )
                    global_in_scope = pc.fill_null(
                        pc.is_in(joined_key, value_set=normalized_tender_key_values), False
                    )
                    column_index = table.schema.get_field_index("tender_in_scope")
                    table = table.set_column(
                        column_index,
                        pa.field("tender_in_scope", pa.bool_(), nullable=True),
                        global_in_scope,
                    )
                if not table.schema.equals(target_schema, check_metadata=False):
                    table = table.cast(target_schema, safe=False)
                writer.write_table(table)
                row_count += table.num_rows
    finally:
        writer.close()

    tmp.replace(output_path)
    return row_count


def load_tender_key_values(tenders_path: Path) -> pa.Array | pa.ChunkedArray:
    """Load the small public tender key set for global FK-scope recomputation."""
    tenders = pq.read_table(tenders_path, columns=["bid_notice_no", "bid_notice_round"])
    joined = _joined_tender_key(tenders["bid_notice_no"], tenders["bid_notice_round"])
    return pc.unique(joined)


def build_global_suppliers(month_dirs: Sequence[Path]) -> pd.DataFrame:
    """Aggregate monthly supplier dimensions into one privacy-minimized dimension."""
    frames = []
    for month_dir in month_dirs:
        frame = pd.read_parquet(month_dir / "05_suppliers.parquet")
        frame = frame.drop(columns=["supplier_name_ko"], errors="ignore")
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)

    result = (
        combined.groupby("supplier_id", as_index=False, sort=True)
        .agg(
            is_bidder=("is_bidder", "max"),
            is_winner=("is_winner", "max"),
            is_contractor=("is_contractor", "max"),
            snapshot_total_bids_in_scope=("snapshot_total_bids_in_scope", "sum"),
            snapshot_total_wins_in_scope=("snapshot_total_wins_in_scope", "sum"),
            snapshot_total_contracts_in_scope=("snapshot_total_contracts_in_scope", "sum"),
            snapshot_total_contract_amount_krw=(
                "snapshot_total_contract_amount_krw",
                "sum",
            ),
        )
        .sort_values("supplier_id")
        .reset_index(drop=True)
    )
    if result["supplier_id"].eq("").any() or not result["supplier_id"].is_unique:
        raise ValueError("Public supplier dimension has blank or duplicate supplier_id")
    return result


def build_global_agencies(month_dirs: Sequence[Path]) -> pd.DataFrame:
    """Aggregate monthly agency dimensions, keeping the latest nonblank agency name."""
    frames = []
    for order, month_dir in enumerate(month_dirs):
        frame = pd.read_parquet(month_dir / "06_agencies.parquet")
        frame["_month_order"] = order
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)

    names = combined[combined["agency_name_ko"].fillna("").astype(str).str.strip() != ""].copy()
    latest_names = (
        names.sort_values(["agency_code", "_month_order"])
        .groupby("agency_code", as_index=False, sort=True)
        .tail(1)[["agency_code", "agency_name_ko"]]
    )
    aggregates = (
        combined.groupby("agency_code", as_index=False, sort=True)
        .agg(
            is_notice_agency=("is_notice_agency", "max"),
            is_demand_agency=("is_demand_agency", "max"),
            is_contract_agency=("is_contract_agency", "max"),
            snapshot_total_tenders_in_scope=("snapshot_total_tenders_in_scope", "sum"),
            snapshot_total_contracts_in_scope=("snapshot_total_contracts_in_scope", "sum"),
        )
    )
    result = aggregates.merge(latest_names, on="agency_code", how="left")
    result["agency_name_ko"] = result["agency_name_ko"].fillna("")
    ordered = [
        "agency_code",
        "agency_name_ko",
        "is_notice_agency",
        "is_demand_agency",
        "is_contract_agency",
        "snapshot_total_tenders_in_scope",
        "snapshot_total_contracts_in_scope",
    ]
    result = result[ordered].sort_values("agency_code").reset_index(drop=True)
    if result["agency_code"].eq("").any() or not result["agency_code"].is_unique:
        raise ValueError("Public agency dimension has blank or duplicate agency_code")
    return result


def _forbidden_schema_columns(path: Path) -> List[str]:
    names = pq.ParquetFile(path).schema_arrow.names
    violations = []
    for name in names:
        if any(pattern.search(name) for pattern in _FORBIDDEN_COLUMN_PATTERNS):
            violations.append(name)
    return violations


def _table_receipt(path: Path) -> Dict[str, Any]:
    metadata = pq.ParquetFile(path).metadata
    return {
        "file": path.name,
        "rows": metadata.num_rows,
        "columns": metadata.num_columns,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def build_kaggle_release(
    curated_root: Path | str,
    out_dir: Path | str,
    start: str,
    end: str,
    historical_summary_path: Path | str,
    report_path: Path | str,
    force: bool = False,
) -> Dict[str, Any]:
    """Build and verify the seven-file public Kaggle release."""
    curated_root = Path(curated_root)
    out_dir = Path(out_dir)
    summary_path = Path(historical_summary_path)
    report_path = Path(report_path)
    month_dirs = _month_dirs(curated_root, start, end)
    _verify_month_inputs(month_dirs)

    with open(summary_path, "r", encoding="utf-8") as handle:
        historical_summary = json.load(handle)
    if not historical_summary.get("all_selected_months_passed"):
        raise ValueError("Historical curated summary has not passed all monthly gates")

    out_dir.mkdir(parents=True, exist_ok=True)
    public_files = list(PUBLIC_FACT_FILES + PUBLIC_DIMENSION_FILES)
    outputs_complete = all((out_dir / name).exists() for name in public_files)
    if outputs_complete and report_path.exists() and not force:
        with open(report_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    tender_filename = "01_tenders.parquet"
    tender_inputs = [month_dir / tender_filename for month_dir in month_dirs]
    merge_fact_parquets(tender_inputs, out_dir / tender_filename, tender_filename)
    tender_key_values = load_tender_key_values(out_dir / tender_filename)

    for filename in PUBLIC_FACT_FILES:
        if filename == tender_filename:
            continue
        inputs = [month_dir / filename for month_dir in month_dirs]
        scope_keys = tender_key_values if "tender_in_scope" in _target_schema(inputs, filename).names else None
        merge_fact_parquets(
            inputs,
            out_dir / filename,
            filename,
            tender_key_values=scope_keys,
        )

    suppliers = build_global_suppliers(month_dirs)
    suppliers.to_parquet(out_dir / "05_suppliers.parquet", compression="zstd", index=False)

    agencies = build_global_agencies(month_dirs)
    agencies.to_parquet(out_dir / "06_agencies.parquet", compression="zstd", index=False)

    receipts = {name: _table_receipt(out_dir / name) for name in public_files}
    expected = historical_summary["totals"]
    expected_rows = {
        "01_tenders.parquet": expected["tenders"],
        "02_bidder_submissions.parquet": expected["bidder_submissions"],
        "03_award_outcomes.parquet": expected["award_outcomes"],
        "04_contracts.parquet": expected["contracts"],
        "07_tender_contract_bridge.parquet": sum(
            pq.ParquetFile(month_dir / "07_tender_contract_bridge.parquet").metadata.num_rows
            for month_dir in month_dirs
        ),
    }
    row_mismatches = {
        name: {"expected": expected_count, "actual": receipts[name]["rows"]}
        for name, expected_count in expected_rows.items()
        if receipts[name]["rows"] != expected_count
    }
    privacy_violations = {
        name: _forbidden_schema_columns(out_dir / name)
        for name in public_files
        if _forbidden_schema_columns(out_dir / name)
    }
    company_name_leaks = {
        name: sorted(set(pq.ParquetFile(out_dir / name).schema_arrow.names) & columns)
        for name, columns in COMPANY_NAME_COLUMNS.items()
        if set(pq.ParquetFile(out_dir / name).schema_arrow.names) & columns
    }
    passed = not row_mismatches and not privacy_violations and not company_name_leaks
    if not passed:
        raise ValueError(
            "Public release validation failed: "
            f"row_mismatches={row_mismatches}; "
            f"privacy_violations={privacy_violations}; "
            f"company_name_leaks={company_name_leaks}"
        )

    report = {
        "schema_version": CURATED_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope_start": start,
        "scope_end": end,
        "source_months": len(month_dirs),
        "release_layout": "seven_relational_parquet_files",
        "privacy_policy": {
            "supplier_public_identity": "supplier_id_only",
            "raw_business_registration_numbers_excluded": True,
            "masked_business_registration_numbers_excluded": True,
            "supplier_company_names_excluded": True,
        },
        "schema_normalization": {
            "contract_amount_krw": "float64",
            "total_contract_amount_krw": "float64",
            "reason": "stable cross-month representation; source values preserved",
        },
        "relationship_normalization": {
            "tender_in_scope": "recomputed against the full 12-month public tender key set"
        },
        "validation": {
            "historical_monthly_gates_passed": True,
            "fact_row_reconciliation_passed": True,
            "forbidden_column_gate_passed": True,
            "company_name_minimization_passed": True,
            "passed": passed,
        },
        "files": receipts,
        "total_release_bytes": sum(item["bytes"] for item in receipts.values()),
    }
    _atomic_write_json(report_path, report)
    return report
