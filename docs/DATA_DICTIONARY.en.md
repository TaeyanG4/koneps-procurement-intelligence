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
- **Lossless Deduplication Key**: `["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn", "bidprcAmt", "bidprcTm"]`
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
