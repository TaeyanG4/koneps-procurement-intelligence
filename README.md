# 대한민국 공공조달 인텔리전스 — KONEPS

**한국어** | [English](README.en.md)

[![CI Pipeline](https://github.com/TaeyanG4/koneps-procurement-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/TaeyanG4/koneps-procurement-intelligence/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Format: Parquet](https://img.shields.io/badge/Data%20Format-Partitioned%20Parquet%20(ZSTD)-orange.svg)](https://parquet.apache.org/)

대한민국 **국가종합전자조달시스템(KONEPS / 나라장터)** 공공조달 생태계의 데이터를 체계적으로 수집하고 전처리하는 재현 가능한 데이터 엔지니어링 및 ETL 파이프라인입니다.

본 프로젝트는 머신러닝, 계량경제학 및 데이터 사이언스 연구에 즉시 활용할 수 있는 캐글(Kaggle) 공개용 연구 데이터셋 구축을 목표로 합니다:
> **"South Korea Public Procurement Intelligence — KONEPS"**

---

## 1. 프로젝트 개요

대한민국 정부 및 공공기관은 매년 **100조 원 이상**의 물품, 공사, 용역을 나라장터(KONEPS)를 통해 조달합니다. 공공데이터포털을 통해 방대한 조달 데이터가 개방되어 있으나, 원천 데이터는 다음과 같은 특성으로 인해 실무 분석에 높은 진입 장벽이 존재합니다:
- 기간별 분할 수집 및 중첩된 XML/JSON 스키마 구조
- 방대한 한국 행정 용어 및 표준화되지 않은 컬럼명
- 입찰공고, 개찰결과, 계약내역, 개별 투찰자 데이터의 분절

본 파이프라인은 조달 전 주기를 유기적으로 연결하는 데이터 엔지니어링 프로세스를 제공합니다:

$$\text{입찰공고 (Tender)} \longrightarrow \text{개찰결과 / 투찰사 (Bidders)} \longrightarrow \text{낙찰 (Award)} \longrightarrow \text{계약 (Contract)} \longrightarrow \text{조달업체 (Supplier)} \longrightarrow \text{수요기관 (Agency)}$$

---

## 2. 데이터의 가치 및 분석 활용성

나라장터 공공조달 데이터는 실세계 정형 데이터(Tabular Data) 분석 및 머신러닝 벤치마크로서 매우 높은 학술적·실무적 가치를 지닙니다:

1. **경매 이론 및 가격 결정 메커니즘 분석**:
   - 복수예비가격 추첨 방식 및 사정률(A-값) 분포 실증 분석
   - 낙찰하한율 기준 기업들의 투찰 분포 및 가격 클러스터링 모델링
2. **머신러닝 예측 모델링**:
   - 입찰 조건별 최종 낙찰률(`award_rate`) 및 입찰 경쟁률(`bidder_count`) 사전 예측
   - 개찰 전 유찰(`is_failed_bid`) 위험 사전 탐지 분류 모델
   - 과거 수주 실적과 시장 집중도 기반 기업별 수주 확률 추정
3. **공공 재정 건전성 및 투명성 연구**:
   - 수요기관별 발주 단가 분산, 지역의무공동도급 영향도 분석
   - 특정 품목·산업군별 시장 집중도(HHI 지수) 및 과점화 모니터링

---

## 3. 파이프라인 아키텍처

파이프라인은 데이터 계층 간 명확한 책임 분리(Separation of Concerns)와 장애 복구 멱등성(Idempotency)을 보장합니다:

```
[ 공공데이터포털 API ]                [ 나라장터 개찰결과 투찰보고서 ]
         │                                         │
         ▼                                         ▼
   (속도 제어 요청)                           (CSV / XLS / XLSX)
         │                                         │
         ▼                                         ▼
   data/raw/*.jsonl.gz                     scripts/ingest_bidder_report.py
   (불변 원천 + 매니페스트 관리)                       │
         │                                         ▼
         │                               data/processed/bidder_outcomes/
   scripts/build_dataset.py
         │
         ▼
   data/processed/<dataset>/year=YYYY/month=MM/*.parquet
   (정규화 영문/한글 매핑 + 엄격한 타입 + Zstandard 압축)
         │
         ▼
   scripts/quality_check.py
   (카디널리티 검증, 중복 감사, 이상치 경계 검사)
         │
         ▼
   [ 연구용 정제 테이블 & Kaggle 데이터셋 배포 ]
```

- **`data/raw/`**: 불변(Immutable) 원천 데이터 압축 보관(`*.jsonl.gz`). 수집 구간별 메타데이터와 완료 상태는 `manifest.json`을 통해 원자적으로 추적됩니다.
- **`data/staging/`**: 중간 결합 및 스키마 검증용 임시 영역.
- **`data/processed/`**: 날짜 파티셔닝(`year=YYYY/month=MM/`)이 적용된 고성능 Apache Parquet 저장소.
- **`data/logs/`**: API 인증키 등 민감정보가 자동 마스킹된 실행 로그 보관.

---

## 4. 수집 대상 데이터셋

1. **조달청_나라장터 공공데이터개방표준서비스 (`PubDataOpnStdService`)**:
   - **입찰공고 (`bids`)**: 발주 공고 메타데이터, 배정예산, 추정가격, 입찰 마감일, 참가 자격 요건.
   - **개찰결과 (`awards`)**: 개찰 일시, 낙찰 업체, 낙찰 금액, 낙찰률, 예정가격, 참가 업체 수.
   - **계약내역 (`contracts`)**: 최종 계약 금액, 계약 체결일, 계약 기간, 계약 당사자(수요기관-수주기업).
2. **개찰결과 상세 투찰보고서 (`bidder_outcomes`)**:
   - 나라장터 포털 화면에서 다운로드되는 기업별 상세 투찰 내역(참가 기업명, 사업자등록번호, 투찰 금액, 투찰률, 탈락 사유).

> **라이선스 안내**: 본 데이터는 공공데이터 저작권 가이드라인 및 **공공누리(KOGL) 제1유형: 출처표시** 조건에 따라 자유롭게 이용할 수 있습니다. 상세 내용은 [DATA_SOURCES.md](docs/DATA_SOURCES.md)를 참고하십시오.

---

## 5. 설치 및 환경 설정

지원 Python 버전: **3.11** 또는 **3.12** (권장).

### Windows (PowerShell)
```powershell
# 1. 가상환경 생성 및 활성화
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. 의존성 패키지 설치
pip install -r requirements.txt
pip install -e .
```

### Linux / macOS (Bash)
```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 2. 의존성 패키지 설치
pip install -r requirements.txt
pip install -e .
```

---

## 6. 공공데이터포털 API 키 발급 및 설정

1. [공공데이터포털(data.go.kr)](https://www.data.go.kr/) 회원가입 및 로그인.
2. `조달청_나라장터 공공데이터개방표준서비스` 검색 후 활용신청(자동 즉시 승인).
3. 마이페이지 > 개발계정에서 **일반 인증키(Decoding)** 복사.
4. 프로젝트 루트에 `.env` 파일 생성:

### Windows (PowerShell)
```powershell
Copy-Item .env.example .env
# .env 파일을 열고 발급받은 키를 입력합니다:
# DATA_GO_KR_SERVICE_KEY=your_actual_key_here
```

### Linux / macOS (Bash)
```bash
cp .env.example .env
# .env 파일을 열고 발급받은 키를 입력합니다
```

> **보안 보장**: `.env` 파일은 `.gitignore`에 등록되어 소스코드 저장소에 커밋되지 않습니다. 모든 콘솔 및 파일 로그에서 인증키는 마스킹(`abcd********wxyz`) 처리됩니다.

---

## 7. 단계별 수집 가이드

### 1단계: 1일 스모크 테스트 (Smoke Test)
API 인증키 정상 동작, 네트워크 통신 및 원천 저장을 최소한의 호출로 검증합니다:

**PowerShell:**
```powershell
python scripts/collect_standard.py --dataset bids --start 2026-09-01 --end 2026-09-01 --page-size 100
```
**Bash:**
```bash
python scripts/collect_standard.py --dataset bids --start 2026-09-01 --end 2026-09-01 --page-size 100
```

*호출 없이 파라미터 분할 동작만 점검하려면 `--dry-run` 플래그를 추가하십시오.*

### 2단계: 1개월 수집 (Monthly Benchmark)
단일 월의 입찰, 낙찰, 계약 전체 피드를 수집합니다:

**PowerShell:**
```powershell
python scripts/collect_standard.py --dataset all --start 2026-08-01 --end 2026-08-31 --page-size 500
```
**Bash:**
```bash
python scripts/collect_standard.py --dataset all --start 2026-08-01 --end 2026-08-31 --page-size 500
```

### 3단계: 1년 MVP 수집 (Historical 1-Year Collection)
최근 1년 치 기준 데이터셋을 수집합니다 (예: 2025-09-01 ~ 2026-09-01):

**PowerShell:**
```powershell
python scripts/collect_standard.py --dataset all --start 2025-09-01 --end 2026-09-01 --page-size 500
```
**Bash:**
```bash
python scripts/collect_standard.py --dataset all --start 2025-09-01 --end 2026-09-01 --page-size 500
```

> **수집 재개(Resumability)**: 수집기는 `data/raw/manifest.json`을 기반으로 동작합니다. 일일 할당량 소진 또는 작업 중단 후 동일한 명령어를 다시 실행하면 이미 성공적으로 저장된 구간은 자동으로 건너뛰고 남은 구간부터 이어받습니다.

---

## 8. 개찰결과 투찰보고서 수집 가이드

나라장터 포털 개찰결과 화면에서 다운로드한 업체별 상세 투찰내역 파일(CSV / Excel)을 표준 Parquet으로 인제스트합니다:

**PowerShell:**
```powershell
python scripts/ingest_bidder_report.py path\to\exported_report.xlsx
```
**Bash:**
```bash
python scripts/ingest_bidder_report.py path/to/exported_report.xlsx
```
- 지원 확장자: `.csv` (`utf-8-sig`, `cp949`, `euc-kr` 인코딩 자동 감지), 최신 `.xlsx`, 바이너리 `.xls` (`xlrd` 지원).
- 정규화된 결과는 `data/processed/bidder_outcomes/`에 저장됩니다.

---

## 9. 정규화 및 Parquet 변환

수집된 원천 `.jsonl.gz` 데이터를 엄격한 스키마와 타입을 적용하여 파티셔닝된 Parquet으로 변환합니다:

**PowerShell:**
```powershell
python scripts/build_dataset.py
```
**Bash:**
```bash
python scripts/build_dataset.py
```
생성되는 분석용 파티션 파일:
```
data/processed/bids/year=2026/month=08/*.parquet
data/processed/awards/year=2026/month=08/*.parquet
data/processed/contracts/year=2026/month=08/*.parquet
data/processed/build_report.json
```

---

## 10. 데이터 품질 검증 및 이상치 감사

행 수, 고유 키 중복, 결측치 비율 및 수치 이상치(음수 금액, 1000% 초과 비정상 투찰률 등)를 종합 점검합니다:

**PowerShell:**
```powershell
python scripts/quality_check.py data/processed/**/*.parquet --strict
```
**Bash:**
```bash
python scripts/quality_check.py data/processed/*/*/*.parquet --strict
```

---

## 11. 디렉토리 구조

```
koneps-procurement-intelligence/
├── src/
│   └── koneps_intel/
│       ├── __init__.py           # 패키지 익스포트 및 버전 정의
│       ├── api.py               # 지수 백오프 기반 HTTP 클라이언트 & XML 에러 파싱
│       ├── config.py            # 환경 변수 로드 및 인증키 마스킹
│       ├── endpoints.py         # 공공데이터 개방표준 엔드포인트 정의
│       ├── collector.py         # 수집 오케스트레이션 및 매니페스트 복구
│       ├── storage.py           # 원천 저장소 및 매니페스트 원자적 갱신
│       ├── parsers.py           # 응답 파싱 및 날짜 윈도우 분할 생성기
│       ├── schemas.py           # 표준 컬럼 영문화 매핑 및 제어 어휘
│       ├── normalize.py         # 엄격한 타입 캐스팅 및 Parquet 파티셔닝
│       ├── quality.py           # 품질 지표 프로파일링 및 이상치 탐지
│       └── utils.py             # 구조화 로깅 및 비밀정보 필터링
│
├── scripts/
│   ├── collect_standard.py      # 원천 API 수집 CLI
│   ├── build_dataset.py         # Parquet 정규화 빌드 CLI
│   ├── ingest_bidder_report.py  # 투찰보고서 엑셀/CSV 인제스트 CLI
│   └── quality_check.py         # 데이터 품질 감사 CLI
│
├── data/
│   ├── raw/                     # 불변 원천 압축 파일 (.jsonl.gz)
│   ├── staging/                 # 정규화 임시 검증 디렉토리
│   ├── processed/               # 연/월 파티셔닝된 분석용 Parquet
│   └── logs/                    # 수집 및 정규화 실행 로그
│
├── tests/
│   ├── fixtures/                # 모의 API 응답 및 테스트용 엑셀/XLS 파일
│   ├── test_api.py              # API 재시도, 타임아웃, 예외 처리 테스트
│   ├── test_parsers.py          # 응답 파싱 및 윈도우 생성 테스트
│   ├── test_collector.py        # 매니페스트 무결성 및 수집 재개 테스트
│   ├── test_normalize.py        # 스키마 캐스팅, 불리언/일시 정규화 테스트
│   ├── test_quality.py          # 품질 프로파일링 및 이상치 경계 테스트
│   └── test_text_integrity.py   # 인코딩 깨짐(?/모지바케) 방지 테스트
│
├── docs/
│   ├── DATA_SOURCES.md          # 공공데이터 출처 및 라이선스 가이드
│   ├── DATA_DICTIONARY.md       # 표준 데이터 사전 및 영문/한글 매핑
│   └── ARCHITECTURE.md          # 시스템 아키텍처 및 무결성 원칙
│
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions 자동 테스트 파이프라인
│
├── .env.example                 # 환경 변수 템플릿
├── .gitignore                   # Git 제외 파일 목록 (원천 데이터, 인증키 등)
├── pyproject.toml               # 패키지 빌드 설정 및 의존성 정의
├── requirements.txt             # 고정 의존성 목록
├── PROJECT_STATUS.md            # 개발 로드맵 및 구현 체크리스트
├── README.md                    # 한국어 프로젝트 메인 문서
└── README.en.md                 # 영문 프로젝트 문서
```

---

## 12. 스키마 및 주요 지표

본 파이프라인은 공공데이터포털의 방대한 한글 행정 필드를 분석 친화적인 표준 영문 컬럼으로 매핑합니다:

| 데이터셋 | 기본 키 (Primary Key) | 주요 분석 컬럼 |
| :--- | :--- | :--- |
| **입찰공고 (`bids`)** | `bid_notice_no`, `bid_notice_ord` | `budget_amount`, `estimated_price`, `bid_method`, `contract_method`, `is_re_bid` |
| **개찰결과 (`awards`)** | `bid_notice_no`, `bid_notice_ord` | `award_amount`, `award_rate`, `scheduled_price`, `bidder_count`, `is_failed_bid` |
| **계약내역 (`contracts`)** | `contract_no`, `contract_ord` | `contract_amount`, `contract_date`, `agency_name`, `supplier_name`, `contract_method` |
| **투찰보고서 (`bidder_outcomes`)** | `bid_notice_no`, `business_reg_no` | `bid_amount`, `bid_rate`, `rank`, `is_successful_bid`, `disqualification_reason` |

상세한 데이터 타입, 한글 원천 컬럼명, 결측치 허용 여부는 [DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)를 참고하십시오.

---

## 13. 캐글 데이터셋 패키징 가이드

1. **데이터셋 구성**:
   - `bids.parquet`, `awards.parquet`, `contracts.parquet`, `bidder_outcomes.parquet`로 구성된 스타/스노우플레이크 스키마 제공.
   - 대용량 데이터는 연도별 분할 또는 단일 압축 Parquet(Zstandard)로 패키징.
2. **Kaggle Metadata (`dataset-metadata.json`)**:
   ```json
   {
     "title": "South Korea Public Procurement Intelligence — KONEPS",
     "id": "your-kaggle-username/south-korea-public-procurement-intelligence-koneps",
     "licenses": [{"name": "CC-BY-4.0"}]
   }
   ```
3. **Kaggle CLI 배포**:
   ```bash
   kaggle datasets create -p data/processed/ --public
   ```

---

## 14. 분석 및 머신러닝 활용 아이디어

- **입찰 낙찰률 예측 (Regression)**: 공고 배정예산, 업종 분류, 발주 시기, 수요기관 특성을 피처로 활용한 최종 낙찰률(`award_rate`) 예측.
- **유찰 조기 경보 모델 (Classification)**: 입찰 참가 자격의 까다로움 및 공고 기간을 분석하여 유찰(`is_failed_bid`) 가능성을 사전에 감지.
- **공급기업 수주 성공률 모델링**: 과거 입찰 참여 빈도, 평균 투찰률, 주력 업종을 바탕으로 기업의 낙찰 확률 예측.
- **조달 시장 집중도 및 담합 탐지 연구**:
  - 특정 공공기관 발주 건에서 반복적으로 짝을 이루어 투찰하는 기업 네트워크 분석.
  - 입찰자 간 투찰 가격 분포의 엔트로피 및 의심스러운 균등 투찰 간격 탐지.
  - 허핀달-허쉬만 지수(HHI)를 통한 조달 분야별 독과점 모니터링.

---

## 15. 보안 및 데이터 거버넌스 정책

- **인증키 보안**: 서비스 인증키는 절대 Git에 커밋하지 않으며, 환경 변수(`.env`)로만 관리됩니다.
- **코드 중심 저장소**: 대용량 데이터 파일은 `.gitignore`에 의해 제외되며, 깃허브에는 소스 코드와 설정만 추적됩니다.
- **개인정보 및 식별자 보호**: 공공 데이터에 포함된 대표자명 및 사업자등록번호는 공개 데이터셋 생성 시 필요에 따라 해시(SHA-256) 가명화 처리를 적용합니다.

---

## 16. 구현 및 검증 현황

| 컴포넌트 | 구현 상태 | 검증 내용 |
| :--- | :--- | :--- |
| **API 클라이언트 (`api.py`)** | 구현 완료 | 단위 테스트 및 모의 환경 검증 완료 (일시적 429/500 에러 지수 백오프 재시도, 비재시도 4xx 즉시 실패, 할당량 초과 처리). |
| **매니페스트 관리 (`storage.py`, `collector.py`)** | 구현 완료 | 장애 복구 시나리오 테스트 통과 (원천 카테고리 불일치 감지, 파일 누락/손상 복구, 매니페스트 재구축 Cases A–E). |
| **정규화 및 파티셔닝 (`normalize.py`)** | 구현 완료 | Nullable 불리언(`boolean` dtype), 일시 정규화(`opening_date` $\rightarrow$ `datetime64[ns]`), 연/월 파티셔닝 검증 통과. |
| **투찰보고서 인제스트 (`ingest_bidder_report.py`)** | 구현 완료 | CSV (`utf-8-sig`, `cp949`), 최신 `.xlsx`, 바이너리 `.xls` (`xlrd` 연동) 실제 파일 인제스트 테스트 통과. |
| **데이터 품질 검사 (`quality.py`, `quality_check.py`)** | 구현 완료 | 정상 및 이상치 데이터프레임 프로파일링 및 경계 검사 테스트 통과. |
| **CI 파이프라인 (`ci.yml`)** | 구현 완료 | GitHub Actions 기반 Python 3.11 및 3.12 전 자동 테스트 통과. |
| **실 API 인증 및 1일 스모크 테스트** | 검증 대기 | 사용자의 `DATA_GO_KR_SERVICE_KEY` 설정 후 즉시 실행 가능한 상태. |
| **과거 1년 치 라이브 수집** | 미착수 | 실 API 스모크 테스트 검증 후 단계적 수행 예정. |
| **관계형 마스터 조인 데이터셋 구축** | 계획됨 | 공고 $\rightarrow$ 투찰 $\rightarrow$ 개찰 $\rightarrow$ 계약 릴레이션 결합 테이블 생성 예정. |
| **캐글 연구 데이터셋 v1 배포** | 계획됨 | 데이터 카드 및 베이스라인 탐색적 데이터 분석(EDA) 노트북 공개 예정. |

---

## 17. 로드맵 및 향후 과제

1. **실제 API 1일 스모크 테스트 수행**: 사용자 인증키를 이용한 `bids`, `awards`, `contracts` 실데이터 수집 검증.
2. **1개월 벤치마크 및 1년 MVP 수집**: 최근 1년 치 데이터 안정적 수집 및 원천 저장소 적재.
3. **포털 투찰보고서 데이터 연계**: 주요 입찰공고에 대한 참가 기업 전수 투찰 내역 수집 및 병합.
4. **마스터 데이터셋 구축**: 공고번호 기준 다대다/일대다 관계 정리 및 누수 없는 머신러닝 피처 엔지니어링 파이프라인 완성.
5. **Kaggle 연구 데이터셋 v1 공개**: 국제 데이터 사이언스 커뮤니티를 위한 데이터 카드, 영문 가이드 및 스타터 노트북 제공.
