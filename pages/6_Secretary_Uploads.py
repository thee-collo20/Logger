"""Rank-protected upload page for HMI and oven-temperature images."""

from datetime import datetime

import pandas as pd
import streamlit as st

from auth import require_role
from db import FACTORY_TIMEZONE, get_image_uploads, init_db, save_image_upload
from nav import render_footer, render_nav
from ocr_tools import get_hourly_oven_readings, process_oven_image

st.set_page_config(page_title="Karani Uploads | Biashara Masters Sawmill", page_icon="📷", layout="wide")
user = require_role({"Admin", "Secretary"})
render_nav()
init_db()

st.title("Karani image uploads")
st.caption(f"Signed in as {user['username']} · uploads are shared in the global image container.")
st.info("Oven images are OCR-processed into hourly readings when six values are detected. HMI images are archived as images.")

with st.form("secretary_image_upload_form", clear_on_submit=True):
    category_label = st.selectbox("Image type", ["Oven temperatures", "HMI"])
    uploads = st.file_uploader(
        "Choose image(s) · JPG, PNG, or WebP · 10 MB maximum each",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )
    submitted = st.form_submit_button("Upload images", type="primary", use_container_width=True)

if submitted:
    if not uploads:
        st.warning("Select at least one image to upload.")
    else:
        saved = 0
        for uploaded in uploads:
            try:
                if category_label == "Oven temperatures":
                    result = process_oven_image(uploaded.name, uploaded.type or "", uploaded.getvalue(), user["username"])
                    saved += 1
                    if result["reading_id"]:
                        st.success(f"Saved {uploaded.name}; OCR recorded hourly temperatures {result['values']}.")
                    else:
                        st.warning(f"Saved {uploaded.name}, but OCR did not find six values. Review the raw OCR text in the image archive.")
                        with st.expander(f"OCR text: {uploaded.name}"):
                            st.text(result["raw_text"] or "No text detected.")
                else:
                    image_id = save_image_upload("hmi", uploaded.name, uploaded.type or "", uploaded.getvalue(), user["username"])
                    saved += 1
                    st.success(f"Saved {uploaded.name} to the global HMI archive (image #{image_id}).")
            except (ValueError, RuntimeError) as error:
                st.error(f"Could not process {uploaded.name}: {error}")
        if saved:
            st.rerun()

st.divider()
st.header("Today's hourly oven temperature dashboard")
reading_date = datetime.now(FACTORY_TIMEZONE).date().isoformat()
readings = get_hourly_oven_readings(reading_date, limit=48)
if not readings:
    st.info("No oven temperature readings have been captured today yet.")
else:
    frame = pd.DataFrame(readings)
    frame["captured_at"] = pd.to_datetime(frame["captured_at"], errors="coerce")
    frame = frame.sort_values("captured_at")
    oven_columns = [f"oven_{number}" for number in range(1, 7)]
    st.line_chart(frame.set_index("captured_at")[oven_columns], y_label="Temperature")
    table_columns = ["reading_date", "hour_label", *oven_columns, "source_filename", "uploaded_by", "captured_at"]
    st.dataframe(frame[table_columns], use_container_width=True, hide_index=True)
    st.caption("All captures are retained, including multiple images uploaded in the same hour.")

st.divider()
st.header("Global oven-temperature image container")
oven_images = get_image_uploads("oven_temperature")
if not oven_images:
    st.info("No oven-temperature images have been uploaded yet.")
else:
    for image in oven_images:
        with st.expander(f"{image['filename']} · uploaded by {image['uploaded_by']} · {image['uploaded_at']} EAT"):
            st.image(image["image_data"], caption=image["filename"], use_container_width=True)
            st.caption(f"Image #{image['id']} · {image['mime_type']} · uploaded by {image['uploaded_by']}")
            if image.get("extracted_numbers"):
                st.code(image["extracted_numbers"], language="json")

st.divider()
st.header("Global HMI image archive")
hmi_images = get_image_uploads("hmi")
if not hmi_images:
    st.info("No HMI images have been uploaded yet.")
else:
    for image in hmi_images:
        with st.expander(f"{image['filename']} · uploaded by {image['uploaded_by']} · {image['uploaded_at']} EAT"):
            st.image(image["image_data"], caption=image["filename"], use_container_width=True)
            st.caption(f"Image #{image['id']} · {image['mime_type']} · uploaded by {image['uploaded_by']}")

render_footer()
