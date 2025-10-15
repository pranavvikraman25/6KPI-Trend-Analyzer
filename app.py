# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import BytesIO
from datetime import date, timedelta

st.set_page_config(page_title="CKPI Multi-KPI Analyzer", layout="wide")
st.title("CKPI Multi-KPI Analyzer — Dashboard for Multiple KPIs")

# ---------------- Thresholds ----------------
KPI_THRESHOLDS = {
    "doorfriction": (30.0, 50.0),
    "cumulativeDoorSpeedError": (0.05, 0.08),
    "lockHookClosingTime": (0.2, 0.6),
    "lockHookTime": (0.3, None),
    "maximumForceDuringCompress": (5.0, 28.0),
    "landingDoorLockRollerClearance": (None, 0.029)
}


# ---------------- Helpers ----------------
def read_file(uploaded):
    name = uploaded.name.lower()
    if name.endswith(".xlsx"):
        return pd.read_excel(uploaded, engine="openpyxl")
    if name.endswith(".xls"):
        return pd.read_excel(uploaded, engine="xlrd")
    if name.endswith(".csv"):
        return pd.read_csv(uploaded)
    if name.endswith(".json"):
        return pd.read_json(uploaded)
    return pd.read_csv(uploaded)

def parse_dates(df, col):
    df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    return df

def detect_peaks_lows(values, low_thresh, high_thresh, std_factor=1.0):
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    peaks, lows = [], []
    if n < 3 or np.isnan(arr).all():
        return peaks, lows
    mean, std = np.nanmean(arr), np.nanstd(arr)
    upper_stat, lower_stat = mean + std_factor*std, mean - std_factor*std
    for i in range(1, n-1):
        a,b,c = arr[i-1], arr[i], arr[i+1]
        if np.isnan(b): continue
        if not np.isnan(a) and not np.isnan(c):
            if b > a and b > c and ((high_thresh is not None and b>high_thresh) or b>upper_stat):
                peaks.append(i)
            if b < a and b < c and ((low_thresh is not None and b<low_thresh) or b<lower_stat):
                lows.append(i)
    return peaks,lows

def color_cycle(i):
    palette = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f"]
    return palette[i % len(palette)]

def df_to_excel_bytes(df_):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_.to_excel(writer, index=False, sheet_name="report")
    out.seek(0)
    return out

# ---------------- Upload ----------------
uploaded = st.file_uploader("Upload KPI file", type=["xlsx","xls","csv","json"])
if not uploaded:
    st.info("Upload a KPI file to begin.")
    st.stop()

try:
    df = read_file(uploaded)
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

if df.empty:
    st.error("Uploaded file is empty.")
    st.stop()

cols_lower = {c.lower(): c for c in df.columns}
required = ["ckpi_statistics_date","ave","ckpi","floor","eq"]
for req in required:
    if req not in cols_lower:
        st.error(f"Required column '{req}' not found")
        st.stop()

date_col, ave_col, ckpi_col, floor_col, eq_col = [cols_lower[c] for c in required]
df = parse_dates(df, date_col)
if df[date_col].isna().all():
    st.error("Could not parse any dates.")
    st.stop()

# ---------------- Sidebar Filters ----------------
st.sidebar.header("Global Filters")

# EQ filter
eq_choices = sorted(df[eq_col].dropna().unique())
selected_eq = st.sidebar.multiselect("Select EQ(s)", eq_choices, default=eq_choices[:2] if eq_choices else [])

# Floor filter
floor_choices = sorted(df[floor_col].dropna().unique())
selected_floors = st.sidebar.multiselect("Select Floor(s)", floor_choices, default=floor_choices[:2] if floor_choices else [])

# KPI filter
kpi_list = list(KPI_THRESHOLDS.keys())
selected_kpis = st.sidebar.multiselect("Select KPI(s)", kpi_list, default=kpi_list)

