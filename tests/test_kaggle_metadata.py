import pyarrow as pa

from koneps_intel.kaggle_metadata import (
    DATASET_SUBTITLE,
    DATASET_TITLE,
    _kaggle_type,
    _validate_owner,
)


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
