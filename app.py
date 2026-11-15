"""Authenticated dashboard for reviewing production logs and factory output."""

from datetime import date, datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from auth import require_role
from db import COLUMNS, SHIFT_NAMES, get_all_logs, init_db, shift_for_datetime
from login_audit import get_last_successful_login
from nav import render_footer, render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
REPORT_COLUMNS = [*COLUMNS, "created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"]
OVEN_COLUMNS = [f"oven_{number}" for number in range(1, 7)]
st.set_page_config(page_title="Production Logs | Biashara Masters Sawmill", page_icon="🪵", layout="wide")
user = require_role({"Admin", "Supervisor", "Production Manager"}, allow_production_manager=True)
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
st.header("Production dashboard")
view_scope = st.radio(
    "Select production view",
    ["Current shift", "Specific shift date", "All shifts"],
    horizontal=True,
    key="dashboard_shift_scope",
    help="Choose a specific shift start date to see its production data, graph, and oven heatmap.",
)
if view_scope == "Current shift":
    selected_date_text = current_shift_date
    selected_shift = current_shift_name
    display_data = data[(data["shift_date"] == selected_date_text) & (data["shift_name"] == selected_shift)].copy()
    st.caption(f"Current {selected_shift} shift · {selected_date_text} (EAT)")
elif view_scope == "Specific shift date":
    filter_cols = st.columns(2)
    with filter_cols[0]:
        selected_date = st.date_input("Shift start date", value=date.fromisoformat(current_shift_date), format="YYYY-MM-DD", key="dashboard_selected_shift_date")
    with filter_cols[1]:
        selected_shift = st.selectbox("Shift", ["All shifts", *SHIFT_NAMES], key="dashboard_selected_shift")
    selected_date_text = selected_date.isoformat()
    date_mask = data["shift_date"] == selected_date_text
    if selected_shift != "All shifts":
        date_mask &= data["shift_name"] == selected_shift
    display_data = data[date_mask].copy()
    shift_caption = selected_shift if selected_shift != "All shifts" else "Day + Night"
    st.caption(f"Selected production: {selected_date_text} · {shift_caption} (EAT)")
else:
    selected_date_text = None
    selected_shift = "All shifts"
    display_data = data.copy()
    st.caption("All recorded shifts and dates")

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
if view_scope == "All shifts":
    report_suffix = "all_shifts"
elif view_scope == "Current shift":
    report_suffix = f"{current_shift_date}_{current_shift_name.lower()}_shift"
else:
    shift_suffix = "all_shifts" if selected_shift == "All shifts" else f"{selected_shift.lower()}_shift"
    report_suffix = f"{selected_date_text}_{shift_suffix}"
st.download_button(
    "⬇ Download production report (XLSX)",
    data=report_buffer.getvalue(),
    file_name=f"production_report_{report_suffix}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()
st.header("Factory overview")
st.caption("Totals, production graph, and oven heatmap reflect the selected view above.")
selected_rolls = len(display_data)
if selected_rolls:
    selected_output = pd.to_numeric(display_data["output"], errors="coerce").sum(min_count=1)
    resin_logged = int(display_data[["right_resin", "center_resin", "left_resin"]].notna().all(axis=1).sum())
    oven_logged = int(display_data[OVEN_COLUMNS].notna().all(axis=1).sum())
else:
    selected_output = None
    resin_logged = oven_logged = 0
metrics = st.columns(4)
metrics[0].metric("Rolls in view", f"{selected_rolls:,}")
metrics[1].metric("Production output", f"{selected_output:,.1f}" if selected_output is not None and pd.notna(selected_output) else "—")
metrics[2].metric("Resin completed", f"{resin_logged}/{selected_rolls}" if selected_rolls else "0/0")
metrics[3].metric("Oven settings completed", f"{oven_logged}/{selected_rolls}" if selected_rolls else "0/0")

if selected_rolls:
    chart_col, heat_col = st.columns([3, 2])
    with chart_col:
        st.subheader("Production output graph")
        chart_data = display_data.copy()
        chart_data["output"] = pd.to_numeric(chart_data["output"], errors="coerce")
        if view_scope == "All shifts":
            chart_data = chart_data.dropna(subset=["shift_date"])
            if chart_data.empty:
                st.info("No dated production records are available for the graph.")
            else:
                daily = chart_data.groupby("shift_date", as_index=False)["output"].sum(min_count=1).sort_values("shift_date")
                measure = st.radio("Production measure", ["Daily total (Day + Night)", "Cumulative total"], horizontal=True, key="dashboard_production_measure")
                if measure == "Cumulative total":
                    daily["plot_output"] = daily["output"].fillna(0).cumsum()
                    y_label = "Cumulative output (all shifts)"
                else:
                    daily["plot_output"] = daily["output"]
                    y_label = "Daily output (Day + Night)"
                chart = px.line(daily, x="shift_date", y="plot_output", markers=True,
                                labels={"shift_date": "Production date (EAT)", "plot_output": y_label}, template="plotly_dark")
                chart.update_traces(line_color="#F59E0B", marker_color="#FBBF24")
                chart.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=25, b=10))
                st.plotly_chart(chart, use_container_width=True)
        else:
            chart_data = chart_data.dropna(subset=["output"]).sort_values("id")
            if chart_data.empty:
                st.info("No production output values are available for this shift.")
            else:
                chart_data["Roll"] = chart_data.apply(lambda row: f"#{int(row['id'])} · {row.get('name') or 'Unnamed'}", axis=1)
                chart = px.bar(chart_data, x="Roll", y="output", color="shift_name",
                               labels={"Roll": "Roll", "output": "Production output", "shift_name": "Shift"},
                               template="plotly_dark", color_discrete_sequence=["#F59E0B", "#38BDF8"])
                chart.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=25, b=10))
                st.plotly_chart(chart, use_container_width=True)
    with heat_col:
        st.subheader("Oven temperature heatmap")
        oven_data = display_data.sort_values("id", ascending=True).copy()
        for column in OVEN_COLUMNS:
            oven_data[column] = pd.to_numeric(oven_data[column], errors="coerce")
        oven_data = oven_data.dropna(subset=OVEN_COLUMNS, how="all")
        available_ovens = [column for column in OVEN_COLUMNS if oven_data[column].notna().any()]
        if oven_data.empty or not available_ovens:
            st.info("No oven temperature entries have been recorded for this selection.")
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
else:
    st.info("No production records are available for the selected view.")

if user["rank"] == "Production Manager":
    st.info("Production Manager access is view-only.")
else:
    st.info("Use the Shift Reports page for detailed shift exports and activity history.")
render_footer()
