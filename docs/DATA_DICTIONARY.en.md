# Data Dictionary

[한국어](DATA_DICTIONARY.md) | **English**

This data dictionary outlines the canonical English column schema produced by the normalization pipeline, preserving original Korean names while presenting standard types for downstream analytics and machine learning.

---

## 1. Tender Notices (`bids`)

- **Source API Operation**: `getDataSetOpnStdBidPblancInfo`
- **Candidate Primary Key**: `(bid_notice_no, bid_notice_round)`

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `bid_notice_no` | `bidNtceNo` | string | Unique tender announcement number (e.g. `R26BK01708300`) |
| `bid_notice_round` | `bidNtceOrd` | string | Announcement revision/round sequence (e.g. `000`) |
| `bid_classification_no` | `bidClsfcNo` | string | Sub-classification index under multi-item tenders |
| `rebid_no` | `rbidNo` | string | Re-bidding iteration counter |
| `bid_title_ko` | `bidNtceNm` | string | Original Korean title of the tender |
| `notice_agency_code` | `ntceInsttCd` | string | Official identifier of publishing agency |
| `notice_agency_name_ko` | `ntceInsttNm` | string | Name of publishing procuring agency |
| `demand_agency_code` | `dmndInsttCd` | string | Official identifier of end-demand agency |
| `demand_agency_name_ko` | `dmndInsttNm` | string | Name of end-demand agency |
| `bid_notice_date` | `bidNtceDate` / `bidNtceDt` | string / date | Date notice was officially published |
| `bid_notice_time` | `bidNtceBgn` | string | Time notice was published (`HH:MM`) |
| `bid_begin_date` | `bidBeginDate` | string / date | Submission window start date |
| `bid_close_date` | `bidClseDate` | string / date | Submission deadline date |
| `opening_date` | `opengDate` | string / date | Bid opening date |
| `assigned_budget_krw` | `asignBdgtAmt` | float64 | Total budget allocated for procurement (KRW) |
| `estimated_price_krw` | `presmptPrce` | float64 | Estimated price (ex-VAT reference price, KRW) |
| `base_amount_krw` | `bsisAmt` | float64 | Base reference amount for multi-pricing pools (KRW) |
| `business_div_name_ko` | `bsnsDivNm` | string | Korean division label (물품, 용역, 공사 등) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | Contract procurement method (일반경쟁, 수의계약 등) |
| `contract_status_ko` | `cntrctCnclsSttusNm`| string | Contract conclusion status |
| `award_method_ko` | `bidwinrDcsnMthdNm` | string | Decision criteria (적격심사, 소액수의, 최저가 등) |
| `award_lower_limit_rate` | `sucsfbidLwltRate` | float64 | Lower-bound bid rate threshold (%) |
| `is_joint_contract` | `cmmnCntrctYn` | boolean | Joint venture contracting indicator |
| `is_electronic_bid` | `elctrnBidYn` | boolean | Electronic bidding indicator |
| `is_international_bid` | `intrntnlBidYn` | boolean | International tender indicator |
| `is_pps_notice` | `ppsNtceYn` | boolean | Public Procurement Service managed notice |
| `is_region_limited` | `rgnLmtYn` | boolean | Regional restriction indicator |
| `is_industry_limited` | `indstrytyLmtYn` | boolean | Industry/license restriction indicator |

---

## 2. Bid Results & Awards (`awards`)

