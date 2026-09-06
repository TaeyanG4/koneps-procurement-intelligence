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
- [ ] Relational curated tables implemented on August pilot (`tenders`, `bidder_submissions`, `award_outcomes`, `contracts`, `bridge`)
- [ ] 1-year historical MVP collected
- [ ] Official bidder outcome report export ingested into `data/processed/bidder_outcomes/` (optional enrichment role)
- [ ] Leak-free ML feature tables generated (competition metrics, win rate history, agency price variance)
- [ ] Curated research dataset v1 packaged, documented, and published with baseline EDA notebook
