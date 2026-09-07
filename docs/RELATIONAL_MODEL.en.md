# South Korea Public Procurement Relational Model Specification

[한국어](RELATIONAL_MODEL.md) | **English**

This document establishes the official relational schema architecture for KONEPS (Korea ON-line E-Procurement System) public procurement data, derived empirically from live API feeds (`bids`, `awards`, `contracts`).

---

## 1. Background & Core Architectural Principles

Empirical analysis from the August 2026 pilot dataset (~2.26 million raw records) established several fundamental structural characteristics:
1. **Extreme 1:N Tender-to-Bidder Submissions**: A single tender announcement attracts dozens to thousands of competing suppliers (average 240.9 bidders in construction; maximum 9,675 bidders for a single tender). The `awards` API feed (`getDataSetOpnStdScsbidInfo`) directly captures individual bidder submissions.
2. **Multi-Lot & Multi-Winner Reality**: Procurement tenders frequently split across multiple lots, classifications, or joint arrangements (40 tenders in August had 2+ winning bidders). The awards feed cannot be coerced into a simplistic 1:1 table without loss of information.
3. **Tender-to-Contract Asymmetry**: Only 35.08% of contracts link directly to a tender announcement identifier. The remaining 64.92% are predominantly private/direct contracts (96.21%) and off-notice competitive contracts (3.79%).
4. **Fan-Out Prevention Policy**: Flattening all feeds into a monolithic master table results in catastrophic row duplication and severe analytical distortion. We implement a clean star/snowflake relational model connected via an explicit bridge table.

---

## 2. Conceptual Entity Relationship Diagram (Mermaid)

```mermaid
erDiagram
    tenders ||--o{ bidder_submissions : "1 : N (Tender Bids)"
    tenders ||--o{ award_outcomes : "1 : 0..N (Award Decisions)"
    tenders ||--o{ tender_contract_bridge : "1 : 0..N (Notice-Contract Link)"
    contracts ||--o{ tender_contract_bridge : "1 : 1 (Contract Mapping)"

    suppliers ||--o{ bidder_submissions : "1 : N (Bidding Firm)"
    suppliers ||--o{ award_outcomes : "1 : N (Winning Firm)"
    suppliers ||--o{ contracts : "1 : N (Contracting Firm)"

    agencies ||--o{ tenders : "1 : N (Procuring/Demanding Agency)"
    agencies ||--o{ contracts : "1 : N (Contracting/Demanding Agency)"

    tenders {
        string bid_notice_no PK
        string bid_notice_round PK
        string bid_title_ko
        string notice_agency_code FK
        string demand_agency_code FK
        timestamp bid_notice_date
        int64 assigned_budget_krw
        int64 estimated_price_krw
        string contract_method_ko
    }

    bidder_submissions {
        string bid_notice_no PK, FK
        string bid_notice_round PK, FK
        string bidder_supplier_id PK, FK
        double bid_amount_krw PK
        string bid_submission_time PK
        double opening_rank PK
        double bid_rate
        timestamp bid_submission_date
        boolean is_selected_winner
        string disqualification_reason_ko
    }

    award_outcomes {
        string bid_notice_no PK, FK
        string bid_notice_round PK, FK
        string winner_supplier_id PK, FK
        double award_amount_krw PK
        string bid_submission_time PK
        double award_rate
        double scheduled_price_krw
        double base_amount_krw
    }

    contracts {
        string unified_contract_no PK
        string contract_no
        string contract_round
        string contract_title_ko
        string contract_agency_code FK
        string demand_agency_code FK
        string contractor_supplier_id FK
        timestamp contract_date
        int64 contract_amount_krw
        string contract_method_ko
    }

    tender_contract_bridge {
        string unified_contract_no PK, FK
        string bid_notice_no FK
        string bid_notice_round FK
        string match_type
    }

    suppliers {
        string supplier_id PK
        string business_reg_no_masked
        string supplier_name_ko
        string ceo_name
        string sigungu_ko
    }

    agencies {
        string agency_code PK
        string agency_name_ko
        string agency_category
    }
```

---

## 3. Detailed Entities & Grain Specifications

