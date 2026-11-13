"""Password-protected admin dashboard with production trend and oven heatmap."""

import hmac
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import COLUMNS, generate_exact_xlsx, get_all_logs, init_db
from nav import render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")

st.set_page_config(page_title="Admin | Wood Lamination Logs", page_icon="🪵", layout="wide")

if "admin_password" not in st.secrets:
    st.error("Admin access is not configured. Add `admin_password` to the app's Streamlit secrets.")
    st.stop()

if not st.session_state.get("admin_authenticated", False):
    st.title("🔒 Admin sign in")
    with st.form("admin_login_form"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        if hmac.compare_digest(password, str(st.secrets["admin_password"])):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()

render_nav()
init_db()

heading_col, logout_col = st.columns([5, 1])
with heading_col:
    st.title("🪵 Production Control Dashboard")
    st.caption("Factory overview · output trends by production date and oven temperatures")
with logout_col:
    if st.button("Sign out", use_container_width=True):
        st.session_state["admin_authenticated"] = False
        st.rerun()

records = get_all_logs(descending=True)
data = pd.DataFrame(records)
if data.empty:
    data = pd.DataFrame(columns=[*COLUMNS, "created_at"])

st.subheader("Factory at a glance")
total_rolls = len(data)
avg_gsm = pd.to_numeric(data["gsm"], errors="coerce").mean() if total_rolls else 0
resin_logged = int(data[["right_resin", "center_resin", "left_resin"]].notna().all(axis=1).sum()) if total_rolls else 0
oven_columns = [f"oven_{number}" for number in range(1, 7)]
oven_logged = int(data[oven_columns].notna().all(axis=1).sum()) if total_rolls else 0

metric_cols = st.columns(5)
metric_cols[0].metric("Total rolls", f"{total_rolls:,}")
metric_cols[1].metric("Total output", f"{pd.to_numeric(data['output'], errors='coerce').sum():,.1f}" if total_rolls else "0")
metric_cols[2].metric("Average GSM", f"{avg_gsm:,.1f}" if pd.notna(avg_gsm) else "—")
metric_cols[3].metric("Resin logged", f"{resin_logged}/{total_rolls}" if total_rolls else "0/0")
metric_cols[4].metric("Oven settings logged", f"{oven_logged}/{total_rolls}" if total_rolls else "0/0")

if total_rolls:
    # Stored ISO timestamps include their original +03:00 offset. Parse them as
    # instants, then group/display by the factory timezone for correct local dates.
    data["created_at_eat"] = pd.to_datetime(data["created_at"], errors="coerce", utc=True).dt.tz_convert(FACTORY_TIMEZONE)
    dated = data.dropna(subset=["created_at_eat"]).copy()
    trend_col, heatmap_col = st.columns([3, 2])

    with trend_col:
        st.subheader("Production output over time — East Africa Time")
        if dated.empty:
            st.info("No dated production records yet. Newly created rolls will appear here; existing historical rows have no recoverable date.")
        else:
            dated["output"] = pd.to_numeric(dated["output"], errors="coerce").fillna(0)
            daily = (
                dated.assign(production_date=dated["created_at_eat"].dt.date)
                .groupby("production_date", as_index=False)["output"]
                .sum()
                .sort_values("production_date")
            )
            daily["cumulative_output"] = daily["output"].cumsum()
            view = st.radio("Trend measure", ["Daily output", "Cumulative output"], horizontal=True, key="admin_output_trend_measure")
            y_column = "output" if view == "Daily output" else "cumulative_output"
            y_label = "Output per day" if view == "Daily output" else "Cumulative output"
            trend = px.line(daily, x="production_date", y=y_column, markers=True, labels={"production_date": "Production date (EAT)", y_column: y_label}, title=view, template="plotly_dark")
            trend.update_traces(line_color="#F59E0B", marker_color="#FBBF24")
            trend.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(trend, use_container_width=True)
            st.caption("Timestamps are recorded and grouped in East Africa Time (Africa/Nairobi, UTC+03:00).")

    with heatmap_col:
        st.subheader("Oven temperature heatmap")
        heat_data = data.sort_values("id", ascending=True).set_index("id")[oven_columns].apply(pd.to_numeric, errors="coerce")
        heat_data = heat_data.dropna(axis=1, how="all")
        if heat_data.empty or heat_data.shape[1] == 0:
            st.info("Oven temperatures have not been recorded yet.")
        else:
            heat = go.Figure(data=go.Heatmap(
                z=heat_data.T.to_numpy(),
                x=[f"#{roll_id}" for roll_id in heat_data.index],
                y=[f"Oven {number}" for number in range(1, 7) if f"oven_{number}" in heat_data.columns],
                colorscale=[[0, "#1F3B3D"], [0.5, "#F59E0B"], [1, "#EF4444"]],
                colorbar=dict(title="Temp"),
                hovertemplate="%{y}<br>Roll %{x}<br>Temperature: %{z}<extra></extra>",
                connectgaps=False,
            ))
            heat.update_layout(title="Temperatures by oven and roll", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=55, b=10), xaxis_title="Roll ID", yaxis_title="Oven")
            st.plotly_chart(heat, use_container_width=True)

st.subheader("Production records")
action_col, download_col = st.columns([1, 2])
with action_col:
    if st.button("↻ Refresh dashboard", use_container_width=True):
        st.rerun()
with download_col:
    st.download_button("⬇ Download XLSX report", data=generate_exact_xlsx(), file_name="wood_lamination_production.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

if total_rolls:
    st.dataframe(data.sort_values("id", ascending=True), use_container_width=True, hide_index=True)
else:
    st.info("No production records have been logged yet.")
