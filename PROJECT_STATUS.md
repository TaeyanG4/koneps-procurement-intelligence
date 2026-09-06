# Project Status & Roadmap

This document tracks the implementation progress and development milestones for **KONEPS Procurement Intelligence**.

---

## Milestone Checklist

### Core Engineering & Pipeline Setup
- [x] Production repository and modular package structure (`src/koneps_intel/`, `scripts/`)
- [x] Robust, fault-tolerant API client (`KonepsClient`) with exponential backoff and XML error parsing
- [x] Safe credential handling and zero-secret logging
- [x] Immutable raw storage in `.jsonl.gz` with atomic writes
- [x] Completion manifest and resumable collection tracking (`ManifestManager`)
- [x] High-performance Parquet normalization with Hive date-partitioning (`year=YYYY/month=MM/`)
- [x] Bidder report ingestion pipeline (`ingest_bidder_report.py`) with CSV and Excel support
- [x] Data quality and anomaly validation engine (`quality_check.py`)
- [x] Comprehensive mock unit and integration test suite (100% pass rate without live API requirement)
- [x] GitHub Actions CI workflow for Python 3.11 and 3.12
- [x] Complete technical documentation (`DATA_SOURCES.md`, `DATA_DICTIONARY.md`, `ARCHITECTURE.md`)

---

### Data Collection & Empirical Validation (Operational Milestones)
- [ ] Live API authentication verified with valid `DATA_GO_KR_SERVICE_KEY`
- [ ] 1-day live collection smoke test verified (`bids`, `awards`, `contracts`)
- [ ] 1-month benchmark dataset collected
- [ ] 1-year historical MVP collected
- [ ] Official bidder outcome report export ingested into `data/processed/bidder_outcomes/`
- [ ] Empirical key and cardinality validation executed (Tender 1:N Bidder, 1:1 Award, 1:N Contract)
- [ ] Procurement master dataset built without row duplication bugs
- [ ] Leak-free ML feature tables generated (competition metrics, win rate history, agency price variance)
- [ ] Kaggle Gold Dataset v1 packaged, documented, and published with baseline EDA notebook