### 3.1 `tenders` (Tender Announcement Master)
- **Concept**: A distinct procurement tender published by a public entity on KONEPS.
- **Intended Grain**: One tender notice and round (1 row per tender).
- **Primary Key**: `(bid_notice_no, bid_notice_round)`
- **Foreign Keys**:
  - `notice_agency_code` $\rightarrow$ `agencies.agency_code`
  - `demand_agency_code` $\rightarrow$ `agencies.agency_code`
- **Verification**: **LIVE VERIFIED** (100% unique across all 32,895 rows in August 2026).
- **Source Feed**: `bids` (`getDataSetOpnStdBidPblancInfo`).

---

### 3.2 `bidder_submissions` (Individual Bidder Submissions)
- **Concept**: A discrete bid submitted by an enterprise for a specific tender.
- **Raw Deduplication Grain vs. Curated PK Distinction**:
  - **Raw Deduplication Grain**: `(bid_notice_no, bid_notice_round, bidder_biz_no, opening_rank, disqualification_reason_ko, bid_amount_krw, bid_submission_time)` — 7-column lossless key used to collapse post-opening snapshot updates in raw API responses (0 duplicates, 100% lossless proven).
  - **Curated Immutable Submission Identity**: Rank and disqualification reason are post-submission outcome attributes rather than submission-time properties. However, pure submission event candidates (Candidates A and B) exhibit collisions (432 and 841 rows respectively) due to unranked negotiation bidders. Therefore, the physical curated table retains the verified 7-column composite key to ensure complete data integrity.
- **Primary Key**: `(bid_notice_no, bid_notice_round, bidder_supplier_id, opening_rank, disqualification_reason_ko, bid_amount_krw, bid_submission_time)`
- **Foreign Keys**:
  - `(bid_notice_no, bid_notice_round)` $\rightarrow$ `tenders` (Nullable: False)
  - `bidder_supplier_id` $\rightarrow$ `suppliers.supplier_id` (Nullable: False)
- **Cardinality**: `tenders (1) : bidder_submissions (N)` (Range: 1 to 9,675 bids per tender, mean: 84.4).
- **Verification**: **LIVE VERIFIED** (2,107,948 normalized rows in August 2026; lossless grain verified).
- **Source Feed**: `awards` (`getDataSetOpnStdScsbidInfo`).

---

### 3.3 `award_outcomes` (Final Opening & Award Decisions)
- **Concept**: The final adjudicated outcome indicating winning suppliers, prices, and rates.
- **Intended Grain**: One award decision per lot/winner in a tender.
- **Primary Key**: `(bid_notice_no, bid_notice_round, winner_supplier_id, award_amount_krw, bid_submission_time)`
- **Empirical Metrics (August 2026 Audit)**:
  - Total Awarded Rows: **17,315 rows**
  - Candidate Key Distinct Count: **17,315** (Duplicate count: **0**, null component rate: 0.0%)
  - Verification Status: **LIVE VERIFIED** (0 duplicates verified across entire pilot).
  - Lot Identity Note: Because the official OpenAPI awards feed does not provide a separate lot/item number (`bid_classification_no`), `bid_submission_time` serves as the empirical discriminator for multi-award tenders.
- **Foreign Keys**:
  - `(bid_notice_no, bid_notice_round)` $\rightarrow$ `tenders`
  - `winner_supplier_id` $\rightarrow$ `suppliers.supplier_id`
- **Cardinality**: `tenders (1) : award_outcomes (0..N)`
  - 0 Winners: 8,197 tenders (32.82% - failed bids or pending review)
  - 1 Winner: 16,741 tenders (67.02% - standard single-winner award)
  - 2+ Winners: 40 tenders (0.16% - multi-item/lot allocations or joint awards)
- **Source Feed**: `awards` rows with `is_selected_winner == True`.

---

### 3.4 `contracts` (Executed Public Contracts)
- **Concept**: Legally executed contracts between public agencies and suppliers.
- **Intended Grain**: One national unified contract.
- **Primary Key**: `unified_contract_no` (`untyCntrctNo`)
- **Foreign Keys**:
  - `contract_agency_code` $\rightarrow$ `agencies.agency_code`
  - `demand_agency_code` $\rightarrow$ `agencies.agency_code`
  - `contractor_supplier_id` $\rightarrow$ `suppliers.supplier_id`
- **Verification**: **LIVE VERIFIED** (115,945 rows in August 2026; 0.0% null rate, 100.0% strictly unique).
- **Source Feed**: `contracts` (`getDataSetOpnStdCntrctInfo`).

