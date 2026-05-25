from __future__ import annotations

from pathlib import Path

import pandas as pd

from services.rainfall_math import parse_precipitation

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HISTORICAL_CSV = DATA_DIR / "historical_monthly_rainfall.csv"
ACTUALS_CSV = DATA_DIR / "daily_rainfall_actuals.csv"


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


def get_month_to_date_actuals(city: str, station_id: str, selected_year: int, selected_month: int) -> dict:
    """Load month-to-date rainfall actuals.

    TODO: Connect this adapter to the validated NWS Daily Climate Report or
    NOWData flow for each WFO. The final parser should read the first Daily
    Climate Report containing complete monthly data, convert trace T and
    missing M values to 0.00, and avoid overwriting settlement data with later
    revisions.
    """
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
