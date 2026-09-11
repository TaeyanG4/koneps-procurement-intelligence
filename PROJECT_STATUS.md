# Project Status & Roadmap

This document tracks the implementation progress and development milestones for **KONEPS Procurement Intelligence**.

---

## Milestone Checklist

### Core Engineering & Pipeline Setup
- [x] Modular package structure (`src/koneps_intel/`, `scripts/`)
- [x] Resilient API client (`KonepsClient`) with exponential backoff and XML error parsing
- [x] Proper transient error retry on HTTP 429, 500, 502, 503, 504 and network timeouts
- [x] Non-retryable error handling (400, 401, 403, 404, 405) with immediate fast-fail
- [x] API quota exhaustion detection and graceful pipeline termination
- [x] Safe credential handling and zero-secret logging with key masking
- [x] Immutable raw storage in `.jsonl.gz` with atomic writes
- [x] Strict raw storage category validation (`expected_category`) preventing feed contamination
- [x] Manifest tracking (`manifest.json`) with automatic recovery and repair across failure scenarios
- [x] High-performance Parquet normalization with Hive date-partitioning (`year=YYYY/month=MM/`)
- [x] Type casting with nullable boolean (`boolean` dtype) and datetime normalization (`datetime64[ns]`)
- [x] Bidder report ingestion pipeline (`ingest_bidder_report.py`) supporting CSV (`utf-8-sig`, `cp949`), `.xlsx`, and real binary `.xls` (via `xlrd`)
- [x] Data quality and anomaly validation engine (`quality_check.py`)
- [x] Unit and integration test suite passing 100% without requiring live API keys
- [x] Dual-language documentation policy: Korean-first (`README.md`) and English (`README.en.md`)
- [x] Hardened repository privacy policy (local AI assistant, agent instructions, and scratch exclusions in `.gitignore`)
- [x] Truthful dry-run statistics semantics (`dry_run_windows`) without phantom saved windows
- [x] Cautious per-source licensing policy documentation with pre-Kaggle verification checkpoint
- [x] Consistent Python support policy (`requires-python = ">=3.11"`) across configuration, docs, and CI
- [x] GitHub Actions CI workflow for Python 3.11 and 3.12 (`.[dev]`)
- [x] Complete technical documentation (`DATA_SOURCES.md`, `DATA_DICTIONARY.md`, `ARCHITECTURE.md`)


---

### Data Collection & Empirical Validation (Operational Milestones)
- [x] Live API authentication verified with valid `DATA_GO_KR_SERVICE_KEY`
- [x] 1-day live collection smoke test verified (`bids`, `awards`, `contracts`)
- [x] 1-month benchmark dataset collected (2026-08: 2,268,948 raw rows, 2,256,788 Parquet rows across bids, contracts, awards - see `docs/PILOT_2026_08.md`)
- [x] Pilot audit corrected (event-date filtering, period contamination removed, single source of truth `pilot_2026_08_metrics.json`)
- [x] Deduplication grain validated (lossless candidate key with `bidprcAmt` + `bidprcTm` preserving 1,067 distinct multi-lot submissions)
- [x] August-only cross-feed cardinality validated (Tender 1:N Bidder Submissions, 1:0..N Award Outcomes, 1:0..N Contracts, 100% unique `untyCntrctNo`)
- [x] Relational model specification created (`docs/RELATIONAL_MODEL.md` & `docs/RELATIONAL_MODEL.en.md`)
- [x] Relational curated tables implemented on August pilot (`tenders`, `bidder_submissions`, `award_outcomes`, `contracts`, `suppliers`, `agencies`, `bridge`) — 7 tables, 115.67 MiB, all reconciliation gates passed
- [x] 1-year historical MVP collected (2025-09-01 ~ 2026-08-31: 41,225,145 canonical raw rows)
- [x] Historical normalized build audited (38,273,402 fact rows, 1,088 Parquet files, all integrity gates passed)
- [x] Restartable month-by-month relational curation completed (12/12 months passed)
- [x] Privacy-minimized canonical Kaggle release built (7 ZSTD Parquet files, 2,612,589,280 bytes; supplier identity is HMAC `supplier_id` only)
- [x] One-row-per-tender quickstart CSV built and published (470,937 rows, 29 columns, 155,062,563 bytes; no supplier identifiers)
- [x] Source service license re-verified on 2026-09-11 (data.go.kr service page: scope of license unrestricted)
- [ ] Official bidder outcome report export ingested into `data/processed/bidder_outcomes/` (optional enrichment role)
- [ ] Leak-free ML feature tables generated (competition metrics, win rate history, agency price variance)
- [x] Curated research dataset v2 packaged and documented locally (`data/processed/kaggle_release_202509_202608/`)
- [x] Kaggle dataset v2 published (`taeyangg4/koneps-public-procurement-intelligence`): live `ready`, 8 user files, 2,767,651,843 bytes, cover, provenance, license, tags, monthly update frequency, and Usability 10/10 verified
- [x] Baseline EDA starter notebook published and executed successfully on Kaggle (`taeyangg4/koneps-procurement-5-minute-market-overview`, v4 `COMPLETE`), with repaired Korean category mapping and quickstart CSV example
- [x] Kaggle Data Explorer descriptions verified against repository metadata: 8/8 file descriptions and 160/160 column descriptions present and exact on v2