---

### 3.5 `tender_contract_bridge` (Tender-Contract Relationship Bridge)
- **Concept**: Resolves the relationship between tender announcements and executed contracts.
- **Intended Grain**: One row per contract mapping.
- **Primary Key**: `unified_contract_no` (strictly unique; 0 contracts map to 2+ tenders)
- **Relationship Type (Tender 1 : N Contract)**:
  - Contracts mapping to 0 tenders: **75,268 rows (64.92%)**
  - Contracts mapping to 1 tender: **40,677 rows (35.08%)**
  - Contracts mapping to 2+ tenders: **0 rows (0.00%)**
  - The empirical relationship is strictly **Tender (1) : Contract (0..N)**. Naive inner joins would discard all 75,268 non-tendered contracts.
- **Foreign Keys**:
  - `unified_contract_no` $\rightarrow$ `contracts.unified_contract_no`
  - `(bid_notice_no, bid_notice_round)` $\rightarrow$ `tenders.(bid_notice_no, bid_notice_round)` (Nullable: True)
- **Empirical Ratios (August 2026)**:
  - Contracts linked to tender notice: **35.08%** (40,677 rows)
  - Contracts without tender notice: **64.92%** (75,268 rows)
    - Private contracts (`contract_method == '수의계약'`): **72,418 rows** (subtotal 100% reconciled)
    - Off-notice competitive contracts: **2,850 rows**

---

### 3.6 `suppliers` (Supplier Dimension Table)
- **Concept**: Unified dimension of all enterprises and sole proprietors participating in procurement.
- **Primary Key**: `supplier_id` (**HMAC-SHA256** pseudonymized `SUP_<32 hex>` hash of normalized 10-digit registration number)
- **Privacy Policy**: Raw business registration numbers are never published; public releases include a stable HMAC pseudo-ID (`supplier_id`) and masked string (`123-45-*****`).
- **Secret Key Separation**: The HMAC key is derived from a dedicated environment variable (`KONEPS_SUPPLIER_HMAC_KEY`), completely separated from the API key (`DATA_GO_KR_SERVICE_KEY`), and must remain stable across all dataset releases.
- **Empirical Volume (August 2026)**:
  - Distinct Bidders: 123,777
  - Distinct Winners: 13,376
  - Distinct Contractors: 59,233
  - Total Unique Suppliers: **143,842**
  - Winner-to-Contract Match Rate: **85.0%** (11,370 overlapping enterprises)

---

### 3.7 `agencies` (Procuring & Demanding Agency Dimension)
- **Concept**: Public sector bodies (national ministries, municipal authorities, state-owned corporations).
- **Primary Key**: `agency_code` (7-digit official administrative code)
- **Empirical Volume (August 2026)**: **14,091 unique public agencies** identified.

---

## 4. Reassessment of the Bidder Report Export Role

Because the live OpenAPI feed `getDataSetOpnStdScsbidInfo` already provides full-fidelity bidder submissions (business registration numbers, bid amounts, bid rates, timestamps, ranks, and disqualification reasons), the role of the portal bidder report export (`bidder_outcomes` CSV/XLS/XLSX) has been adjusted:
- **Previous Role**: Mandatory core source
- **New Role**: **Optional Enrichment & Cross-Validation**
- **Report-Exclusive Fields**:
  - Detailed supplier municipal district (`bidder_sigungu_ko`)
  - Corporate scale classification at contract time (SME, micro-enterprise)
  - Extended multi-year contract subdivision tags
- **Strategy**: Decouples historical bulk crawling from manual portal exports while preserving ingestion compatibility for focused localized analyses.

---

## 5. Dataset Publication & Format Policy

1. **Canonical Analytical Format**:
   - **Partitioned Apache Parquet (Zstandard compression)**
   - Date partitioning: `year=YYYY/month=MM/`
   - Strict typing: nullable boolean (`boolean` dtype), nanosecond timestamps (`datetime64[ns]`), int64, and float64.
2. **Raw Archival Storage**:
   - Immutable `.jsonl.gz` with atomic writes and SHA-256 manifests.
3. **Auxiliary Export Formats**:
   - CSV: Summary dimension tables and data dictionaries.
   - XLSX: Human-readable reports under 100,000 rows.
   - **Constraint**: Multi-million-row submission tables are never exported to Excel formats.
