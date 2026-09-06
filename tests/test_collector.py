import gzip
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from koneps_intel.api import QuotaExceededError
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


def test_collector_case_b_missing_raw_file(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0
    def mock_get_page(*args, **kwargs):
        mock_client.calls += 1
        return ([{"bidNtceNo": "RETRY01"}], 1)
    mock_client.get_page.side_effect = mock_get_page

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)
    spec = FEEDS["bids"]
    start = date(2026, 9, 1)
    end = date(2026, 9, 1)

    # Manifest says complete, but no file exists on disk (Case B)
    rec = ManifestRecord(
        dataset=spec.name,
        endpoint=spec.operation,
        start=start.isoformat(),
        end=end.isoformat(),
        category=None,
        download_timestamp="2026-09-01T10:00:00Z",
        row_count=1,
        total_expected=1,
        api_calls=1,
        status="complete",
        source_filename="bids_all_20260901_20260901.jsonl.gz",
    )
    collector.manifest.record(rec)
    assert collector.manifest.is_completed(spec.name, start.isoformat(), end.isoformat(), None)

    # Calling collect_window should detect missing raw file, call API, and succeed
    rows, calls, path = collector.collect_window(spec, start, end, page_size=10, force=False)
    assert rows == 1
    assert calls == 1
    assert path.exists()
    assert collector.manifest.is_completed(spec.name, start.isoformat(), end.isoformat(), None)


def test_collector_case_c_reconstruct_manifest(tmp_path):
    mock_client = MagicMock()
    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)
    spec = FEEDS["bids"]
    start = date(2026, 9, 1)
    end = date(2026, 9, 1)

    path = RawStorage.get_window_path(out_dir, spec.name, "all", "20260901", "20260901")
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "feed": spec.name,
        "operation": spec.operation,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "business_code": None,
        "status": "complete",
        "rows": 1,
        "total_expected": 1,
        "api_calls": 1,
        "collected_at_utc": "2026-09-01T12:00:00Z",
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"__collector_meta__": meta}) + "\n")
        f.write(json.dumps({"bidNtceNo": "RECON01"}) + "\n")

    # Manifest does not have record
    assert not collector.manifest.is_completed(spec.name, start.isoformat(), end.isoformat(), None)

    # collect_window should reconstruct manifest without calling API
    rows, calls, out_path = collector.collect_window(spec, start, end, page_size=10, force=False)
    assert rows == 0
    assert calls == 0
    assert mock_client.get_page.call_count == 0
    assert collector.manifest.is_completed(spec.name, start.isoformat(), end.isoformat(), None)


def test_collector_case_d_corrupt_raw_file(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0
    def mock_get_page(*args, **kwargs):
        mock_client.calls += 1
        return ([{"bidNtceNo": "CLEAN01"}], 1)
    mock_client.get_page.side_effect = mock_get_page

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)
    spec = FEEDS["bids"]
    start = date(2026, 9, 1)
    end = date(2026, 9, 1)

    # Create corrupt file
    path = RawStorage.get_window_path(out_dir, spec.name, "all", "20260901", "20260901")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"bad gzip corrupted data \x00\xff")

    # collect_window should delete corrupt file, re-download, and write valid archive
    rows, calls, out_path = collector.collect_window(spec, start, end, page_size=10, force=False)
    assert rows == 1
    assert calls == 1
    assert out_path.exists()
    assert collector.manifest.is_completed(spec.name, start.isoformat(), end.isoformat(), None)


def test_collector_quota_exceeded_propagates(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0
    mock_client.get_page.side_effect = QuotaExceededError("Day quota limit exceeded")

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)

    with pytest.raises(QuotaExceededError):
        collector.collect(dataset="bids", start=date(2026, 9, 1), end=date(2026, 9, 1))


def test_cli_collect_standard_quota_exit_code_3(monkeypatch, tmp_path):
    from scripts import collect_standard

    monkeypatch.setattr(
        "sys.argv",
        [
            "collect_standard.py",
            "--dataset", "bids",
            "--start", "2026-09-01",
            "--end", "2026-09-01",
            "--out", str(tmp_path / "raw"),
        ],
    )
    monkeypatch.setattr("scripts.collect_standard.get_service_key", lambda required=True: "dummy_key_123")

    with patch.object(Collector, "collect", side_effect=QuotaExceededError("Limit reached")):
        with pytest.raises(SystemExit) as exc_info:
            collect_standard.main()
        assert exc_info.value.code == 3
