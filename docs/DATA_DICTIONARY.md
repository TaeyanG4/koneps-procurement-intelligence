# 데이터 사전 (Data Dictionary)

**한국어** | [English](DATA_DICTIONARY.en.md)

본 문서는 **대한민국 공공조달 인텔리전스 (KONEPS)** 파이프라인에서 정규화된 표준 데이터셋의 영문 표준 컬럼명, 원천 한글 필드명, 데이터 타입 및 비즈니스 정의를 기술합니다.

---

## 1. 입찰공고 (`bids`)

- **원천 API 오퍼레이션**: `getDataSetOpnStdBidPblancInfo`
- **기본 식별키 (Candidate PK)**: `(bid_notice_no, bid_notice_round)`

| 표준 영문 컬럼명 | 원천 API 필드 (한글) | 데이터 타입 | 설명 및 비즈니스 정의 |
| :--- | :--- | :--- | :--- |
| `bid_notice_no` | `bidNtceNo` | string | 고유 입찰공고번호 (예: `R26BK01708300`) |
| `bid_notice_round` | `bidNtceOrd` | string | 공고 차수/정정 차수 (예: `000`, `001`) |
| `bid_classification_no` | `bidClsfcNo` | string | 복수 물품 분할 발주 시 공고 분류 번호 |
| `rebid_no` | `rbidNo` | string | 재입찰/재공고 차수 |
| `bid_title_ko` | `bidNtceNm` | string | 원천 입찰공고명 |
| `notice_agency_code` | `ntceInsttCd` | string | 공고 발주기관 7자리 표준코드 |
| `notice_agency_name_ko` | `ntceInsttNm` | string | 발주기관명 |
| `demand_agency_code` | `dmndInsttCd` | string | 실수요기관 7자리 표준코드 |
| `demand_agency_name_ko` | `dmndInsttNm` | string | 수요기관명 |
| `bid_notice_date` | `bidNtceDate` / `bidNtceDt` | string / date | 입찰공고 게시일자 (`YYYY-MM-DD`) |
| `bid_notice_time` | `bidNtceBgn` | string | 공고 게시시각 (`HH:MM`) |
| `bid_begin_date` | `bidBeginDate` | string / date | 입찰서 접수 개시일시 |
| `bid_close_date` | `bidClseDate` | string / date | 입찰서 접수 마감일시 |
| `opening_date` | `opengDate` | string / date | 입찰 개찰일시 |
| `assigned_budget_krw` | `asignBdgtAmt` | float64 | 배정예산액 (원) |
| `estimated_price_krw` | `presmptPrce` | float64 | 추정가격 (부가가치세 제외 기준가, 원) |
| `base_amount_krw` | `bsisAmt` | float64 | 복수예비가격 추첨을 위한 기초금액 (원) |
| `business_div_name_ko` | `bsnsDivNm` | string | 업무구분명 (물품, 용역, 공사, 외자) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | 계약체결방법 (일반경쟁, 제한경쟁, 지명경쟁, 수의계약) |
| `contract_status_ko` | `cntrctCnclsSttusNm`| string | 계약체결상태 |
| `award_method_ko` | `bidwinrDcsnMthdNm` | string | 낙찰자결정방법 (적격심사, 소액수의, 최저가낙찰제 등) |
| `award_lower_limit_rate` | `sucsfbidLwltRate` | float64 | 낙찰하한율 (%) |
| `is_joint_contract` | `cmmnCntrctYn` | boolean | 공동수급(공동도급) 허용 여부 |
| `is_electronic_bid` | `elctrnBidYn` | boolean | 전자입찰 여부 |
| `is_international_bid` | `intrntnlBidYn` | boolean | 국제입찰 여부 |
| `is_pps_notice` | `ppsNtceYn` | boolean | 조달청 자체발주 공고 여부 |
| `is_region_limited` | `rgnLmtYn` | boolean | 지역제한입찰 여부 |
| `is_industry_limited` | `indstrytyLmtYn` | boolean | 업종제한입찰 여부 |

---

## 2. 개찰결과 및 투찰내역 (`awards`)

