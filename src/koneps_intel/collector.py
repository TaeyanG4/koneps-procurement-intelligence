"""High-level collection orchestrator for KONEPS standard feeds."""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from koneps_intel.api import KonepsClient, QuotaExceededError
from koneps_intel.endpoints import BUSINESS_DIVISIONS, FEEDS, FeedSpec
from koneps_intel.parsers import feed_windows, format_boundary
from koneps_intel.storage import ManifestManager, ManifestRecord, RawStorage
from koneps_intel.utils import get_logger


@dataclass
class CollectionStats:
    total_rows: int = 0
    total_calls: int = 0
    skipped_windows: int = 0
    completed_windows: int = 0
    dry_run_windows: int = 0



class Collector:
    """Orchestrates API calls, pagination, raw storage, and manifest tracking."""

    def __init__(
        self,
        client: KonepsClient,
        out_dir: Path,
        manifest_manager: Optional[ManifestManager] = None,
        logger=None,
    ):
        self.client = client
        self.out_dir = out_dir
        self.manifest = manifest_manager or ManifestManager(out_dir / "manifest.json")
        self.logger = logger or get_logger("koneps_intel.collector")

    def collect_window(
        self,
        spec: FeedSpec,
        start: date,
        end: date,
        page_size: int,
        business_code: Optional[str] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> Tuple[int, int, Path]:
        """Collect records for one date window and persist atomically."""
        label = BUSINESS_DIVISIONS.get(business_code, business_code) if business_code else "all"
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        path = RawStorage.get_window_path(self.out_dir, spec.name, label, start_str, end_str)

        # Check resumability & file validity (Cases A, B, C, D, E)
        is_done = self.manifest.is_completed(spec.name, start.isoformat(), end.isoformat(), business_code)

        if not force:
            if path.exists():
                is_valid, reason, meta, rows = RawStorage.validate_window(
                    path,
                    expected_feed=spec.name,
                    expected_start=start.isoformat(),
                    expected_end=end.isoformat(),
                    expected_category=business_code,
                )
                if is_valid:
                    if is_done:
                        # Case A: Manifest complete + valid raw file -> safe skip
                        self.logger.info("SKIP %s [%s to %s] %s (already collected and verified)", spec.name, start, end, label)
                        return 0, 0, path
                    else:
                        # Case C: Valid raw file exists, but manifest missing -> reconstruct manifest entry
                        self.logger.info("RECONSTRUCT %s [%s to %s] %s manifest from valid raw file", spec.name, start, end, label)
                        finish_utc = (meta or {}).get("collected_at_utc") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        total_exp = (meta or {}).get("total_expected")
                        api_calls = (meta or {}).get("api_calls", 0)
                        record = ManifestRecord(
                            dataset=spec.name,
                            endpoint=spec.operation,
                            start=start.isoformat(),
                            end=end.isoformat(),
                            category=business_code,
                            download_timestamp=finish_utc,
                            row_count=rows,
                            total_expected=total_exp,
                            api_calls=api_calls,
                            status="complete",
                            source_filename=path.name,
                        )
                        self.manifest.record(record)
                        return 0, 0, path
                else:
                    # Case D: Raw file exists but is corrupt -> remove and re-download
                    self.logger.warning("CORRUPT %s [%s to %s] %s (%s). Removing corrupt file and re-downloading.", spec.name, start, end, label, reason)
                    path.unlink(missing_ok=True)
                    self.manifest.remove_record(spec.name, start.isoformat(), end.isoformat(), business_code)
            else:
                if is_done:
                    # Case B: Manifest recorded complete, but raw file missing -> remove invalid manifest record and re-download
                    self.logger.warning("MISSING %s [%s to %s] %s raw file missing despite complete manifest record. Re-downloading.", spec.name, start, end, label)
                    self.manifest.remove_record(spec.name, start.isoformat(), end.isoformat(), business_code)

        if dry_run:
            self.logger.info("DRY-RUN %s [%s to %s] %s -> %s", spec.name, start, end, label, path.name)
            return 0, 0, path

        base_params: Dict[str, Any] = {
            spec.start_param: format_boundary(start, spec.date_format, is_end=False),
            spec.end_param: format_boundary(end, spec.date_format, is_end=True),
        }
        if business_code:
            base_params["bsnsDivCd"] = business_code

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        if tmp.exists():
            tmp.unlink()

        page = 1
        row_count = 0
        calls_before = self.client.calls
        total_expected: Optional[int] = None
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        initial_meta = {
            "feed": spec.name,
            "operation": spec.operation,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "business_code": business_code,
            "business_label": label,
            "page_size": page_size,
            "status": "collecting",
            "started_at_utc": now_utc,
        }

        try:
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                f.write(json.dumps({"__collector_meta__": initial_meta}, ensure_ascii=False) + "\n")
                while True:
                    params = {**base_params, "pageNo": page, "numOfRows": page_size}
                    items, total = self.client.get_page(spec.operation, params)
                    if total_expected is None:
                        total_expected = total

                    for item in items:
                        f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
                    row_count += len(items)

                    self.logger.info(
                        "PAGE %-9s %s..%s %-12s page=%-4d +%-4d collected=%-8d total=%d",
                        spec.name,
                        start,
                        end,
                        label,
                        page,
                        len(items),
                        row_count,
                        total,
                    )

                    if not items or row_count >= total or len(items) < page_size:
                        break
                    page += 1

                finish_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                final_meta = {
                    **initial_meta,
                    "status": "complete",
                    "rows": row_count,
                    "total_expected": total_expected,
                    "api_calls": self.client.calls - calls_before,
                    "collected_at_utc": finish_utc,
                }
                f.write(json.dumps({"__collector_meta__": final_meta}, ensure_ascii=False) + "\n")

            tmp.replace(path)
            api_calls = self.client.calls - calls_before

            # Update manifest
            record = ManifestRecord(
                dataset=spec.name,
                endpoint=spec.operation,
                start=start.isoformat(),
                end=end.isoformat(),
                category=business_code,
                download_timestamp=finish_utc,
                row_count=row_count,
                total_expected=total_expected,
                api_calls=api_calls,
                status="complete",
                source_filename=path.name,
            )
            self.manifest.record(record)
            self.logger.info("SAVE %s (rows=%d, api_calls=%d)", path.name, row_count, api_calls)
            return row_count, api_calls, path

        except QuotaExceededError as q_err:
            if tmp.exists():
                tmp.unlink()
            self.logger.error("STOP Daily quota exceeded during window %s [%s..%s]: %s", spec.name, start, end, q_err)
            raise
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

    def collect(
        self,
        dataset: str,
        start: date,
        end: date,
        page_size: int = 500,
        force: bool = False,
        dry_run: bool = False,
    ) -> CollectionStats:
        """Run the collection loop over requested datasets and date ranges."""
        selected = list(FEEDS) if dataset == "all" else [dataset]
        stats = CollectionStats()

        self.logger.info("START collection datasets=%s range=[%s to %s]", selected, start, end)

        for name in selected:
            spec = FEEDS[name]
            codes = BUSINESS_DIVISIONS.keys() if spec.needs_business_division else [None]
            for win_start, win_end in feed_windows(spec, start, end):
                for code in codes:
                    try:
                        rows, calls, _ = self.collect_window(
                            spec=spec,
                            start=win_start,
                            end=win_end,
                            page_size=page_size,
                            business_code=code,
                            force=force,
                            dry_run=dry_run,
                        )
                        stats.total_rows += rows
                        stats.total_calls += calls
                        if dry_run:
                            stats.dry_run_windows += 1
                        elif rows == 0 and calls == 0:
                            stats.skipped_windows += 1
                        else:
                            stats.completed_windows += 1
                    except QuotaExceededError:
                        self.logger.error(
                            "Collection paused due to quota limit during %s [%s..%s]. Re-run tomorrow to resume.",
                            name,
                            win_start,
                            win_end,
                        )
                        raise

        if dry_run:
            self.logger.info(
                "DRY-RUN collection: planned_windows=%d, api_calls=0, files_written=0",
                stats.dry_run_windows,
            )
        else:
            self.logger.info(
                "DONE collection: total_rows=%d, total_api_calls=%d, completed_windows=%d, skipped_windows=%d",
                stats.total_rows,
                stats.total_calls,
                stats.completed_windows,
                stats.skipped_windows,
            )
        return stats

