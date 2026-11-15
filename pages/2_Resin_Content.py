"""Station page for logging and viewing resin content against an active roll."""

import pandas as pd
import streamlit as st

from auth import require_role
from db import COLUMNS, get_all_logs, init_db, update_roll_fields
from nav import render_footer, render_nav

st.set_page_config(page_title="Resin Content | Biashara Masters Sawmill", page_icon="🪵", layout="centered")
user = require_role({"Admin", "Supervisor", "Operator", "Production Manager"})
render_nav()
init_db()
st.title("Resin Content")
if user["rank"] == "Production Manager":
    st.caption("View production resin records · read-only")
    records = get_all_logs(descending=False)
    if records:
        frame = pd.DataFrame(records)
        st.dataframe(frame[["id", "name", "right_resin", "center_resin", "left_resin", "gsm", "output", "shift_date", "shift_name"]],
                     use_container_width=True, hide_index=True)
    else:
        st.info("No production records are available yet.")
else:
    st.caption("Enter resin content for the selected roll")
    rolls = get_all_logs(descending=True)
    if not rolls:
        st.info("No rolls are available yet. Create a roll on the Paper ID station first.")
    else:
        labels = {int(roll["id"]): f"ID #{roll['id']} - {roll.get('name') or ''}" for roll in rolls}
        selected_id = st.selectbox("Active roll", options=list(labels), format_func=lambda roll_id: labels[roll_id])
        with st.form("resin_content_form"):
            right = st.number_input("Right", min_value=0.0, value=0.0, step=0.1, format="%.3f")
            center = st.number_input("Center", min_value=0.0, value=0.0, step=0.1, format="%.3f")
            left = st.number_input("Left", min_value=0.0, value=0.0, step=0.1, format="%.3f")
            submitted = st.form_submit_button("Save Resin Content", type="primary", use_container_width=True)
        if submitted:
            if update_roll_fields(selected_id, {"right_resin": right, "center_resin": center, "left_resin": left},
                                  actor=user["username"], rank=user["rank"], station="Resin Content"):
                st.success(f"Resin content saved for {labels[selected_id]}.")
            else:
                st.error("The selected roll no longer exists. Refresh this page and try again.")
render_footer()
