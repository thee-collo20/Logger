"""Authenticated dashboard for reviewing production logs and factory output."""

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from auth import require_role
from db import COLUMNS, get_all_logs, init_db, shift_for_datetime
from login_audit import get_last_successful_login
from nav import render_footer, render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
REPORT_COLUMNS = [*COLUMNS, "created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"]
st.set_page_config(page_title="Production Logs | Biashara Masters Sawmill", page_icon="🪵", layout="wide")
user = require_role({"Admin", "Supervisor", "Production Manager"})
render_nav()
init_db()

st.title("🪵 Biashara Masters Sawmill — Production Dashboard")
st.caption(f"Signed in as {user['username']} ({user['rank']})")
last_login = get_last_successful_login()
if last_login:
    st.success(
        f"Last successful login: {last_login['username']} ({last_login['rank']}) at {last_login['logged_at_eat']} EAT"
    )
else:
    st.info("No successful sign-ins have been recorded yet.")

records = get_all_logs(descending=False)
data = pd.DataFrame(records)
if data.empty:
    data = pd.DataFrame(columns=REPORT_COLUMNS)

current_shift_date, current_shift_name = shift_for_datetime(datetime.now(FACTORY_TIMEZONE))
st.header("Shift production")
view_scope = st.radio(
    "Show production for",
    ["Current shift", "All shifts"],
    horizontal=True,
    key="dashboard_shift_scope",
    help="Current shift shows only the active Day or Night shift in East Africa Time.",
)
if view_scope == "Current shift":
    display_data = data[(data["shift_date"] == current_shift_date) & (data["shift_name"] == current_shift_name)].copy()
    st.caption(f"Current {current_shift_name} shift · {current_shift_date} (EAT)")
else:
    display_data = data.copy()
    st.caption("All recorded shifts")

output_total = pd.to_numeric(display_data["output"], errors="coerce").sum(min_count=1)
metric_cols = st.columns(2)
metric_cols[0].metric("Rolls", f"{len(display_data):,}")
metric_cols[1].metric("Total production output", f"{output_total:,.1f}" if pd.notna(output_total) else "—")
if display_data.empty:
    st.info("No production logs have been recorded for this selection yet.")
else:
    st.dataframe(display_data.sort_values("id", ascending=True)[REPORT_COLUMNS], use_container_width=True, hide_index=True)

report_buffer = BytesIO()
with pd.ExcelWriter(report_buffer, engine="openpyxl") as writer:
    display_data[REPORT_COLUMNS].to_excel(writer, sheet_name="Production Report", index=False)
report_buffer.seek(0)
report_suffix = f"{current_shift_date}_{current_shift_name.lower()}_shift" if view_scope == "Current shift" else "all_shifts"
st.download_button(
    "⬇ Download production report (XLSX)",
    data=report_buffer.getvalue(),
    file_name=f"production_report_{report_suffix}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()
st.header("Global factory overview")
st.caption("Factory-wide totals and charts include all assigned production logs across Day and Night shifts.")
total_rolls = len(data)
oven_columns = [f"oven_{number}" for number in range(1, 7)]
if total_rolls:
    total_output = pd.to_numeric(data["output"], errors="coerce").sum(min_count=1)
    resin_logged = int(data[["right_resin", "center_resin", "left_resin"]].notna().all(axis=1).sum())
    oven_logged = int(data[oven_columns].notna().all(axis=1).sum())
else:
    total_output = None
    resin_logged = oven_logged = 0
metrics = st.columns(4)
metrics[0].metric("All rolls", f"{total_rolls:,}")
metrics[1].metric("All-shift output", f"{total_output:,.1f}" if total_output is not None and pd.notna(total_output) else "—")
metrics[2].metric("Resin completed", f"{resin_logged}/{total_rolls}" if total_rolls else "0/0")
metrics[3].metric("Oven settings completed", f"{oven_logged}/{total_rolls}" if total_rolls else "0/0")

if total_rolls:
    chart_col, heat_col = st.columns([3, 2])
    with chart_col:
        st.subheader("Global production output by date")
        dated = data.dropna(subset=["shift_date"]).copy()
        if dated.empty:
            st.info("No dated production records yet.")
        else:
            dated["output"] = pd.to_numeric(dated["output"], errors="coerce").fillna(0)
            daily = dated.groupby("shift_date", as_index=False)["output"].sum().sort_values("shift_date")
            measure = st.radio("Production measure", ["Daily total (Day + Night)", "Cumulative total"], horizontal=True, key="dashboard_production_measure")
            if measure == "Cumulative total":
                daily["plot_output"] = daily["output"].cumsum()
                y_label = "Cumulative output (all shifts)"
            else:
                daily["plot_output"] = daily["output"]
                y_label = "Daily output (Day + Night)"
            chart = px.line(daily, x="shift_date", y="plot_output", markers=True,
                            labels={"shift_date": "Production date (EAT)", "plot_output": y_label}, template="plotly_dark")
            chart.update_traces(line_color="#F59E0B", marker_color="#FBBF24")
            chart.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=25, b=10))
            st.plotly_chart(chart, use_container_width=True)
    with heat_col:
        st.subheader("Global oven temperature heatmap")
        oven_data = data.sort_values("id", ascending=True).copy()
        for column in oven_columns:
            oven_data[column] = pd.to_numeric(oven_data[column], errors="coerce")
        oven_data = oven_data.dropna(subset=oven_columns, how="all")
        available_ovens = [column for column in oven_columns if oven_data[column].notna().any()]
        if oven_data.empty or not available_ovens:
            st.info("No oven temperature entries have been recorded yet.")
        else:
            heat_labels = oven_data.apply(
                lambda row: f"{row.get('shift_date') or 'Unassigned date'} {row.get('shift_name') or 'Unassigned shift'} · #{int(row['id'])}", axis=1
            ).tolist()
            heat = go.Figure(data=go.Heatmap(
                z=oven_data[available_ovens].T.to_numpy(), x=heat_labels,
                y=[f"Oven {int(column.split('_')[1])}" for column in available_ovens],
                colorscale=[[0, "#1F3B3D"], [0.5, "#F59E0B"], [1, "#EF4444"]],
                colorbar=dict(title="Temp"), hovertemplate="%{y}<br>%{x}<br>Temperature: %{z}<extra></extra>", connectgaps=False,
            ))
            heat.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               margin=dict(l=10, r=10, t=25, b=10), xaxis_title="Shift date · shift · roll ID", yaxis_title="Oven")
            st.plotly_chart(heat, use_container_width=True)
elif not data.empty:
    st.info("Production records exist, but no current factory metrics are available.")

st.info("Production Manager access is view-only. Use the Shift Reports page for detailed shift exports and activity history.")
render_footer()
