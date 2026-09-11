import pandas as pd

from koneps_intel.quickstart import (
    QUICKSTART_FILENAME,
    build_quickstart_csv,
    business_division_en,
    contract_method_group_en,
)


def test_korean_category_mapping_preserves_unknown_labels():
    assert business_division_en(" 용역 ") == "Services"
    assert business_division_en("공사") == "Construction"
    assert business_division_en("물품") == "Goods"
    assert business_division_en("외자") == "Foreign supplies"
    assert business_division_en("신규구분") == "신규구분"
    assert business_division_en(None) == "Unknown"

    assert contract_method_group_en("수의계약") == "Direct / negotiated"
    assert contract_method_group_en("제한 경쟁") == "Restricted competition"
    assert contract_method_group_en("경쟁-일반") == "Open competition"
    assert contract_method_group_en("지명경쟁") == "Selective competition"
    assert contract_method_group_en("신규방식") == "신규방식"


def test_build_quickstart_csv_keeps_one_tender_row_and_aggregates(tmp_path):
    pd.DataFrame(
        {
            "bid_notice_no": ["N1", "N2"],
            "bid_notice_round": ["000", "000"],
            "bid_title_ko": ["A", "B"],
            "bid_notice_date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "business_div_name_ko": ["용역", "물품"],
            "contract_method_ko": ["수의계약", "일반경쟁"],
            "notice_agency_code": ["A1", "A2"],
            "notice_agency_name_ko": ["Agency 1", "Agency 2"],
            "demand_agency_code": ["D1", "D2"],
            "demand_agency_name_ko": ["Demand 1", "Demand 2"],
            "assigned_budget_krw": [1000.0, 2000.0],
            "estimated_price_krw": [900.0, 1900.0],
            "is_electronic_bid": [True, True],
            "is_international_bid": [False, False],
            "is_region_limited": [False, True],
            "is_industry_limited": [True, False],
        }
    ).to_parquet(tmp_path / "01_tenders.parquet", index=False)
    pd.DataFrame(
        {
            "bid_notice_no": ["N1", "N1", "OUT"],
            "bid_notice_round": ["000", "000", "000"],
            "tender_in_scope": [True, True, False],
            "award_rate": [90.0, 150.0, 80.0],
            "award_amount_krw": [500.0, 250.0, 100.0],
            "award_date": pd.to_datetime(["2026-01-03", "2026-01-04", "2026-01-05"]),
        }
    ).to_parquet(tmp_path / "03_award_outcomes.parquet", index=False)
    pd.DataFrame(
        {
            "bid_notice_no": ["N1", "N1", "OUT"],
            "bid_notice_round": ["000", "000", "000"],
            "tender_in_scope": [True, True, False],
            "unified_contract_no": ["C1", "C2", "C3"],
            "contract_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
            "contract_amount_krw": [300.0, 400.0, 500.0],
        }
    ).to_parquet(tmp_path / "07_tender_contract_bridge.parquet", index=False)

    report = build_quickstart_csv(tmp_path)
    result = pd.read_csv(tmp_path / QUICKSTART_FILENAME)

    assert report["rows"] == 2
    assert report["selected_award_rows_reconciled"] == 2
    assert report["valid_award_rate_rows_reconciled"] == 1
    assert report["distinct_tender_contract_links_reconciled"] == 2
    assert not result.duplicated(["bid_notice_no", "bid_notice_round"]).any()
    n1 = result.loc[result["bid_notice_no"] == "N1"].iloc[0]
    n2 = result.loc[result["bid_notice_no"] == "N2"].iloc[0]
    assert n1["business_division_en"] == "Services"
    assert n1["contract_method_group_en"] == "Direct / negotiated"
    assert n1["selected_award_count"] == 2
    assert n1["valid_award_rate_count"] == 1
    assert n1["median_award_rate_pct"] == 90.0
    assert n1["linked_contract_count"] == 2
    assert bool(n1["has_selected_award"])
    assert not bool(n2["has_selected_award"])
    assert not any("supplier" in column.lower() for column in result.columns)
