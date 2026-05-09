import streamlit as st
import gridstatus
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import os

# --- 1. WEB CONFIG & STYLING ---
st.set_page_config(page_title="SPP Analyst Dashboard", layout="wide")
st.title("⚡ SPP Operational Performance Dashboard")
st.markdown("Automated Analysis of Southwest Power Pool Load and Forecast Variance")

# --- 2. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("Control Panel")
    if st.button('🔄 Sync Live SPP Data'):
        # Clear cache to force a fresh download
        for f in ["spp_load_cache.csv", "spp_load_forecast_cache.csv", "spp_load_forecast_YESTERDAY_cache.csv"]:
            if os.path.exists(f): os.remove(f)
        st.success("Cache cleared! Fetching fresh data...")
        st.rerun()
    
    st.info("This tool performs automated Variance Analysis comparing 7-day and 1-day forecasts against real-time 5-minute load data.")

# --- 3. SETUP & DATES ---
now = datetime.now().replace(microsecond=0)
yesterday = now - timedelta(days=1)
weekAgo = now - timedelta(days=6)

spp = gridstatus.SPP()

# --- 4. DATA ACQUISITION & CACHING ---
# Actual Load
cache_file_load = "spp_load_cache.csv"
if not os.path.exists(cache_file_load):
    with st.spinner("Downloading real-time actuals..."):
        load = spp.get_load(date=yesterday, end=now)
        load.to_csv(cache_file_load, index=False)
load = pd.read_csv(cache_file_load)

# Forecasts
cache_file_forecast_week = "spp_load_forecast_cache.csv"
if not os.path.exists(cache_file_forecast_week):
    with st.spinner("Downloading 7-day forecast..."):
        load_forecast_week = spp.get_load_forecast(date=weekAgo)
        load_forecast_week.to_csv(cache_file_forecast_week, index=False)
df_week_raw = pd.read_csv(cache_file_forecast_week)

cache_file_forecast_yesterday = "spp_load_forecast_YESTERDAY_cache.csv"
if not os.path.exists(cache_file_forecast_yesterday):
    with st.spinner("Downloading 1-day forecast..."):
        load_forecast_yest = spp.get_load_forecast(date=yesterday)
        load_forecast_yest.to_csv(cache_file_forecast_yesterday, index=False)
df_yest_raw = pd.read_csv(cache_file_forecast_yesterday)

# --- 5. CLEANING & ANALYTICS ---
def clean_and_window(df, start, end):
    df['Interval End'] = pd.to_datetime(df['Interval End']).dt.tz_localize(None)
    if 'Publish Time' in df.columns:
        df = df.sort_values('Publish Time').drop_duplicates('Interval End', keep='last')
    return df[df['Interval End'].between(start, end)].sort_values('Interval End')

load['Interval End'] = pd.to_datetime(load['Interval End']).dt.tz_localize(None)
df_week = clean_and_window(df_week_raw, yesterday, now)
df_yest = clean_and_window(df_yest_raw, yesterday, now)

# Resample and Calc Variance
actual_hourly = load.set_index('Interval End').resample('1H')['Load'].mean().reset_index()

def get_diff(actuals, forecast):
    merged = pd.merge(actuals, forecast[['Interval End', 'Load Forecast']], on='Interval End')
    merged['Pct_Diff'] = ((merged['Load'] - merged['Load Forecast']) / merged['Load Forecast']) * 100
    return merged

diff_week = get_diff(actual_hourly, df_week)
diff_yest = get_diff(actual_hourly, df_yest)

# --- 6. KPI METRICS ---
mape_yest = diff_yest['Pct_Diff'].abs().mean()
peak_load = load['Load'].max()
current_error = diff_yest['Pct_Diff'].iloc[-1] if not diff_yest.empty else 0

m1, m2, m3 = st.columns(3)
m1.metric("Peak System Load", f"{peak_load:,.0f} MW")
m2.metric("Avg Forecast Error (MAPE)", f"{mape_yest:.2f}%")
m3.metric("Current Variance", f"{current_error:.1f}%", delta_color="inverse")

# --- 7. VISUALIZATIONS ---
tab1, tab2 = st.tabs(["Operational View", "Variance Analysis"])

with tab1:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=load['Interval End'], y=load['Load'], name='Actual Load', line=dict(color='blue')))
    fig2.add_trace(go.Scatter(x=df_yest['Interval End'], y=df_yest['Load Forecast'], name='1-Day Forecast', line=dict(color='green', dash='dash')))
    fig2.update_layout(title="Real-Time Load vs. Yesterday's Forecast", template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig2, use_container_width=True)

with tab2:
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=diff_week['Interval End'], y=diff_week['Pct_Diff'], name='7-Day Error %', marker_color='red', opacity=0.6))
    fig3.add_trace(go.Bar(x=diff_yest['Interval End'], y=diff_yest['Pct_Diff'], name='1-Day Error %', marker_color='green', opacity=0.6))
    fig3.update_layout(title="Forecast Error Convergence (7-Day vs 1-Day)", yaxis_title="Error (%)", barmode='group', template="plotly_white")
    fig3.add_hline(y=0, line_color="black")
    st.plotly_chart(fig3, use_container_width=True)

# --- 8. ANALYST LOG ---
st.divider()
st.subheader("📋 Automated Analyst Briefing")
if mape_yest < 3.0:
    st.success(f"System performing within reliability bounds. Current MAPE: {mape_yest:.2f}%")
else:
    st.warning(f"High variance detected. System MAPE ({mape_yest:.2f}%) exceeds standard 3% threshold.")

st.write(f"**Observation:** The peak load of {peak_load:,.0f} MW was successfully captured by the 1-Day forecast model with a convergence gain of { (diff_week['Pct_Diff'].abs().mean() - mape_yest):.2f}% over the 7-day outlook.")