- **원천 API 오퍼레이션**: `getDataSetOpnStdScsbidInfo`
- **원천 무손실 중복제거 식별키 (Raw Deduplication Grain)**: `["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn", "bidprcAmt", "bidprcTm"]`
- **큐레이티드 테이블 기본 키 (Curated PK)**: `(bid_notice_no, bid_notice_round, bidder_supplier_id, opening_rank, disqualification_reason_ko, bid_amount_krw, bid_submission_time)` (원천 7개 컬럼 무손실 그레인과 동일하게 유지)
- **의도된 그레인**: 특정 공고·차수 내 개별 기업의 1회 입찰 투찰 제출 건 (`bidder_submissions`).

| 표준 영문 컬럼명 | 원천 API 필드 (한글) | 데이터 타입 | 설명 및 비즈니스 정의 |
| :--- | :--- | :--- | :--- |
| `bid_notice_no` | `bidNtceNo` | string | 연계 입찰공고번호 |
| `bid_notice_round` | `bidNtceOrd` | string | 공고 차수 |
| `bid_title_ko` | `bidNtceNm` | string | 공고명 |
| `business_div_name_ko` | `bsnsDivNm` | string | 업무구분 (물품, 외자, 공사, 용역) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | 계약체결방법 |
| `award_method_ko` | `bidwinrDcsnMthdNm` | string | 낙찰자결정방법 |
| `notice_agency_code` | `ntceInsttCd` | string | 발주기관코드 |
| `notice_agency_name_ko` | `ntceInsttNm` | string | 발주기관명 |
| `demand_agency_code` | `dmndInsttCd` | string | 수요기관코드 |
| `demand_agency_name_ko` | `dmndInsttNm` | string | 수요기관명 |
| `opening_date` | `opengDate` | string / date | 개찰일자 (`YYYY-MM-DD`) |
| `opening_rank` | `opengRank` | float64 | 개찰 순위 (1순위가 예정가격 대비 최적투찰자) |
| `bidder_business_registration_no` | `bidprcCorpBizrno` | string | 투찰기업 10자리 사업자등록번호 |
| `bidder_name_ko` | `bidprcCorpNm` | string | 투찰기업 상호명 |
| `bid_amount_krw` | `bidprcAmt` | float64 | 제출된 입찰 투찰금액 (원) |
| `bid_rate` | `bidprcRt` | float64 | 예정가격 대비 투찰률 (%) |
| `bid_submission_date` | `bidprcDate` | string / date | 투찰일자 |
| `bid_submission_time` | `bidprcTm` | string | 투찰시각 (`HH:MM`) |
| `is_selected_winner` | `sucsfYn` | boolean | 최종 낙찰사 선정 여부 |
| `disqualification_reason_ko` | `dqlfctnRsn` | string | 심사 탈락사유 (예: 예정가격초과, 자격미달 등) |
| `award_amount_krw` | `fnlSucsfAmt` | float64 | 최종 확정 낙찰금액 (원) |
| `award_rate` | `fnlSucsfRt` | float64 | 최종 낙찰률 (%) |
| `award_date` | `fnlSucsfDate` | string / date | 최종 낙찰결정일자 |
| `winner_name_ko` | `fnlSucsfCorpNm` | string | 최종 낙찰기업 상호 |
| `winner_business_registration_no` | `fnlSucsfCorpBizrno` | string | 최종 낙찰기업 사업자등록번호 |
| `estimated_price_krw` | `presmptPrce` | float64 | 추정가격 (원) |
| `scheduled_price_krw` | `rsrvtnPrce` | float64 | 복수예가 추첨을 통해 확정된 최종 예정가격 (원) |
| `base_amount_krw` | `bssAmt` | float64 | 기초금액 (원) |

---

## 3. 계약내역 (`contracts`)

- **원천 API 오퍼레이션**: `getDataSetOpnStdCntrctInfo`
- **기본 식별키 (Candidate PK)**: `unified_contract_no` (`untyCntrctNo`, 100% 고유성 실증 완료)

