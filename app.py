"""Authenticated dashboard for reviewing production logs."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from auth import require_role
from db import COLUMNS, get_all_logs, init_db, shift_for_datetime
from login_audit import get_last_successful_login
from nav import render_footer, render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
st.set_page_config(page_title="Production Logs | Biashara Masters Sawmill", page_icon="🪵", layout="wide")
user = require_role({"Admin", "Supervisor"})
render_nav()
init_db()

st.title("🪵 Biashara Masters Sawmill — Production Logs")
st.caption(f"Supervisor dashboard · signed in as {user['username']} ({user['rank']})")
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
    data = pd.DataFrame(columns=[*COLUMNS, "created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"])

current_shift_date, current_shift_name = shift_for_datetime(datetime.now(FACTORY_TIMEZONE))
st.subheader("Current shift production")
view_scope = st.radio(
    "Show production for",
    ["Current shift", "All shifts"],
    horizontal=True,
    key="dashboard_shift_scope",
    help="Current shift shows only the active Day or Night shift in East Africa Time.",
)
if view_scope == "Current shift":
    display_data = data[
        (data["shift_date"] == current_shift_date)
        & (data["shift_name"] == current_shift_name)
    ].copy()
    st.caption(f"Current {current_shift_name} shift · {current_shift_date} (EAT)")
else:
    display_data = data.copy()
    st.caption("All recorded shifts")

output_total = pd.to_numeric(display_data["output"], errors="coerce").sum(min_count=1)
metric_cols = st.columns(2)
metric_cols[0].metric("Rolls", f"{len(display_data):,}")
metric_cols[1].metric("Total production output", f"{output_total:,.1f}" if pd.notna(output_total) else "—")
if display_data.empty:
    if view_scope == "Current shift":
        st.info("No production logs have been recorded for the current shift yet.")
    else:
        st.info("No production logs yet. Records entered at the stations will appear here.")
else:
    display_columns = [*COLUMNS, "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"]
    st.dataframe(display_data.sort_values("id", ascending=True)[display_columns], use_container_width=True, hide_index=True)
st.info("Shift reports and record attribution are available in the Shift Reports page.")
render_footer()
