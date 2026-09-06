# South Korea Public Procurement Intelligence ? KONEPS

[![CI Pipeline](https://github.com/TaeyanG4/koneps-procurement-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/TaeyanG4/koneps-procurement-intelligence/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Format: Parquet](https://img.shields.io/badge/Data%20Format-Partitioned%20Parquet%20(ZSTD)-orange.svg)](https://parquet.apache.org/)

Production-grade, reproducible data collection and ETL pipeline for South Korea's **KONEPS** (Korea ON-line E-Procurement System / ??? ????) public procurement ecosystem.

Designed to prepare a publication-ready, machine-learning-friendly research dataset titled:
> **"South Korea Public Procurement Intelligence ? KONEPS"**

---

## 1. Project Purpose

Every year, the South Korean government procures over **$100 billion+ USD** in goods, construction works, and services through KONEPS. Despite the vast transparency of this open data, the raw government feeds are difficult for international data scientists to analyze due to:
- Complex temporal chunking and nested XML/JSON schemas.
- Monolithic Korean administrative column names.
- Fragmented records across separate bidding, award, and contract feeds.

This repository provides an automated, resumable data engineering pipeline connecting the full procurement lifecycle:

$$\text{Tender Notice} \longrightarrow \text{Bidders / Bid Submissions} \longrightarrow \text{Award / Selection} \longrightarrow \text{Contract} \longrightarrow \text{Supplier} \longrightarrow \text{Procuring Agency}$$

---

## 2. Why KONEPS Data Matters for Data Science & ML

The KONEPS dataset is an exceptional benchmark for real-world tabular data science, econometrics, and machine learning:
1. **Auction Theory & Bid Distribution**: Study how bid prices cluster near expected prices, examine bidding floor dynamics, and detect statistical anomalies.
2. **Predictive Modeling**:
   - Predict winning bid rates (`award_rate`) and competition density (`bidder_count`).
   - Identify tender failure risks (`is_failed_bid`) before bid opening.
   - Forecast supplier win probability conditioned on historical win rates and market concentration.
3. **Public Spending Transparency**: Measure agency-level price variance, regional joint-venture effects, and market concentration (HHI index).

---

## 3. Pipeline Architecture

The pipeline enforces strict separation of concerns across data layers:

```
[ data.go.kr API ]                [ Official Bidder Report ]
         ?                                    ?
         ?                                    ?
  (Paced Requests)                   (CSV / XLS / XLSX)
         ?                                    ?
         ?                                    ?
  data/raw/*.jsonl.gz                scripts/ingest_bidder_report.py
  (Immutable Raw + Manifest)                  ?
         ?                                    ?
         ?                          data/processed/bidder_outcomes/
  scripts/build_dataset.py
         ?
         ?
  data/processed/<dataset>/year=YYYY/month=MM/*.parquet
  (Canonical English + Korean Columns + Strict Types)
         ?
         ?
  scripts/quality_check.py
  (Cardinality Inspection, Duplicate Auditing, Anomaly Bounds)
         ?
         ?
  [ ML-Ready Curated Tables & Kaggle Gold Publication ]
```

- **`data/raw/`**: Immutable, compressed JSONL archives (`*.jsonl.gz`) tracking window metadata and completion status in `manifest.json`.
- **`data/staging/`**: Intermediate scratch files for join validation.
- **`data/processed/`**: Partitioned, type-safe Parquet files with Zstandard compression.
- **`data/logs/`**: Detailed run logs with automatic secret sanitization.

---

## 4. Primary Data Sources

1. **KONEPS Public Data Open Standard Service (`PubDataOpnStdService`)**:
   - **Tenders (`bids`)**: Announcement metadata, budgets, deadlines, and procurement methods.
   - **Awards (`awards`)**: Opening ranks, winning bids, winning suppliers, and scheduled prices.
   - **Contracts (`contracts`)**: Final contracted values, execution dates, and contracting parties.
2. **Official Bidder Outcome Report Export (`bidder_outcomes`)**:
   - Official portal export providing comprehensive company-level submissions (all bidders, submitted amounts, bid rates, and disqualification reasons).

---

## 5. Installation

Recommended Python version: **3.11** or **3.12**.

### Windows (PowerShell)
```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
pip install -e .
```

### Linux / macOS (Bash)
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -e .
```

---

## 6. API Key Setup

1. Register an account on [data.go.kr](https://www.data.go.kr/).
2. Apply for `???_???? ????????????` (Standard Open Data Service, automatic instant approval).
3. Copy your **decoding service key** (?? ??? - Decoding).
4. Create a local `.env` file from `.env.example`:

### Windows (PowerShell)
```powershell
Copy-Item .env.example .env
# Edit .env and paste your key:
# DATA_GO_KR_SERVICE_KEY=your_actual_key_here
```

### Linux / macOS (Bash)
```bash
cp .env.example .env
# Edit .env and paste your key
```

> **Security Guarantee**: `.env` is strictly ignored by Git. Keys are masked in all console logs (e.g. `abcd********wxyz`) and stripped from error traces.

---

## 7. Step-by-Step Collection Guide

### Step 1: 1-Day API Smoke Test
Verify credentials, endpoint connectivity, and raw storage without consuming excessive API quota:

**PowerShell:**
```powershell
python scripts/collect_standard.py --dataset bids --start 2026-09-01 --end 2026-09-01 --page-size 100
```
**Bash:**
```bash
python scripts/collect_standard.py --dataset bids --start 2026-09-01 --end 2026-09-01 --page-size 100
```

### Step 2: 1-Month Collection
Collect all feeds for a recent single month:

**PowerShell:**
```powershell
python scripts/collect_standard.py --dataset all --start 2026-08-01 --end 2026-08-31 --page-size 500
```
**Bash:**
```bash
python scripts/collect_standard.py --dataset all --start 2026-08-01 --end 2026-08-31 --page-size 500
```

### Step 3: 1-Year Historical MVP Collection
Collect the initial target historical range (e.g. 2025-09-01 to 2026-09-01):

**PowerShell:**
```powershell
python scripts/collect_standard.py --dataset all --start 2025-09-01 --end 2026-09-01 --page-size 500
```
**Bash:**
```bash
python scripts/collect_standard.py --dataset all --start 2025-09-01 --end 2026-09-01 --page-size 500
```

> **Resumability**: The collector uses `data/raw/manifest.json`. If a job is stopped or daily quotas are reached, re-running the exact same command skips already-completed chunks.

---

## 8. Bidder Report Ingestion

To ingest the official bidder export containing company-level bid amounts and rankings:

**PowerShell:**
```powershell
python scripts/ingest_bidder_report.py path\to\exported_report.xlsx
```
**Bash:**
```bash
python scripts/ingest_bidder_report.py path/to/exported_report.xlsx
```
Supports `.csv` (auto-detecting `utf-8-sig`, `cp949`, `euc-kr`), `.xlsx`, and `.xls`.

---

## 9. Build Partitioned Parquet

Convert raw `.jsonl.gz` files into typed, partitioned Parquet datasets:

**PowerShell:**
```powershell
python scripts/build_dataset.py
```
**Bash:**
```bash
python scripts/build_dataset.py
```
Outputs partitioned analytical files:
```
data/processed/bids/year=2026/month=08/*.parquet
data/processed/awards/year=2026/month=08/*.parquet
data/processed/contracts/year=2026/month=08/*.parquet
data/processed/build_report.json
```

---

## 10. Quality Checks & Anomaly Audits

Run automated profiling to check row counts, duplicate keys, null ratios, and numeric anomalies (such as negative prices or impossible bid rates):

**PowerShell:**
```powershell
python scripts/quality_check.py data/processed/**/*.parquet --strict
```
**Bash:**
```bash
python scripts/quality_check.py data/processed/*/*/*.parquet --strict
```

---

## 11. Directory Structure

```
koneps-procurement-intelligence/
??? src/
?   ??? koneps_intel/
?       ??? __init__.py           # Package exports & version
?       ??? api.py               # Resilient HTTP client & retry logic
?       ??? config.py            # Environment config & key redaction
?       ??? endpoints.py         # Feed definitions & API parameters
?       ??? collector.py         # Collection orchestrator
?       ??? storage.py           # Raw storage & manifest tracking
?       ??? parsers.py           # Response extractors & window generators
?       ??? schemas.py           # Column aliases & controlled vocabularies
?       ??? normalize.py         # Type casting & Parquet conversion
?       ??? quality.py           # Quality checks & anomaly detection
?       ??? utils.py             # Structured logging & secret filtering
?
??? scripts/
?   ??? collect_standard.py      # Raw collection CLI
?   ??? build_dataset.py         # Parquet normalization CLI
?   ??? ingest_bidder_report.py  # Bidder report ingestion CLI
?   ??? quality_check.py         # Quality profiling CLI
?
??? data/
?   ??? raw/                     # Raw immutable .jsonl.gz files
?   ??? staging/                 # Intermediate processing scratchpad
?   ??? processed/               # Partitioned Parquet datasets
?   ??? logs/                    # Pipeline execution logs
?
??? tests/
?   ??? fixtures/                # Mock API responses and sample files
?   ??? test_api.py              # API client & error handling tests
?   ??? test_parsers.py          # Response & window parsing tests
?   ??? test_collector.py        # Collection & resume logic tests
?   ??? test_normalize.py        # Schema casting & Parquet tests
?   ??? test_quality.py          # Quality profiling & anomaly tests
?
??? docs/
?   ??? DATA_SOURCES.md          # Data sources & licensing documentation
?   ??? DATA_DICTIONARY.md       # Canonical schemas & field descriptions
?   ??? ARCHITECTURE.md          # System architecture & design principles
?
??? .github/
?   ??? workflows/
?       ??? ci.yml               # Automated GitHub CI testing workflow
?
??? .env.example                 # Template for environment credentials
??? .gitignore                   # Exclusions for secrets, caches, and datasets
??? pyproject.toml               # Package build configuration & pytest options
??? requirements.txt             # Locked dependencies
??? PROJECT_STATUS.md            # Implementation roadmap and status
??? README.md                    # Project documentation
```

---

## 12. Security & Data Policy

- **No Secrets in Git**: Service keys are never committed or logged in plain text.
- **Code Only in GitHub**: Collected procurement datasets are excluded from Git (`.gitignore`) and will be distributed via Kaggle Datasets.
- **Privacy & Business Numbers**: Before publishing public ML tables, business registration numbers will be assessed for pseudonymization.

---

## 13. Kaggle Publication Roadmap

- [x] Phase 1: Modular data engineering pipeline & test suite.
- [ ] Phase 2: Live collection of 1-year historical baseline.
- [ ] Phase 3: Empirical cardinality verification (Tender 1:N Bidder).
- [ ] Phase 4: Leak-free tabular feature engineering for machine learning.
- [ ] Phase 5: Publication of **"South Korea Public Procurement Intelligence ? KONEPS"** on Kaggle with baseline EDA and prediction notebooks.
