from __future__ import annotations

import calendar
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
except ModuleNotFoundError:
    go = None

from config.cities import get_city_config, get_city_names
from services.climate_reports import get_historical_monthly_average, get_month_to_date_actuals
from services.nws_api import get_forecast_rainfall
from services.probability_model import (
    estimate_probability_above_threshold,
    recommendation_from_probability,
)
from services.rainfall_math import (
    accumulated_rainfall,
    accumulated_today,
    daily_cumulative_frame,
    days_remaining_in_month,
    recent_daily_volatility,
)

st.set_page_config(page_title="NWS Rainfall Monitor", layout="wide")


MONTHS = list(calendar.month_name)[1:]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #080B10;
            color: #F4F7FB;
        }
        [data-testid="stHeader"] { background: rgba(8, 11, 16, 0.84); }
        .block-container {
            max-width: 1280px;
            padding-top: 2.2rem;
            padding-bottom: 3rem;
        }
        h1 {
            color: #FFFFFF;
            font-size: clamp(2.4rem, 6vw, 4.8rem) !important;
            line-height: 0.95 !important;
            font-weight: 900 !important;
            letter-spacing: 0 !important;
            margin-bottom: 0.25rem !important;
        }
        .subtitle {
            color: #A8B1C1;
            font-size: 1.05rem;
            margin-bottom: 1.35rem;
        }
        .station-line {
            color: #CCD5E3;
            background: #101722;
            border: 1px solid #1D2938;
            border-radius: 8px;
            padding: 0.85rem 1rem;
            margin: 0.7rem 0 1rem;
        }
        .kpi-card {
            background: linear-gradient(180deg, #121925 0%, #0D131D 100%);
            border: 1px solid #223047;
            border-radius: 8px;
            padding: 1rem 1.05rem;
            min-height: 118px;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.24);
        }
        .kpi-label {
            color: #8F9BAD;
            font-size: 0.78rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.04rem;
            margin-bottom: 0.55rem;
        }
        .kpi-value {
            color: #FFFFFF;
            font-size: 2rem;
            font-weight: 850;
            line-height: 1.05;
        }
        .kpi-sub {
            color: #9EABB9;
            font-size: 0.86rem;
            margin-top: 0.5rem;
        }
        div[role="radiogroup"] {
            gap: 0.45rem;
        }
        div[role="radiogroup"] label {
            background: #101722;
            border: 1px solid #263246;
            border-radius: 999px;
            padding: 0.38rem 0.78rem;
            color: #D6DDE8;
            min-height: 38px;
        }
        div[role="radiogroup"] label:has(input:checked) {
            background: #D92525;
            border-color: #F04444;
            color: white;
        }
        div[role="radiogroup"] label p {
            font-size: 0.9rem;
            font-weight: 750;
        }
        .stButton > button {
            background: #D92525;
            color: white;
            border: 1px solid #F04444;
            border-radius: 999px;
            font-weight: 800;
        }
        .stButton > button:hover {
            background: #F04444;
            color: white;
            border-color: #FF6969;
        }
        section[data-testid="stSidebar"] {
            background: #0B1018;
        }
        .callout {
            background: #101722;
            border: 1px solid #253147;
            border-radius: 8px;
            padding: 1rem;
            color: #D9E1ED;
        }
        .warning {
            color: #F6C56B;
            font-weight: 750;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, sub: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=900, show_spinner=False)
def cached_forecast(city_config: dict, selected_year: int, selected_month: int) -> dict:
    return get_forecast_rainfall(city_config, selected_year, selected_month)


def threshold_selector() -> float:
    selected = st.radio(
        "Kalshi-style threshold",
        ["Above 1 inch", "Above 2 inches", "Above 3 inches", "Above custom threshold"],
        horizontal=True,
    )
    if selected == "Above custom threshold":
        return float(st.number_input("Custom threshold in inches", min_value=0.01, value=4.0, step=0.25))
    return float(selected.split()[1])


