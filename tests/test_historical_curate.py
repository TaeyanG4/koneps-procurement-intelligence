from pathlib import Path

import pandas as pd
import pytest

from koneps_intel.curate import select_processed_parquet_files
from koneps_intel.historical_curate import month_scopes


def test_month_scopes_full_historical_year():
    scopes = month_scopes("2025-09-01", "2026-08-31")
    assert len(scopes) == 12
    assert scopes[0] == ("2025-09-01", "2025-09-30")
    assert scopes[-1] == ("2026-08-01", "2026-08-31")


def test_month_scopes_preserves_partial_boundaries():
    assert month_scopes("2026-01-15", "2026-03-07") == [
        ("2026-01-15", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-07"),
    ]


def test_month_scopes_rejects_reverse_range():
    with pytest.raises(ValueError, match="start must be on or before end"):
        month_scopes("2026-08-31", "2026-08-01")


def test_select_processed_parquet_files_uses_only_intersecting_partitions(tmp_path):
    feed_root = tmp_path / "awards"
    jan = feed_root / "year=2026" / "month=01"
    feb = feed_root / "year=2026" / "month=02"
    mar = feed_root / "year=2026" / "month=03"
    for folder in (jan, feb, mar):
        folder.mkdir(parents=True)
        pd.DataFrame({"x": [1]}).to_parquet(folder / "part.parquet", index=False)

    selected = select_processed_parquet_files(
        tmp_path, "awards", "2026-02-10", "2026-03-05"
    )

    assert selected == [feb / "part.parquet", mar / "part.parquet"]


def test_select_processed_parquet_files_returns_empty_when_partition_absent(tmp_path):
    assert select_processed_parquet_files(
        Path(tmp_path), "bids", "2026-08-01", "2026-08-31"
    ) == []
