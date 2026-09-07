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


def test_collector_category_match_skips(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0
    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)

    spec = FEEDS["awards"]
    start = date(2026, 9, 1)
    end = date(2026, 9, 1)
    category = "1"  # goods

    path = RawStorage.get_window_path(out_dir, spec.name, "goods", "20260901", "20260901")
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "feed": spec.name,
        "operation": spec.operation,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "business_code": "1",
        "status": "complete",
        "rows": 1,
        "total_expected": 1,
        "api_calls": 1,
        "collected_at_utc": "2026-09-01T12:00:00Z",
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"__collector_meta__": meta}) + "\n")
        f.write(json.dumps({"awardNo": "AW01"}) + "\n")

    # Record in manifest
    rec = ManifestRecord(
        dataset=spec.name,
        endpoint=spec.operation,
        start=start.isoformat(),
        end=end.isoformat(),
        category="1",
        download_timestamp="2026-09-01T12:00:00Z",
        row_count=1,
        total_expected=1,
        api_calls=1,
        status="complete",
        source_filename=path.name,
    )
    collector.manifest.record(rec)

    # Calling collect_window for category 1 should match and skip
    rows, calls, out_path = collector.collect_window(
        spec, start, end, page_size=10, business_code="1", force=False
    )
    assert rows == 0
    assert calls == 0
    assert mock_client.get_page.call_count == 0


def test_collector_category_mismatch_invalidates(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0

    def mock_get_page(*args, **kwargs):
        mock_client.calls += 1
        return ([{"awardNo": "CORRECT_GOODS"}], 1)

    mock_client.get_page.side_effect = mock_get_page

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)

    spec = FEEDS["awards"]
    start = date(2026, 9, 1)
    end = date(2026, 9, 1)

    # Create raw file at the path for category 1 (goods), but with metadata saying business_code="3" (construction)
    path = RawStorage.get_window_path(out_dir, spec.name, "goods", "20260901", "20260901")
    path.parent.mkdir(parents=True, exist_ok=True)
    mismatched_meta = {
        "feed": spec.name,
        "operation": spec.operation,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "business_code": "3",  # Mismatched! Expected 1
        "status": "complete",
        "rows": 1,
        "total_expected": 1,
        "api_calls": 1,
        "collected_at_utc": "2026-09-01T12:00:00Z",
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"__collector_meta__": mismatched_meta}) + "\n")
        f.write(json.dumps({"awardNo": "WRONG_CONSTRUCTION"}) + "\n")

    # Call collect_window expecting category "1"
    rows, calls, out_path = collector.collect_window(
        spec, start, end, page_size=10, business_code="1", force=False
    )

    # Should detect category mismatch, remove stale file, call API, and write clean file with category 1
    assert rows == 1
    assert calls == 1
    assert mock_client.calls == 1

    meta, items = RawStorage.read_window(out_path)
    assert meta["business_code"] == "1"
    assert items[0]["awardNo"] == "CORRECT_GOODS"


def test_collector_dry_run_stats(tmp_path):
    mock_client = MagicMock()
    mock_client.calls = 0
    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)

    start = date(2026, 9, 1)
    end = date(2026, 9, 1)

    stats = collector.collect(dataset="bids", start=start, end=end, dry_run=True)
    assert stats.dry_run_windows == 1
    assert stats.completed_windows == 0
    assert stats.skipped_windows == 0
    assert stats.total_rows == 0
    assert stats.total_calls == 0
    assert mock_client.get_page.call_count == 0
    assert not (out_dir / "bids").exists()


def test_cli_dry_run_reporting(monkeypatch, tmp_path, caplog):
    import logging
    from scripts import collect_standard

    monkeypatch.setattr(
        "sys.argv",
        [
            "collect_standard.py",
            "--dataset", "bids",
            "--start", "2026-09-01",
            "--end", "2026-09-01",
            "--out", str(tmp_path / "raw"),
            "--dry-run",
        ],
    )

    with caplog.at_level(logging.INFO):
        collect_standard.main()

    messages = [rec.message for rec in caplog.records]
    assert any("DRY-RUN COMPLETE: planned_windows=1, api_calls=0, files_written=0" in m for m in messages)
    assert not any("windows_saved=" in m for m in messages)
    assert not any("COMPLETED: total_rows=" in m for m in messages)


