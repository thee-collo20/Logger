"""Station page for creating and reviewing paper / roll IDs."""

import pandas as pd
import streamlit as st

from auth import require_role
from db import get_all_rolls, get_next_id, init_db, insert_roll
from nav import render_footer, render_nav

st.set_page_config(page_title="Paper ID | Biashara Masters Sawmill", page_icon="🪵", layout="centered")
user = require_role({"Admin", "Supervisor", "Operator"})
render_nav()
init_db()

st.title("Paper ID")
st.caption("Create a new wood lamination production roll")
st.markdown(f"### Upcoming Roll ID: **#{get_next_id()}**")
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
        roll_id = insert_roll(name, gsm, output, actor=user["username"], rank=user["rank"])
        st.success(f"Logged successfully — ID #{roll_id}: {name}")
st.divider()
st.subheader("Roll ID register")
rolls = get_all_rolls()
if rolls:
    register = pd.DataFrame(rolls, columns=["ID", "Name"]).sort_values("ID", ascending=True)
    st.dataframe(register, use_container_width=True, hide_index=True)
else:
    st.info("No roll IDs have been created yet.")
render_footer()
