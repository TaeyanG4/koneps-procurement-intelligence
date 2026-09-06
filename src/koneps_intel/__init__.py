"""KONEPS Procurement Intelligence package.

Provides modular tools for data collection, normalization, quality validation,
and feature engineering for South Korea's KONEPS public procurement data.
"""

__version__ = "0.1.1"

from koneps_intel.api import (
    AuthenticationError,
    KonepsApiError,
    KonepsClient,
    PermanentApiError,
    QuotaExceededError,
    TransientApiError,
)
from koneps_intel.collector import Collector
from koneps_intel.endpoints import BUSINESS_DIVISIONS, FEEDS, FeedSpec
from koneps_intel.privacy import generate_supplier_id
from koneps_intel.quality import profile_dataframe, run_quality_checks
from koneps_intel.storage import ManifestManager, RawStorage

__all__ = [
    "__version__",
    "generate_supplier_id",
    "KonepsClient",
    "KonepsApiError",
    "AuthenticationError",
    "QuotaExceededError",
    "PermanentApiError",
    "TransientApiError",
    "Collector",
    "FEEDS",
    "FeedSpec",
    "BUSINESS_DIVISIONS",
    "RawStorage",
    "ManifestManager",
    "run_quality_checks",
    "profile_dataframe",
]
