from __future__ import annotations

import calendar
import html
from datetime import date, datetime
from typing import Optional
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
from services.rainfall_math import (
    accumulated_rainfall,
    accumulated_today,
    daily_cumulative_frame,
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
        [data-testid="stHeader"] {
            background: rgba(8, 11, 16, 0.86);
        }
        .block-container {
            max-width: 1280px;
            padding: 2.2rem 1.35rem 3rem;
        }
        h1 {
            color: #FFFFFF;
            font-size: clamp(2.35rem, 6vw, 4.8rem) !important;
            line-height: 0.96 !important;
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
        .kpi-grid {
            display: grid;
            gap: 1rem;
            margin: 1rem 0 1.25rem;
        }
        .kpi-grid {
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        }
        .kpi-card {
            background: linear-gradient(180deg, #121925 0%, #0D131D 100%);
            border: 1px solid #223047;
            border-radius: 8px;
            padding: 1rem 1.05rem;
            min-height: 118px;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.24);
        }
        .kpi-card.accent-red {
            border-color: rgba(255, 75, 75, 0.7);
            box-shadow: 0 18px 45px rgba(255, 75, 75, 0.08);
        }
        .kpi-card.accent-blue {
            border-color: rgba(98, 199, 255, 0.7);
            box-shadow: 0 18px 45px rgba(98, 199, 255, 0.08);
        }
        .kpi-card.accent-gray {
            border-color: rgba(154, 166, 184, 0.55);
        }
        .kpi-card.accent-red .kpi-value {
            color: #FF5B5B;
        }
        .kpi-card.accent-blue .kpi-value {
            color: #62C7FF;
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
        .section-title {
            color: #F8FAFC;
            font-size: 1.55rem;
            font-weight: 850;
            margin: 1.15rem 0 0.35rem;
        }
        .source-note {
            color: #A8B1C1;
            font-size: 0.92rem;
            margin: -0.2rem 0 1rem;
        }
        .legend-note {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            color: #B8C2D2;
            font-size: 0.9rem;
            margin: 0.25rem 0 0.85rem;
        }
        .legend-pill {
            background: #101722;
            border: 1px solid #263246;
            border-radius: 999px;
            padding: 0.28rem 0.62rem;
        }
        .dot-red, .dot-blue, .dot-gray {
            display: inline-block;
            width: 9px;
            height: 9px;
            border-radius: 999px;
            margin-right: 0.35rem;
        }
        .dot-red { background: #FF4B4B; }
        .dot-blue { background: #62C7FF; }
        .dot-gray { background: #9AA6B8; }
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
            background: #141820;
            border-color: #F04444;
            color: #FF4B4B;
        }
        div[role="radiogroup"] label p {
            font-size: 0.9rem;
            font-weight: 750;
        }
        .stButton > button {
            background: #141820;
            color: #FF4B4B;
            border: 1px solid #F04444;
            border-radius: 999px;
            font-weight: 800;
        }
        .stButton > button:hover {
            background: #1C202A;
            color: #FF6B6B;
            border-color: #FF6969;
        }
        @media (max-width: 720px) {
            .block-container {
                padding: 1.25rem 0.75rem 2rem;
            }
            .subtitle {
                font-size: 0.95rem;
            }
            .station-line {
                font-size: 0.9rem;
                line-height: 1.45;
            }
            .kpi-grid {
                grid-template-columns: 1fr;
                gap: 0.75rem;
            }
            .kpi-card {
                min-height: 104px;
            }
            .kpi-value {
                font-size: 1.75rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_card_html(label: str, value: str, sub: str = "", accent: str = "") -> str:
    accent_class = f" accent-{accent}" if accent else ""
    return (
        f'<div class="kpi-card{accent_class}">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-value">{html.escape(value)}</div>'
        f'<div class="kpi-sub">{html.escape(sub)}</div>'
        "</div>"
    )


def render_card_grid(cards: list[dict]) -> None:
    card_html = "".join(
        kpi_card_html(
            card["label"],
            card["value"],
            card.get("sub", ""),
            card.get("accent", ""),
        )
        for card in cards
    )
    st.markdown(f'<div class="kpi-grid">{card_html}</div>', unsafe_allow_html=True)


def format_inches(value: Optional[float]) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f'{value:.2f}"'


@st.cache_data(ttl=900, show_spinner=False)
def cached_forecast(city_config: dict, selected_year: int, selected_month: int) -> dict:
    return get_forecast_rainfall(city_config, selected_year, selected_month)


def make_chart(
    frame: pd.DataFrame,
    today_day: int,
    month_end_day: int,
    historical_avg: Optional[float],
):
    if go is None:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=frame["day"],
            y=frame["actual_daily"],
            name="Daily observed rain",
            marker_color="rgba(255, 75, 75, 0.42)",
            hovertemplate="Day %{x}<br>Observed daily: %{y:.2f} in<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=frame["day"],
            y=frame["forecast_daily"],
            name="Daily forecast rain",
            marker_color="rgba(98, 199, 255, 0.34)",
            hovertemplate="Day %{x}<br>Forecast daily: %{y:.2f} in<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["day"],
            y=frame["actual_cumulative"],
            mode="lines+markers",
            name="Observed cumulative",
            line=dict(color="#FF4B4B", width=4, shape="hv"),
            marker=dict(size=6, color="#FF4B4B"),
            hovertemplate="Day %{x}<br>Observed cumulative: %{y:.2f} in<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["day"],
            y=frame["forecast_cumulative"],
            mode="lines+markers",
            name="Forecast cumulative",
            line=dict(color="#62C7FF", width=3, dash="dash", shape="hv"),
            marker=dict(size=6, color="#62C7FF"),
            hovertemplate="Day %{x}<br>Projected cumulative: %{y:.2f} in<extra></extra>",
        )
    )
    if historical_avg:
        fig.add_hline(
            y=historical_avg,
            line_dash="dot",
            line_color="#9AA6B8",
            annotation_text=f"Historical normal {historical_avg:.2f} in",
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
        barmode="overlay",
        height=520,
        paper_bgcolor="#080B10",
        plot_bgcolor="#0D131D",
        font=dict(color="#DDE5F0"),
        margin=dict(l=36, r=18, t=36, b=42),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        xaxis=dict(
            title="Day of month",
            gridcolor="#1F2937",
            zeroline=False,
            tickmode="array",
            tickvals=list(range(1, month_end_day + 1)),
            range=[0.5, month_end_day + 0.5],
        ),
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
    _, selected_month_end = calendar.monthrange(selected_year, selected_month)
    selected_start = date(selected_year, selected_month, 1)
    selected_end = date(selected_year, selected_month, selected_month_end)
    is_current_month = selected_start <= today <= selected_end
    is_past_month = selected_end < today
    today_day = today.day if is_current_month else selected_month_end if is_past_month else 1

    st.markdown(
        f"""
        <div class="station-line">
            <strong>{html.escape(city_config["location"])}</strong> &middot;
            Climate product {html.escape(city_config["station_id"])} &middot;
            Station {html.escape(city_config["observation_station"])} &middot;
            WFO {html.escape(city_config["wfo"])} &middot;
            Local time {local_now.strftime("%b %-d, %Y %-I:%M %p")} &middot;
            Kalshi mapping {html.escape(city_config["kalshi_market"])}
        </div>
        """,
        unsafe_allow_html=True,
    )

    historical = get_historical_monthly_average(city, city_config["station_id"], selected_month)
    actuals_result = get_month_to_date_actuals(
        city,
        city_config["station_id"],
        selected_year,
        selected_month,
        city_config["wfo"],
    )
    if is_past_month:
        forecast = {
            "daily": pd.DataFrame(columns=["date", "qpf_inches", "source"]),
            "total_inches": 0.0,
            "confidence": "N/A",
            "source": "Past month selected; forecast is not used.",
        }
    else:
        forecast = cached_forecast(city_config, selected_year, selected_month)

    actuals = actuals_result["daily"]
    has_actuals = not actuals.empty
    historical_avg = historical["value"]
    observed_total = accumulated_rainfall(actuals) if has_actuals else None
    observed_today = accumulated_today(actuals, today) if has_actuals and is_current_month else None
    forecast_remaining = None if is_past_month else forecast["total_inches"]
    projected_total = None if observed_total is None else observed_total + (forecast_remaining or 0.0)
    chart_frame = daily_cumulative_frame(actuals, forecast["daily"], selected_year, selected_month)

    render_card_grid(
        [
            {
                "label": "Historical Month Rainfall",
                "value": format_inches(historical_avg),
                "sub": historical["source"],
                "accent": "gray",
            },
            {
                "label": "Observed Month Rainfall",
                "value": format_inches(observed_total),
                "sub": actuals_result["source"],
                "accent": "red",
            },
            {
                "label": "Forecast Remaining Rainfall",
                "value": format_inches(forecast_remaining),
                "sub": forecast["confidence"],
                "accent": "blue",
            },
            {
                "label": "Projected Full-Month Rainfall",
                "value": format_inches(projected_total),
                "sub": "Observed plus forecast remaining",
                "accent": "blue",
            },
            {
                "label": "Observed Today",
                "value": format_inches(observed_today),
                "sub": "Only shown for current-month rows",
                "accent": "red",
            },
        ]
    )

    st.markdown('<div class="section-title">Daily Rainfall Timeline</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="source-note">
            Observed source: {html.escape(actuals_result["source"])} &middot;
            Forecast source: {html.escape(forecast["source"])}
        </div>
        <div class="legend-note">
            <span class="legend-pill"><span class="dot-red"></span>Red = observed rainfall</span>
            <span class="legend-pill"><span class="dot-blue"></span>Blue = forecast rainfall</span>
            <span class="legend-pill"><span class="dot-gray"></span>Gray dotted = historical normal</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    chart = make_chart(chart_frame, today_day, selected_month_end, historical_avg)
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})
    else:
        st.warning(
            "Plotly is not installed, so this deployment is showing a simple fallback chart. "
            "Add plotly to requirements.txt and redeploy to see the full chart."
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

            **Warning:** This monitor is decision-support only. Final settlement depends on the official Kalshi market rules and NWS report.
            """
        )


if __name__ == "__main__":
    main()
