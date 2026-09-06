# KONEPS 공공데이터포털 실시간 API 검증 보고서

**한국어** | [English](LIVE_VALIDATION.en.md)

본 문서는 조달청 나라장터 표준 공공데이터 API(`PubDataOpnStdService` v1.2)에 대한 실시간 연동 검증 및 1일치(`2026-09-01`) 스모크 테스트 수집·정제·품질 검증 결과를 기록한 공식 기술 보고서입니다.

---

## 1. 검증 개요 및 환경

- **검증 일시**: 2026년 9월 7일
- **연동 서비스**: 공공데이터포털(`data.go.kr`) 조달청 나라장터 개방표준서비스 (`PubDataOpnStdService` v1.2)
- **인증 방식**: 공공데이터포털 일반 인증키 (`DATA_GO_KR_SERVICE_KEY`)
- **수집 대상 일자**: `2026-09-01` (1일 스모크 테스트)
- **테스트 대상 피드**:
  1. `bids` (`getDataSetOpnStdBidPblancInfo` - 입찰공고 정보)
  2. `awards` (`getDataSetOpnStdScsbidInfo` - 개찰/낙찰자 결정 정보, 4개 업무구분 전수)
  3. `contracts` (`getDataSetOpnStdCntrctInfo` - 계약 체결 정보)
- **실행 환경**: Windows 11, Python 3.12 (CI: Python 3.11 & 3.12)

---

## 2. API 규격 일치화 및 보안 인증 검증

