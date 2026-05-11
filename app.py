import streamlit as st
import gridstatus
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import sqlite3
import os

# --- 1. WEB CONFIG & STYLING ---
st.set_page_config(page_title="SPP Analyst Dashboard", layout="wide")
st.title("⚡ SPP Operational Performance Dashboard")
st.markdown("Automated Analysis of Southwest Power Pool Load and Forecast Variance")

# --- 2. DATABASE SETUP ---
DB_NAME = "spp_data.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    return conn

# Create tables if they don't exist
with get_db_connection() as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS actual_load (
            "Interval End" TEXT PRIMARY KEY,
            "Load" REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forecasts (
            "Interval End" TEXT,
            "Publish Time" TEXT,
            "Load Forecast" REAL,
            "Forecast Type" TEXT,
            PRIMARY KEY ("Interval End", "Forecast Type")
        )
    """)

# --- 3. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("Control Panel")
    if st.button('Sync Live SPP Data'):
        # Clear database tables instead of deleting files
        with get_db_connection() as conn:
            conn.execute("DELETE FROM actual_load")
            conn.execute("DELETE FROM forecasts")
        st.success("Database cleared! Fetching fresh data...")
        st.rerun()
    
    st.info("This tool performs automated Variance Analysis comparing 7-day and 1-day forecasts against real-time 5-minute load data.")

# --- 4. SETUP & DATES ---
now = datetime.now().replace(microsecond=0)
yesterday = now - timedelta(days=1)
weekAgo = now - timedelta(days=6)

spp = gridstatus.SPP()

# --- 5. DATA ACQUISITION & SQL STORAGE ---
def store_data(df, table_name, mode='append'):
    with get_db_connection() as conn:
        # We add 'mode' so we can choose to 'replace' or 'append'
        df.to_sql(table_name, conn, if_exists=mode, index=False, method='multi')

# Actual Load
with get_db_connection() as conn:
    # Use a try-except block in case the table doesn't exist yet
    try:
        check_load = pd.read_sql("SELECT COUNT(*) as count FROM actual_load", conn)['count'][0]
    except:
        check_load = 0

if check_load == 0:
    with st.spinner("Downloading and storing real-time actuals..."):
        load_data = spp.get_load(date=yesterday, end=now)
        # Use 'replace' here to avoid the UNIQUE constraint error on first run
        store_data(load_data[['Interval End', 'Load']], 'actual_load', mode='replace')

# ... Repeat the same logic for the Forecasts section ...

load = pd.read_sql("SELECT * FROM actual_load", get_db_connection())

# Forecasts (7-Day and 1-Day)
with get_db_connection() as conn:
    check_forecasts = pd.read_sql("SELECT COUNT(*) as count FROM forecasts", conn)['count'][0]

if check_forecasts == 0:
    with st.spinner("Downloading forecasts..."):
        # Week Ago
        f_week = spp.get_load_forecast(date=weekAgo)
        f_week['Forecast Type'] = '7-Day'
        # Yesterday
        f_yest = spp.get_load_forecast(date=yesterday)
        f_yest['Forecast Type'] = '1-Day'
        
        combined_f = pd.concat([f_week, f_yest])
        store_data(combined_f[['Interval End', 'Publish Time', 'Load Forecast', 'Forecast Type']], 'forecasts')

df_week_raw = pd.read_sql("SELECT * FROM forecasts WHERE \"Forecast Type\" = '7-Day'", get_db_connection())
df_yest_raw = pd.read_sql("SELECT * FROM forecasts WHERE \"Forecast Type\" = '1-Day'", get_db_connection())

# --- 6. CLEANING & ANALYTICS ---
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

# --- 7. KPI METRICS ---
mape_yest = diff_yest['Pct_Diff'].abs().mean()
peak_load = load['Load'].max()
current_error = diff_yest['Pct_Diff'].iloc[-1] if not diff_yest.empty else 0

m1, m2, m3 = st.columns(3)
m1.metric("Peak System Load", f"{peak_load:,.0f} MW")
m2.metric("Avg Forecast Error (MAPE)", f"{mape_yest:.2f}%")
m3.metric("Current Variance", f"{current_error:.1f}%", delta_color="inverse")

# --- 8. VISUALIZATIONS ---
tab1, tab2 = st.tabs(["Operational Comparison", "Variance Analysis"])

with tab1:
    st.subheader("Comparison: Forecast vs. Real-Time Load")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=load['Interval End'], y=load['Load'], name='Actual Load', line=dict(color='blue')))
    fig1.add_trace(go.Scatter(x=df_week['Interval End'], y=df_week['Load Forecast'], name='7-Day Forecast', line=dict(color='red', dash='dash')))
    fig1.update_layout(title="7-Day Forecast Accuracy", template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig1, use_container_width=True)

    st.divider()

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=load['Interval End'], y=load['Load'], name='Actual Load', line=dict(color='blue')))
    fig2.add_trace(go.Scatter(x=df_yest['Interval End'], y=df_yest['Load Forecast'], name='1-Day Forecast', line=dict(color='green', dash='dash')))
    fig2.update_layout(title="1-Day Forecast Accuracy", template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig2, use_container_width=True)

with tab2:
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=diff_week['Interval End'], y=diff_week['Pct_Diff'], name='7-Day Error %', marker_color='red', opacity=0.6))
    fig3.add_trace(go.Bar(x=diff_yest['Interval End'], y=diff_yest['Pct_Diff'], name='1-Day Error %', marker_color='green', opacity=0.6))
    fig3.update_layout(title="Forecast Error Convergence (7-Day vs 1-Day)", yaxis_title="Error (%)", barmode='group', template="plotly_white")
    fig3.add_hline(y=0, line_color="black")
    st.plotly_chart(fig3, use_container_width=True)

# --- 9. ANALYST LOG ---
st.divider()
st.subheader("Automated Analyst Briefing")
if mape_yest < 3.0:
    st.success(f"System performing within reliability bounds. Current MAPE: {mape_yest:.2f}%")
else:
    st.warning(f"High variance detected. System MAPE ({mape_yest:.2f}%) exceeds standard 3% threshold.")

st.write(f"**Observation:** The peak load of {peak_load:,.0f} MW was successfully captured by the 1-Day forecast model with a convergence gain of { (diff_week['Pct_Diff'].abs().mean() - mape_yest):.2f}% over the 7-day outlook.")