- **Source API Operation**: `getDataSetOpnStdScsbidInfo`
- **Raw Deduplication Grain**: `["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn", "bidprcAmt", "bidprcTm"]` (7-column lossless key to collapse post-opening snapshot updates).
- **Curated Table Primary Key**: `(bid_notice_no, bid_notice_round, bidder_supplier_id, opening_rank, disqualification_reason_ko, bid_amount_krw, bid_submission_time)` (retains 7-column lossless grain).
- **Intended Grain**: One submission per bidder per tender lot (`bidder_submissions`).

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `bid_notice_no` | `bidNtceNo` | string | Associated tender announcement number |
| `bid_notice_round` | `bidNtceOrd` | string | Tender revision sequence |
| `bid_title_ko` | `bidNtceNm` | string | Original Korean title |
| `business_div_name_ko` | `bsnsDivNm` | string | Business division (물품, 외자, 공사, 용역) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | Contract procurement method |
| `award_method_ko` | `bidwinrDcsnMthdNm` | string | Winning bidder determination method |
| `notice_agency_code` | `ntceInsttCd` | string | Notice agency identifier |
| `notice_agency_name_ko` | `ntceInsttNm` | string | Notice agency name |
| `demand_agency_code` | `dmndInsttCd` | string | Demand agency identifier |
| `demand_agency_name_ko` | `dmndInsttNm` | string | Demand agency name |
| `opening_date` | `opengDate` | string / date | Bid opening date |
| `opening_rank` | `opengRank` | float64 | Opening evaluation rank (1 = closest to threshold) |
| `bidder_business_registration_no` | `bidprcCorpBizrno` | string | Bidding company 10-digit business registration number |
| `bidder_name_ko` | `bidprcCorpNm` | string | Bidding company name |
| `bid_amount_krw` | `bidprcAmt` | float64 | Submitted bid amount (KRW) |
| `bid_rate` | `bidprcRt` | float64 | Bid rate relative to reference price (%) |
| `bid_submission_date` | `bidprcDate` | string / date | Bid submission date |
| `bid_submission_time` | `bidprcTm` | string | Bid submission time (`HH:MM`) |
| `is_selected_winner` | `sucsfYn` | boolean | True if selected as winning bidder |
| `disqualification_reason_ko` | `dqlfctnRsn` | string | Disqualification reason (e.g. 예정가격초과, 자격미달 등) |
| `award_amount_krw` | `fnlSucsfAmt` | float64 | Final winning bid amount (KRW) |
| `award_rate` | `fnlSucsfRt` | float64 | Final winning bid rate (%) |
| `award_date` | `fnlSucsfDate` | string / date | Final award date |
| `winner_name_ko` | `fnlSucsfCorpNm` | string | Final winning company name |
| `winner_business_registration_no` | `fnlSucsfCorpBizrno` | string | Final winner business registration number |
| `estimated_price_krw` | `presmptPrce` | float64 | Estimated price (KRW) |
| `scheduled_price_krw` | `rsrvtnPrce` | float64 | Final scheduled price (KRW) |
| `base_amount_krw` | `bssAmt` | float64 | Base reference amount (KRW) |

---

## 3. Contracts (`contracts`)

- **Source API Operation**: `getDataSetOpnStdCntrctInfo`
- **Candidate Primary Key**: `unified_contract_no` (`untyCntrctNo`, 100% strictly unique)

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `unified_contract_no` | `untyCntrctNo` | string | National unified contract identifier |
| `contract_no` | `cntrctNo` | string | Primary agency contract number |
| `contract_round` | `cntrctOrd` | string | Contract modification / round sequence |
| `contract_title_ko` | `cntrctNm` | string | Official contract title |
| `contract_date` | `cntrctCnclsDate` | string / date | Date contract was concluded (`YYYY-MM-DD`) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | Contract conclusion method |
| `contract_amount_krw` | `cntrctAmt` | float64 | Signed contract amount for current installment (KRW) |
| `total_contract_amount_krw`| `ttalCntrctAmt` | float64 | Cumulative total contract value (KRW) |
| `contract_agency_code` | `cntrctInsttCd` | string | Contracting agency code |
| `contract_agency_name_ko` | `cntrctInsttNm` | string | Contracting agency name |
| `demand_agency_code` | `dmndInsttCd` | string | Demand agency code |
| `demand_agency_name_ko` | `dmndInsttNm` | string | Demand agency name |
| `contractor_business_registration_no` | `rprsntCorpBizrno` | string | Contractor business registration number |
| `contractor_name_ko` | `rprsntCorpNm` | string | Contractor business name |
| `bid_notice_no` | `bidNtceNo` | string | Associated tender notice number |
| `bid_notice_round` | `bidNtceOrd` | string | Associated tender notice round |
| `contract_period` | `cntrctPrd` | string | Contract duration/period |
| `is_joint_contract` | `cmmnCntrctYn` | boolean | Joint contracting indicator |
| `is_domestic_corp` | `dmstcCorpYn` | boolean | Domestic corporation indicator |

---

## 4. Bidder Outcome Report (`bidder_outcomes`)

- **Role**: Optional enrichment & localized cross-validation source

