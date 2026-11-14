"""Authenticated OCR page for reading and reviewing resin and output values."""

import hashlib
import math

import streamlit as st

from auth import require_role
from db import get_all_rolls, init_db, update_roll_fields
from nav import render_footer, render_nav
from ocr_tools import PRODUCTION_FIELDS, parse_production_values, run_ocr

st.set_page_config(page_title="Production OCR | Biashara Masters Sawmill", page_icon="🔎", layout="wide")
user = require_role({"Admin"})
render_nav()
init_db()

st.title("Production OCR — Resin & Output")
st.caption("Read a production image, review the OCR suggestions, and save confirmed values to an existing roll.")
st.warning("OCR suggestions can be inaccurate. Review every field before saving; existing records are updated, never replaced wholesale.")

rolls = get_all_rolls()
if not rolls:
    st.info("No paper rolls exist yet. Create a roll on the Paper ID page before entering its resin/output values.")
else:
    roll_labels = {roll_id: f"ID #{roll_id} — {name or 'Unnamed roll'}" for roll_id, name in rolls}
    selected_roll = st.selectbox(
        "Apply reviewed values to roll",
        options=[roll_id for roll_id, _ in rolls],
        format_func=lambda roll_id: roll_labels[roll_id],
    )
    uploaded = st.file_uploader(
        "Upload a resin/output image (JPG, PNG, or WebP)",
        type=["jpg", "jpeg", "png", "webp"],
        key="production_ocr_image",
    )
    image_key = hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded else None
    if st.session_state.get("production_ocr_image_key") != image_key:
        st.session_state.pop("production_ocr_text", None)
        st.session_state.pop("production_ocr_values", None)
        st.session_state["production_ocr_image_key"] = image_key

    if uploaded and st.button("Read image with OCR", type="primary"):
        try:
            text = run_ocr(uploaded.getvalue())
            st.session_state["production_ocr_text"] = text
            st.session_state["production_ocr_values"] = parse_production_values(text)
            st.success("Image read. Confirm or correct the values below before saving.")
        except RuntimeError as error:
            st.error(str(error))

    extracted = st.session_state.get("production_ocr_values", {})
    raw_text = st.session_state.get("production_ocr_text", "")
    if raw_text:
        with st.expander("OCR text review"):
            st.text(raw_text or "No text detected.")

    with st.form("review_production_ocr_form"):
        st.subheader("Review values")
        st.caption("Blank fields are left unchanged on the selected roll. Edit OCR results as needed.")
        value_inputs = {}
        field_labels = {
            "right_resin": "Right resin",
            "center_resin": "Center resin",
            "left_resin": "Left resin",
            "output": "Output",
        }
        columns = st.columns(2)
        for index, field in enumerate(PRODUCTION_FIELDS):
            suggestion = extracted.get(field)
            with columns[index % 2]:
                value_inputs[field] = st.text_input(
                    field_labels[field],
                    value=f"{suggestion:g}" if suggestion is not None else "",
                    key=f"ocr_review_{field}",
                    help="Leave blank to keep this field unchanged.",
                )
        submitted = st.form_submit_button("Save reviewed values to selected roll", type="primary", use_container_width=True)

    if submitted:
        changes = {}
        invalid = []
        for field, raw_value in value_inputs.items():
            if not raw_value.strip():
                continue
            try:
                value = float(raw_value.strip().replace(",", "."))
                if not math.isfinite(value) or value < 0:
                    raise ValueError
                changes[field] = value
            except ValueError:
                invalid.append(field_labels[field])
        if invalid:
            st.error("Enter valid non-negative numbers for: " + ", ".join(invalid))
        elif not changes:
            st.warning("No values provided; nothing was saved.")
        elif update_roll_fields(selected_roll, changes, actor=user["username"], rank=user["rank"], station="Production OCR"):
            st.success(f"Saved {', '.join(field_labels[field] for field in changes)} to {roll_labels[selected_roll]}.")
        else:
            st.error("The selected roll no longer exists. Refresh and try again.")

render_footer()
