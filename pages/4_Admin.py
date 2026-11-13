"""Password-protected admin dashboard for production log records."""

import hmac

import pandas as pd
import streamlit as st

from db import COLUMNS, generate_exact_xlsx, get_all_logs, init_db
from nav import render_nav

st.set_page_config(page_title="Admin | Wood Lamination Logs", page_icon="🪵", layout="wide")

# Configure in Streamlit Cloud: App settings → Secrets.
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
    st.caption("Factory overview · wood lamination production records")
with logout_col:
    if st.button("Sign out", use_container_width=True):
        st.session_state["admin_authenticated"] = False
        st.rerun()

records = get_all_logs(descending=True)
data = pd.DataFrame(records, columns=COLUMNS)

st.subheader("Factory at a glance")
if data.empty:
    st.info("No production records have been logged yet.")
    total_rolls = 0
    avg_gsm = avg_output = avg_speed = 0.0
    resin_logged = oven_logged = 0
else:
    total_rolls = len(data)
    avg_gsm = data["gsm"].dropna().mean() if data["gsm"].notna().any() else 0.0
    avg_output = data["output"].dropna().mean() if data["output"].notna().any() else 0.0
    avg_speed = data["line_speed"].dropna().mean() if data["line_speed"].notna().any() else 0.0
    resin_logged = int(data[["right_resin", "center_resin", "left_resin"]].notna().all(axis=1).sum())
    oven_columns = [f"oven_{number}" for number in range(1, 7)]
    oven_logged = int(data[oven_columns].notna().all(axis=1).sum())

metric_cols = st.columns(5)
metric_cols[0].metric("Total rolls", f"{total_rolls:,}")
metric_cols[1].metric("Average GSM", f"{avg_gsm:,.1f}")
metric_cols[2].metric("Average output", f"{avg_output:,.1f}")
metric_cols[3].metric("Resin logged", f"{resin_logged}/{total_rolls}" if total_rolls else "0/0")
metric_cols[4].metric("Oven settings logged", f"{oven_logged}/{total_rolls}" if total_rolls else "0/0")
st.caption(f"Average line speed: {avg_speed:,.2f} L/S")

st.subheader("Production records")
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

if not data.empty:
    # Display in ascending roll-ID order for a chronological factory log.
    display_data = data.sort_values("id", ascending=True)
    st.dataframe(display_data, use_container_width=True, hide_index=True)