### 2.1 URL 이중 인코딩(Double Percent-Encoding) 방지
- **문제 현상**: 공공데이터포털의 Encoding 키(`%3D`, `%2B` 포함)를 `requests.get(params=...)`에 그대로 전달할 경우, 라이브러리 내부에서 `%253D`로 이중 인코딩되어 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` (코드 30) 에러가 발생함.
- **해결 방안**: `get_service_key()` 및 `KonepsClient._build_request()`에서 `urllib.parse.unquote()`를 적용하여 Decoding/Encoding 키 형태와 무관하게 정확한 바이트가 전송되도록 처리함.

### 2.2 공식 파라미터 케이싱 일치화
- `PubDataOpnStdService` 표준 규격에 맞추어 인증키 쿼리 파라미터를 `ServiceKey`로 통일함.

### 2.3 awards 피드 1일 윈도우 분할
- `getDataSetOpnStdScsbidInfo`의 `opengBgnDt`/`opengEndDt` 허용 범위가 최대 1일(당일 00:00 ~ 23:59)로 제한되어 있으므로 `endpoints.py`의 `awards` feed spec을 `window_days=1`로 확정 적용함.

### 2.4 무출력 보안 정책 (Zero-Secret Policy)
- API 서비스 키는 환경변수(`.env`)에서만 로드하며, 로그 및 콘솔 출력 시 `izyp********Yg==`와 같이 마스킹 처리되어 절대 노출되지 않음을 확인함.
- 수집된 원천 `.jsonl.gz`, `.parquet`, `.env` 파일은 `.gitignore`에 전면 등록되어 저장소 유출을 방지함.

---

## 3. 1일치 실시간 수집 결과 (`2026-09-01`)

| 데이터셋 | 오퍼레이션 | 대상 구분 | 수집 행 수 (Rows) | API 호출 수 | 산출물 크기 (압축 raw) | 상태 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **bids** | `getDataSetOpnStdBidPblancInfo` | 전체 | 1,564 | 16 | 240 KB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | 물품 (1) | 24,627 | 247 | 1.16 MB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | 외자 (2) | 12 | 1 | 1.78 KB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | 공사 (3) | 99,601 | 100 | 5.37 MB | Complete |
| **awards** | `getDataSetOpnStdScsbidInfo` | 용역 (5) | 5,672 | 6 | 288 KB | Complete |
| **contracts** | `getDataSetOpnStdCntrctInfo` | 전체 | 6,269 | 7 | 643 KB | Complete |
| **합계** | - | - | **137,745** | **377** | **~7.7 MB** | **전수 성공** |

> [!TIP]
> **페이징 성능 최적화 성과**:
> `getDataSetOpnStdScsbidInfo` 및 `getDataSetOpnStdCntrctInfo`는 `numOfRows=999`를 공식 지원합니다. 공사(construction) 부문(99,601건) 수집 시 100단위 페이징(약 1,000회 호출 필요) 대신 999단위 페이징을 적용하여 단 100회의 호출(약 4분 소요)로 일일 호출 한도(1,000건/일) 소진 없이 신속하고 안전하게 수집을 완료했습니다.

---

## 4. 실측 데이터 스키마 및 입도(Grain) 분석

### 4.1 핵심 발견: awards 피드의 데이터 입도와 중복 제거 키 보정
- **실측 분석**: `getDataSetOpnStdScsbidInfo` 피드는 단순 1공고당 1행(낙찰자 1개사)이 아니라, **해당 개찰일에 열린 모든 공고의 개찰 순위별 전체 투찰 업체(Bidder Submission) 행**을 반환함.
- **데이터 유실 방지 조치**:
  - 기존 초기 구현체의 디듀플리케이션 키가 `["bidNtceNo", "bidNtceOrd"]`로 지정되어 있어, 그대로 정규화할 경우 공고당 1개 행만 남고 **99.5%의 투찰자 데이터가 유실(공사 기준 99,601건 -> 419건으로 압축)**될 심각한 위험이 확인됨.
  - 이를 방지하기 위해 `DEDUPLICATION_KEYS["awards"]`를 `["bidNtceNo", "bidNtceOrd", "bidprcCorpBizrno", "opengRank", "dqlfctnRsn"]`로 즉각 보정함.
  - 보정 결과: 유효한 입찰자 128,250건이 보존되고 네트워크 재조회 등으로 발생한 순수 중복만 정확하게 제거됨.

### 4.2 실측 API 필드 정합성 일치화
실시간 수집된 실제 응답 스키마와 내부 캐노니컬 매핑의 차이를 실측하여 전면 보정함:

1. **bids (입찰공고, 53개 실측 필드)**:
   - 수요기관: `dminsttCd` 뿐만 아니라 실측 API 표준인 `dmndInsttCd`, `dmndInsttNm` 지원.
   - 추정가격: `presmPtce` 외 실측 필드명인 `presmptPrce` 반영.
   - 공고일/마감일: `bidNtceDate`, `bidNtceBgn`, `bidBeginDate`, `bidClseDate`, `opengDate` 반영.
   - 낙찰방법: `bidwinrDcsnMthdNm` 매핑 추가.

2. **awards (개찰/낙찰자, 38개 실측 필드)**:
   - 투찰자 레벨: `bidprcCorpBizrno` (투찰업체사업자번호), `bidprcCorpNm` (투찰업체명), `bidprcAmt` (투찰금액), `bidprcRt` (투찰율), `opengRank` (개찰순위), `sucsfYn` (낙찰여부), `dqlfctnRsn` (부적격사유).
   - 최종 낙찰자 레벨: `fnlSucsfAmt` (최종낙찰금액), `fnlSucsfRt` (최종낙찰율), `fnlSucsfCorpNm` (낙찰업체명), `fnlSucsfCorpBizrno` (낙찰업체사업자번호), `fnlSucsfDate` (낙찰일자).
   - 가격 기준: `presmptPrce` (추정가격), `rsrvtnPrce` (예정가격), `bssAmt` (기초금액).

3. **contracts (계약, 44개 실측 필드)**:
   - 식별자: `untyCntrctNo` (통합계약번호 - 6,269건 전수 100% Unique 키로 확인됨), `cntrctNo` (계약번호), `cntrctOrd` (계약차수).
   - 계약금액: `cntrctAmt` (금차계약금액), `ttalCntrctAmt` (총계약금액).
   - 계약상대자: `rprsntCorpBizrno` (대표업체사업자등록번호), `rprsntCorpNm` (대표업체명).

---

## 5. Parquet 정규화 및 데이터 품질 검증

`scripts/build_dataset.py`를 통해 원천 JSONL 데이터를 Hive 파티셔닝(`year=2026/month=09/`) Parquet 데이터셋으로 변환하고, `scripts/quality_check.py --strict`로 전수 검증을 수행함.

### 5.1 Parquet 변환 결과

| 데이터셋 피드 | 파티션 경로 | 정규화 행 수 | 컬럼 수 | 압축 포맷 |
| :--- | :--- | :--- | :--- | :--- |
| **bids** | `data/processed/bids/year=2026/month=09/` | 1,564 | 95 | zstd |
| **awards (공사)** | `data/processed/awards/year=2026/month=09/` | 98,110 | 79 | zstd |
| **awards (외자)** | `data/processed/awards/year=2026/month=09/` | 12 | 79 | zstd |
| **awards (물품)** | `data/processed/awards/year=2026/month=09/` | 24,573 | 79 | zstd |
| **awards (용역)** | `data/processed/awards/year=2026/month=09/` | 5,555 | 79 | zstd |
| **contracts** | `data/processed/contracts/year=2026/month=09/` | 6,269 | 82 | zstd |

### 5.2 엄격 품질 검증 결과 (`quality_check.py --strict`)

- **검사 파일 수**: 6개 파일 (총 136,083행)
- **치명적 결함(Critical Issues)**: **0건 (False)**
- **완전 중복 행(Duplicate Full Rows)**: **0건**
- **음수 금액(Negative Monetary Amounts)**: **0건**
- **통합계약번호 결측률(untyCntrctNo null ratio)**: **0.0% (고유성 100%)**
- **인코딩 무결성**: 한글 문자 깨짐(Garbled text, `?`, `\ufffd`) 없이 순수 UTF-8로 완전 보존 확인.

---

## 6. 결론 및 다음 마일스톤 권장사항

1. **실시간 연동 성공**: 조달청 나라장터 공공데이터포털 API의 모든 표준 피드가 정상 인증 및 수집 가능함을 완벽하게 입증함.
2. **차기 권장 마일스톤**:
   - **"1개월 파일럿 수집 (1-Month Benchmark)"** 진행을 권장함.
   - 1개월 수집 시 `awards` 피드의 공사 부문은 월간 약 200만~300만 행에 달할 수 있으므로, 공공데이터포털 개발계정(1,000호출/일)에서 **운영계정(10,000~100,000호출/일)**으로의 자동 트래픽 상향 신청을 권장함.
