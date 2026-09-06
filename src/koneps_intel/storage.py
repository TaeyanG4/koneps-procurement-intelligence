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
        except Exception:
            # If manifest is unreadable, start clean without crashing
            self._records = {}

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

    def list_records(self) -> List[ManifestRecord]:
        """Return all tracked manifest records."""
        return list(self._records.values())


class RawStorage:
    """Handles writing and reading raw compressed JSONL archives."""

    @staticmethod
    def get_window_path(out_dir: Path, dataset: str, label: str, start_str: str, end_str: str) -> Path:
        filename = f"{dataset}_{label}_{start_str}_{end_str}.jsonl.gz"
        return out_dir / dataset / filename

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
