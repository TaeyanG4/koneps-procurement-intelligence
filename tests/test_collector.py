"""Unit tests for Collector and ManifestManager."""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from koneps_intel.collector import Collector
from koneps_intel.endpoints import FEEDS
from koneps_intel.storage import ManifestManager, ManifestRecord, RawStorage


def test_manifest_manager(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    mgr = ManifestManager(manifest_path)

    assert not mgr.is_completed("bids", "2026-09-01", "2026-09-01", None)

    rec = ManifestRecord(
        dataset="bids",
        endpoint="getDataSetOpnStdBidPblancInfo",
        start="2026-09-01",
        end="2026-09-01",
        category=None,
        download_timestamp="2026-09-01T12:00:00Z",
        row_count=10,
        total_expected=10,
        api_calls=1,
        status="complete",
        source_filename="bids_all_20260901_20260901.jsonl.gz",
    )
    mgr.record(rec)

    # Reload from disk
    mgr2 = ManifestManager(manifest_path)
    assert mgr2.is_completed("bids", "2026-09-01", "2026-09-01", None)
    assert len(mgr2.list_records()) == 1


def test_collector_collect_window_and_resume(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0
    def mock_get_page(*args, **kwargs):
        mock_client.calls += 1
        return ([{"bidNtceNo": "TEST01", "title": "Test Bid"}], 1)
    mock_client.get_page.side_effect = mock_get_page

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)

    spec = FEEDS["bids"]
    start = date(2026, 9, 1)
    end = date(2026, 9, 1)

    # 1. First collection
    rows, calls, path = collector.collect_window(spec, start, end, page_size=10)
    assert rows == 1
    assert calls == 1
    assert path.exists()

    # Read back raw data
    meta, items = RawStorage.read_window(path)
    assert meta["status"] == "complete"
    assert len(items) == 1
    assert items[0]["bidNtceNo"] == "TEST01"

    # 2. Resuming should skip without calling API again
    calls_before = mock_client.calls
    rows2, calls2, path2 = collector.collect_window(spec, start, end, page_size=10, force=False)
    assert rows2 == 0
    assert calls2 == 0
    assert mock_client.calls == calls_before

    # 3. Force re-download should execute
    rows3, calls3, path3 = collector.collect_window(spec, start, end, page_size=10, force=True)
    assert rows3 == 1
    assert calls3 == 1


def test_collector_dry_run(tmp_path):
    mock_client = MagicMock()
    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)

    spec = FEEDS["bids"]
    rows, calls, path = collector.collect_window(
        spec, date(2026, 9, 1), date(2026, 9, 1), page_size=10, dry_run=True
    )
    assert rows == 0
    assert calls == 0
    assert not path.exists()
    assert mock_client.get_page.call_count == 0
