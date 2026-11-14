"""Rank-protected production reports, roll maintenance, and audit history."""

from datetime import date
import logging
import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from auth import require_role
from db import (
    COLUMNS, SHIFT_NAMES, delete_roll, generate_shift_xlsx, get_all_logs,
    get_recent_activity, init_db, update_roll_fields,
)
from nav import render_footer, render_nav

LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="Shift Reports | Biashara Masters Sawmill", page_icon="🪵", layout="wide")
user = require_role({"Admin", "Supervisor"})
render_nav()
init_db()

st.title("🪵 Biashara Masters Sawmill — Production Control")
st.caption("Global production analytics, shift reports, and user-attributed logging history.")
records = get_all_logs(descending=False)
data = pd.DataFrame(records)
if data.empty:
    data = pd.DataFrame(columns=[*COLUMNS, "created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"])

st.header("Global factory overview")
st.caption("Charts aggregate all assigned production logs across Day and Night shifts.")
total_rolls = len(data)
oven_columns = [f"oven_{number}" for number in range(1, 7)]
if total_rolls:
    output_values = pd.to_numeric(data["output"], errors="coerce")
    total_output = output_values.sum(min_count=1)
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
    global_chart_col, global_heat_col = st.columns([3, 2])
    with global_chart_col:
        st.subheader("Global production output by date")
        dated = data.dropna(subset=["shift_date"]).copy()
        if dated.empty:
            st.info("No dated production records yet. Historical records without shift dates are omitted from this chart.")
        else:
            dated["output"] = pd.to_numeric(dated["output"], errors="coerce").fillna(0)
            daily = dated.groupby("shift_date", as_index=False)["output"].sum().sort_values("shift_date")
            measure = st.radio("Production measure", ["Daily total (Day + Night)", "Cumulative total"], horizontal=True, key="global_production_measure")
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
    with global_heat_col:
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

st.divider()
st.header("Date- and shift-specific log / export")
filter_col, shift_col = st.columns(2)
with filter_col:
    report_date = st.date_input("Shift start date", value=date.today(), format="YYYY-MM-DD")
with shift_col:
    shift_name = st.selectbox("Shift to review/export", SHIFT_NAMES, help="Day: 07:00–18:59 · Night: 19:00–06:59 next day")
shift_date_text = report_date.isoformat()
selected = data[(data["shift_date"] == shift_date_text) & (data["shift_name"] == shift_name)].copy() if total_rolls else data.copy()
st.caption(f"Selected report: {shift_date_text} · {shift_name} shift (EAT)")
if selected.empty:
    st.info("No records are assigned to this shift yet. You can still download an empty shift workbook as a template.")
else:
    st.metric("Rolls in selected shift", len(selected))
    report_columns = [*COLUMNS, "created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"]
    st.dataframe(selected.sort_values("id", ascending=True)[report_columns], use_container_width=True, hide_index=True)
