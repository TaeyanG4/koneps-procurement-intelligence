"""API endpoints and feed definitions for KONEPS standard open data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

BASE_URL = "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService"
DEFAULT_PAGE_SIZE = 500

# API Return Codes
SUCCESS_CODES = {"00", "000", "0"}
NO_DATA_CODES = {"03", "NODATA_ERROR"}
AUTH_CODES = {"20", "30", "31", "SERVICE_KEY_IS_NULL", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}
QUOTA_CODES = {"22", "23", "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}

# Korean Procurement Business Divisions (업무구분)
BUSINESS_DIVISIONS: Dict[str, str] = {
    "1": "goods",         # 물품
    "2": "foreign",       # 외자
    "3": "construction",  # 공사
    "5": "service",       # 용역
}


@dataclass(frozen=True)
class FeedSpec:
    """Specification for a KONEPS open data feed."""
    name: str
    operation: str
    start_param: str
    end_param: str
    date_format: str
    window_days: int | None = None
    monthly: bool = False
    needs_business_division: bool = False


FEEDS: Dict[str, FeedSpec] = {
    "bids": FeedSpec(
        name="bids",
        operation="getDataSetOpnStdBidPblancInfo",
        start_param="bidNtceBgnDt",
        end_param="bidNtceEndDt",
        date_format="%Y%m%d%H%M",
        monthly=True,
    ),
    "awards": FeedSpec(
        name="awards",
        operation="getDataSetOpnStdScsbidInfo",
        start_param="opengBgnDt",
        end_param="opengEndDt",
        date_format="%Y%m%d%H%M",
        window_days=7,
        needs_business_division=True,
    ),
    "contracts": FeedSpec(
        name="contracts",
        operation="getDataSetOpnStdCntrctInfo",
        start_param="cntrctCnclsBgnDate",
        end_param="cntrctCnclsEndDate",
        date_format="%Y%m%d",
        window_days=7,
    ),
}