| Canonical English Column | Source Column (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `procurement_channel` | `조달방식` | string | Procurement channel |
| `business_type` | `업무구분` | string | Business category |
| `bidding_method` | `입찰방법` | string | Bidding mechanism |
| `bid_notice_no` | `입찰공고번호` | string | Tender notice number |
| `bid_notice_round` | `입찰공고차수` | string | Notice revision round |
| `bid_title_ko` | `공고명` | string | Tender notice title |
| `opening_rank` | `개찰순위` | float64 | Opening bid rank |
| `is_selected_winner` | `낙찰자선정여부` | boolean | Selected as winner |
| `bidder_name_ko` | `업체명` | string | Bidding company name |
| `bidder_business_registration_no`| `업체사업자등록번호` | string | Bidding company business registration number |
| `bid_amount_krw` | `투찰금액` | float64 | Submitted bid amount (KRW) |
| `bid_rate` | `투찰율` | float64 | Submitted bid rate (%) |
| `is_disqualified` | `부적격여부` | boolean | Disqualification indicator |
| `disqualification_reason_ko`| `입찰부적격사유` | string | Reason stated for disqualification |
| `bidder_sigungu_ko` | `업체소재시군구` | string | Municipal district of bidder |
| `current_contract_amount_krw`| `금차계약금액` | float64 | Current contract amount (KRW) |
| `total_contract_amount_krw` | `총계약금액` | float64 | Total contracted amount (KRW) |

---

## 5. Candidate ML Feature Columns

Features engineered following relational bridge construction:
- `bidder_count`: Total valid bidders per tender notice (competition intensity)
- `market_hhi`: Herfindahl-Hirschman index by industry code and procuring entity
- `supplier_historical_win_rate`: Cumulative time-safe win rate prior to tender date
- `scheduled_price_ratio`: Scheduled price relative to base amount (`scheduled_price_krw / base_amount_krw`)
- `bid_price_ratio`: Bid amount relative to estimated price (`bid_amount_krw / estimated_price_krw`)

---

## 6. Curated Relational Tables (`CURATED_SCHEMA_VERSION = "1.0.0"`)

Schema specifications for the 7 normalized relational tables generated under `data/processed/curated/YYYY_MM/`.

### 6.1 `01_tenders.parquet` (Tender Announcements Master)
- **Physical Primary Key (PK)**: `(bid_notice_no, bid_notice_round)`
- **Row Count**: 32,895 rows (August 2026, 100% unique)
- **Key Columns**: `bid_notice_no`, `bid_notice_round`, `bid_notice_name_ko`, `notice_agency_code`, `notice_agency_name_ko`, `demand_agency_code`, `demand_agency_name_ko`, `business_div_name_ko`, `contract_method_ko`, `award_method_ko`, `assigned_budget_krw`, `estimated_price_krw`, `bid_notice_date`, `bid_begin_date`, `bid_close_date`, `opening_date`, `is_joint_contract`, `is_electronic_bid`, `is_region_limited`, `is_industry_limited`

### 6.2 `02_bidder_submissions.parquet` (Individual Bidder Submissions)
- **Physical Primary Key (PK)**: `bid_submission_id` (`BID_<32 hex>`, deterministic SHA-256 surrogate key, 100% unique)
- **Business Reconciliation Grain**: `(bid_notice_no, bid_notice_round, bidder_supplier_id, opening_rank, disqualification_reason_ko, bid_amount_krw, bid_submission_time)` (7-column lossless grain)
- **Row Count**: 2,107,948 rows (August 2026)
- **Key Columns**:
  - `bid_submission_id`: string (PK, `BID_` prefix)
  - `bid_notice_no`, `bid_notice_round`: tender reference (FK)
  - `bidder_supplier_id`: pseudonymized supplier reference (FK, `SUP_` prefix)
  - `tender_in_scope`: whether tender notice is in current scope window (`boolean`)
  - `bid_amount_krw`: submitted bid amount (`float64`, KRW)
  - `bid_rate_pct`: bid rate relative to scheduled price (`float64`, %)
  - `opening_rank`: rank determined at opening (`float64`)
  - `is_selected_winner`: whether bid was selected as winner (`boolean`)
  - `disqualification_reason_ko`: disqualification reason (`string`)
  - `bid_submission_time`: bid submission timestamp (`string`)

### 6.3 `03_award_outcomes.parquet` (Final Award Outcomes)
- **Physical Primary Key (PK)**: `award_outcome_id` (`AWD_<32 hex>`, deterministic SHA-256 surrogate key, 100% unique)
- **Business Reconciliation Grain**: `(bid_notice_no, bid_notice_round, winner_supplier_id, award_amount_krw, bid_submission_time)`
- **Row Count**: 17,315 rows (all selected winners)
- **Award Amount Null Policy**: Exactly 24 rows (0.14%) have NULL `award_amount_krw` due to unfinalized post-opening adjudication. Preserved as `NULL` per `DO NOT IMPUTE` policy.
- **Key Columns**:
  - `award_outcome_id`: string (PK, `AWD_` prefix)
  - `bid_notice_no`, `bid_notice_round`: tender reference (FK)
  - `winner_supplier_id`: winning supplier reference (FK, `SUP_` prefix)
  - `tender_in_scope`: whether tender notice is in current scope window (`boolean`)
  - `award_amount_krw`: final contract award amount (`float64`, Nullable in 24 cases)
  - `award_rate`: final award rate (`float64`, %)
  - `award_date`: award decision date (`string`)
  - `scheduled_price_krw`: final scheduled price (`float64`)
  - `base_amount_krw`: base price (`float64`)
  - `award_method_ko`: award decision method (`string`)

### 6.4 `04_contracts.parquet` (Executed Contracts Master)
- **Physical Primary Key (PK)**: `unified_contract_no` (`untyCntrctNo`, 100% unique)
- **Row Count**: 115,945 rows
- **Key Columns**: `unified_contract_no`, `contract_no`, `contract_round`, `contract_title_ko`, `contract_date`, `contract_method_ko`, `total_contract_amount_krw`, `contract_amount_krw`, `contract_agency_code`, `contract_agency_name_ko`, `demand_agency_code`, `demand_agency_name_ko`, `contractor_supplier_id` (FK), `contractor_name_ko`, `bid_notice_no`, `bid_notice_round`, `contract_period`, `is_joint_contract`

### 6.5 `05_suppliers.parquet` (Supplier Dimension)
- **Physical Primary Key (PK)**: `supplier_id` (`SUP_<32 hex>`, HMAC-SHA256 hash key)
- **Row Count**: 143,842 enterprises (consolidated across bidders, winners, and contractors)
- **Privacy Preservation**: Zero raw business registration numbers; masked string (`masked_biz_no`: `123-45-*****`) provided.
- **Key Columns**:
  - `supplier_id`: pseudonymized supplier identifier (PK)
  - `supplier_name_ko`: registered company name (`string`)
  - `masked_biz_no`: masked business registration number (`123-45-*****`)
  - `is_bidder`, `is_winner`, `is_contractor`: participation role flags (`boolean`)
  - `total_bids_in_scope`, `total_wins_in_scope`, `total_contracts_in_scope`: monthly activity counts (`int64`)
  - `total_contract_amount_krw`: monthly total contracted amount (`float64`)

### 6.6 `06_agencies.parquet` (Agency Dimension)
- **Physical Primary Key (PK)**: `agency_code` (7-digit standard public agency code)
- **Row Count**: 14,091 public entities
- **Key Columns**:
  - `agency_code`: standard agency code (PK)
  - `agency_name_ko`: official agency name (`string`)
  - `is_notice_agency`, `is_demand_agency`, `is_contract_agency`: role flags (`boolean`)
  - `total_tenders_in_scope`, `total_contracts_in_scope`: monthly procurement activity counts (`int64`)

### 6.7 `07_tender_contract_bridge.parquet` (Tender-Contract Relationship Bridge)
- **Physical Primary Key (PK)**: `unified_contract_no`
- **Row Count**: 40,677 rows (100% of tender-linked contracts; 75,268 unlinked contracts excluded)
- **Key Columns**:
  - `unified_contract_no`: contract identifier (PK, FK $\rightarrow$ `contracts`)
  - `bid_notice_no`, `bid_notice_round`: tender notice key (FK $\rightarrow$ `tenders`)
  - `tender_in_scope`: whether tender notice is in current scope window (`boolean`)
  - `contract_amount_krw`: contract amount (`float64`)
  - `contract_date`: contract date (`string`)
  - `contractor_supplier_id`: contractor reference (FK $\rightarrow$ `suppliers`)