st.download_button(
    f"⬇ Download {shift_date_text} {shift_name} Shift XLSX",
    data=generate_shift_xlsx(shift_date_text, shift_name),
    file_name=f"wood_lamination_{shift_date_text}_{shift_name.lower()}_shift.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

if user["rank"] == "Admin":
    st.divider()
    st.header("Edit or delete roll information")
    st.caption("These controls are restricted to Admin. Every edit and deletion is recorded in the activity history.")
    if data.empty:
        st.info("There are no rolls to edit or delete.")
    else:
        roll_ids = data["id"].astype(int).tolist()
        selected_roll_id = st.selectbox(
            "Select roll", options=roll_ids,
            format_func=lambda roll_id: f"#{roll_id} — {data.loc[data['id'] == roll_id, 'name'].iloc[0] or 'Unnamed roll'}",
            key="admin_roll_selection",
        )
        original = data.loc[data["id"] == selected_roll_id].iloc[0]

        def numeric_value(field: str) -> float:
            value = pd.to_numeric(original.get(field), errors="coerce")
            return float(value) if pd.notna(value) else 0.0

        with st.form("admin_edit_roll_form"):
            edit_name = st.text_input("Paper name", value=str(original.get("name") or ""))
            edit_gsm = st.number_input("GSM", min_value=0.0, value=numeric_value("gsm"), step=1.0)
            edit_output = st.number_input("Output", min_value=0.0, value=numeric_value("output"), step=1.0)
            resin_cols = st.columns(3)
            with resin_cols[0]:
                edit_right = st.number_input("Right resin", min_value=0.0, value=numeric_value("right_resin"), step=0.1, format="%.3f")
            with resin_cols[1]:
                edit_center = st.number_input("Center resin", min_value=0.0, value=numeric_value("center_resin"), step=0.1, format="%.3f")
            with resin_cols[2]:
                edit_left = st.number_input("Left resin", min_value=0.0, value=numeric_value("left_resin"), step=0.1, format="%.3f")
            oven_values = []
            oven_cols = st.columns(3)
            for index, column in enumerate(oven_columns):
                with oven_cols[index % 3]:
                    oven_values.append(st.number_input(f"Oven {index + 1}", value=numeric_value(column), step=1.0, format="%.1f"))
            edit_speed = st.number_input("Line speed", min_value=0.0, value=numeric_value("line_speed"), step=0.1, format="%.2f")
            edit_time = st.text_input("Log time (EAT)", value=str(original.get("log_time") or ""))
            try:
                initial_shift_date = date.fromisoformat(str(original.get("shift_date"))) if pd.notna(original.get("shift_date")) else date.today()
            except ValueError:
                initial_shift_date = date.today()
            edit_shift_date = st.date_input("Shift start date", value=initial_shift_date, format="YYYY-MM-DD")
            shift_options = list(SHIFT_NAMES)
            old_shift = original.get("shift_name")
            if old_shift not in shift_options:
                shift_options.append("Unassigned")
            edit_shift = st.selectbox("Shift", shift_options,
                                      index=shift_options.index(old_shift) if old_shift in shift_options else shift_options.index("Unassigned"))
            save_edit = st.form_submit_button("Save roll changes", type="primary", use_container_width=True)
        if save_edit:
            cleaned_name = edit_name.strip()
            if not cleaned_name:
                st.error("Paper name cannot be empty.")
            else:
                changes = {
                    "name": cleaned_name, "gsm": edit_gsm, "output": edit_output,
                    "right_resin": edit_right, "center_resin": edit_center, "left_resin": edit_left,
                    **{column: value for column, value in zip(oven_columns, oven_values)},
                    "line_speed": edit_speed, "log_time": edit_time.strip(),
                    "shift_date": edit_shift_date.isoformat() if edit_shift != "Unassigned" else None,
                    "shift_name": edit_shift if edit_shift != "Unassigned" else None,
                }
                if update_roll_fields(selected_roll_id, changes, actor=user["username"], rank=user["rank"], station="Admin edit"):
                    st.success(f"Roll #{selected_roll_id} updated.")
                    st.rerun()
                else:
                    st.error("That roll no longer exists. Refresh and try again.")

        with st.form("admin_delete_roll_form"):
            confirm_delete = st.checkbox(f"I understand that deleting roll #{selected_roll_id} cannot be undone.")
            delete_submitted = st.form_submit_button("Delete selected roll", type="secondary", use_container_width=True)
        if delete_submitted:
            if not confirm_delete:
                st.error("Confirm the deletion before continuing.")
            elif delete_roll(selected_roll_id, actor=user["username"], rank=user["rank"]):
                st.success(f"Roll #{selected_roll_id} deleted.")
                st.rerun()
            else:
                st.error("That roll no longer exists. Refresh and try again.")

st.divider()
st.header("Who logged each shift entry")
try:
    activity = pd.DataFrame(get_recent_activity())
except (sqlite3.Error, OSError, ValueError, TypeError):
    LOGGER.exception("The activity history could not be displayed")
    activity = pd.DataFrame()
if activity.empty:
    st.info("Activity history is temporarily unavailable or no activity has been recorded yet. Production reports and roll data remain available.")
else:
    st.dataframe(activity, use_container_width=True, hide_index=True)
render_footer()
