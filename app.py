"""Supervisor dashboard for wood lamination production logs."""

import pandas as pd
import streamlit as st

from db import COLUMNS, get_all_logs, init_db
from nav import render_nav

st.set_page_config(page_title="Production Logs | Supervisor", page_icon="🪵", layout="wide")
render_nav()
init_db()

st.title("🪵 Wood Lamination — Production Logs")
st.caption("Supervisor dashboard · production records in ascending roll-ID order")

if st.button("↻ Refresh Data", use_container_width=True):
    st.rerun()

records = get_all_logs(descending=False)
if records:
    display_columns = [*COLUMNS, "shift_date", "shift_name"]
    display_data = pd.DataFrame(records).sort_values("id", ascending=True)
    st.dataframe(display_data[display_columns], use_container_width=True, hide_index=True)
else:
    st.info("No production logs yet. Records entered at the stations will appear here.")

st.info("Shift reports and record corrections are available in the password-protected Admin page.")
