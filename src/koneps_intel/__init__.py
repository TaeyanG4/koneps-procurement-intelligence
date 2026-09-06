"""KONEPS Procurement Intelligence package.

Provides modular tools for data collection, normalization, quality validation,
and feature engineering for South Korea's KONEPS public procurement data.
"""

__version__ = "0.1.0"

from koneps_intel.api import KonepsClient, KonepsApiError, AuthenticationError, QuotaExceededError
from koneps_intel.collector import Collector
from koneps_intel.endpoints import FEEDS, FeedSpec, BUSINESS_DIVISIONS
from koneps_intel.storage import RawStorage, ManifestManager
from koneps_intel.quality import run_quality_checks, profile_dataframe

__all__ = [
    "__version__",
    "KonepsClient",
    "KonepsApiError",
    "AuthenticationError",
    "QuotaExceededError",
    "Collector",
    "FEEDS",
    "FeedSpec",
    "BUSINESS_DIVISIONS",
    "RawStorage",
    "ManifestManager",
    "run_quality_checks",
    "profile_dataframe",
]
