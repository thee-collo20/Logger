"""Station page for creating and reviewing paper / roll IDs."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from auth import require_role
from db import get_all_logs, init_db, insert_roll, shift_for_datetime
from nav import render_footer, render_nav

FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
st.set_page_config(page_title="Paper ID | Biashara Masters Sawmill", page_icon="🪵", layout="centered")
user = require_role({"Admin", "Supervisor", "Operator", "Secretary", "Production Manager"})
render_nav()
init_db()


def _shift_paper_ids(records: list[dict]) -> list[dict]:
    """Assign display IDs from 1 independently within each dated shift."""
    counters: dict[tuple[str, str], int] = {}
    result = []
    for record in sorted(records, key=lambda item: item["id"]):
        shift_date = record.get("shift_date") or "Unassigned"
        shift_name = record.get("shift_name") or "Unassigned"
        key = (shift_date, shift_name)
        counters[key] = counters.get(key, 0) + 1
        result.append({"Paper ID": counters[key], "Name": record.get("name") or "", "Shift date": shift_date, "Shift": shift_name})
    return result


records = get_all_logs(descending=False)
now = datetime.now(FACTORY_TIMEZONE)
current_shift_date, current_shift_name = shift_for_datetime(now)
current_shift_count = sum(
    record.get("shift_date") == current_shift_date and record.get("shift_name") == current_shift_name
    for record in records
)
next_paper_id = current_shift_count + 1

st.title("Paper ID")
st.caption("Create a new wood lamination production roll. Paper IDs restart at 1 for each shift.")
st.markdown(f"### Upcoming Paper ID: **#{next_paper_id}**")
if user["rank"] == "Production Manager":
    st.info("Production Manager access is view-only.")
else:
    with st.form("paper_id_form", clear_on_submit=True):
        name_input = st.text_input("Wood Lamination Paper Name", placeholder="Enter paper name")
        gsm = st.number_input("GSM", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        output = st.number_input("Output", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        submitted = st.form_submit_button("Save Paper ID", type="primary", use_container_width=True)
    if submitted:
        name = name_input.strip()
        if not name:
            st.error("Please enter a paper name.")
        else:
            name = name[0].upper() + name[1:]
            insert_roll(name, gsm, output, actor=user["username"], rank=user["rank"])
            st.success(f"Logged successfully — Paper ID #{next_paper_id}: {name}")
st.divider()
st.subheader("Shift Paper ID register")
if records:
    register = pd.DataFrame(_shift_paper_ids(records))
    st.dataframe(register, use_container_width=True, hide_index=True)
else:
    st.info("No roll IDs have been created yet.")
render_footer()
