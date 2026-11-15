"""Rank-protected upload page for HMI and oven-temperature images."""

from datetime import datetime

import pandas as pd
import streamlit as st

from auth import require_role
from db import FACTORY_TIMEZONE, get_image_uploads, init_db, save_image_upload
from nav import render_footer, render_nav
from ocr_tools import get_hourly_oven_readings, process_oven_image

st.set_page_config(page_title="Karani Uploads | Biashara Masters Sawmill", page_icon="📷", layout="wide")
user = require_role({"Admin", "Secretary", "Production Manager"})
render_nav()
init_db()
st.title("Karani image uploads")
st.caption(f"Signed in as {user['username']} · images and readings are shared globally.")
is_view_only = user["rank"] == "Production Manager"
if is_view_only:
    st.info("Production Manager access is view-only.")
else:
    st.info("Oven images are OCR-processed into hourly readings when six values are detected. HMI images are archived as images.")
    category_label = st.selectbox("Image type", ["Oven temperatures", "HMI"], key="karani_image_category")
    image_source = st.radio("Choose how to add an image", ("Choose image(s)", "Take a photo"), horizontal=True, key="karani_image_source")

    def save_image(filename: str, mime_type: str, image_bytes: bytes) -> bool:
        """Store one image in its category and report its processing result."""
        try:
            if category_label == "Oven temperatures":
                result = process_oven_image(filename, mime_type, image_bytes, user["username"])
                if result["reading_id"]:
                    st.success(f"Saved {filename}; OCR recorded hourly temperatures {result['values']}.")
                else:
                    st.warning(f"Saved {filename}, but OCR did not find six values. Review the raw OCR text in the image archive.")
                    with st.expander(f"OCR text: {filename}"):
                        st.text(result["raw_text"] or "No text detected.")
            else:
                image_id = save_image_upload("hmi", filename, mime_type, image_bytes, user["username"])
                st.success(f"Saved {filename} to the global HMI archive (image #{image_id}).")
            return True
        except (ValueError, RuntimeError) as error:
            st.error(f"Could not process {filename}: {error}")
            return False

    if image_source == "Choose image(s)":
        st.session_state["karani_camera_enabled"] = False
        with st.form("secretary_image_upload_form", clear_on_submit=True):
            uploads = st.file_uploader("Choose image(s) · JPG, PNG, or WebP · 10 MB maximum each",
                                       type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
            submitted = st.form_submit_button("Upload images", type="primary", use_container_width=True)
        if submitted:
            if not uploads:
                st.warning("Select at least one image to upload.")
            else:
                saved = sum(save_image(uploaded.name, uploaded.type or "", uploaded.getvalue()) for uploaded in uploads)
                if saved:
                    st.rerun()
    elif not st.session_state.get("karani_camera_enabled"):
        if st.button("Take photo", type="primary", key="karani_open_camera"):
            st.session_state["karani_camera_enabled"] = True
            st.rerun()
    else:
        photo = st.camera_input("Capture an image", key="karani_camera_capture")
        if photo:
            st.caption("Review the photo, then choose Save photo to add it to the shared image archive.")
            if st.button("Save photo", type="primary", key="karani_save_photo"):
                if save_image(photo.name or "camera-photo.jpg", photo.type or "image/jpeg", photo.getvalue()):
                    st.session_state["karani_camera_enabled"] = False
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
