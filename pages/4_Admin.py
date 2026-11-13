"""Password-protected admin page for viewing production log records."""

import hmac

import pandas as pd
import streamlit as st

from db import COLUMNS, generate_exact_xlsx, get_all_logs, init_db
from nav import render_nav

st.set_page_config(page_title="Admin | Wood Lamination Logs", page_icon="🪵", layout="wide")

# Set this value in Streamlit Cloud: App settings → Secrets.
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
    st.title("🪵 Production Log Admin")
    st.caption("Read-only view of production records available in this app.")
with logout_col:
    if st.button("Sign out", use_container_width=True):
        st.session_state["admin_authenticated"] = False
        st.rerun()

col_refresh, col_download = st.columns([1, 2])
with col_refresh:
    if st.button("↻ Refresh data", use_container_width=True):
        st.rerun()
with col_download:
    st.download_button(
        "⬇ Download XLSX report",
        data=generate_exact_xlsx(),
        file_name="wood_lamination_production.xlsx",
        mime="application/vnd/openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

records = get_all_logs(descending=True)
if not records:
    st.info("No production records have been logged yet.")
else:
    data = pd.DataFrame(records, columns=COLUMNS)
    st.metric("Total rolls", len(data))
    st.dataframe(data, use_container_width=True, hide_index=True)
