"""Supervisor dashboard for wood lamination production logs."""

import pandas as pd
import streamlit as st

from db import COLUMNS, generate_exact_xlsx, get_all_logs, init_db
from nav import render_nav

st.set_page_config(page_title="Production Logs | Supervisor", page_icon="🪵", layout="wide")
render_nav()
init_db()

st.title("🪵 Wood Lamination — Production Logs")
st.caption("Supervisor dashboard · production records in roll-ID order")

refresh_col, download_col = st.columns([1, 2])
with refresh_col:
    if st.button("↻ Refresh Data", use_container_width=True):
        st.rerun()
with download_col:
    st.download_button(
        "⬇ Download Exact XLSX Report",
        data=generate_exact_xlsx(),
        file_name="wood_lamination_production.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

records = get_all_logs(descending=False)
if records:
    # Explicit sort keeps the displayed register ascending by Paper ID.
    display_data = pd.DataFrame(records, columns=COLUMNS).sort_values("id", ascending=True)
    st.dataframe(display_data, use_container_width=True, hide_index=True)
else:
    st.info("No production logs yet. Records entered at the stations will appear here.")

st.info("Record corrections and deletions are restricted to the password-protected Admin page.")
