"""Admin page: read-only view of all production log records."""

import pandas as pd
import streamlit as st

from db import COLUMNS, generate_exact_xlsx, get_all_logs, init_db
from nav import render_nav

st.set_page_config(page_title="Admin | Wood Lamination Logs", page_icon="🪵", layout="wide")
render_nav()
init_db()

st.title("🪵 Production Log Admin")
st.caption("Read-only view of all records currently available in the app database.")

col_refresh, col_download = st.columns([1, 2])
with col_refresh:
    if st.button("↻ Refresh data", use_container_width=True):
        st.rerun()
with col_download:
    st.download_button(
        "⬇ Download XLSX report",
        data=generate_exact_xlsx(),
        file_name="wood_lamination_production.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

records = get_all_logs(descending=True)
if not records:
    st.info("No production records have been logged yet.")
else:
    data = pd.DataFrame(records, columns=COLUMNS)
    st.metric("Total rolls", len(data))
    st.dataframe(data, use_container_width=True, hide_index=True)
