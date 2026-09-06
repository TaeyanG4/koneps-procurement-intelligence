# KONEPS Kaggle Gold Candidate — Collection Plan

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

## Phase 2 — Join design

Candidate grain:

- Tender grain: `bid_notice_no + bid_notice_round + classification`
- Bidder grain: tender grain + bidder business registration number + submission
- Contract grain: contract number / unified contract number

Never join before checking 1:1 vs 1:N cardinality. A tender can have many bidders and sometimes several classifications/contracts.

## Phase 3 — Gold-facing tables

Target publication structure:

```text
raw-ish standardized tables
  bids/
  awards/
  contracts/
  bidder_outcomes.parquet

curated tables (after schema validation)
  procurement_master.parquet
  bidder_competition.parquet
  supplier_features.parquet
  agency_features.parquet
  market_features.parquet
```

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

## Privacy / responsible publication checkpoint

The official bidder report contains company names and business registration numbers. Before Kaggle publication:

- verify current source license and Kaggle policy
- assess whether raw registration numbers add meaningful analytical value
- prefer a stable hashed supplier ID in the public modeling table when the raw identifier is unnecessary
- keep provenance and transformation documentation

