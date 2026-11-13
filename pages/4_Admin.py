"""Password-protected admin dashboard and date/shift report management."""

import hmac
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import (
    COLUMNS,
    SHIFT_NAMES,
    delete_roll,
    generate_shift_xlsx,
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
head_col, logout_col = st.columns([5, 1])
with head_col:
    st.title("🪵 Production Control Dashboard")
    st.caption("Shift-based production overview · dates and times in East Africa Time")
with logout_col:
    if st.button("Sign out", use_container_width=True):
        st.session_state["admin_authenticated"] = False
        st.rerun()

records = get_all_logs(descending=False)
data = pd.DataFrame(records)
if data.empty:
    data = pd.DataFrame(columns=[*COLUMNS, "created_at", "shift_date", "shift_name"])

# Admin chooses a shift to review/export. Shift date is the date the shift began;
# a night shift runs 19:00 through 06:59 the following morning.
st.header("Shift log and report")
filter_col, shift_col = st.columns(2)
with filter_col:
    report_date = st.date_input("Shift start date", value=date.today(), format="YYYY-MM-DD")
with shift_col:
    shift_name = st.selectbox("Shift", SHIFT_NAMES, help="Day: 07:00–18:59 · Night: 19:00–06:59 next day")
shift_date_text = report_date.isoformat()
if not data.empty:
    selected = data[(data["shift_date"] == shift_date_text) & (data["shift_name"] == shift_name)].copy()
else:
    selected = data.copy()

st.caption(f"Selected report: {shift_date_text} · {shift_name} shift (EAT)")
if not selected.empty:
    st.metric("Rolls in selected shift", len(selected))
else:
    st.info("No records are assigned to this shift yet. You can still download an empty shift workbook as a template.")

st.download_button(
    f"⬇ Download {shift_date_text} {shift_name} Shift XLSX",
    data=generate_shift_xlsx(shift_date_text, shift_name),
    file_name=f"wood_lamination_{shift_date_text}_{shift_name.lower()}_shift.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

# Overview metrics and charts use all assigned records; reports remain shift-separated.
if not data.empty:
    st.subheader("Factory at a glance")
    total_rolls = len(data)
    oven_cols = [f"oven_{number}" for number in range(1, 7)]
    complete_resin = int(data[["right_resin", "center_resin", "left_resin"]].notna().all(axis=1).sum())
    complete_ovens = int(data[oven_cols].notna().all(axis=1).sum())
    m = st.columns(4)
    m[0].metric("Total rolls", f"{total_rolls:,}")
    m[1].metric("Total output", f"{pd.to_numeric(data['output'], errors='coerce').sum():,.1f}")
    m[2].metric("Resin logged", f"{complete_resin}/{total_rolls}")
    m[3].metric("Oven settings logged", f"{complete_ovens}/{total_rolls}")

    trend_data = data.dropna(subset=["shift_date", "shift_name"]).copy()
    if not trend_data.empty:
        trend_data["output"] = pd.to_numeric(trend_data["output"], errors="coerce").fillna(0)
        daily = trend_data.groupby(["shift_date", "shift_name"], as_index=False)["output"].sum()
        daily["shift"] = daily["shift_name"] + " shift"
        st.subheader("Output by production date and shift")
        trend = px.line(
            daily, x="shift_date", y="output", color="shift", markers=True,
            labels={"shift_date": "Shift start date (EAT)", "output": "Output", "shift": "Shift"},
            template="plotly_dark",
            color_discrete_map={"Day shift": "#F59E0B", "Night shift": "#38BDF8"},
        )
        trend.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(trend, use_container_width=True)

    st.subheader(f"Oven temperatures · {shift_date_text} {shift_name} shift")
    oven_data = selected.sort_values("id", ascending=True).set_index("id")[oven_cols].apply(pd.to_numeric, errors="coerce")
    oven_data = oven_data.dropna(axis=1, how="all")
    if oven_data.empty or oven_data.shape[1] == 0:
        st.info("No oven temperature entries in the selected shift yet.")
    else:
        heat = go.Figure(data=go.Heatmap(
            z=oven_data.T.to_numpy(),
            x=[f"#{roll_id}" for roll_id in oven_data.index],
            y=[f"Oven {number}" for number in range(1, 7) if f"oven_{number}" in oven_data.columns],
            colorscale=[[0, "#1F3B3D"], [0.5, "#F59E0B"], [1, "#EF4444"]],
            colorbar=dict(title="Temp"), hovertemplate="%{y}<br>Roll %{x}<br>Temp: %{z}<extra></extra>",
        ))
        heat.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis_title="Roll ID", yaxis_title="Oven")
        st.plotly_chart(heat, use_container_width=True)

st.subheader(f"Records · {shift_date_text} {shift_name} shift")
if selected.empty:
    st.caption("No records to display for this date and shift.")
else:
    st.dataframe(selected.sort_values("id", ascending=True)[[*COLUMNS, "created_at", "shift_date", "shift_name"]], use_container_width=True, hide_index=True)

st.divider()
st.header("Correct or remove a record")
st.warning("Admin-only: edits and deletions affect the production log and cannot be undone.")
if data.empty:
    st.caption("There are no records to manage.")
else:
    record_by_id = {int(row["id"]): row for row in records}
    selected_id = st.selectbox(
        "Select roll ID to manage", options=list(record_by_id),
        format_func=lambda roll_id: f"ID #{roll_id} — {record_by_id[roll_id]['name'] or '(unnamed)'} · {record_by_id[roll_id].get('shift_date') or 'Unassigned'} {record_by_id[roll_id].get('shift_name') or ''}",
        key="admin_manage_roll_id",
    )
    current = record_by_id[selected_id]
    with st.expander(f"Edit roll #{selected_id}"):
        with st.form(f"admin_edit_form_{selected_id}"):
            name = st.text_input("Name", value=current["name"] or "")
            c1, c2, c3 = st.columns(3)
            with c1:
                gsm = st.number_input("GSM", value=float(current["gsm"] or 0), format="%.2f")
                output = st.number_input("Output", value=float(current["output"] or 0), format="%.2f")
                right = st.number_input("Right resin", value=float(current["right_resin"] or 0), format="%.3f")
                center = st.number_input("Center resin", value=float(current["center_resin"] or 0), format="%.3f")
                left = st.number_input("Left resin", value=float(current["left_resin"] or 0), format="%.3f")
            with c2:
                oven_1 = st.number_input("Oven 1", value=float(current["oven_1"] or 0), format="%.1f")
                oven_2 = st.number_input("Oven 2", value=float(current["oven_2"] or 0), format="%.1f")
                oven_3 = st.number_input("Oven 3", value=float(current["oven_3"] or 0), format="%.1f")
                oven_4 = st.number_input("Oven 4", value=float(current["oven_4"] or 0), format="%.1f")
            with c3:
                oven_5 = st.number_input("Oven 5", value=float(current["oven_5"] or 0), format="%.1f")
                oven_6 = st.number_input("Oven 6", value=float(current["oven_6"] or 0), format="%.1f")
                speed = st.number_input("Line speed (L/S)", value=float(current["line_speed"] or 0), format="%.2f")
                log_time = st.text_input("Time (EAT)", value=current["log_time"] or "")
            move_date_text = st.text_input("Shift start date (YYYY-MM-DD)", value=current.get("shift_date") or "")
            move_shift = st.selectbox("Assigned shift", SHIFT_NAMES, index=SHIFT_NAMES.index(current["shift_name"]) if current.get("shift_name") in SHIFT_NAMES else 0)
            save = st.form_submit_button("Save changes", type="primary", use_container_width=True)
        if save:
            cleaned_name = name.strip()
            try:
                date.fromisoformat(move_date_text)
                if not cleaned_name:
                    raise ValueError("Name cannot be blank.")
                update_roll_fields(selected_id, {
                    "name": cleaned_name, "gsm": gsm, "output": output,
                    "right_resin": right, "center_resin": center, "left_resin": left,
                    "oven_1": oven_1, "oven_2": oven_2, "oven_3": oven_3,
                    "oven_4": oven_4, "oven_5": oven_5, "oven_6": oven_6,
                    "line_speed": speed, "log_time": log_time.strip(),
                    "shift_date": move_date_text, "shift_name": move_shift,
                })
                st.success(f"Roll #{selected_id} updated.")
                st.rerun()
            except ValueError as exc:
                st.error(f"Invalid edit: {exc}")

    with st.expander(f"Delete roll #{selected_id}"):
        st.warning("Deleting this roll permanently removes it from the database and reports.")
        confirm = st.checkbox("Confirm permanent deletion", key=f"confirm_delete_{selected_id}")
        if st.button("Delete selected roll", disabled=not confirm, type="secondary"):
            if delete_roll(selected_id):
                st.success(f"Roll #{selected_id} deleted.")
                st.rerun()
            st.error("The roll no longer exists. Refresh and retry.")
