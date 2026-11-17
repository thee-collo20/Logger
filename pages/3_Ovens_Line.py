"""Station page for per-roll oven temperatures, line speed, and production time."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from auth import require_role
from db import get_all_logs, init_db, update_roll_fields
from nav import render_footer, render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
st.set_page_config(page_title="Ovens & Line | Biashara Masters Sawmill", page_icon="🪵", layout="wide")
user = require_role({"Admin", "Supervisor", "Operator", "Production Manager"})
render_nav()
init_db()
st.title("Ovens & Line")
if user["rank"] == "Production Manager":
    st.caption("Oven temperatures and line settings · read-only")
    records = get_all_logs(descending=False)
    if records:
        frame = pd.DataFrame(records)
        columns = ["id", "name", "shift_date", "shift_name", *[f"oven_{number}" for number in range(1, 7)], "line_speed", "log_time"]
        st.dataframe(frame[columns], use_container_width=True, hide_index=True)
    else:
        st.info("No production records are available yet.")
else:
    st.caption("Record oven temperatures and line settings once for the selected roll · East Africa Time")
    records = get_all_logs()
    if not records:
        st.info("No rolls are available yet. Create a roll on the Paper ID station first.")
    else:
        labels = {int(record["id"]): f"ID #{record['id']} - {record.get('name') or ''}" for record in records}
        records_by_id = {int(record["id"]): record for record in records}
        selected_id = st.selectbox(
            "Roll",
            options=list(labels),
            format_func=lambda roll_id: labels[roll_id],
        )
        selected_record = records_by_id[selected_id]

        def current_value(field: str) -> float:
            value = pd.to_numeric(selected_record.get(field), errors="coerce")
            return float(value) if pd.notna(value) else 0.0

        st.caption("Existing values are loaded when you select a roll, so updating one entry does not reset its other settings.")
        with st.form("ovens_line_form"):
            first_row = st.columns(2)
            with first_row[0]:
                oven_1 = st.number_input("Oven 1", value=current_value("oven_1"), step=1.0, format="%.1f")
            with first_row[1]:
                oven_2 = st.number_input("Oven 2", value=current_value("oven_2"), step=1.0, format="%.1f")
            second_row = st.columns(2)
            with second_row[0]:
                oven_3 = st.number_input("Oven 3", value=current_value("oven_3"), step=1.0, format="%.1f")
            with second_row[1]:
                oven_4 = st.number_input("Oven 4", value=current_value("oven_4"), step=1.0, format="%.1f")
            third_row = st.columns(2)
            with third_row[0]:
                oven_5 = st.number_input("Oven 5", value=current_value("oven_5"), step=1.0, format="%.1f")
            with third_row[1]:
                oven_6 = st.number_input("Oven 6", value=current_value("oven_6"), step=1.0, format="%.1f")
            line_speed = st.number_input("Line Speed (L/S)", min_value=0.0, value=current_value("line_speed"), step=0.1, format="%.2f")
            log_time = st.text_input(
                "Time (EAT, HH:MM:SS)",
                value=str(selected_record.get("log_time") or datetime.now(FACTORY_TIMEZONE).strftime("%H:%M:%S")),
            )
            submitted = st.form_submit_button("Save Ovens & Line", type="primary", use_container_width=True)
        if submitted:
            if not log_time.strip():
                st.error("Please enter a time.")
            elif update_roll_fields(selected_id, {
                "oven_1": oven_1, "oven_2": oven_2, "oven_3": oven_3, "oven_4": oven_4,
                "oven_5": oven_5, "oven_6": oven_6, "line_speed": line_speed, "log_time": log_time.strip(),
            }, actor=user["username"], rank=user["rank"], station="Ovens & Line"):
                st.success(f"Oven settings and line speed saved for {labels[selected_id]}.")
            else:
                st.error("The selected roll no longer exists. Refresh this page and try again.")
render_footer()
