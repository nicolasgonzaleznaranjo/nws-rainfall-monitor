from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Tuple

import pandas as pd
import requests

from services.rainfall_math import month_bounds, parse_precipitation

USER_AGENT = "NWS Rainfall Monitor, local Streamlit app"
TIMEOUT_SECONDS = 12


def _headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json, application/json",
    }


def _get_json(url: str) -> dict:
    response = requests.get(url, headers=_headers(), timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def get_gridpoint_metadata(latitude: float, longitude: float) -> dict:
    url = f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}"
    return _get_json(url)


def get_forecast_grid_data(city_config: dict) -> Tuple[Optional[dict], Optional[str]]:
    """Return NWS gridpoint forecast data, or an error message.

    Some gridpoint offices publish QPF values more completely than others.
    The app treats missing QPF as a low-confidence forecast rather than a
    crash-worthy failure.
    """
    try:
        metadata = get_gridpoint_metadata(city_config["latitude"], city_config["longitude"])
        grid_url = metadata["properties"]["forecastGridData"]
        return _get_json(grid_url), None
    except Exception as exc:  # noqa: BLE001 - user-facing app should degrade gracefully
        return None, str(exc)


def _period_to_daily_qpf(periods: list[dict], selected_year: int, selected_month: int) -> pd.DataFrame:
    _, month_end = month_bounds(selected_year, selected_month)
    rows = []
    for period in periods:
        valid_time = period.get("validTime", "")
        value = period.get("value")
        if not valid_time or value is None:
            continue
        start_text = valid_time.split("/")[0]
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00")).date()
        if start.year == selected_year and start.month == selected_month and start <= month_end:
            # NWS quantitativePrecipitation values are millimeters.
            rows.append(
                {
                    "date": start.isoformat(),
                    "qpf_inches": parse_precipitation(value) / 25.4,
                    "source": "NWS gridpoint quantitativePrecipitation",
                }
            )
    if not rows:
        return pd.DataFrame(columns=["date", "qpf_inches", "source"])
    return pd.DataFrame(rows).groupby("date", as_index=False).agg(
        qpf_inches=("qpf_inches", "sum"),
        source=("source", "first"),
    )


def get_forecast_rainfall(city_config: dict, selected_year: int, selected_month: int) -> dict:
    grid_data, error = get_forecast_grid_data(city_config)
    if not grid_data:
        return {
            "daily": pd.DataFrame(columns=["date", "qpf_inches", "source"]),
            "total_inches": 0.0,
            "confidence": "Low",
            "source": f"NWS forecast unavailable: {error}",
        }

    qpf_periods = (
        grid_data.get("properties", {})
        .get("quantitativePrecipitation", {})
        .get("values", [])
    )
    daily = _period_to_daily_qpf(qpf_periods, selected_year, selected_month)
    total = float(daily["qpf_inches"].sum()) if not daily.empty else 0.0

    if total > 0:
        return {
            "daily": daily,
            "total_inches": total,
            "confidence": "Medium",
            "source": "NWS gridpoint quantitativePrecipitation",
        }

    pop_periods = (
        grid_data.get("properties", {})
        .get("probabilityOfPrecipitation", {})
        .get("values", [])
    )
    pop_rows = []
    for period in pop_periods:
        value = period.get("value")
        valid_time = period.get("validTime", "")
        if value is None or not valid_time:
            continue
        start = datetime.fromisoformat(valid_time.split("/")[0].replace("Z", "+00:00")).date()
        if start.year == selected_year and start.month == selected_month:
            # Conservative placeholder: probability-only forecasts do not give
            # rainfall amount. This lets the chart show a tiny low-confidence
            # estimate while clearly marking the source as incomplete.
            pop_rows.append(
                {
                    "date": start.isoformat(),
                    "qpf_inches": max(float(value), 0.0) / 100 * 0.03,
                    "source": "NWS probabilityOfPrecipitation fallback",
                }
            )

    daily = pd.DataFrame(pop_rows)
    if not daily.empty:
        daily = daily.groupby("date", as_index=False).agg(
            qpf_inches=("qpf_inches", "sum"),
            source=("source", "first"),
        )

    return {
        "daily": daily if not daily.empty else pd.DataFrame(columns=["date", "qpf_inches", "source"]),
        "total_inches": float(daily["qpf_inches"].sum()) if not daily.empty else 0.0,
        "confidence": "Low",
        "source": "NWS probability-only fallback; QPF unavailable or incomplete",
    }