def make_chart(frame: pd.DataFrame, selected_threshold: float, today_day: int):
    if go is None:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame["day"],
            y=frame["actual_cumulative"],
            mode="lines+markers",
            name="Actual accumulated",
            line=dict(color="#F04444", width=4),
            marker=dict(size=5),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["day"],
            y=frame["forecast_cumulative"],
            mode="lines+markers",
            name="Forecast projection",
            line=dict(color="#7DD3FC", width=3, dash="dash"),
            marker=dict(size=5),
        )
    )
    for threshold in sorted({1.0, 2.0, 3.0, float(selected_threshold)}):
        fig.add_hline(
            y=threshold,
            line_dash="dot",
            line_color="#AAB4C3" if threshold != selected_threshold else "#F6C56B",
            annotation_text=f"{threshold:g} in",
            annotation_position="top left",
        )
    fig.add_vline(
        x=today_day,
        line_color="#E5E7EB",
        line_width=1,
        line_dash="dash",
        annotation_text="Today",
        annotation_position="top",
    )
    fig.update_layout(
        height=430,
        paper_bgcolor="#080B10",
        plot_bgcolor="#0D131D",
        font=dict(color="#DDE5F0"),
        margin=dict(l=30, r=25, t=28, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(title="Day of month", gridcolor="#1F2937", zeroline=False),
        yaxis=dict(title="Rainfall inches", gridcolor="#1F2937", zeroline=False),
    )
    return fig


def main() -> None:
    inject_css()
    st.title("NWS Rainfall Monitor")
    st.markdown(
        '<div class="subtitle">Fast rainfall monitor using official NWS station forecast + live station observation history.</div>',
        unsafe_allow_html=True,
    )

    city = st.radio("City", get_city_names(), index=get_city_names().index("Seattle/Tacoma"), horizontal=True)
    month_name = st.radio("Month", MONTHS, index=datetime.now().month - 1, horizontal=True)
    selected_month = MONTHS.index(month_name) + 1
    selected_year = datetime.now().year

    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    city_config = get_city_config(city)
    local_now = datetime.now(ZoneInfo(city_config["timezone"]))
    today = local_now.date()
    today_day = today.day if today.month == selected_month and today.year == selected_year else 1

    st.markdown(
        f"""
        <div class="station-line">
            <strong>{city_config["location"]}</strong> &middot; Climate product {city_config["station_id"]} &middot;
            Station {city_config["observation_station"]} &middot; WFO {city_config["wfo"]} &middot;
            Local time {local_now.strftime("%b %-d, %Y %-I:%M %p")} &middot; Kalshi mapping {city_config["kalshi_market"]}
        </div>
        """,
        unsafe_allow_html=True,
    )

    historical = get_historical_monthly_average(city, city_config["station_id"], selected_month)
    actuals_result = get_month_to_date_actuals(city, city_config["station_id"], selected_year, selected_month)
    forecast = cached_forecast(city_config, selected_year, selected_month)

    actuals = actuals_result["daily"]
    historical_avg = historical["value"]
    accumulated = accumulated_rainfall(actuals)
    today_total = accumulated_today(actuals, today)
    forecast_remaining = forecast["total_inches"]
    projected_total = accumulated + forecast_remaining
    days_remaining = days_remaining_in_month(today, selected_month, selected_year)

    threshold = threshold_selector()
    probability_result = estimate_probability_above_threshold(
        threshold=threshold,
        accumulated=accumulated,
        forecast_remaining=forecast_remaining,
        historical_month_avg=historical_avg,
        days_remaining=days_remaining,
        forecast_confidence=forecast["confidence"],
    )
    recommendation = recommendation_from_probability(
        probability_result["probability"],
        probability_result["confidence"],
    )
    buffer = projected_total - threshold

    kpi_cols = st.columns(6)
    with kpi_cols[0]:
        kpi_card("Historical Month Rainfall", f'{historical_avg:.2f}"', historical["source"])
    with kpi_cols[1]:
        kpi_card("Accumulated Month Rainfall", f'{accumulated:.2f}"', actuals_result["source"])
    with kpi_cols[2]:
        kpi_card("Forecast Month Rainfall", f'{forecast_remaining:.2f}"', forecast["confidence"])
    with kpi_cols[3]:
        kpi_card("Projected Month Rainfall", f'{projected_total:.2f}"', f'Buffer {buffer:+.2f}"')
    with kpi_cols[4]:
        kpi_card("Accumulated Today", f'{today_total:.2f}"', "Trace and missing count as 0.00")
    with kpi_cols[5]:
        kpi_card("Probability of Occurrence", f'{probability_result["probability"]:.0%}', probability_result["confidence"])

    st.markdown("### Threshold View")
    trade_cols = st.columns([1.1, 1.1, 1.1, 2.7])
    with trade_cols[0]:
        kpi_card("Selected Threshold", f'Above {threshold:g}"', "Strictly greater than")
    with trade_cols[1]:
        kpi_card("Recommendation", recommendation, f'Data confidence: {probability_result["confidence"]}')
    with trade_cols[2]:
        kpi_card("Recent Volatility", f'{recent_daily_volatility(actuals):.2f}"', "Last available local rows")
    with trade_cols[3]:
        st.markdown(
            f"""
            <div class="callout">
                <strong>Model note:</strong> {probability_result["explanation"]}<br>
                <span class="warning">Forecast source:</span> {forecast["source"]}
            </div>
            """,
            unsafe_allow_html=True,
        )

    chart_frame = daily_cumulative_frame(actuals, forecast["daily"], selected_year, selected_month)
    chart = make_chart(chart_frame, threshold, today_day)
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True)
    else:
        st.warning(
            "Plotly is not installed, so this deployment is showing a simple fallback chart. "
            "Add plotly to requirements.txt and redeploy to see the full threshold chart."
        )
        fallback_chart = chart_frame.set_index("day")[["actual_cumulative", "forecast_cumulative"]]
        st.line_chart(fallback_chart)

    with st.expander("Market Rules"):
        st.markdown(
            """
            - Monthly total precipitation is measured in inches.
            - The official NWS Daily Climate Report is determinative.
            - The first report containing full-month data controls.
            - Trace `T` counts as `0.00`.
            - Missing `M` counts as `0.00`.
            - Later revisions do not count for this monitor's settlement view.
            - Above means strictly greater than the selected threshold.

            **Warning:** This monitor is decision-support only. Final settlement depends on the official Kalshi market rules and NWS report.
            """
        )


if __name__ == "__main__":
    main()
