"""Station page for oven temperatures, line speed, and production time."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from auth import require_role
from db import get_all_rolls, init_db, update_roll_fields
from nav import render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")

st.set_page_config(page_title="Ovens & Line | Lamination Logger", page_icon="🪵", layout="centered")
user = require_role({"Admin", "Supervisor", "Operator"})
render_nav()
init_db()

st.title("Ovens & Line")
st.caption("Log process settings for the selected roll · East Africa Time")
rolls = get_all_rolls()
if not rolls:
    st.info("No rolls are available yet. Create a roll on the Paper ID station first.")
else:
    labels = {roll_id: f"ID #{roll_id} - {name}" for roll_id, name in rolls}
    selected_id = st.selectbox("Active roll", options=[roll_id for roll_id, _ in rolls], format_func=lambda roll_id: labels[roll_id])
    with st.form("ovens_line_form"):
        first_row = st.columns(2)
        with first_row[0]:
            oven_1 = st.number_input("Oven 1", step=1.0, format="%.1f")
        with first_row[1]:
            oven_2 = st.number_input("Oven 2", step=1.0, format="%.1f")
        second_row = st.columns(2)
        with second_row[0]:
            oven_3 = st.number_input("Oven 3", step=1.0, format="%.1f")
        with second_row[1]:
            oven_4 = st.number_input("Oven 4", step=1.0, format="%.1f")
        third_row = st.columns(2)
        with third_row[0]:
            oven_5 = st.number_input("Oven 5", step=1.0, format="%.1f")
        with third_row[1]:
            oven_6 = st.number_input("Oven 6", step=1.0, format="%.1f")
        line_speed = st.number_input("Line Speed (L/S)", min_value=0.0, value=0.0, step=0.1, format="%.2f")
        log_time = st.text_input("Time (EAT, HH:MM:SS)", value=datetime.now(FACTORY_TIMEZONE).strftime("%H:%M:%S"))
        submitted = st.form_submit_button("Save Ovens & Line", type="primary", use_container_width=True)
    if submitted:
        if not log_time.strip():
            st.error("Please enter a time.")
        else:
            saved = update_roll_fields(
                selected_id,
                {
                    "oven_1": oven_1, "oven_2": oven_2, "oven_3": oven_3,
                    "oven_4": oven_4, "oven_5": oven_5, "oven_6": oven_6,
                    "line_speed": line_speed, "log_time": log_time.strip(),
                },
                actor=user["username"], rank=user["rank"], station="Ovens & Line",
            )
            if saved:
                st.success(f"Oven settings and line speed saved for {labels[selected_id]}.")
            else:
                st.error("The selected roll no longer exists. Refresh this page and try again.")
