# Data Sources & Licensing Guide

This document describes the primary data sources, service endpoints, operational constraints, and licensing considerations for the **KONEPS Procurement Intelligence** pipeline.

---

## 1. Korean Public Data Portal (data.go.kr) APIs

The primary automated ingestion stream relies on the official Open Data Standard APIs provided by South Korea's Public Procurement Service (조달청 나라장터 / KONEPS) via the Public Data Portal (`data.go.kr`).

- **Service Name**: 조달청_나라장터 공공데이터개방표준서비스 (KONEPS Public Data Open Standard Service)
- **Base Endpoint**: `https://apis.data.go.kr/1230000/ao/PubDataOpnStdService`
- **Protocol**: HTTPS GET (JSON and XML response payloads)
- **Authentication**: `serviceKey` (Standard decoding key issued per account)
- **Traffic Limits**:
  - Development account quota: 10,000 requests / day (auto-approved upon request)
  - Production account quota: Custom scale-up available upon application

### Endpoints Supported

| Dataset | Operation Name | Temporal Parameter | Date Format | Pacing / Window Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **Tender Notices (`bids`)** | `getDataSetOpnStdBidPblancInfo` | `bidNtceBgnDt` ~ `bidNtceEndDt` | `YYYYMMDDHHMM` | Monthly calendar slices (`month_windows`) |
| **Successful Bids (`awards`)** | `getDataSetOpnStdScsbidInfo` | `opengBgnDt` ~ `opengEndDt` | `YYYYMMDDHHMM` | 7-day windows, partitioned by business division (`bsnsDivCd` 1, 2, 3, 5) |
| **Contracts (`contracts`)** | `getDataSetOpnStdCntrctInfo` | `cntrctCnclsBgnDate` ~ `cntrctCnclsEndDate` | `YYYYMMDD` | 7-day windows |

### Business Divisions (`bsnsDivCd`)
For endpoints requiring business division segmentation (notably awards):
- `1`: Goods (물품)
- `2`: Foreign Supplies (외자)
- `3`: Construction / Civil Works (공사)
- `5`: Services / Consulting (용역)

---

## 2. Official KONEPS Bidder Outcome Report Export

In addition to standard API feeds, detailed bidder-level competition records are extracted from official KONEPS exports:

- **Source Portal**: KONEPS Open Procurement Data Portal (공공데이터 개방포털 / 나라장터)
- **Report Name**: 입찰공고 기업별 투찰 및 계약내역 (Tender Notice Bidder-Level Bidding & Contract History)
- **Ingestion Script**: `scripts/ingest_bidder_report.py`
- **Supported File Formats**: CSV (`.csv`), Excel (`.xlsx`, `.xls`)
- **Key Dimensions Provided**:
  - Tender notice identifier (`bid_notice_no`, `bid_notice_round`)
  - Target agency & procuring entity (`notice_agency_name_ko`, `demand_agency_name_ko`)
  - Budgetary parameters (`allocated_budget_krw`, `estimated_price_krw`, `base_amount_krw`, `scheduled_price_krw`)
  - Bidder identity & submission (`bidder_name_ko`, `bidder_business_registration_no`, `bid_amount_krw`, `bid_rate`)
  - Ranking & selection outcomes (`opening_rank`, `is_selected_winner`, `is_disqualified`, `disqualification_reason_ko`)
  - Contract execution (`contract_no`, `contract_date`, `current_contract_amount_krw`, `total_contract_amount_krw`)

---

## 3. Data Governance & Licensing

### Source Data Licensing
- Public data distributed through `data.go.kr` and KONEPS is published under South Korea's **Act on Promotion of the Provision and Use of Public Data (공공데이터의 제공 및 이용 활성화에 관한 법률)** and the **Korea Open Government License (KOGL / 공공누리)**.
- Specific datasets on data.go.kr are subject to their individual terms of provision indicated on each service page. Users must verify the specific reuse conditions per endpoint on data.go.kr prior to commercial redistribution.
- **Code vs. Data Separation**: The source code in this repository is maintained separately from the collected datasets. Historical data is not committed to Git and will be distributed independently via Kaggle Datasets under applicable terms.

### Privacy and Responsible Publication Checkpoints
1. **Business Registration Numbers**: Korean business registration numbers (`사업자등록번호`) identify corporate and commercial entities. Before public release on Kaggle, the data engineering pipeline verifies whether raw numbers should be preserved or pseudonymized into stable hashed identifiers (`supplier_id_hash`).
2. **Personal Data Protection**: Public procurement tenders occasionally involve sole proprietors or individuals. Any personal identifying numbers (e.g. resident registration numbers) are strictly excluded by source APIs.
3. **No Credential Exposure**: Never commit API keys, service tokens, or `.env` files into source control.
