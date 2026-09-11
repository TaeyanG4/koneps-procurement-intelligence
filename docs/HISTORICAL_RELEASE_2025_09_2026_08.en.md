# KONEPS 12-Month Historical Release Validation Report

[한국어](HISTORICAL_RELEASE_2025_09_2026_08.md) | **English**

Validated scope: **2025-09-01 through 2026-08-31**
Validation date: **2026-09-11**

## 1. Release Status

Collection, normalization, relational curation, and public Kaggle packaging are complete for the recent 12 months of the KONEPS Public Data Open Standard Service `bids`, `awards`, and `contracts` feeds.

- Canonical raw rows: **41,225,145**
- Normalized Parquet rows: **38,273,402**
- Monthly relational curation: **12/12 months PASS**
- Public release files: **7 ZSTD Parquet files**
- Public release size: **2,612,589,280 bytes** (about 2.61 GB)

Normalized fact rows reconcile exactly:

`470,937 tenders + 35,907,867 bidder submissions + 1,894,598 contracts = 38,273,402 rows`

`award_outcomes` is a selected-winner subset of bidder submissions and is therefore not added again to the reconciliation total.

## 2. Public Kaggle Files

| File | Grain | Rows | Columns | Bytes |
| :--- | :--- | ---: | ---: | ---: |
| `01_tenders.parquet` | tender notice + round | 470,937 | 32 | 29,781,660 |
| `02_bidder_submissions.parquet` | individual bid submission | 35,907,867 | 28 | 2,396,046,821 |
| `03_award_outcomes.parquet` | selected award outcome | 305,995 | 25 | 34,718,596 |
| `04_contracts.parquet` | unified contract | 1,894,598 | 24 | 134,436,150 |
| `05_suppliers.parquet` | pseudonymized supplier | 261,474 | 8 | 6,218,548 |
| `06_agencies.parquet` | public agency code | 27,214 | 7 | 463,642 |
| `07_tender_contract_bridge.parquet` | tender-contract link | 637,107 | 7 | 10,923,863 |

Per-file SHA-256 receipts are stored in `docs/metrics/release_202509_202608.json`.

## 3. Integrity and Resumability

Historical data is curated independently by calendar month. Every month passes primary-key, raw-to-curated row reconciliation, FK coverage, forbidden-column, dtype, and bridge assertion checks. `scripts/build_historical_curated.py` reuses complete monthly checkpoints, allowing interrupted builds to resume safely.

The final public release is assembled by `scripts/build_kaggle_release.py`, which streams monthly fact tables in PyArrow batches. It never loads all 35.9 million bidder submissions into memory at once. Contract amount fields that varied between `int64` and `double` across monthly partitions are normalized to public `float64` fields without changing source values.

Because monthly curated `tender_in_scope` flags have month-local semantics, the public builder **recomputes them against the complete 12-month `01_tenders` key set**. The final release directly links 32,662,091 bidder submissions, 279,463 award outcomes, and 398,392 bridge rows to tenders inside the public 12-month scope.

## 4. Privacy Policy

The Kaggle release uses only a dedicated-secret **HMAC-SHA256** `supplier_id` as the public supplier identity.

- Raw business registration numbers: **excluded**
- Masked business registration numbers: **excluded**
- Bidder/winner/contractor company names: **excluded**
- Supplier-dimension company names: **excluded**
- Public agency codes and agency names: retained for analysis and joins

To preserve stable `supplier_id` values across future versions, `KONEPS_SUPPLIER_HMAC_KEY` must remain unchanged after the first public release.

## 5. Source-Anomaly Preservation

The pipeline distinguishes source anomalies from transformation errors. Values verified against the original KONEPS JSON are not deleted or silently coerced to zero.

- Negative bidder `bid_amount_krw`: **1 row**
- Negative contract `contract_amount_krw`: **10 rows**
- Negative contract `total_contract_amount_krw`: **10 rows**
- NULL `award_amount_krw` among selected awards: **280 rows**

These are documented as source anomalies/warnings so downstream users can apply task-specific filters if needed.

## 6. License Verification

As verified on 2026-09-11, the Public Data Portal page for **KONEPS Public Data Open Standard Service** (page last edited 2026-06-29) lists the service as free and its scope of license as unrestricted.

Source: https://www.data.go.kr/en/data/15023678/standard.do

The Kaggle metadata therefore uses `other` rather than inventing a Creative Commons license, and the dataset overview attributes the Public Procurement Service and Public Data Portal while linking to the source terms.

## 7. Reproduction Commands

```bash
python scripts/build_dataset.py --start 2025-09-01 --end 2026-08-31
python scripts/audit_historical.py --start 2025-09-01 --end 2026-08-31 --raw data/raw --processed data/processed/historical_202509_202608
python scripts/build_historical_curated.py --start 2025-09-01 --end 2026-08-31 --processed data/processed/historical_202509_202608
python scripts/build_kaggle_release.py --start 2025-09-01 --end 2026-08-31
```

The final local public payload is generated under `data/processed/kaggle_release_202509_202608/`. Public Kaggle v1 (`taeyangg4/koneps-public-procurement-intelligence`) was published on 2026-09-11. Live readback confirms `ready` status, byte-for-byte sizes for all seven remote files, the custom cover, provenance, license, and monthly update frequency. Starter EDA notebook v2 (`taeyangg4/koneps-procurement-5-minute-market-overview`) also completed successfully in the Kaggle runtime. Data Explorer file/column descriptions are tracked separately because the live API had not exposed parsed columns/descriptions on the same date.
