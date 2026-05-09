import streamlit as st
import gridstatus
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import os

# --- WEB CONFIG ---
st.set_page_config(page_title="SPP Analyst Dashboard", layout="wide")
st.title("⚡ SPP Operational Performance Dashboard")

# --- DATE LOGIC ---
now = datetime.now().replace(microsecond=0)
yesterday = now - timedelta(days=1)
week_ago = now - timedelta(days=6)

# --- SIDEBAR CONTROLS ---
st.sidebar.header("Data Settings")
if st.sidebar.button("Refresh Live Data"):
    # Logic to delete CSVs and re-download
    if os.path.exists("spp_load_cache.csv"): os.remove("spp_load_cache.csv")
    st.rerun()

# --- DATA PROCESSING (Your existing logic) ---
# [Insert your current data acquisition and cleaning code here]

# --- UI LAYOUT: KPI METRICS ---
col1, col2, col3 = st.columns(3)
mape_yest = diff_yest['Pct_Diff'].abs().mean()
peak_load = load['Load'].max()

col1.metric("Peak Load", f"{peak_load:,.0f} MW")
col2.metric("1-Day Forecast Error", f"{mape_yest:.2f}%")
col3.metric("Status", "Operational", delta_color="normal")

# --- UI LAYOUT: GRAPHS ---
st.subheader("Real-Time vs Forecast Analysis")
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Variance & Error Analysis")
st.plotly_chart(fig3, use_container_width=True)

# --- UI LAYOUT: ALERTS ---
threshold = 5.0
major_deviations = diff_yest[diff_yest['Pct_Diff'].abs() > threshold]
if not major_deviations.empty:
    st.warning(f"Reliability Alert: {len(major_deviations)} intervals exceeded {threshold}% variance.")
    st.table(major_deviations[['Interval End', 'Pct_Diff']])