import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
import pytest

from koneps_intel.kaggle_metadata import (
    DATASET_SUBTITLE,
    DATASET_TITLE,
    _kaggle_type,
    _validate_owner,
    build_dataset_metadata,
)
from koneps_intel.quickstart import QUICKSTART_COLUMNS, QUICKSTART_FILENAME
from koneps_intel.release import PUBLIC_DIMENSION_FILES, PUBLIC_FACT_FILES


def test_kaggle_type_mapping():
    assert _kaggle_type(pa.bool_()) == "boolean"
    assert _kaggle_type(pa.int64()) == "integer"
    assert _kaggle_type(pa.float64()) == "number"
    assert _kaggle_type(pa.timestamp("ns")) == "datetime"
    assert _kaggle_type(pa.string()) == "string"


def test_validate_owner():
    assert _validate_owner("valid-owner_1") == "valid-owner_1"


def test_kaggle_title_and_subtitle_length_constraints():
    assert 6 <= len(DATASET_TITLE) <= 50
    assert 20 <= len(DATASET_SUBTITLE) <= 80


def _write_minimal_release(tmp_path):
    table = pa.table({"bid_notice_no": ["N1"]})
    for filename in PUBLIC_FACT_FILES + PUBLIC_DIMENSION_FILES:
        pq.write_table(table, tmp_path / filename)


def test_dataset_metadata_includes_quickstart_csv_schema(tmp_path):
    _write_minimal_release(tmp_path)
    pd.DataFrame([{column: None for column in QUICKSTART_COLUMNS}]).to_csv(
        tmp_path / QUICKSTART_FILENAME,
        index=False,
        encoding="utf-8",
    )

    metadata = build_dataset_metadata(tmp_path, owner="owner")

    resource = metadata["resources"][0]
    assert resource["path"] == QUICKSTART_FILENAME
    assert [field["name"] for field in resource["schema"]["fields"]] == QUICKSTART_COLUMNS


def test_dataset_metadata_rejects_stale_quickstart_header(tmp_path):
    _write_minimal_release(tmp_path)
    (tmp_path / QUICKSTART_FILENAME).write_text("wrong_column\nvalue\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Quickstart CSV header"):
        build_dataset_metadata(tmp_path, owner="owner")
