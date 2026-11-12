"""Station page for creating a paper / roll ID."""

import streamlit as st

from db import get_next_id, init_db, insert_roll

st.set_page_config(page_title="Paper ID | Lamination Logger", page_icon="🪵", layout="centered")
st.markdown("<style>[data-testid=\"stSidebar\"] {display: none;}</style>", unsafe_allow_html=True)
init_db()

st.title("Paper ID")
st.caption("Create a new production roll")
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
        roll_id = insert_roll(name, gsm, output)
        st.success(f"Logged successfully — ID #{roll_id}: {name}")
