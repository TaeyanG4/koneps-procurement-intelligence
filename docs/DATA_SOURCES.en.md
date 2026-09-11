# Data Sources & Licensing Guide

[한국어](DATA_SOURCES.md) | **English**

This document describes the primary data sources, service endpoints, operational constraints, and licensing considerations for the **KONEPS Procurement Intelligence** pipeline.

---

## 1. Korean Public Data Portal (data.go.kr) APIs

The primary automated ingestion stream relies on official Open Data Standard APIs provided by South Korea's Public Procurement Service (조달청 나라장터 / KONEPS) via the Public Data Portal (`data.go.kr`).

- **Service Name**: 조달청_나라장터 공공데이터개방표준서비스 (KONEPS Public Data Open Standard Service)
- **Base Endpoint**: `https://apis.data.go.kr/1230000/ao/PubDataOpnStdService`
- **Protocol**: HTTPS GET (JSON and XML response payloads)
- **Authentication**: `ServiceKey` (Standard decoding key issued per account)
- **Observed Limits**:
  - Configured key successfully performed 2,365 API calls without a quota error during the August 2026 pilot.

### Supported Endpoints

| Dataset | Operation Name | Temporal Parameter | Date Format | Pacing / Window Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **Tender Notices (`bids`)** | `getDataSetOpnStdBidPblancInfo` | `bidNtceBgnDt` ~ `bidNtceEndDt` | `YYYYMMDDHHMM` | Monthly calendar slices (`month_windows`) |
| **Successful Bids (`awards`)** | `getDataSetOpnStdScsbidInfo` | `opengBgnDt` ~ `opengEndDt` | `YYYYMMDDHHMM` | **1-day windows** (API v1.2 required), partitioned by business division (`bsnsDivCd` 1, 2, 3, 5) |
| **Contracts (`contracts`)** | `getDataSetOpnStdCntrctInfo` | `cntrctCnclsBgnDate` ~ `cntrctCnclsEndDate` | `YYYYMMDD` | 7-day weekly slices (`week_windows`) |

### Business Divisions (`bsnsDivCd`)
For endpoints requiring business division segmentation (awards):
- `1`: Goods (물품)
- `2`: Foreign Supplies (외자)
- `3`: Construction / Civil Works (공사) — accounts for ~77.6% of all awards records
- `5`: Services / Consulting (용역)

---

## 2. Official KONEPS Bidder Outcome Report Export

In addition to standard API feeds, detailed bidder-level competition records can be ingested from official KONEPS exports:
- **Source Portal**: KONEPS Open Procurement Data Portal (조달청 나라장터)
- **Report Name**: 입찰공고 기업별 투찰 및 계약내역 (Tender Notice Bidder-Level Bidding & Contract History)
- **Ingestion Script**: `scripts/ingest_bidder_report.py`
- **Supported Formats**: CSV (`.csv`), Excel (`.xlsx`, `.xls`)
- **Role**: Because the live awards API already provides full bidder submissions, portal exports serve as **Optional Enrichment & Cross-Validation**.

---

## 3. Data Governance & Licensing

### Source Data Licensing
- Public data distributed through `data.go.kr` and KONEPS is governed by South Korea's **Act on Promotion of the Provision and Use of Public Data (공공데이터의 제공 및 이용 활성화에 관한 법률)** and the individual permission terms displayed on each service page. The project does not invent a Creative Commons or KOGL subtype when the source page does not state one.
- **Re-verified 2026-09-11**: the `KONEPS Public Data Open Standard Service` page (last edited 2026-06-29) lists the service as free and its **scope of license as unrestricted**. Source: `https://www.data.go.kr/en/data/15023678/standard.do`
- **Code vs. Data Separation**: Source code is versioned in GitHub; collected procurement datasets are excluded (`.gitignore`) and distributed independently via Kaggle Datasets.

### Responsible Publication Checkpoints
1. **Source-by-Source License Re-Verification**: The standard API service was re-verified on 2026-09-11. If a separate KONEPS portal export is ever included in the public payload, its terms will be verified independently before publication.
2. **Business Registration Number Pseudonymization and Minimization**: The public release uses only a dedicated-secret HMAC-SHA256 `supplier_id`. Raw and masked business registration numbers are both excluded.
3. **Supplier Name Minimization**: The v1 Kaggle payload also excludes bidder, winner, contractor, and supplier-dimension company names. Public agency names remain for institutional analysis and joins.
4. **Personal Data Protection**: Personal identification information is not included in the public release.
5. **No Credential Exposure**: API keys, HMAC secrets, service tokens, and `.env` files are strictly excluded from source control.
