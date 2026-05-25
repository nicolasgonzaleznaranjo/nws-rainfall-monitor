from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from services.rainfall_math import parse_precipitation

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HISTORICAL_CSV = DATA_DIR / "historical_monthly_rainfall.csv"
ACTUALS_CSV = DATA_DIR / "daily_rainfall_actuals.csv"
NWS_PRODUCTS_URL = "https://api.weather.gov/products/types/CLI/locations/{wfo}"
NWS_TIMEOUT_SECONDS = 12
NWS_HEADERS = {
    "User-Agent": "NWS Rainfall Monitor, local Streamlit app",
    "Accept": "application/geo+json, application/json",
}


def get_historical_monthly_average(city: str, station_id: str, month: int) -> dict:
    if not HISTORICAL_CSV.exists():
        return {"value": 0.0, "source": "Missing local historical CSV"}

    data = pd.read_csv(HISTORICAL_CSV)
    match = data[
        (data["city"] == city)
        & (data["station_id"] == station_id)
        & (data["month"].astype(int) == int(month))
    ]
    if match.empty:
        return {"value": 0.0, "source": "No local historical row found"}

    return {
        "value": parse_precipitation(match.iloc[0]["historical_avg_inches"]),
        "source": "Local fallback CSV",
    }


def get_month_to_date_actuals(
    city: str,
    station_id: str,
    selected_year: int,
    selected_month: int,
    wfo: Optional[str] = None,
) -> dict:
    """Load month-to-date rainfall actuals.

    TODO: Connect this adapter to the validated NWS Daily Climate Report or
    NOWData daily-history flow for each WFO. This MVP first tries the latest
    NWS CLI product for a month-to-date precipitation total, then falls back to
    the local CSV. A final settlement parser should specifically store the
    first Daily Climate Report containing complete monthly data and avoid
    overwriting it with later revisions.
    """
    if wfo:
        live = _get_latest_cli_month_to_date_total(station_id, selected_year, selected_month, wfo)
        if not live.empty:
            return {
                "daily": live,
                "source": "NWS Daily Climate Report MTD total",
                "confidence": "High",
            }

    local = _get_local_actuals(city, station_id, selected_year, selected_month)
    if not local.empty:
        return {
            "daily": local,
            "source": "Local fallback CSV",
            "confidence": "Medium",
        }

    return {
        "daily": pd.DataFrame(columns=["date", "city", "station_id", "precipitation_inches", "source"]),
        "source": "No local actuals found; live climate parser not connected yet",
        "confidence": "Low",
    }


def _get_latest_cli_month_to_date_total(
    station_id: str,
    selected_year: int,
    selected_month: int,
    wfo: str,
) -> pd.DataFrame:
    """Try to read the latest official NWS Daily Climate Report product.

    The NWS product feed gives recent CLI reports by WFO. Product text formats
    vary a little by office, so this parser is intentionally conservative: if
    it cannot confidently find a MONTH TO DATE precipitation value, it returns
    an empty frame and lets the CSV fallback handle the app.
    """
    try:
        listing = requests.get(
            NWS_PRODUCTS_URL.format(wfo=wfo),
            headers=NWS_HEADERS,
            timeout=NWS_TIMEOUT_SECONDS,
        )
        listing.raise_for_status()
        products = listing.json().get("@graph", [])
    except Exception:
        return pd.DataFrame(columns=["date", "city", "station_id", "precipitation_inches", "source"])

    station_products = [
        product for product in products if str(product.get("id", "")).upper().startswith(station_id.upper())
    ]
    candidates = station_products or products[:8]

    for product in candidates[:8]:
        product_url = product.get("@id") or product.get("id")
        if not product_url:
            continue
        text, issued_date = _fetch_product_text(product_url)
        if not text:
            continue
        total = _parse_month_to_date_precipitation(text)
        if total is None:
            continue

        report_date = issued_date or date.today()
        if report_date.year != selected_year or report_date.month != selected_month:
            continue

        return pd.DataFrame(
            [
                {
                    "date": report_date.isoformat(),
                    "city": "",
                    "station_id": station_id,
                    "precipitation_inches": total,
                    "source": "NWS Daily Climate Report MTD total",
                }
            ]
        )

    return pd.DataFrame(columns=["date", "city", "station_id", "precipitation_inches", "source"])


def _fetch_product_text(product_url: str) -> tuple[str, Optional[date]]:
    try:
        response = requests.get(product_url, headers=NWS_HEADERS, timeout=NWS_TIMEOUT_SECONDS)
        response.raise_for_status()
        properties = response.json().get("properties", {})
        issued = properties.get("issuanceTime") or properties.get("issued")
        issued_date = None
        if issued:
            issued_date = datetime.fromisoformat(issued.replace("Z", "+00:00")).date()
        return properties.get("productText", ""), issued_date
    except Exception:
        return "", None


def _parse_month_to_date_precipitation(product_text: str) -> Optional[float]:
    patterns = [
        r"MONTH TO DATE\s+([0-9.]+|T|M)\b",
        r"MONTH\s+TO\s+DATE\s+([0-9.]+|T|M)\b",
    ]
    upper_text = product_text.upper()
    for pattern in patterns:
        match = re.search(pattern, upper_text)
        if match:
            return parse_precipitation(match.group(1))
    return None


def _get_local_actuals(city: str, station_id: str, selected_year: int, selected_month: int) -> pd.DataFrame:
    if not ACTUALS_CSV.exists():
        return pd.DataFrame(columns=["date", "city", "station_id", "precipitation_inches", "source"])

    data = pd.read_csv(ACTUALS_CSV)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"])
    match = data[
        (data["city"] == city)
        & (data["station_id"] == station_id)
        & (data["date"].dt.year == selected_year)
        & (data["date"].dt.month == selected_month)
    ].copy()
    if match.empty:
        return pd.DataFrame(columns=["date", "city", "station_id", "precipitation_inches", "source"])

    match["date"] = match["date"].dt.date.astype(str)
    match["precipitation_inches"] = match["precipitation_inches"].apply(parse_precipitation)
    return match.sort_values("date")
