# NWS Rainfall Monitor

Dark Streamlit dashboard for monitoring Kalshi-style monthly rainfall markets with NWS station configuration, fallback historical data, fallback observed rainfall, NWS forecast adapters, threshold probabilities, and a simple rainfall timeline chart.

## 1. How to run the app

1. Download or clone this repo.
2. Open a terminal in the repo folder.
3. Install the packages:

```bash
pip install -r requirements.txt
```

4. Start Streamlit:

```bash
streamlit run app.py
```

5. Your browser should open the app automatically.

## 2. How to add a new city

Open `config/cities.py` and add one new entry inside `CITIES`.

Use this shape:

```python
"City Name": {
    "station_id": "CLIXXX",
    "observation_station": "KXXX",
    "wfo": "XXX",
    "location": "City, ST",
    "timezone": "America/New_York",
    "latitude": 00.0000,
    "longitude": -00.0000,
    "kalshi_market": "KXRAINXXXX",
},
```

`station_id` should be the NWS Daily Climate Report product used for the market. `observation_station` should be the official airport/station code used for local station context.

## 3. How to add historical rainfall data

Open `data/historical_monthly_rainfall.csv`.

Add one row for each month:

```csv
city,station_id,month,historical_avg_inches
Example City,CLIXXX,1,3.12
Example City,CLIXXX,2,2.45
```

Months use numbers: January is `1`, February is `2`, and December is `12`.

## 4. How to connect live NWS Daily Climate Report parsing

The app is already structured for this in `services/climate_reports.py`.

For the MVP, month-to-date actual rainfall comes from:

```text
data/daily_rainfall_actuals.csv
```

To connect live settlement-style data, update `get_month_to_date_actuals()` so it pulls from the applicable NWS Daily Climate Report or NOWData source for the selected WFO/station. Keep these settlement rules in the parser:

- Trace `T` becomes `0.00`.
- Missing `M` becomes `0.00`.
- The first full-month Daily Climate Report controls.
- Later revisions should not overwrite the settlement view unless you intentionally store them separately.

## 5. How the probability model works

The MVP model lives in `services/probability_model.py`.

It calculates:

```text
projected_total = accumulated_rainfall + forecast_remaining_rainfall
buffer = projected_total - threshold
```

Then it turns that buffer into a simple probability. The model gives more uncertainty when:

- There are more days left in the month.
- The forecast confidence is low.
- The historical monthly average is large.

This is a transparent decision-support model, not an official Kalshi price model.

## 6. Known limitations

- NWS gridpoint QPF is not always available or complete for every city.
- If QPF is missing, the app uses probability of precipitation as a very low-confidence fallback.
- Live NWS Daily Climate Report parsing is scaffolded but still needs endpoint validation per WFO.
- The included actual rainfall CSV is sample fallback data so the app can run immediately.
- Final settlement depends on official Kalshi market rules and the official NWS report.
