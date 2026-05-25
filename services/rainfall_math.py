from __future__ import annotations

import calendar
from datetime import date, datetime

import pandas as pd


def parse_precipitation(value) -> float:
    """Convert NWS-style precipitation values to inches.

    Kalshi-style settlement notes treat trace (T) and missing (M) as 0.00.
    """
    if value is None:
        return 0.0
    text = str(value).strip().upper()
    if text in {"", "T", "M", "NAN", "NONE"}:
        return 0.0
    try:
        return max(float(text), 0.0)
    except ValueError:
        return 0.0


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def days_remaining_in_month(today: date, selected_month: int, selected_year: int) -> int:
    if today.year != selected_year or today.month != selected_month:
        _, end = month_bounds(selected_year, selected_month)
        if today < date(selected_year, selected_month, 1):
            return calendar.monthrange(selected_year, selected_month)[1]
        if today > end:
            return 0
    return calendar.monthrange(selected_year, selected_month)[1] - today.day


def accumulated_rainfall(actuals: pd.DataFrame) -> float:
    if actuals.empty:
        return 0.0
    return float(actuals["precipitation_inches"].apply(parse_precipitation).sum())


def accumulated_today(actuals: pd.DataFrame, today: date) -> float:
    if actuals.empty:
        return 0.0
    dates = pd.to_datetime(actuals["date"]).dt.date
    todays_rows = actuals.loc[dates == today]
    return accumulated_rainfall(todays_rows)


def daily_cumulative_frame(
    actuals: pd.DataFrame,
    forecast_daily: pd.DataFrame,
    selected_year: int,
    selected_month: int,
) -> pd.DataFrame:
    _, month_end = month_bounds(selected_year, selected_month)
    days = list(range(1, month_end.day + 1))
    frame = pd.DataFrame({"day": days})
    frame["actual_daily"] = 0.0
    frame["forecast_daily"] = 0.0

    if not actuals.empty:
        actuals = actuals.copy()
        actuals["date"] = pd.to_datetime(actuals["date"]).dt.date
        actuals["day"] = [d.day for d in actuals["date"]]
        actuals["precipitation_inches"] = actuals["precipitation_inches"].apply(parse_precipitation)
        by_day = actuals.groupby("day")["precipitation_inches"].sum()
        frame["actual_daily"] = frame["day"].map(by_day).fillna(0.0)

    if not forecast_daily.empty:
        forecast_daily = forecast_daily.copy()
        forecast_daily["date"] = pd.to_datetime(forecast_daily["date"]).dt.date
        forecast_daily["day"] = [d.day for d in forecast_daily["date"]]
        forecast_daily["qpf_inches"] = forecast_daily["qpf_inches"].apply(parse_precipitation)
        by_day = forecast_daily.groupby("day")["qpf_inches"].sum()
        frame["forecast_daily"] = frame["day"].map(by_day).fillna(0.0)

    frame["actual_cumulative"] = frame["actual_daily"].cumsum()

    last_actual_day = 0
    if not actuals.empty:
        last_actual_day = int(max(actuals["day"]))

    base_total = frame.loc[frame["day"] <= last_actual_day, "actual_daily"].sum()
    frame["forecast_cumulative"] = None
    running = base_total
    for idx, row in frame.iterrows():
        if row["day"] > last_actual_day:
            running += row["forecast_daily"]
            frame.at[idx, "forecast_cumulative"] = running

    return frame


def recent_daily_volatility(actuals: pd.DataFrame) -> float:
    if actuals.empty or len(actuals) < 2:
        return 0.0
    values = actuals["precipitation_inches"].apply(parse_precipitation)
    return float(values.tail(10).std() or 0.0)
