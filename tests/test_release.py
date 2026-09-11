import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from koneps_intel.release import (
    build_global_agencies,
    build_global_suppliers,
    merge_fact_parquets,
)


def test_merge_fact_parquets_drops_company_name_and_promotes_amount(tmp_path):
    month1 = tmp_path / "m1.parquet"
    month2 = tmp_path / "m2.parquet"
    out = tmp_path / "04_contracts.parquet"
    pd.DataFrame(
        {
            "unified_contract_no": ["C1"],
            "contract_amount_krw": pd.Series([100], dtype="int64"),
            "total_contract_amount_krw": pd.Series([100], dtype="int64"),
            "contractor_name_ko": ["Company A"],
        }
    ).to_parquet(month1, index=False)
    pd.DataFrame(
        {
            "unified_contract_no": ["C2"],
            "contract_amount_krw": pd.Series([-12.5], dtype="float64"),
            "total_contract_amount_krw": pd.Series([-12.5], dtype="float64"),
            "contractor_name_ko": ["Company B"],
        }
    ).to_parquet(month2, index=False)

    rows = merge_fact_parquets([month1, month2], out, "04_contracts.parquet", batch_size=1)

    assert rows == 2
    schema = pq.ParquetFile(out).schema_arrow
    assert "contractor_name_ko" not in schema.names
    assert str(schema.field("contract_amount_krw").type) == "double"
    assert str(schema.field("total_contract_amount_krw").type) == "double"
    result = pd.read_parquet(out)
    assert result["contract_amount_krw"].tolist() == [100.0, -12.5]


def test_build_global_suppliers_sums_monthly_snapshot_stats_and_removes_name(tmp_path):
    month_dirs = []
    for idx, bids in enumerate((2, 3), start=1):
        month_dir = tmp_path / f"2026_{idx:02d}"
        month_dir.mkdir()
        pd.DataFrame(
            {
                "supplier_id": ["SUP_x"],
                "supplier_name_ko": ["Company X"],
                "is_bidder": [True],
                "is_winner": [idx == 2],
                "is_contractor": [False],
                "snapshot_total_bids_in_scope": [bids],
                "snapshot_total_wins_in_scope": [1 if idx == 2 else 0],
                "snapshot_total_contracts_in_scope": [0],
                "snapshot_total_contract_amount_krw": [0.0],
            }
        ).to_parquet(month_dir / "05_suppliers.parquet", index=False)
        month_dirs.append(month_dir)

    result = build_global_suppliers(month_dirs)

    assert result.loc[0, "snapshot_total_bids_in_scope"] == 5
    assert bool(result.loc[0, "is_winner"])
    assert "supplier_name_ko" not in result.columns


def test_build_global_agencies_keeps_latest_name_and_sums_stats(tmp_path):
    month_dirs = []
    for idx, name in enumerate(("Old Name", "New Name"), start=1):
        month_dir = tmp_path / f"2026_{idx:02d}"
        month_dir.mkdir()
        pd.DataFrame(
            {
                "agency_code": ["AG1"],
                "agency_name_ko": [name],
                "is_notice_agency": [True],
                "is_demand_agency": [False],
                "is_contract_agency": [idx == 2],
                "snapshot_total_tenders_in_scope": [idx],
                "snapshot_total_contracts_in_scope": [idx - 1],
            }
        ).to_parquet(month_dir / "06_agencies.parquet", index=False)
        month_dirs.append(month_dir)

    result = build_global_agencies(month_dirs)

    assert result.loc[0, "agency_name_ko"] == "New Name"
    assert result.loc[0, "snapshot_total_tenders_in_scope"] == 3
    assert result.loc[0, "snapshot_total_contracts_in_scope"] == 1
    assert bool(result.loc[0, "is_contract_agency"])


def test_merge_fact_parquets_recomputes_tender_scope_against_global_keys(tmp_path):
    source = tmp_path / "07_tender_contract_bridge_input.parquet"
    out = tmp_path / "07_tender_contract_bridge.parquet"
    pd.DataFrame(
        {
            "unified_contract_no": ["C1", "C2"],
            "bid_notice_no": ["N1", "N2"],
            "bid_notice_round": ["000", "000"],
            "match_type": ["exact", "exact"],
            "tender_in_scope": [False, True],
            "contract_date": ["2026-02-01", "2026-02-02"],
            "contract_amount_krw": [100, 200],
        }
    ).to_parquet(source, index=False)

    merge_fact_parquets(
        [source],
        out,
        "07_tender_contract_bridge.parquet",
        tender_key_values=pa.array(["N1\x1f000"]),
    )

    result = pd.read_parquet(out)
    assert result["tender_in_scope"].tolist() == [True, False]