def test_page_receipt_generation_and_storage(tmp_path):
    """Verify that public-safe page receipt metadata is generated and recorded on each page fetch."""
    from koneps_intel.collector import generate_page_receipt

    items = [
        {"bidNtceNo": "R26BK001", "bidprcAmt": "1000", "corpNm": "Company A"},
        {"bidNtceNo": "R26BK002", "bidprcAmt": "2000", "corpNm": "Company B"},
    ]
    receipt = generate_page_receipt(
        dataset="awards",
        window_start="2026-08-01",
        window_end="2026-08-31",
        category="1",
        page_no=1,
        items=items,
        reported_total_count=100,
    )

    assert receipt["run_id"] == "default"
    assert receipt["attempt_id"] == "attempt_1"
    assert receipt["dataset"] == "awards"
    assert receipt["category"] == "1"
    assert receipt["page_no"] == 1
    assert receipt["page_row_count"] == 2
    assert receipt["reported_total_count"] == 100
    assert receipt["first_record_hash"] is not None
    assert receipt["last_record_hash"] is not None
    assert receipt["page_hash"] is not None
    assert receipt["first_record_hash"] != receipt["last_record_hash"]

    # Verify custom run_id and attempt_id
    receipt_custom = generate_page_receipt(
        dataset="awards",
        window_start="2026-08-01",
        window_end="2026-08-31",
        category="1",
        page_no=1,
        items=items,
        reported_total_count=100,
        run_id="run_20260907_001",
        attempt_id="attempt_2_retry",
    )
    assert receipt_custom["run_id"] == "run_20260907_001"
    assert receipt_custom["attempt_id"] == "attempt_2_retry"

    # Verify no raw sensitive strings in receipt
    receipt_json = json.dumps(receipt)
    assert "Company A" not in receipt_json
    assert "Company B" not in receipt_json
    assert "ServiceKey" not in receipt_json

    # Test collector writes receipt
    mock_client = MagicMock()
    mock_client.calls = 0
    mock_client.get_page.return_value = (items, 2)

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)
    spec = FEEDS["bids"]
    start = date(2026, 8, 1)
    end = date(2026, 8, 31)

    rows, calls, path = collector.collect_window(spec, start, end, page_size=10)
    assert rows == 2

    # Check that receipt file was created in receipts_dir
    receipt_files = list(collector.receipts_dir.glob("*.jsonl"))
    assert len(receipt_files) == 1
    with open(receipt_files[0], "r", encoding="utf-8") as rf:
        line = rf.readline()
        logged_rcpt = json.loads(line)
        assert logged_rcpt["page_no"] == 1
        assert logged_rcpt["page_row_count"] == 2
        assert "run_id" in logged_rcpt
        assert "attempt_id" in logged_rcpt


def test_page_receipt_attempt_and_failure_semantics(tmp_path):
    """Verify that multiple attempts append distinct receipts and failed attempts record receipts."""
    from koneps_intel.collector import generate_page_receipt, Collector
    from koneps_intel.endpoints import FEEDS

    mock_client = MagicMock()
    # First attempt raises an error on page 2
    mock_client.get_page.side_effect = [
        ([{"col": "val1"}], 100),
        RuntimeError("Network timeout on page 2"),
    ]

    out_dir = tmp_path / "raw"
    collector = Collector(client=mock_client, out_dir=out_dir)
    spec = FEEDS["bids"]
    start = date(2026, 8, 1)
    end = date(2026, 8, 31)

    with pytest.raises(RuntimeError):
        collector.collect_window(spec, start, end, page_size=1)

    # Page 1 receipt was still recorded before failure
    receipt_files = list(collector.receipts_dir.glob("*.jsonl"))
    assert len(receipt_files) == 1
    with open(receipt_files[0], "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        rcpt1 = json.loads(lines[0])
        assert rcpt1["page_no"] == 1



