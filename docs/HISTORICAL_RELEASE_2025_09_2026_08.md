# KONEPS 12개월 역사 데이터 릴리스 검증 보고서

**한국어** | [English](HISTORICAL_RELEASE_2025_09_2026_08.en.md)

검증 범위: **2025-09-01 ~ 2026-08-31**
검증일: **2026-09-11**

## 1. 릴리스 상태

최근 12개월 KONEPS 공공데이터개방표준서비스의 `bids`, `awards`, `contracts` 수집·정규화·관계형 큐레이션·Kaggle 공개 패키징이 완료되었습니다.

- Canonical raw rows: **41,225,145**
- 정규화 Parquet rows: **38,273,402**
- 월별 관계형 큐레이션: **12/12개월 PASS**
- 최종 공개 파일: **7개 ZSTD Parquet**
- 최종 공개 크기: **2,612,589,280 bytes** (약 2.61 GB)

정규화 fact 행 수는 정확히 다음과 같이 대사됩니다.

`470,937 tenders + 35,907,867 bidder submissions + 1,894,598 contracts = 38,273,402 rows`

`award_outcomes`는 bidder submissions 중 최종 선정 낙찰자만 추출한 부분집합이므로 위 합계에 중복 가산하지 않습니다.

## 2. Kaggle 공개 파일

| 파일 | 그레인 | 행 수 | 컬럼 수 | 크기(bytes) |
| :--- | :--- | ---: | ---: | ---: |
| `01_tenders.parquet` | 입찰공고 + 공고차수 | 470,937 | 32 | 29,781,660 |
| `02_bidder_submissions.parquet` | 개별 투찰 제출 | 35,907,867 | 28 | 2,396,046,821 |
| `03_award_outcomes.parquet` | 최종 선정 낙찰 결과 | 305,995 | 25 | 34,718,596 |
| `04_contracts.parquet` | 통합계약번호 | 1,894,598 | 24 | 134,436,150 |
| `05_suppliers.parquet` | 가명화 공급업체 | 261,474 | 8 | 6,218,548 |
| `06_agencies.parquet` | 공공기관 코드 | 27,214 | 7 | 463,642 |
| `07_tender_contract_bridge.parquet` | 공고-계약 연결 | 637,107 | 7 | 10,923,863 |

파일별 SHA-256 receipt는 `docs/metrics/release_202509_202608.json`에 기록됩니다.

## 3. 무결성 및 재시작성

역사 데이터는 월 단위로 독립 큐레이션되며 각 월마다 PK, raw-to-curated 행 수, FK coverage, forbidden-column, dtype, bridge assertions를 검증합니다. `scripts/build_historical_curated.py`는 완료된 월을 재사용하므로 중단 후 재실행할 수 있습니다.

최종 공개본은 `scripts/build_kaggle_release.py`가 월별 fact 파일을 PyArrow batch로 스트리밍 병합합니다. 따라서 3,590만 건의 bidder submissions를 한 번에 메모리에 적재하지 않습니다. 월별 `int64`/`double` 차이가 있던 계약 금액 필드는 공개 스키마에서 `float64`로 통일하되 원천 값을 변경하지 않습니다.

월별 큐레이션의 `tender_in_scope`는 월 단위 의미를 가지므로 최종 공개본에서는 **12개월 전체 `01_tenders` 키 집합을 기준으로 재계산**합니다. 최종적으로 bidder submissions 32,662,091건, award outcomes 279,463건, bridge 398,392건이 공개 범위 tender와 직접 연결됩니다.

## 4. 프라이버시 정책

Kaggle 공개본의 공급업체 식별자는 전용 비밀키 기반 **HMAC-SHA256** `supplier_id`만 사용합니다.

- 원문 사업자등록번호: **제외**
- 마스킹 사업자등록번호: **제외**
- 투찰사/낙찰사/계약업체 상호명: **제외**
- 공급업체 차원 상호명: **제외**
- 공공기관 코드/기관명: 분석 및 조인 목적으로 유지

동일한 `supplier_id`를 향후 버전에서도 유지하려면 `KONEPS_SUPPLIER_HMAC_KEY`는 최초 공개 이후 변경하지 않아야 합니다.

## 5. 원천 이상치 보존 정책

금액이나 비율의 이상치는 정규화 오류와 원천값 이상을 구분합니다. 원천 KONEPS JSON과 대조된 값은 삭제하거나 0으로 치환하지 않습니다.

- bidder submission 음수 `bid_amount_krw`: **1건**
- contract 음수 `contract_amount_krw`: **10건**
- contract 음수 `total_contract_amount_krw`: **10건**
- selected award의 `award_amount_krw` NULL: **280건**

이 값들은 source anomaly/warning으로 문서화하며 모델링 시 목적에 따라 별도 필터링할 수 있습니다.

## 6. 라이선스 확인

2026-09-11 기준 공공데이터포털의 **조달청_나라장터 공공데이터개방표준서비스** 페이지(수정일 2026-06-29)는 비용 `무료`, 이용허락범위 `제한 없음`으로 표시됩니다.

Source: https://www.data.go.kr/en/data/15023678/standard.do

Kaggle metadata에서는 특정 Creative Commons 조건을 임의로 부여하지 않고 `other`를 사용하며, 데이터 설명에 조달청/공공데이터포털 출처와 원 서비스 이용조건을 명시합니다.

## 7. 재현 명령

```bash
python scripts/build_dataset.py --start 2025-09-01 --end 2026-08-31
python scripts/audit_historical.py --start 2025-09-01 --end 2026-08-31 --raw data/raw --processed data/processed/historical_202509_202608
python scripts/build_historical_curated.py --start 2025-09-01 --end 2026-08-31 --processed data/processed/historical_202509_202608
python scripts/build_kaggle_release.py --start 2025-09-01 --end 2026-08-31
```

최종 로컬 공개본은 `data/processed/kaggle_release_202509_202608/`에 생성됩니다. 2026-09-11 공개 Kaggle v1(`taeyangg4/koneps-public-procurement-intelligence`) 게시를 완료했으며, 서버 상태 `ready`, 7개 원격 파일의 바이트 크기 일치, 커버, 출처, 라이선스, 월별 업데이트 주기를 live readback으로 확인했습니다. 스타터 EDA Notebook(`taeyangg4/koneps-procurement-5-minute-market-overview`) v2도 Kaggle 런타임에서 `COMPLETE`로 실행되었습니다. Data Explorer의 파일/컬럼 설명은 같은 날 live API에서 아직 노출되지 않아 플랫폼 메타데이터 후속 확인 항목으로 별도 추적합니다.
