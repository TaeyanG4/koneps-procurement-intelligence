"""Storage and manifest tracking for raw data ingestion."""
from __future__ import annotations

import gzip
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from koneps_intel.config import RAW_DIR


@dataclass
class ManifestRecord:
    """Metadata tracking record for an ingested data slice."""
    dataset: str
    endpoint: str
    start: str
    end: str
    category: Optional[str]
    download_timestamp: str
    row_count: int
    total_expected: Optional[int]
    api_calls: int
    status: str
    source_filename: str


class ManifestManager:
    """Manages the raw collection manifest for robust resumability."""

    def __init__(self, manifest_path: Optional[Path] = None):
        self.path = manifest_path or (RAW_DIR / "manifest.json")
        self._records: Dict[str, ManifestRecord] = {}
        self._load()

    def _key(self, dataset: str, start: str, end: str, category: Optional[str]) -> str:
        cat_str = category or "all"
        return f"{dataset}::{cat_str}::{start}::{end}"

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    rec = ManifestRecord(**item)
                    key = self._key(rec.dataset, rec.start, rec.end, rec.category)
                    self._records[key] = rec
        except Exception as exc:
            # Preserve the corrupted manifest file rather than silently overwriting it
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            corrupt_backup = self.path.parent / f"manifest.corrupt.{ts}.json"
            try:
                import shutil
                shutil.copy2(self.path, corrupt_backup)
            except Exception:
                pass

            # Attempt to reconstruct manifest from existing valid raw window files
            self._records = {}
            raw_dir = self.path.parent
            for raw_file in raw_dir.glob("*/*.jsonl.gz"):
                valid, reason, meta, rows = RawStorage.validate_window(raw_file)
                if valid and meta:
                    rec = ManifestRecord(
                        dataset=meta.get("feed", raw_file.parent.name),
                        endpoint=meta.get("operation", ""),
                        start=meta.get("window_start", ""),
                        end=meta.get("window_end", ""),
                        category=meta.get("business_code"),
                        download_timestamp=meta.get("collected_at_utc", ts),
                        row_count=rows,
                        total_expected=meta.get("total_expected"),
                        api_calls=meta.get("api_calls", 1),
                        status="complete",
                        source_filename=raw_file.name,
                    )
                    key = self._key(rec.dataset, rec.start, rec.end, rec.category)
                    self._records[key] = rec

            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        items = [asdict(r) for r in self._records.values()]
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def is_completed(self, dataset: str, start: str, end: str, category: Optional[str]) -> bool:
        """Check if a specific dataset window was already completed successfully."""
        key = self._key(dataset, start, end, category)
        rec = self._records.get(key)
        return rec is not None and rec.status == "complete"

    def record(self, record: ManifestRecord) -> None:
        """Record or update window metadata in the manifest."""
        key = self._key(record.dataset, record.start, record.end, record.category)
        self._records[key] = record
        self._save()

    def remove_record(self, dataset: str, start: str, end: str, category: Optional[str]) -> None:
        """Remove a window record if data was invalid or quarantined."""
        key = self._key(dataset, start, end, category)
        if key in self._records:
            del self._records[key]
            self._save()

    def list_records(self) -> List[ManifestRecord]:
        """Return all tracked manifest records."""
        return list(self._records.values())


class RawStorage:
    """Handles writing, reading, and verifying raw compressed JSONL archives."""

    @staticmethod
    def get_window_path(out_dir: Path, dataset: str, label: str, start_str: str, end_str: str) -> Path:
        filename = f"{dataset}_{label}_{start_str}_{end_str}.jsonl.gz"
        return out_dir / dataset / filename

    @staticmethod
    def validate_window(
        path: Path,
        expected_feed: Optional[str] = None,
        expected_start: Optional[str] = None,
        expected_end: Optional[str] = None,
        expected_category: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], int]:
        """Validate integrity, metadata, and record counts of a raw window file."""
        if not path.exists():
            return False, "File does not exist", None, 0

        meta: Dict[str, Any] = {}
        rows = 0
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        obj = json.loads(line_str)
                    except json.JSONDecodeError:
                        return False, "Malformed JSON line encountered", None, rows

                    if "__collector_meta__" in obj:
                        meta.update(obj["__collector_meta__"])
                        continue
                    rows += 1
        except (gzip.BadGzipFile, EOFError, OSError) as exc:
            return False, f"Decompression failed: {exc}", None, 0
        except Exception as exc:
            return False, f"Read error: {exc}", None, 0

        if not meta:
            return False, "No collector metadata record found", None, rows

        if meta.get("status") != "complete":
            return False, f"Metadata status is not complete (was: {meta.get('status')})", meta, rows

        if expected_feed and meta.get("feed") != expected_feed:
            return False, f"Feed mismatch: expected {expected_feed}, got {meta.get('feed')}", meta, rows

        if expected_start and meta.get("window_start") != expected_start:
            return False, f"Window start mismatch: expected {expected_start}, got {meta.get('window_start')}", meta, rows

        if expected_end and meta.get("window_end") != expected_end:
            return False, f"Window end mismatch: expected {expected_end}, got {meta.get('window_end')}", meta, rows

        # Verify row count if recorded in final metadata
        expected_rows = meta.get("rows")
        if expected_rows is not None and int(expected_rows) != rows:
            return False, f"Row count mismatch: metadata expected {expected_rows}, read {rows}", meta, rows

        return True, "Valid", meta, rows

    @staticmethod
    def read_window(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Read metadata and item records from a raw gzip-compressed JSONL file."""
        meta: Dict[str, Any] = {}
        rows: List[Dict[str, Any]] = []
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                obj = json.loads(line_str)
                if "__collector_meta__" in obj:
                    meta.update(obj["__collector_meta__"])
                    continue
                rows.append(obj)
        return meta, rows

    @staticmethod
    def write_window(
        path: Path,
        items: List[Dict[str, Any]],
        meta: Dict[str, Any],
    ) -> None:
        """Atomically write raw records and metadata to compressed JSONL."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        if tmp.exists():
            tmp.unlink()

        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            f.write(json.dumps({"__collector_meta__": meta}, ensure_ascii=False) + "\n")
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            meta_complete = {**meta, "status": "complete", "rows": len(items)}
            f.write(json.dumps({"__collector_meta__": meta_complete}, ensure_ascii=False) + "\n")

        tmp.replace(path)
