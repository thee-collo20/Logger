"""Authenticated dashboard for reviewing production logs."""

import pandas as pd
import streamlit as st

from auth import require_role
from db import COLUMNS, get_all_logs, init_db
from nav import render_nav

st.set_page_config(page_title="Production Logs | Supervisor", page_icon="🪵", layout="wide")
user = require_role({"Admin", "Supervisor"})
render_nav()
init_db()

st.title("🪵 Wood Lamination — Production Logs")
st.caption(f"Supervisor dashboard · signed in as {user['username']} ({user['rank']})")

if st.button("↻ Refresh Data", use_container_width=True):
    st.rerun()

records = get_all_logs(descending=False)
if records:
    display_columns = [*COLUMNS, "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"]
    display_data = pd.DataFrame(records).sort_values("id", ascending=True)
    st.dataframe(display_data[display_columns], use_container_width=True, hide_index=True)
else:
    st.info("No production logs yet. Records entered at the stations will appear here.")

st.info("Shift reports and record attribution are available in the Shift Reports page.")
