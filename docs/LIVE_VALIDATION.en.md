# KONEPS OpenAPI Live Validation & Smoke Test Report

[한국어](LIVE_VALIDATION.md) | **English**

This technical report documents the initial live verification and 1-day smoke test (`2026-09-01`) for South Korea's Public Procurement Service (KONEPS) OpenAPI (`PubDataOpnStdService` v1.2) across data collection, normalization, and quality validation.

---

## 1. Overview & Verification Environment

- **Validation Date**: September 7, 2026
- **Service**: Public Data Portal (`data.go.kr`) KONEPS Open Data Standard Service (`PubDataOpnStdService` v1.2)
- **Authentication**: Public Data Portal Decoding Key (`DATA_GO_KR_SERVICE_KEY`)
- **Target Date**: `2026-09-01` (1-Day Smoke Test)
- **Target Feeds**:
  1. `bids` (`getDataSetOpnStdBidPblancInfo` - Tender Notice Info)
  2. `awards` (`getDataSetOpnStdScsbidInfo` - Opening and Award Info across 4 business divisions)
  3. `contracts` (`getDataSetOpnStdCntrctInfo` - Executed Contract Info)
- **Environment**: Windows 11, Python 3.12 (CI: Python 3.11 & 3.12)

---

## 2. API Specification Alignment & Security Safeguards

### 2.1 Prevention of Double Percent-Encoding
- Applying `urllib.parse.unquote()` in `get_service_key()` and `KonepsClient._build_request()` ensures that both Encoding and Decoding keys transmit correct bytes via HTTP requests without triggering `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` (code 30).

### 2.2 Standard Query Parameter Casing
- Authentication query parameter standardized to `ServiceKey` as required by official OpenAPI v1.2 specifications.

### 2.3 Awards Feed 1-Day Window Strategy
- Because `getDataSetOpnStdScsbidInfo` restricts queries to a maximum 1-day range (`opengBgnDt` ~ `opengEndDt`), `endpoints.py` configures `window_days=1` for the awards feed.

### 2.4 Zero-Secret Policy
- All credentials load from local environment (`.env`) and are masked (`izyp********Yg==`) in console and log files.

---

## 3. 1-Day Live Smoke Test Results (`2026-09-01`)

| Feed | Operation | Business Category | Rows | API Calls | Compressed Raw Size | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **bids** | `getDataSetOpnStdBidPblancInfo` | All | 1,564 | 16 | 240 KB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | Goods (1) | 24,627 | 247 | 1.16 MB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | Foreign (2) | 12 | 1 | 1.78 KB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | Construction (3) | 99,601 | 100 | 5.37 MB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | Service (5) | 5,672 | 6 | 288 KB | Complete |
| **contracts** | `getDataSetOpnStdCntrctInfo` | All | 6,269 | 7 | 643 KB | Complete |
| **Total** | - | - | **137,745** | **377** | **~7.7 MB** | **100% Success** |

---

## 4. Empirical Schema & Grain Findings

### 4.1 Awards Feed Grain & Deduplication Refinement
- The live awards API operation returns all bidder submissions for each opened tender.
- Deduplication candidate key was refined to avoid collapsing distinct bidder records, preserving 128,250 unique bidder submissions for the smoke test day.

### 4.2 Field Verification
- `bids` (53 fields observed): Added support for `dmndInsttCd`, `dmndInsttNm`, `presmptPrce`, `bidwinrDcsnMthdNm`.
- `awards` (38 fields observed): Both bidder-level (`bidprcCorpBizrno`, `bidprcAmt`, `bidprcRt`, `opengRank`) and winner-level (`fnlSucsfAmt`, `fnlSucsfCorpNm`) fields verified.
- `contracts` (44 fields observed): Verified `untyCntrctNo` as a 100% unique national contract key.

---

## 5. Parquet Normalization & Quality Assurance

Converted into Hive-partitioned Parquet datasets (`year=2026/month=09/`) via `scripts/build_dataset.py` and validated with `scripts/quality_check.py --strict`:
- Files checked: 6 Parquet files (136,083 total rows)
- Critical issues: 0 (False)
- Duplicate full rows: 0
- Negative monetary amounts: 0
- Unified contract number null ratio: 0.0% (100% unique)
- Encoding integrity: Verified UTF-8 without garbled characters or `\ufffd`.