# Date filter with preset ranges
st.sidebar.markdown("### Date Range")
preset_range = st.sidebar.selectbox("Quick Select", ["Custom", "Past Week", "Past Month", "Past 3 Months", "Past 6 Months", "Past Year"])
today = date.today()
if preset_range == "Custom":
    start_date, end_date = st.sidebar.date_input("Select Date Range", [df[date_col].min().date(), df[date_col].max().date()])
elif preset_range == "Past Week":
    start_date, end_date = today - timedelta(days=7), today
elif preset_range == "Past Month":
    start_date, end_date = today - timedelta(days=30), today
elif preset_range == "Past 3 Months":
    start_date, end_date = today - timedelta(days=90), today
elif preset_range == "Past 6 Months":
    start_date, end_date = today - timedelta(days=180), today
else:  # Past Year
    start_date, end_date = today - timedelta(days=365), today

# Sensitivity slider
std_factor = st.sidebar.slider("Peak/Low Sensitivity", 0.5, 3.0, 1.0, 0.1)

# ---------------- Apply filters ----------------
df_filtered = df[
    df[eq_col].isin(selected_eq) &
    df[floor_col].isin(selected_floors) &
    df[ckpi_col].str.lower().isin([k.lower() for k in selected_kpis]) &
    (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
]

if df_filtered.empty:
    st.warning("No data after filters.")
    st.stop()

# ---------------- KPI Graphs ----------------
kpi_summary = []
for kpi_name in selected_kpis:
    df_kpi = df_filtered[df_filtered[ckpi_col].str.lower() == kpi_name.lower()]
    if df_kpi.empty:
        st.info(f"No data for KPI: {kpi_name}")
        continue

    st.subheader(f"KPI: {kpi_name}")
    fig = go.Figure()
    floors = sorted(df_kpi[floor_col].dropna().unique())
    for i, floor in enumerate(floors):
        df_floor = df_kpi[df_kpi[floor_col] == floor].sort_values(date_col)
        if df_floor.empty: continue
        color = color_cycle(i)
        fig.add_trace(go.Scatter(
            x=df_floor[date_col],
            y=df_floor[ave_col],
            mode="lines+markers",
            name=f"Floor {floor}",
            line=dict(color=color, width=2),
            marker=dict(size=6)
        ))

        low_thresh, high_thresh = KPI_THRESHOLDS.get(kpi_name.lower(), (None, None))
        peaks, lows = detect_peaks_lows(df_floor[ave_col].values, low_thresh, high_thresh, std_factor)

        fig.add_trace(go.Scatter(
            x=df_floor[date_col].values[peaks],
            y=df_floor[ave_col].values[peaks],
            mode="markers",
            marker=dict(symbol="triangle-up", color="red", size=10),
            name=f"Peaks (Floor {floor})"
        ))
        fig.add_trace(go.Scatter(
            x=df_floor[date_col].values[lows],
            y=df_floor[ave_col].values[lows],
            mode="markers",
            marker=dict(symbol="triangle-down", color="blue", size=10),
            name=f"Lows (Floor {floor})"
        ))

        kpi_summary.append({
            "kpi": kpi_name,
            "floor": floor,
            "peaks": len(peaks),
            "lows": len(lows),
            "rows": len(df_floor)
        })

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="ave",
        height=400,
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------- Actionable Insights ----------------
st.subheader("⚡ Actionable Insights Report ⚡")
report_rows = []
solution_map = {
    1: "Follow solution 1",
    2: "Follow solution 2",
    3: "This is the reason for the error"
}

for rec in kpi_summary:
    if rec['peaks'] + rec['lows'] > rec['rows']*0.2:
        report_rows.append({
            "KPI": rec['kpi'],
            "Floor": rec['floor'],
            "Action Needed": "⚠️ High uncertainty → Technician check",
            "Remedy / Reason": solution_map.get((rec['peaks']+rec['lows'])%3+1)
        })

report_df = pd.DataFrame(report_rows)
if not report_df.empty:
    st.dataframe(report_df)
    st.download_button(
        "Download Actionable Report (Excel)",
        data=df_to_excel_bytes(report_df),
        file_name="kpi_actionable_report.xlsx"
    )
else:
    st.info("No action needed for selected filters.")
