"""Streaming audit helpers for large historical KONEPS builds.

The one-year awards feed is too large to concatenate into one pandas DataFrame.
This module therefore validates raw-plan completeness and processed Parquet
invariants one file at a time, using an on-disk uint64 key-hash array for the
global duplicate check.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from koneps_intel.endpoints import BUSINESS_DIVISIONS, FEEDS
from koneps_intel.parsers import feed_windows, parse_date
from koneps_intel.schemas import DEDUPLICATION_KEYS
from koneps_intel.storage import RawStorage


PRIMARY_EVENT_DATE = {
    "bids": "bid_notice_date",
    "awards": "opening_date",
    "contracts": "contract_date",
}


def canonical_raw_plan(raw_root: Path, start: str, end: str) -> Dict[str, Any]:
    """Validate the exact collector window plan against manifest and raw files."""
    start_date = parse_date(start)
    end_date = parse_date(end)
    manifest_path = raw_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_key = {
        (
            row.get("dataset"),
            row.get("start"),
            row.get("end"),
            str(row.get("category") or ""),
        ): row
        for row in manifest
    }

    feed_metrics: Dict[str, Any] = {}
    missing_manifest: List[str] = []
    missing_files: List[str] = []
    noncomplete: List[str] = []
    canonical_names: set[str] = set()
    canonical_keys: set[tuple[str, str, str, str]] = set()

    for feed, spec in FEEDS.items():
        codes: Iterable[Optional[str]] = BUSINESS_DIVISIONS.keys() if spec.needs_business_division else [None]
        expected = 0
        rows = 0
        api_calls = 0
        nonempty = 0
        for win_start, win_end in feed_windows(spec, start_date, end_date):
            for code in codes:
                expected += 1
                category = str(code or "")
                key = (feed, win_start.isoformat(), win_end.isoformat(), category)
                canonical_keys.add(key)
                label = BUSINESS_DIVISIONS.get(code, code) if code else "all"
                path = RawStorage.get_window_path(
                    raw_root,
                    feed,
                    label,
                    win_start.strftime("%Y%m%d"),
                    win_end.strftime("%Y%m%d"),
                )
                canonical_names.add(path.name)
                rec = by_key.get(key)
                if rec is None:
                    missing_manifest.append(path.name)
                else:
                    row_count = int(rec.get("row_count") or 0)
                    rows += row_count
                    api_calls += int(rec.get("api_calls") or 0)
                    nonempty += int(row_count > 0)
                    if rec.get("status") != "complete":
                        noncomplete.append(path.name)
                if not path.exists():
                    missing_files.append(path.name)

        feed_metrics[feed] = {
            "canonical_windows": expected,
            "canonical_raw_rows": rows,
            "canonical_api_calls": api_calls,
            "nonempty_windows": nonempty,
        }

    extra_manifest = []
    for row in manifest:
        key = (
            row.get("dataset"),
            row.get("start"),
            row.get("end"),
            str(row.get("category") or ""),
        )
        if row.get("dataset") in FEEDS and key not in canonical_keys:
            extra_manifest.append(str(row.get("source_filename") or key))

    extra_raw_files: List[str] = []
    for feed in FEEDS:
        for path in (raw_root / feed).glob("*.jsonl.gz"):
            if path.name not in canonical_names:
                extra_raw_files.append(path.name)

    return {
        "scope": {"start": start, "end": end},
        "feeds": feed_metrics,
        "canonical_windows": sum(v["canonical_windows"] for v in feed_metrics.values()),
        "canonical_raw_rows": sum(v["canonical_raw_rows"] for v in feed_metrics.values()),
        "canonical_api_calls": sum(v["canonical_api_calls"] for v in feed_metrics.values()),
        "missing_manifest_entries": missing_manifest,
        "missing_raw_files": missing_files,
        "noncomplete_manifest_entries": noncomplete,
        "noncanonical_manifest_entries": sorted(extra_manifest),
        "noncanonical_raw_files": sorted(extra_raw_files),
        "complete": not missing_manifest and not missing_files and not noncomplete,
    }


def _common_effective_keys(files: Sequence[Path], feed: str) -> List[str]:
    configured = DEDUPLICATION_KEYS[feed]
    common: Optional[set[str]] = None
    for path in files:
        names = set(pq.ParquetFile(path).schema_arrow.names)
        present = {key for key in configured if key in names}
        common = present if common is None else common & present
    common = common or set()
    return [key for key in configured if key in common]


def _count_sorted_hash_duplicates(path: Path, count: int) -> int:
    if count <= 1:
        return 0
    hashes = np.memmap(path, dtype=np.uint64, mode="r+", shape=(count,))
    hashes.sort(kind="quicksort")
    duplicates = 0
    step = 5_000_000
    previous_last: Optional[np.uint64] = None
    for offset in range(0, count, step):
        chunk = np.asarray(hashes[offset : min(offset + step, count)])
        if previous_last is not None and len(chunk):
            duplicates += int(chunk[0] == previous_last)
        if len(chunk) > 1:
            duplicates += int(np.count_nonzero(chunk[1:] == chunk[:-1]))
        if len(chunk):
            previous_last = chunk[-1]
    del hashes
    return duplicates


def audit_processed_feed(
    processed_root: Path,
    feed: str,
    start: str,
    end: str,
    temp_dir: Path,
) -> Dict[str, Any]:
    """Audit a processed feed without loading the full historical table at once."""
    files = sorted((processed_root / feed).glob("**/*.parquet"))
    if not files:
        return {"feed": feed, "files": 0, "rows": 0, "critical_failures": ["no parquet files"]}

    event_col = PRIMARY_EVENT_DATE[feed]
    effective_keys = _common_effective_keys(files, feed)
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    rows = 0
    null_event_dates = 0
    out_of_scope_rows = 0
    source_window_violations = 0
    event_min: Optional[pd.Timestamp] = None
    event_max: Optional[pd.Timestamp] = None
    source_files: set[str] = set()
    key_null_counts: Counter[str] = Counter()
    negative_monetary: Counter[str] = Counter()
    invalid_rates: Counter[str] = Counter()
    schema_missing_event: List[str] = []
    unreadable_files: List[str] = []

    temp_dir.mkdir(parents=True, exist_ok=True)
    hash_path = temp_dir / f"{feed}_key_hashes.bin"
    hash_count = 0
    with hash_path.open("wb") as hash_out:
        for path in files:
            try:
                parquet = pq.ParquetFile(path)
                schema_names = parquet.schema_arrow.names
                rows += parquet.metadata.num_rows
                if event_col not in schema_names:
                    schema_missing_event.append(str(path))
                    continue

                money_cols = [c for c in schema_names if c.endswith("_krw")]
                rate_cols = [c for c in ("bid_rate", "award_rate", "award_lower_limit_rate") if c in schema_names]
                wanted = list(dict.fromkeys(
                    [event_col, "_source_file", "_window_start", "_window_end"]
                    + effective_keys
                    + money_cols
                    + rate_cols
                ))
                wanted = [c for c in wanted if c in schema_names]
                df = parquet.read(columns=wanted).to_pandas()

                event = pd.to_datetime(df[event_col], errors="coerce").dt.normalize()
                null_event_dates += int(event.isna().sum())
                valid_event = event.dropna()
                if not valid_event.empty:
                    cur_min = valid_event.min()
                    cur_max = valid_event.max()
                    event_min = cur_min if event_min is None else min(event_min, cur_min)
                    event_max = cur_max if event_max is None else max(event_max, cur_max)
                out_of_scope_rows += int(((event < start_ts) | (event > end_ts)).fillna(False).sum())

                if "_window_start" in df.columns and "_window_end" in df.columns:
                    win_start = pd.to_datetime(df["_window_start"], errors="coerce").dt.normalize()
                    win_end = pd.to_datetime(df["_window_end"], errors="coerce").dt.normalize()
                    bad = event.notna() & win_start.notna() & win_end.notna() & ((event < win_start) | (event > win_end))
                    source_window_violations += int(bad.sum())

                if "_source_file" in df.columns:
                    source_files.update(df["_source_file"].dropna().astype(str).unique().tolist())

                for key in effective_keys:
                    key_null_counts[key] += int(df[key].isna().sum())

                if effective_keys:
                    key_frame = df[effective_keys].astype("string")
                    hashed = pd.util.hash_pandas_object(key_frame, index=False).to_numpy(dtype=np.uint64)
                    hash_out.write(hashed.tobytes(order="C"))
                    hash_count += len(hashed)

                for col in money_cols:
                    values = pd.to_numeric(df[col], errors="coerce")
                    negative_monetary[col] += int((values < 0).sum())
                for col in rate_cols:
                    values = pd.to_numeric(df[col], errors="coerce")
                    invalid_rates[col] += int(((values < 0) | (values > 500)).sum())
            except Exception as exc:  # pragma: no cover - exercised by real audit failures
                unreadable_files.append(f"{path}: {type(exc).__name__}: {exc}")

    global_key_duplicate_hashes = _count_sorted_hash_duplicates(hash_path, hash_count) if effective_keys else 0
    hash_path.unlink(missing_ok=True)

    critical_failures: List[str] = []
    data_warnings: List[str] = []
    if unreadable_files:
        critical_failures.append(f"{len(unreadable_files)} unreadable parquet files")
    if schema_missing_event:
        critical_failures.append(f"{len(schema_missing_event)} files missing {event_col}")
    if null_event_dates:
        critical_failures.append(f"{null_event_dates} null {event_col} values")
    if out_of_scope_rows:
        critical_failures.append(f"{out_of_scope_rows} rows outside requested scope")
    if source_window_violations:
        critical_failures.append(f"{source_window_violations} rows outside source window")
    if global_key_duplicate_hashes:
        critical_failures.append(f"{global_key_duplicate_hashes} duplicate effective-key hashes across output")
    if sum(negative_monetary.values()):
        data_warnings.append(
            "negative monetary source values detected; preserve source-faithfully and document as anomalies"
        )
    if sum(invalid_rates.values()):
        data_warnings.append(
            "rate values outside the audit sanity range [0, 500] detected; preserve source-faithfully and document as anomalies"
        )

    return {
        "feed": feed,
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "rows": rows,
        "event_date_column": event_col,
        "event_date_min": event_min.date().isoformat() if event_min is not None else None,
        "event_date_max": event_max.date().isoformat() if event_max is not None else None,
        "null_event_dates": null_event_dates,
        "out_of_scope_rows": out_of_scope_rows,
        "source_window_violations": source_window_violations,
        "source_files_with_rows": len(source_files),
        "effective_deduplication_keys": effective_keys,
        "dedup_key_null_counts": dict(key_null_counts),
        "global_key_duplicate_hashes": global_key_duplicate_hashes,
        "negative_monetary_counts": {k: v for k, v in negative_monetary.items() if v},
        "invalid_rate_counts": {k: v for k, v in invalid_rates.items() if v},
        "files_missing_event_column": schema_missing_event,
        "unreadable_files": unreadable_files,
        "data_warnings": data_warnings,
        "critical_failures": critical_failures,
    }


def run_historical_audit(
    raw_root: Path,
    processed_root: Path,
    start: str,
    end: str,
    output_path: Path,
) -> Dict[str, Any]:
    """Run the canonical raw-plan and streaming processed-data audit."""
    raw = canonical_raw_plan(raw_root, start, end)
    temp_dir = processed_root / ".qa_tmp"
    processed = {
        feed: audit_processed_feed(processed_root, feed, start, end, temp_dir)
        for feed in ("bids", "awards", "contracts")
    }
    try:
        temp_dir.rmdir()
    except OSError:
        pass

    build_report_path = processed_root / "build_report.json"
    build_report = json.loads(build_report_path.read_text(encoding="utf-8")) if build_report_path.exists() else []
    build_by_feed = {item["feed"]: item for item in build_report}
    reconciliation: Dict[str, Any] = {}
    for feed, metrics in processed.items():
        report = build_by_feed.get(feed, {})
        manifest_rows = raw["feeds"][feed]["canonical_raw_rows"]
        reconciliation[feed] = {
            "manifest_raw_rows": manifest_rows,
            "build_rows_before_dedupe": report.get("rows_before_dedupe"),
            "build_rows_after_dedupe": report.get("rows_after_dedupe"),
            "parquet_metadata_rows": metrics["rows"],
            "raw_rows_match_build_input": report.get("rows_before_dedupe") == manifest_rows,
            "processed_rows_match_build_output": report.get("rows_after_dedupe") == metrics["rows"],
        }

    critical: List[str] = []
    if not raw["complete"]:
        critical.append("canonical raw plan incomplete")
    for feed, rec in reconciliation.items():
        if not rec["raw_rows_match_build_input"]:
            critical.append(f"{feed}: raw/build input row mismatch")
        if not rec["processed_rows_match_build_output"]:
            critical.append(f"{feed}: build/parquet output row mismatch")
    for feed, metrics in processed.items():
        critical.extend(f"{feed}: {failure}" for failure in metrics["critical_failures"])

    warnings = [
        f"{feed}: {warning}"
        for feed, metrics in processed.items()
        for warning in metrics.get("data_warnings", [])
    ]

    result = {
        "scope": {"start": start, "end": end},
        "raw_plan": raw,
        "processed": processed,
        "reconciliation": reconciliation,
        "summary": {
            "canonical_windows": raw["canonical_windows"],
            "canonical_raw_rows": raw["canonical_raw_rows"],
            "processed_rows": sum(item["rows"] for item in processed.values()),
            "processed_parquet_files": sum(item["files"] for item in processed.values()),
            "processed_bytes": sum(item["bytes"] for item in processed.values()),
            "data_warnings": warnings,
            "critical_failures": critical,
            "passed": not critical,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
