# 공공데이터 출처 및 라이선스 가이드 (Data Sources & Licensing Guide)

**한국어** | [English](DATA_SOURCES.en.md)

본 문서는 **대한민국 공공조달 인텔리전스 (KONEPS Procurement Intelligence)** 파이프라인에서 사용하는 공공데이터 출처, 서비스 엔드포인트, 수집 제약 조건 및 라이선스 거버넌스 정책을 기술합니다.

---

## 1. 공공데이터포털(data.go.kr) OpenAPI

자동화 수집 파이프라인은 공공데이터포털(`data.go.kr`)을 통해 조달청이 개방하는 나라장터(KONEPS) 공공데이터개방표준서비스를 활용합니다.

- **서비스명**: 조달청_나라장터 공공데이터개방표준서비스 (KONEPS Public Data Open Standard Service)
- **기본 엔드포인트 URL**: `https://apis.data.go.kr/1230000/ao/PubDataOpnStdService`
- **통신 프로토콜**: HTTPS GET (JSON 및 XML 응답)
- **인증 방식**: `ServiceKey` (계정별 발급되는 일반 인증키 Decoding 값)
- **호출 트래픽 특성**:
  - 기본 개발계정 트래픽 한도: 일 1,000 ~ 10,000건 (신청 시 즉시 승인)
  - 실운영 계정: 대용량 트래픽 허용 (2026-08 파일럿 수집 시 단일 세션 2,365회 호출 무결주 확인)

### 지원 엔드포인트 규격

| 데이터셋 | 오퍼레이션명 (Operation) | 조회 일시 파라미터 | 날짜 형식 | 수집 윈도우 분할 전략 |
| :--- | :--- | :--- | :--- | :--- |
| **입찰공고 (`bids`)** | `getDataSetOpnStdBidPblancInfo` | `bidNtceBgnDt` ~ `bidNtceEndDt` | `YYYYMMDDHHMM` | 1개월 단위 캘린더 분할 (`month_windows`) |
| **개찰결과 (`awards`)** | `getDataSetOpnStdScsbidInfo` | `opengBgnDt` ~ `opengEndDt` | `YYYYMMDDHHMM` | **1일 단위 윈도우** (API v1.2 규격 필수) × 4대 업무구분(`bsnsDivCd` 1, 2, 3, 5) |
| **계약내역 (`contracts`)** | `getDataSetOpnStdCntrctInfo` | `cntrctCnclsBgnDate` ~ `cntrctCnclsEndDate` | `YYYYMMDD` | 7일 단위 주간 분할 (`week_windows`) |

### 업무구분 코드 (`bsnsDivCd`)
개찰결과 등 업무구분 분할이 필수적인 엔드포인트:
- `1`: 물품 (Goods)
- `2`: 외자 (Foreign Supplies)
- `3`: 공사 (Construction / Civil Works) — 전체 개찰결과의 약 77.6% 점유
- `5`: 용역 (Services / Consulting)

---

## 2. 나라장터 포털 상세 투찰보고서 익스포트 (Bidder Report Export)

표준 API 피드 외에, 특정 공고 건에 대한 포털 세부 투찰내역을 추출할 수 있습니다:
- **출처 포털**: 조달청 나라장터(KONEPS) 개찰결과 상세 조회 화면
- **보고서 명칭**: 입찰공고 기업별 투찰 및 계약내역
- **인제스트 스크립트**: `scripts/ingest_bidder_report.py`
- **지원 파일 포맷**: CSV(`.csv`), Excel(`.xlsx`, 바이너리 `.xls` 지원)
- **역할 및 위상**: 표준 `awards` API가 투찰 기업 정보(사업자번호, 투찰금액, 투찰률, 개찰순위)를 전수 제공함에 따라, 포털 보고서는 **선택적 데이터 강화 및 교차 검증(Optional Enrichment)** 보조 소스로 활용됩니다.

---

## 3. 데이터 거버넌스 및 라이선스 정책

### 원천 데이터 라이선스
- 공공데이터포털 및 나라장터를 통해 제공되는 데이터는 대한민국의 **「공공데이터의 제공 및 이용 활성화에 관한 법률」** 및 각 서비스 페이지에 표시된 개별 이용조건을 따릅니다. 특정 Creative Commons/공공누리 유형을 서비스 페이지 확인 없이 임의로 부여하지 않습니다.
- **2026-09-11 재확인**: `조달청_나라장터 공공데이터개방표준서비스` 페이지(수정일 2026-06-29)는 비용 `무료`, **이용허락범위 `제한 없음`**으로 표시됩니다. Source: `https://www.data.go.kr/en/data/15023678/standard.do`
- **코드와 데이터의 분리**: 본 GitHub 저장소는 소스코드와 파이프라인만 관리하며, 수집된 대용량 원천 데이터는 Git에 커밋하지 않고 Kaggle Datasets를 통해 별도 배포합니다.

### 책임 있는 데이터 공개 원칙 (Responsible Publication Checkpoints)
1. **Source-by-Source License Re-Verification (출처별 이용조건 재검증)**: 표준 API 서비스는 2026-09-11 재확인 완료했습니다. 향후 별도 나라장터 포털 export를 공개본에 포함할 경우 해당 export의 이용조건은 다시 별도 검증합니다.
2. **사업자등록번호 가명화 및 최소화**: 공개 데이터셋은 전용 비밀키 기반 HMAC-SHA256 `supplier_id`만 공급업체 식별자로 사용합니다. 원문 사업자등록번호와 마스킹 사업자등록번호는 모두 제외합니다.
3. **공급업체 상호명 최소화**: v1 Kaggle 공개본에서는 투찰사·낙찰사·계약업체·공급업체 차원의 상호명도 제외합니다. 공공기관명은 기관 분석과 조인을 위해 유지합니다.
4. **개인정보 보호**: 공공입찰 데이터 중 개인식별정보(주민등록번호 등)는 공개 데이터셋에 포함하지 않습니다.
5. **인증키 보안**: 서비스 인증키, HMAC 비밀키, 개인 토큰, `.env` 파일은 절대 소스코드 저장소에 커밋하지 않습니다.
