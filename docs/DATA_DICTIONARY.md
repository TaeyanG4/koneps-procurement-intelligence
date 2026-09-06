# Data Dictionary

This data dictionary outlines the canonical English column schema produced by the normalization pipeline, preserving original Korean names while presenting standard types for downstream analytics and machine learning.

---

## 1. Tender Notices (`bids`)

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
| `bid_notice_date` | `bidNtceDate` / `bidNtceDt` | string / date | Date the notice was officially published |
| `bid_notice_time` | `bidNtceBgn` | string | Time the notice was published (HH:MM) |
| `bid_begin_date` | `bidBeginDate` | string / date | Tender submission window start date |
| `bid_close_date` | `bidClseDate` | string / date | Tender submission deadline date |
| `opening_date` | `opengDate` | string / date | Bid opening date |
| `assigned_budget_krw` | `asignBdgtAmt` | float64 | Total budget allocated for the procurement (KRW) |
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

> [!NOTE]
> The live KONEPS OpenAPI operation `getDataSetOpnStdScsbidInfo` provides bidder-level resolution (each row represents a bidder submission for an opened tender, or tender status if failed/unbid).

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
| `opening_rank` | `opengRank` | float64 | Opening evaluation rank (1 = first rank) |
| `bidder_business_registration_no` | `bidprcCorpBizrno` | string | Bidding company's 10-digit business registration number |
| `bidder_name_ko` | `bidprcCorpNm` | string | Bidding company name |
| `bid_amount_krw` | `bidprcAmt` | float64 | Submitted bid amount (KRW) |
| `bid_rate` | `bidprcRt` | float64 | Bid rate relative to reference price (%) |
| `bid_submission_date` | `bidprcDate` | string / date | Bid submission date |
| `is_selected_winner` | `sucsfYn` | boolean | True if this bidder was selected as winner |
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

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `unified_contract_no` | `untyCntrctNo` | string | National unified contract identifier |
| `contract_no` | `cntrctNo` | string | Primary contract number |
| `contract_round` | `cntrctOrd` | string | Contract modification / round sequence |
| `contract_title_ko` | `cntrctNm` | string | Official contract title |
| `contract_date` | `cntrctCnclsDate` | string / date | Date contract was concluded (`YYYY-MM-DD`) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | Contract conclusion method (수간, 일반경쟁 등) |
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

| Canonical English Column | Source Column (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `procurement_channel` | `조달방식` | string | Procurement channel (e.g. 자체조달 vs 중앙조달) |
| `business_type` | `업무구분` | string | Business category (물품, 공사, 용역) |
| `bidding_method` | `입찰방법` | string | Bidding mechanism (전자입찰, 직찰 등) |
| `bid_notice_no` | `입찰공고번호` | string | Tender notice number |
| `bid_notice_round` | `입찰공고차수` | string | Notice revision round |
| `bid_title_ko` | `공고명` | string | Tender notice title |
| `opening_rank` | `개찰순위` | int64 / float64 | Opening bid rank (1 = closest to scheduled threshold) |
| `is_selected_winner` | `낙찰자선정여부` | boolean | True if company was officially selected as winner |
| `bidder_name_ko` | `업체명` | string | Bidding company name |
| `bidder_business_registration_no`| `업체사업자등록번호` | string | Bidding company business registration number |
| `bid_amount_krw` | `투찰금액` | float64 | Submitted bid amount (KRW) |
| `bid_rate` | `투찰율` | float64 | Submitted bid rate relative to reference price (%) |
| `is_disqualified` | `부적격여부` | boolean | True if bid was disqualified during opening / evaluation |
| `disqualification_reason_ko`| `입찰부적격사유` | string | Reason stated for disqualification |
| `current_contract_amount_krw`| `금차계약금액` | float64 | Executed contract amount for this term (KRW) |
| `total_contract_amount_krw` | `총계약금액` | float64 | Cumulative contracted amount (KRW) |

---

## 5. Candidate Gold ML Feature Columns (TBD / Empirical Stage)

Columns planned for future enrichment after join cardinality verification:

- `bidder_count` (TBD: Calculated from distinct bidders per tender)
- `market_hhi` (TBD: Herfindahl-Hirschman concentration index per industry code)
- `supplier_historical_win_rate` (TBD: Time-safe cumulative win rate before tender date)
- `scheduled_price_ratio` (TBD: `scheduled_price_krw / base_amount_krw`)
- `bid_price_ratio` (TBD: `bid_amount_krw / estimated_price_krw`)