| 표준 영문 컬럼명 | 원천 API 필드 (한글) | 데이터 타입 | 설명 및 비즈니스 정의 |
| :--- | :--- | :--- | :--- |
| `unified_contract_no` | `untyCntrctNo` | string | 정부 통합계약번호 (국가 표준 고유 식별키) |
| `contract_no` | `cntrctNo` | string | 기관별 원천 계약번호 |
| `contract_round` | `cntrctOrd` | string | 계약 변경/차수 번호 |
| `contract_title_ko` | `cntrctNm` | string | 계약 체결명 |
| `contract_date` | `cntrctCnclsDate` | string / date | 계약 체결일자 (`YYYY-MM-DD`) |
| `contract_method_ko` | `cntrctCnclsMthdNm` | string | 계약체결방법 (수의계약, 일반경쟁 등) |
| `contract_amount_krw` | `cntrctAmt` | float64 | 금차 체결 계약금액 (원) |
| `total_contract_amount_krw`| `ttalCntrctAmt` | float64 | 장기계약 시 총 계약금액 (원) |
| `contract_agency_code` | `cntrctInsttCd` | string | 계약체결기관 7자리 표준코드 |
| `contract_agency_name_ko` | `cntrctInsttNm` | string | 계약체결기관명 |
| `demand_agency_code` | `dmndInsttCd` | string | 수요기관코드 |
| `demand_agency_name_ko` | `dmndInsttNm` | string | 수요기관명 |
| `contractor_business_registration_no` | `rprsntCorpBizrno` | string | 수주계약기업 사업자등록번호 |
| `contractor_name_ko` | `rprsntCorpNm` | string | 수주계약기업 상호 |
| `bid_notice_no` | `bidNtceNo` | string | 연계 입찰공고번호 (미연계 시 결측) |
| `bid_notice_round` | `bidNtceOrd` | string | 연계 입찰공고차수 |
| `contract_period` | `cntrctPrd` | string | 계약 이행기간 |
| `is_joint_contract` | `cmmnCntrctYn` | boolean | 공동계약 체결 여부 |
| `is_domestic_corp` | `dmstcCorpYn` | boolean | 국내기업 여부 |

---

## 4. 포털 투찰보고서 (`bidder_outcomes`)

- **인제스트 스크립트**: `scripts/ingest_bidder_report.py`
- **역할**: 보조 데이터 강화 및 교차 검증용 선택적 소스

| 표준 영문 컬럼명 | 원천 한글 컬럼 | 데이터 타입 | 설명 및 비즈니스 정의 |
| :--- | :--- | :--- | :--- |
| `procurement_channel` | `조달방식` | string | 조달방식 (자체조달, 중앙조달 등) |
| `business_type` | `업무구분` | string | 업무구분 (물품, 공사, 용역) |
| `bidding_method` | `입찰방법` | string | 입찰방법 (전자입찰, 직찰 등) |
| `bid_notice_no` | `입찰공고번호` | string | 입찰공고번호 |
| `bid_notice_round` | `입찰공고차수` | string | 공고차수 |
| `bid_title_ko` | `공고명` | string | 공고명 |
| `opening_rank` | `개찰순위` | float64 | 개찰순위 |
| `is_selected_winner` | `낙찰자선정여부` | boolean | 최종 낙찰자 선정 여부 |
| `bidder_name_ko` | `업체명` | string | 투찰기업 상호명 |
| `bidder_business_registration_no`| `업체사업자등록번호` | string | 투찰기업 사업자등록번호 |
| `bid_amount_krw` | `투찰금액` | float64 | 투찰금액 (원) |
| `bid_rate` | `투찰율` | float64 | 사정률 대비 투찰률 (%) |
| `is_disqualified` | `부적격여부` | boolean | 적격심사 탈락 여부 |
| `disqualification_reason_ko`| `입찰부적격사유` | string | 탈락사유 |
| `bidder_sigungu_ko` | `업체소재시군구` | string | 기업 소재 기초지자체 (포털 보고서 전용 필드) |
| `current_contract_amount_krw`| `금차계약금액` | float64 | 금차 계약금액 (원) |
| `total_contract_amount_krw` | `총계약금액` | float64 | 총 계약금액 (원) |

