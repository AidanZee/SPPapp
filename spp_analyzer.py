#import gridstatus
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import os

# --- 1. SETUP & DATES ---
now = datetime.now().replace(microsecond=0)
yesterday = now - timedelta(days=1)
weekAgo = now - timedelta(days=6)

print(f"Analysis Window: {yesterday} to {now}")

spp = gridstatus.SPP()

# --- 2. DATA ACQUISITION & CACHING ---
cache_file_load = "spp_load_cache.csv"
if not os.path.exists(cache_file_load):
    load = spp.get_load(date=yesterday, end=now)
    load.to_csv(cache_file_load, index=False)
load = pd.read_csv(cache_file_load)

# Forecast from 1 Week Ago
cache_file_forecast_week = "spp_load_forecast_cache.csv"
if not os.path.exists(cache_file_forecast_week):
    load_forecast_week = spp.get_load_forecast(date=weekAgo)
    load_forecast_week.to_csv(cache_file_forecast_week, index=False)
df_week_raw = pd.read_csv(cache_file_forecast_week)

# Forecast from Yesterday
cache_file_forecast_yesterday = "spp_load_forecast_YESTERDAY_cache.csv"
if not os.path.exists(cache_file_forecast_yesterday):
    load_forecast_yest = spp.get_load_forecast(date=yesterday)
    load_forecast_yest.to_csv(cache_file_forecast_yesterday, index=False)
df_yest_raw = pd.read_csv(cache_file_forecast_yesterday)

# --- 3. DEDUPLICATION & WINDOW FILTERING ---
# (Crucial 'Quality Assurance' step to remove revision noise)
def clean_and_window(df, start, end):
    df['Interval End'] = pd.to_datetime(df['Interval End']).dt.tz_localize(None)
    if 'Publish Time' in df.columns:
        df = df.sort_values('Publish Time').drop_duplicates('Interval End', keep='last')
    return df[df['Interval End'].between(start, end)].sort_values('Interval End')

load['Interval End'] = pd.to_datetime(load['Interval End']).dt.tz_localize(None)
df_week = clean_and_window(df_week_raw, yesterday, now)
df_yest = clean_and_window(df_yest_raw, yesterday, now)

# --- 4. VARIANCE CALCULATIONS (The "Difference" Logic) ---
# Resample 5-min actuals to 1-hour to match forecast
actual_hourly = load.set_index('Interval End').resample('1H')['Load'].mean().reset_index()

# Merge and calculate Deltas for both forecasts
diff_week = pd.merge(actual_hourly, df_week[['Interval End', 'Load Forecast']], on='Interval End')
diff_week['MW_Diff'] = diff_week['Load'] - diff_week['Load Forecast']
diff_week['Pct_Diff'] = (diff_week['MW_Diff'] / diff_week['Load Forecast']) * 100

diff_yest = pd.merge(actual_hourly, df_yest[['Interval End', 'Load Forecast']], on='Interval End')
diff_yest['MW_Diff'] = diff_yest['Load'] - diff_yest['Load Forecast']
diff_yest['Pct_Diff'] = (diff_yest['MW_Diff'] / diff_yest['Load Forecast']) * 100

# --- 5. VISUALIZATION ---

# FIG 1: Week-Old Forecast vs Actual
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=load['Interval End'], y=load['Load'], name='Actual Load', line=dict(color='blue')))
fig1.add_trace(go.Scatter(x=df_week['Interval End'], y=df_week['Load Forecast'], name='7-Day Forecast', line=dict(color='red', dash='dash')))
fig1.update_layout(title="Actual vs 7-Day Forecast", template="plotly_white")
fig1.show()

# FIG 2: Yesterday's Forecast vs Actual
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=load['Interval End'], y=load['Load'], name='Actual Load', line=dict(color='blue')))
fig2.add_trace(go.Scatter(x=df_yest['Interval End'], y=df_yest['Load Forecast'], name='1-Day Forecast', line=dict(color='green', dash='dash')))
fig2.update_layout(title="Actual vs 1-Day Forecast", template="plotly_white")
fig2.show()

# NEW FIG 3: PERCENT DIFFERENCE COMPARISON
# This allows you to see if the forecast improved as the date got closer
fig3 = go.Figure()
fig3.add_trace(go.Bar(x=diff_week['Interval End'], y=diff_week['Pct_Diff'], name='7-Day Error %', marker_color='red', opacity=0.6))
fig3.add_trace(go.Bar(x=diff_yest['Interval End'], y=diff_yest['Pct_Diff'], name='1-Day Error %', marker_color='green', opacity=0.6))

fig3.update_layout(
    title="Forecast Performance: 7-Day vs 1-Day Percent Error",
    yaxis_title="Error (%)",
    barmode='group',
    template="plotly_white",
    hovermode="x unified"
)
fig3.add_hline(y=0, line_color="black")
fig3.show()

print("Graphs generated. Check your browser/output for the variance analysis.")
# --- 6. AUTOMATED ANALYST BRIEFING ---
print("\n" + "="*50)
print("       SPP OPERATIONAL PERFORMANCE SUMMARY")
print("="*50)

# Calculate Statistics
peak_load = load['Load'].max()
peak_time = load.loc[load['Load'].idxmax(), 'Interval End'].strftime('%H:%M')

mape_week = diff_week['Pct_Diff'].abs().mean()
mape_yest = diff_yest['Pct_Diff'].abs().mean()

# Improvement Analysis
improvement = mape_week - mape_yest

print(f"Daily Peak Load:      {peak_load:,.0f} MW at {peak_time}")
print(f"7-Day Forecast Error: {mape_week:.2f}% (MAPE)")
print(f"1-Day Forecast Error: {mape_yest:.2f}% (MAPE)")
print(f"Model Convergence:    {improvement:.2f}% accuracy gain as real-time approached.")

# --- 7. RELIABILITY THRESHOLD ALERTS ---
# Flagging any hour where the forecast was off by more than 5%
threshold = 5.0
major_deviations = diff_yest[diff_yest['Pct_Diff'].abs() > threshold]

if not major_deviations.empty:
    print(f"\n[ALERT] {len(major_deviations)} reliability threshold violations (> {threshold}%):")
    for _, row in major_deviations.iterrows():
        status = "UNDER-FORECAST" if row['Pct_Diff'] > 0 else "OVER-FORECAST"
        print(f" - {row['Interval End'].strftime('%H:%M')}: {row['Pct_Diff']:.1f}% ({status})")
else:
    print(f"\n[PASS] All 1-Day forecast intervals within {threshold}% reliability target.")

print("="*50)
