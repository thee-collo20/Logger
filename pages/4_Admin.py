"""Password-protected admin dashboard and production record management."""

import hmac
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import (
    COLUMNS,
    delete_roll,
    generate_exact_xlsx,
    get_all_logs,
    init_db,
    update_roll_fields,
)
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
    # Timestamps contain the +03:00 EAT offset. Convert instants into factory-local dates.
    data["created_at_eat"] = pd.to_datetime(data["created_at"], errors="coerce", utc=True).dt.tz_convert(FACTORY_TIMEZONE)
    dated = data.dropna(subset=["created_at_eat"]).copy()
    trend_col, heatmap_col = st.columns([3, 2])

    with trend_col:
        st.subheader("Production output over time — East Africa Time")
        if dated.empty:
            st.info("No dated production records yet. Older records have no recoverable calendar date.")
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
            trend = px.line(
                daily,
                x="production_date",
                y=y_column,
                markers=True,
                labels={"production_date": "Production date (EAT)", y_column: y_label},
                title=view,
                template="plotly_dark",
            )
            trend.update_traces(line_color="#F59E0B", marker_color="#FBBF24")
            trend.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(trend, use_container_width=True)
            st.caption("Production dates use Africa/Nairobi (EAT, UTC+03:00).")

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

st.subheader("All production records")
action_col, download_col = st.columns([1, 2])
with action_col:
    if st.button("↻ Refresh dashboard", use_container_width=True):
        st.rerun()
with download_col:
    st.download_button(
        "⬇ Download XLSX report",
        data=generate_exact_xlsx(),
        file_name="wood_lamination_production.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

if total_rolls:
    st.dataframe(data.sort_values("id", ascending=True)[[*COLUMNS, "created_at"]], use_container_width=True, hide_index=True)
else:
    st.info("No production records have been logged yet.")

st.divider()
st.header("Correct or remove a record")
st.warning("Admin-only: edits and deletions affect the production log and cannot be undone.")
if not records:
    st.caption("There are no records to edit or delete.")
else:
    record_by_id = {int(row["id"]): row for row in records}
    selected_id = st.selectbox(
        "Select roll ID to manage",
        options=list(record_by_id),
        format_func=lambda roll_id: f"ID #{roll_id} — {record_by_id[roll_id]['name'] or '(unnamed)'}",
        key="admin_manage_roll_id",
    )
    current = record_by_id[selected_id]

    with st.expander(f"Edit roll #{selected_id}"):
        with st.form(f"admin_edit_form_{selected_id}"):
            name = st.text_input("Name", value=current["name"] or "")
            col1, col2, col3 = st.columns(3)
            with col1:
                gsm = st.number_input("GSM", value=float(current["gsm"] or 0), format="%.2f")
                output = st.number_input("Output", value=float(current["output"] or 0), format="%.2f")
                right_resin = st.number_input("Right resin", value=float(current["right_resin"] or 0), format="%.3f")
                center_resin = st.number_input("Center resin", value=float(current["center_resin"] or 0), format="%.3f")
                left_resin = st.number_input("Left resin", value=float(current["left_resin"] or 0), format="%.3f")
            with col2:
                oven_1 = st.number_input("Oven 1", value=float(current["oven_1"] or 0), format="%.1f")
                oven_2 = st.number_input("Oven 2", value=float(current["oven_2"] or 0), format="%.1f")
                oven_3 = st.number_input("Oven 3", value=float(current["oven_3"] or 0), format="%.1f")
                oven_4 = st.number_input("Oven 4", value=float(current["oven_4"] or 0), format="%.1f")
            with col3:
                oven_5 = st.number_input("Oven 5", value=float(current["oven_5"] or 0), format="%.1f")
                oven_6 = st.number_input("Oven 6", value=float(current["oven_6"] or 0), format="%.1f")
                line_speed = st.number_input("Line speed (L/S)", value=float(current["line_speed"] or 0), format="%.2f")
                log_time = st.text_input("Time (EAT, HH:MM:SS)", value=current["log_time"] or "")
            save = st.form_submit_button("Save changes", type="primary", use_container_width=True)
        if save:
            cleaned_name = name.strip()
            if not cleaned_name:
                st.error("Name cannot be blank.")
            else:
                update_roll_fields(selected_id, {
                    "name": cleaned_name,
                    "gsm": gsm,
                    "output": output,
                    "right_resin": right_resin,
                    "center_resin": center_resin,
                    "left_resin": left_resin,
                    "oven_1": oven_1,
                    "oven_2": oven_2,
                    "oven_3": oven_3,
                    "oven_4": oven_4,
                    "oven_5": oven_5,
                    "oven_6": oven_6,
                    "line_speed": line_speed,
                    "log_time": log_time.strip(),
                })
                st.success(f"Roll #{selected_id} updated.")
                st.rerun()

    with st.expander(f"Delete roll #{selected_id}"):
        st.warning("Deleting this roll permanently removes it from the database and reports.")
        confirm_delete = st.checkbox("Confirm permanent deletion", key=f"confirm_delete_{selected_id}")
        if st.button("Delete selected roll", disabled=not confirm_delete, type="secondary"):
            if delete_roll(selected_id):
                st.success(f"Roll #{selected_id} deleted.")
                st.rerun()
            st.error("The roll no longer exists. Refresh and retry.")
