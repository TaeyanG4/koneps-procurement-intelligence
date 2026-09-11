# KONEPS Kaggle Dataset — Collection Plan


## Dataset working title

**South Korea Public Procurement Intelligence — Tenders, Bids, Awards & Contracts**

## Core principle

Do **not** publish a raw government-data dump. Build a reusable procurement research dataset where a Kaggle user can immediately study competition, winning prices, failed bids, suppliers and agencies.

## Phase 1 — MVP (recent 12 months)

Collect:

1. `bids`: standard tender announcements
2. `awards`: standard successful-bid/opening records
3. `contracts`: standard contract records
4. `bidder_outcomes`: bidder-level official report export

Why recent 12 months first:
- validate real schema before historical backfill
- measure volume and API-call cost
- verify join cardinality
- create first EDA/ML notebooks quickly

*Status*: **Completed for the initial 12-month MVP (2025-09-01 ~ 2026-08-31).** The collection contains 41,225,145 canonical raw rows and 38,273,402 normalized fact rows. All 12 monthly relational builds passed reconciliation and privacy gates; the public 7-file Kaggle payload is 2.61 GB. See `docs/HISTORICAL_RELEASE_2025_09_2026_08.md`.

## Phase 2 — Join design & Relational Implementation (Completed)

Candidate grain:

- Tender grain: `bid_notice_no + bid_notice_round + classification`
- Bidder grain: tender grain + bidder business registration number + submission
- Contract grain: contract number / unified contract number

Never join before checking 1:1 vs 1:N cardinality. A tender can have many bidders and sometimes several classifications/contracts.

## Phase 3 — Curated target tables


Implemented v1 publication structure:

```text
01_tenders.parquet
02_bidder_submissions.parquet
03_award_outcomes.parquet
04_contracts.parquet
05_suppliers.parquet
06_agencies.parquet
07_tender_contract_bridge.parquet
```

The seven files are intentionally distinct relational grains rather than duplicated serializations. The public supplier dimension exposes only stable HMAC `supplier_id`; raw/masked business registration numbers and supplier company names are excluded from the Kaggle payload.

## Phase 4 — Features

Candidate features:

- bidder_count
- allocated_budget_krw
- estimated_price_krw
- base_amount_krw
- scheduled_price_krw
- winning_price_krw
- award_ratio
- days_notice_to_open
- days_open_to_contract
- supplier_previous_bids
- supplier_previous_wins
- supplier_historical_win_rate
- agency_historical_bidder_count
- market_supplier_count
- market_hhi
- failed_bid flag
- single_bid flag

All historical features must be time-safe: calculate using only information available before each observation date to avoid target leakage.

## Phase 5 — Historical backfill

After the recent-year MVP passes quality checks:

1. 3 years
2. 5 years
3. 10 years
4. maximum useful historical coverage

Backfill older data only after confirming that schemas and IDs are stable enough.

## Phase 6 — Kaggle publication package

Minimum launch package:

- ZSTD Parquet
- English aliases + original Korean fields
- source/provenance documentation
- data dictionary
- missingness/key-cardinality report
- one strong overview notebook
- one ML baseline notebook
- one supplier/market-structure notebook
- scheduled incremental update

*Current status*: public Dataset v1 is live at `taeyangg4/koneps-public-procurement-intelligence`. Kaggle live readback confirms `ready` status, all seven remote file byte sizes, the custom cover, source provenance, `other` license, valid tags, and monthly update frequency. The starter overview notebook is also public at `taeyangg4/koneps-procurement-5-minute-market-overview`; v2 executed successfully on Kaggle and reproduced the release counts and award-rate summary. The remaining publication-side metadata item is Data Explorer file/column-description reflection: on 2026-09-11 the live backend still reports no parsed columns/descriptions even though complete resource schemas are present in `dataset-metadata.json`. Remaining content work is the leak-free ML baseline, supplier/market-structure notebook, and automated incremental version update.

## Privacy / responsible publication checkpoint

The official bidder report contains company names and business registration numbers. Before Kaggle publication:

- verify current source license and Kaggle policy (API service re-verified 2026-09-11: data.go.kr reports scope of license as unrestricted)
- assess whether raw registration numbers add meaningful analytical value
- use a stable HMAC-SHA256 supplier ID in public tables; raw and masked registration numbers are excluded
- exclude supplier company names from the v1 Kaggle payload as an additional data-minimization measure
- keep provenance and transformation documentation
