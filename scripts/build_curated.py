#!/usr/bin/env python3
"""CLI script to build relational curated tables from processed Parquet data.

Generates 7 normalized tables:
  1. 01_tenders.parquet
  2. 02_bidder_submissions.parquet
  3. 03_award_outcomes.parquet
  4. 04_contracts.parquet
  5. 05_suppliers.parquet
  6. 06_agencies.parquet
  7. 07_tender_contract_bridge.parquet

Applies strict mathematical reconciliation gates, deterministic surrogate PKs,
HMAC-based pseudonymization for suppliers (without leaking raw business numbers),
and outputs a sanitized aggregate metrics JSON artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is on python path for direct CLI script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from koneps_intel.curate import main

if __name__ == "__main__":
    main()
