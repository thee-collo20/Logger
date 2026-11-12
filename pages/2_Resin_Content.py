"""Station page for logging resin content against an active roll."""

import streamlit as st

from db import get_all_rolls, init_db, update_roll_fields

st.set_page_config(page_title="Resin Content | Lamination Logger", page_icon="🪵", layout="centered")
st.markdown("<style>[data-testid=\"stSidebar\"] {display: none;}</style>", unsafe_allow_html=True)
init_db()

st.title("Resin Content")
st.caption("Enter resin content for the selected roll")
rolls = get_all_rolls()
if not rolls:
    st.info("No rolls are available yet. Create a roll on the Paper ID station first.")
else:
    labels = {roll_id: f"ID #{roll_id} - {name}" for roll_id, name in rolls}
    selected_id = st.selectbox(
        "Active roll", options=[roll_id for roll_id, _ in rolls],
        format_func=lambda roll_id: labels[roll_id], index=0,
    )
    with st.form("resin_content_form"):
        right = st.number_input("Right", min_value=0.0, value=0.0, step=0.1, format="%.3f")
        center = st.number_input("Center", min_value=0.0, value=0.0, step=0.1, format="%.3f")
        left = st.number_input("Left", min_value=0.0, value=0.0, step=0.1, format="%.3f")
        submitted = st.form_submit_button("Save Resin Content", type="primary", use_container_width=True)
    if submitted:
        if update_roll_fields(selected_id, {"right_resin": right, "center_resin": center, "left_resin": left}):
            st.success(f"Resin content saved for {labels[selected_id]}.")
        else:
            st.error("The selected roll no longer exists. Refresh this page and try again.")
