"""Password-protected admin dashboard with global and shift-specific views."""

import hmac
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import (
    COLUMNS,
    SHIFT_NAMES,
    generate_shift_xlsx,
    get_all_logs,
    init_db,
)
from nav import render_nav

st.set_page_config(page_title="Admin | Wood Lamination Logs", page_icon="🪵", layout="wide")

# Protect production records; configure admin_password in Streamlit Cloud Secrets.
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
    st.caption("Global production analytics include both day and night shifts. Shift reports are managed separately below.")
with logout_col:
    if st.button("Sign out", use_container_width=True):
        st.session_state["admin_authenticated"] = False
        st.rerun()

records = get_all_logs(descending=False)
data = pd.DataFrame(records)
if data.empty:
    data = pd.DataFrame(columns=[*COLUMNS, "created_at", "shift_date", "shift_name"])

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

    # Aggregate both shifts into one total per production shift-start date.
    # The date field represents the date the shift began; night-shift records
    # after midnight remain attributed to the previous evening's shift date.
    with global_chart_col:
        st.subheader("Global production output by date")
        dated = data.dropna(subset=["shift_date"]).copy()
        if dated.empty:
            st.info("No dated production records yet. Historical records without shift dates are omitted from this chart.")
        else:
            dated["output"] = pd.to_numeric(dated["output"], errors="coerce").fillna(0)
            daily = (
                dated.groupby("shift_date", as_index=False)["output"]
                .sum()
                .sort_values("shift_date")
            )
            measure = st.radio(
                "Production measure",
                ["Daily total (Day + Night)", "Cumulative total"],
                horizontal=True,
                key="global_production_measure",
            )
            if measure == "Cumulative total":
                daily["plot_output"] = daily["output"].cumsum()
                y_label = "Cumulative output (all shifts)"
            else:
                daily["plot_output"] = daily["output"]
                y_label = "Daily output (Day + Night)"
            chart = px.line(
                daily,
                x="shift_date",
                y="plot_output",
                markers=True,
                labels={"shift_date": "Production date (EAT)", "plot_output": y_label},
                template="plotly_dark",
            )
            chart.update_traces(line_color="#F59E0B", marker_color="#FBBF24")
            chart.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=25, b=10),
            )
            st.plotly_chart(chart, use_container_width=True)
            st.caption("Each date total includes all assigned Day and Night shift records for that shift start date.")

    # One global heatmap includes every roll with oven readings; each x-axis
    # label shows shift date, shift, and roll ID so the two shifts remain clear.
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
            def roll_label(row: pd.Series) -> str:
                shift_date = row.get("shift_date") or "Unassigned date"
                shift_name = row.get("shift_name") or "Unassigned shift"
                return f"{shift_date} {shift_name} · #{int(row['id'])}"

            heat_labels = oven_data.apply(roll_label, axis=1).tolist()
            heat = go.Figure(
                data=go.Heatmap(
                    z=oven_data[available_ovens].T.to_numpy(),
                    x=heat_labels,
                    y=[f"Oven {int(column.split('_')[1])}" for column in available_ovens],
                    colorscale=[[0, "#1F3B3D"], [0.5, "#F59E0B"], [1, "#EF4444"]],
                    colorbar=dict(title="Temp"),
                    hovertemplate="%{y}<br>%{x}<br>Temperature: %{z}<extra></extra>",
                    connectgaps=False,
                )
            )
            heat.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=25, b=10),
                xaxis_title="Shift date · shift · roll ID (all shifts)",
                yaxis_title="Oven",
            )
            st.plotly_chart(heat, use_container_width=True)

st.divider()
st.header("Date- and shift-specific log / export")
filter_col, shift_col = st.columns(2)
with filter_col:
    report_date = st.date_input("Shift start date", value=date.today(), format="YYYY-MM-DD")
with shift_col:
    shift_name = st.selectbox(
        "Shift to review/export",
        SHIFT_NAMES,
        help="Day: 07:00–18:59 · Night: 19:00–06:59 next day",
    )
shift_date_text = report_date.isoformat()
if total_rolls:
    selected = data[(data["shift_date"] == shift_date_text) & (data["shift_name"] == shift_name)].copy()
else:
    selected = data.copy()

st.caption(f"Selected report: {shift_date_text} · {shift_name} shift (EAT)")
if selected.empty:
    st.info("No records are assigned to this shift yet. You can still download an empty shift workbook as a template.")
else:
    st.metric("Rolls in selected shift", len(selected))
    st.dataframe(
        selected.sort_values("id", ascending=True)[[*COLUMNS, "created_at", "shift_date", "shift_name"]],
        use_container_width=True,
        hide_index=True,
    )

st.download_button(
    f"⬇ Download {shift_date_text} {shift_name} Shift XLSX",
    data=generate_shift_xlsx(shift_date_text, shift_name),
    file_name=f"wood_lamination_{shift_date_text}_{shift_name.lower()}_shift.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