---

## 5. 후보 머신러닝 피처 컬럼 (Candidate ML Feature Columns)

조인 카디널리티 검증 및 관계형 브릿지 구축 후 생성될 2차 파생 피처:
- `bidder_count`: 공고당 유효 투찰 기업 수 (경쟁 강도 지표)
- `market_hhi`: 업종 및 발주기관별 시장 집중도 (허핀달-허쉬만 지수)
- `supplier_historical_win_rate`: 해당 공고 이전 시점까지의 공급기업 누적 수주 성공률 (누수 방지 시계열 처리)
- `scheduled_price_ratio`: 기초금액 대비 예정가격 사정률 (`scheduled_price_krw / base_amount_krw`)
- `bid_price_ratio`: 추정가격 대비 투찰금액 비율 (`bid_amount_krw / estimated_price_krw`)

---

## 6. 관계형 큐레이티드 테이블 (`CURATED_SCHEMA_VERSION = "1.0.0"`)

정규화 Parquet 피드로부터 생성되는 7개의 정규화 관계형 테이블(`data/processed/curated/YYYY_MM/`)의 표준 컬럼 구조입니다.

### 6.1 `01_tenders.parquet` (입찰공고 마스터)
- **물리 기본 키 (PK)**: `(bid_notice_no, bid_notice_round)`
- **행 수**: 32,895행 (8월 기준, 100% 고유)
- **주요 컬럼**: `bid_notice_no`, `bid_notice_round`, `bid_notice_name_ko`, `notice_agency_code`, `notice_agency_name_ko`, `demand_agency_code`, `demand_agency_name_ko`, `business_div_name_ko`, `contract_method_ko`, `award_method_ko`, `assigned_budget_krw`, `estimated_price_krw`, `bid_notice_date`, `bid_begin_date`, `bid_close_date`, `opening_date`, `is_joint_contract`, `is_electronic_bid`, `is_region_limited`, `is_industry_limited`

### 6.2 `02_bidder_submissions.parquet` (개별 기업 투찰 기록)
- **물리 기본 키 (PK)**: `bid_submission_id` (`BID_<32 hex>`, SHA-256 대리 키, 100% 고유)
- **비즈니스 대조 그레인**: `(bid_notice_no, bid_notice_round, bidder_supplier_id, opening_rank, disqualification_reason_ko, bid_amount_krw, bid_submission_time)` (7-컬럼 무손실 그레인)
- **행 수**: 2,107,948행 (8월 기준)
- **주요 컬럼**:
  - `bid_submission_id`: 문자열 (PK, `BID_` 접두어)
  - `bid_notice_no`, `bid_notice_round`: 연계 공고 키 (FK)
  - `bidder_supplier_id`: 가명화 기업 키 (FK, `SUP_` 접두어)
  - `tender_in_scope`: 당월 큐레이티드 공고 연계 여부 (`boolean`)
  - `bid_amount_krw`: 투찰금액 (`float64`)
  - `bid_rate_pct`: 투찰률 (`float64`, %)
  - `opening_rank`: 개찰순위 (`float64`)
  - `is_selected_winner`: 낙찰자 선정 여부 (`boolean`)
  - `disqualification_reason_ko`: 탈락사유 (`string`)
  - `bid_submission_time`: 투찰시각 (`string`)

