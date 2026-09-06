# Data Dictionary

This data dictionary outlines the canonical English column schema produced by the normalization pipeline, preserving original Korean names while presenting standard types for downstream analytics and machine learning.

---

## 1. Tender Notices (`bids`)

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `bid_notice_no` | `bidNtceNo` | string | Unique tender announcement number (e.g. `20260901001`) |
| `bid_notice_round` | `bidNtceOrd` | string | Announcement revision/round sequence (e.g. `00`) |
| `bid_classification_no` | `bidClsfcNo` | string | Sub-classification index under multi-item tenders |
| `rebid_no` | `rbidNo` | string | Re-bidding iteration counter |
| `bid_title_ko` | `bidNtceNm` | string | Original Korean title of the tender |
| `notice_agency_code` | `ntceInsttCd` | string | Official identifier of publishing agency |
| `notice_agency_name_ko` | `ntceInsttNm` | string | Name of publishing procuring agency |
| `demand_agency_code` | `dminsttCd` | string | Official identifier of end-demand agency |
| `demand_agency_name_ko` | `dminsttNm` | string | Name of end-demand agency |
| `bid_notice_date` | `bidNtceDt` | string / timestamp | Date and time the notice was officially published |
| `bid_notice_begin_datetime`| `bidNtceBgnDt` | string / timestamp | Tender submission window start |
| `bid_notice_end_datetime` | `bidNtceEndDt` | string / timestamp | Tender submission deadline |
| `opening_datetime` | `opengDt` | string / timestamp | Bid opening date and time |
| `assigned_budget_krw` | `asignBdgtAmt` | float64 | Total budget allocated for the procurement (KRW) |
| `estimated_price_krw` | `presmPtce` | float64 | Estimated price (ex-VAT reference price, KRW) |
| `base_amount_krw` | `bsisAmt` | float64 | Base reference amount for multi-pricing pools (KRW) |
| `business_div_code` | `bsnsDivCd` | string | Procurement division code (`1`: Goods, `3`: Works, `5`: Services) |
| `business_div_name_ko` | `bsnsDivNm` | string | Korean division label (??, ??, ?? ?) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | Contract procurement method (????, ????, ????) |
| `award_method_ko` | `sucsfbidMthdNm` | string | Decision criteria (????, ????????, ??????) |
| `award_lower_limit_rate` | `sucsfbidLwltRate` | float64 | Lower-bound bid rate threshold (%) |

---

## 2. Successful Bids & Awards (`awards`)

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `bid_notice_no` | `bidNtceNo` | string | Associated tender announcement number |
| `bid_notice_round` | `bidNtceOrd` | string | Tender revision sequence |
| `bid_classification_no` | `bidClsfcNo` | string | Sub-classification index |
| `bid_title_ko` | `bidNtceNm` | string | Original Korean title |
| `opening_datetime` | `opengDt` | string / timestamp | Date and time bid was unsealed |
| `award_amount_krw` | `sucsfbidAmt` | float64 | Final winning bid amount (KRW) |
| `award_rate` | `sucsfbidRate` | float64 | Winning bid amount divided by scheduled price (%) |
| `winner_name_ko` | `corpNm` | string | Winning supplier company name |
| `winner_business_registration_no` | `bizno` | string | Winner's 10-digit Korean business registration number |
| `scheduled_price_krw` | `plndPrice` | float64 | Final scheduled price determined from random draw pool (KRW) |

---

## 3. Contracts (`contracts`)

| Canonical English Column | Source API Field (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `unified_contract_no` | `untyCntrctNo` | string | National unified contract identifier |
| `contract_no` | `cntrctNo` | string | Primary contract number |
| `contract_ref_no` | `cntrctRefNo` | string | Contract modification / reference sequence |
| `contract_title_ko` | `cntrctNm` | string | Official contract subject |
| `contract_date` | `cntrctCnclsDate` | string / date | Date contract concluded (`YYYY-MM-DD` or `YYYYMMDD`) |
| `contract_amount_krw` | `cntrctAmt` | float64 | Current signed contract amount (KRW) |
| `total_contract_amount_krw`| `totCntrctAmt` | float64 | Cumulative total value across multi-year commitments (KRW) |
| `contractor_name_ko` | `corpNm` | string | Contractor business name |
| `contractor_business_registration_no` | `bizno` | string | Contractor's business registration number |

---

## 4. Bidder Outcome Report (`bidder_outcomes`)

| Canonical English Column | Source Column (Korean) | Data Type | Description |
| :--- | :--- | :--- | :--- |
| `procurement_channel` | `????` | string | Procurement channel (e.g. ???? vs ????) |
| `business_type` | `????` | string | Business category (??, ??, ??) |
| `bidding_method` | `????` | string | Bidding mechanism (????, ?? ?) |
| `bid_notice_no` | `??????` | string | Tender notice number |
| `bid_notice_round` | `??????` | string | Notice revision round |
| `bid_title_ko` | `???` | string | Tender notice title |
| `opening_rank` | `????` | int64 / float64 | Opening bid rank (1 = closest to scheduled threshold) |
| `is_selected_winner` | `???????` | boolean | True if company was officially selected as winner |
| `bidder_name_ko` | `???` | string | Bidding company name |
| `bidder_business_registration_no`| `?????????` | string | Bidding company business registration number |
| `bid_amount_krw` | `????` | float64 | Submitted bid amount (KRW) |
| `bid_rate` | `???` | float64 | Submitted bid rate relative to reference price (%) |
| `is_disqualified` | `?????` | boolean | True if bid was disqualified during opening / evaluation |
| `disqualification_reason_ko`| `???????` | string | Reason stated for disqualification |
| `current_contract_amount_krw`| `??????` | float64 | Executed contract amount for this term (KRW) |
| `total_contract_amount_krw` | `?????` | float64 | Cumulative contracted amount (KRW) |

---

## 5. Candidate Gold ML Feature Columns (TBD / Empirical Stage)

Columns planned for future enrichment after join cardinality verification:

- `bidder_count` (TBD: Calculated from distinct bidders per tender)
- `market_hhi` (TBD: Herfindahl-Hirschman concentration index per industry code)
- `supplier_historical_win_rate` (TBD: Time-safe cumulative win rate before tender date)
- `scheduled_price_ratio` (TBD: `scheduled_price_krw / base_amount_krw`)
- `bid_price_ratio` (TBD: `bid_amount_krw / estimated_price_krw`)