### 6.3 `03_award_outcomes.parquet` (최종 낙찰 결과)
- **물리 기본 키 (PK)**: `award_outcome_id` (`AWD_<32 hex>`, SHA-256 대리 키, 100% 고유)
- **비즈니스 대조 그레인**: `(bid_notice_no, bid_notice_round, winner_supplier_id, award_amount_krw, bid_submission_time)`
- **행 수**: 17,315행 (선정 낙찰자 전수)
- **낙찰금액 결측치 정책**: 24건(0.14%) `award_amount_krw` 결측치는 적격심사 등 개찰 직후 미확정 상태로 `DO NOT IMPUTE` 정책에 따라 `NULL` 보존.
- **주요 컬럼**:
  - `award_outcome_id`: 문자열 (PK, `AWD_` 접두어)
  - `bid_notice_no`, `bid_notice_round`: 연계 공고 키 (FK)
  - `winner_supplier_id`: 낙찰 기업 키 (FK, `SUP_` 접두어)
  - `tender_in_scope`: 당월 큐레이티드 공고 연계 여부 (`boolean`)
  - `award_amount_krw`: 최종 낙찰금액 (`float64`, 24건 Nullable)
  - `award_rate`: 낙찰률 (`float64`, %)
  - `award_date`: 낙찰결정일자 (`string`)
  - `scheduled_price_krw`: 예정가격 (`float64`)
  - `base_amount_krw`: 기초금액 (`float64`)
  - `award_method_ko`: 낙찰자결정방법 (`string`)

### 6.4 `04_contracts.parquet` (정부 계약 마스터)
- **물리 기본 키 (PK)**: `unified_contract_no` (`untyCntrctNo`, 100% 고유)
- **행 수**: 115,945행
- **주요 컬럼**: `unified_contract_no`, `contract_no`, `contract_round`, `contract_title_ko`, `contract_date`, `contract_method_ko`, `total_contract_amount_krw`, `contract_amount_krw`, `contract_agency_code`, `contract_agency_name_ko`, `demand_agency_code`, `demand_agency_name_ko`, `contractor_supplier_id` (FK), `contractor_name_ko`, `bid_notice_no`, `bid_notice_round`, `contract_period`, `is_joint_contract`

### 6.5 `05_suppliers.parquet` (공급업체 차원)
- **물리 기본 키 (PK)**: `supplier_id` (`SUP_<32 hex>`, HMAC-SHA256 해시 키)
- **행 수**: 143,842개사 (투찰사, 낙찰사, 계약체결사 전수 통합)
- **프라이버시 보존**: 원천 사업자번호 완전 제거, 마스킹 번호(`masked_biz_no`: `123-45-*****`) 제공.
- **주요 컬럼**:
  - `supplier_id`: 가명화 기업 식별자 (PK)
  - `supplier_name_ko`: 기업 상호명 (`string`)
  - `masked_biz_no`: 마스킹된 사업자등록번호 (`123-45-*****`)
  - `is_bidder`, `is_winner`, `is_contractor`: 기업 역할 플래그 (`boolean`)
  - `total_bids_in_scope`, `total_wins_in_scope`, `total_contracts_in_scope`: 당월 활동 실적 (`int64`)
  - `total_contract_amount_krw`: 당월 계약체결 총액 (`float64`)

### 6.6 `06_agencies.parquet` (발주 및 수요기관 차원)
- **물리 기본 키 (PK)**: `agency_code` (7자리 공공기관 표준코드)
- **행 수**: 14,091개 기관
- **주요 컬럼**:
  - `agency_code`: 표준 기관코드 (PK)
  - `agency_name_ko`: 공식 기관명 (`string`)
  - `is_notice_agency`, `is_demand_agency`, `is_contract_agency`: 기관 역할 플래그 (`boolean`)
  - `total_tenders_in_scope`, `total_contracts_in_scope`: 당월 조달 활동 건수 (`int64`)

### 6.7 `07_tender_contract_bridge.parquet` (공고-계약 연결 브릿지)
- **물리 기본 키 (PK)**: `unified_contract_no`
- **행 수**: 40,677행 (공고 연계 계약 100% 수록, 미연계 계약 75,268건은 제외)
- **주요 컬럼**:
  - `unified_contract_no`: 계약 식별자 (PK, FK $\rightarrow$ `contracts`)
  - `bid_notice_no`, `bid_notice_round`: 입찰공고 키 (FK $\rightarrow$ `tenders`)
  - `tender_in_scope`: 당월 큐레이티드 공고 연계 여부 (`boolean`)
  - `contract_amount_krw`: 계약금액 (`float64`)
  - `contract_date`: 계약일자 (`string`)
  - `contractor_supplier_id`: 계약기업 키 (FK $\rightarrow$ `suppliers`)
