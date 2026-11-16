"""Rank-protected upload page for oven-temperature images and HMI photos."""

from datetime import datetime

import pandas as pd
import streamlit as st

from auth import require_role
from db import FACTORY_TIMEZONE, get_all_rolls, get_image_uploads, init_db
from hmi_archive import ensure_hmi_archive, get_hmi_photos, save_hmi_photo
from nav import render_footer, render_nav
from ocr_tools import get_hourly_oven_readings, process_oven_image

st.set_page_config(page_title="Karani Uploads | Biashara Masters Sawmill", page_icon="📷", layout="wide")
user = require_role({"Admin", "Secretary", "Production Manager"})
render_nav()
init_db()
ensure_hmi_archive()
st.title("Karani uploads · HMI photo archive")
st.caption(f"Signed in as {user['username']} · captures are timestamped in East Africa Time and shared with management.")
is_view_only = user["rank"] == "Production Manager"

if not is_view_only:
    st.header("Capture HMI photos")
    st.caption("Save a photo during each hourly check and after every roll. After-roll captures are linked to the selected roll.")
    capture_label = st.radio(
        "Capture occasion",
        ["Hourly check", "After roll production"],
        horizontal=True,
        key="hmi_capture_occasion",
    )
    capture_type = "hourly" if capture_label == "Hourly check" else "after_roll"
    rolls = get_all_rolls()
    roll_id = None
    if capture_type == "after_roll":
        if not rolls:
            st.warning("Create a Paper ID before recording an after-roll HMI photo.")
        else:
            roll_labels = {rid: f"#{rid} · {name or 'Unnamed roll'}" for rid, name in rolls}
            roll_id = st.selectbox(
                "Roll just completed",
                options=[rid for rid, _ in rolls],
                format_func=lambda rid: roll_labels[rid],
                key="hmi_after_roll_id",
            )
    elif rolls:
        roll_labels = {rid: f"#{rid} · {name or 'Unnamed roll'}" for rid, name in rolls}
        roll_id = st.selectbox(
            "Related roll (optional)",
            options=[None, *roll_labels],
            format_func=lambda rid: "No specific roll" if rid is None else roll_labels[rid],
            key="hmi_hourly_roll_id",
        )

    photo_method = st.radio(
        "Choose how to add the HMI photo",
        ["Upload a photo", "Take a photo"],
        horizontal=True,
        key="hmi_photo_method",
        help="Your camera is only requested after you select Take a photo.",
    )
    photo = None
    if photo_method == "Upload a photo":
        photo = st.file_uploader(
            "Choose an HMI photo · JPG, PNG, or WebP · 10 MB maximum",
            type=["jpg", "jpeg", "png", "webp"],
            key="hmi_photo_upload",
        )
    else:
        photo = st.camera_input("Take HMI photo", key="hmi_archive_camera")

    if photo:
        st.image(photo, caption="Review before saving", use_container_width=True)
        if st.button("Save HMI photo to archive", type="primary", key="save_hmi_archive_photo"):
            try:
                photo_id = save_hmi_photo(
                    photo.getvalue(), photo.name or "hmi-photo.jpg", photo.type or "image/jpeg",
                    user["username"], capture_type, roll_id=roll_id,
                )
            except ValueError as error:
                st.error(str(error))
            else:
                st.success(f"HMI photo #{photo_id} saved with a timestamp and shift record.")
                st.rerun()

    st.divider()
    st.header("Oven temperature image upload")
    st.caption("Oven temperature images are OCR-processed into hourly readings when six values are detected.")
    oven_source = st.radio(
        "Choose how to add an oven image",
        ("Upload image(s)", "Take a photo"),
        horizontal=True,
        key="oven_image_source",
        help="Your camera is only requested after you select Take a photo.",
    )

    def save_oven_image(filename: str, mime_type: str, image_bytes: bytes) -> bool:
        """Store and process one oven image, displaying the OCR outcome."""
        try:
            result = process_oven_image(filename, mime_type, image_bytes, user["username"])
            if result["reading_id"]:
                st.success(f"Saved {filename}; OCR recorded hourly temperatures {result['values']}.")
            else:
                st.warning("Image archived, but OCR did not find six values. Review its OCR text in the archive.")
                with st.expander(f"OCR text: {filename}"):
                    st.text(result["raw_text"] or "No text detected.")
            return True
        except (ValueError, RuntimeError) as error:
            st.error(f"Could not process {filename}: {error}")
            return False

    if oven_source == "Upload image(s)":
        with st.form("oven_image_upload_form", clear_on_submit=True):
            uploads = st.file_uploader(
                "Choose oven image(s) · JPG, PNG, or WebP · 10 MB maximum each",
                type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True,
                key="oven_image_uploads",
            )
            submitted = st.form_submit_button("Upload oven images", type="primary", use_container_width=True)
        if submitted:
            if not uploads:
                st.warning("Select at least one image.")
            else:
                saved = sum(save_oven_image(upload.name, upload.type or "", upload.getvalue()) for upload in uploads)
                if saved:
                    st.rerun()
    else:
        oven_photo = st.camera_input("Capture oven temperatures", key="oven_camera_capture")
        if oven_photo and st.button("Save and read oven photo", type="primary", key="save_oven_camera_photo"):
            if save_oven_image(oven_photo.name or "oven-photo.jpg", oven_photo.type or "image/jpeg", oven_photo.getvalue()):
                st.rerun()
else:
    st.info("Production Manager access is view-only.")

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
st.header("HMI photo archive")
filter_col, roll_col = st.columns(2)
with filter_col:
    archive_type_label = st.selectbox("Capture type", ["All captures", "Hourly checks", "After-roll photos"])
archive_type = {"All captures": None, "Hourly checks": "hourly", "After-roll photos": "after_roll"}[archive_type_label]
with roll_col:
    archive_rolls = get_all_rolls()
    archive_roll_options = [None, *[rid for rid, _ in archive_rolls]]
    archive_roll_names = {rid: f"#{rid} · {name or 'Unnamed roll'}" for rid, name in archive_rolls}
    selected_archive_roll = st.selectbox(
        "Filter by roll", options=archive_roll_options,
        format_func=lambda rid: "All rolls" if rid is None else archive_roll_names[rid],
        key="hmi_archive_roll_filter",
    )
hmi_photos = get_hmi_photos(capture_type=archive_type, roll_id=selected_archive_roll)
if not hmi_photos:
    st.info("No HMI photos match this archive filter yet.")
else:
    for image in hmi_photos:
        occasion = "Hourly check" if image["capture_type"] == "hourly" else "After roll"
        roll_text = f" · Roll #{image['roll_id']}" if image["roll_id"] is not None else ""
        title = f"{occasion}{roll_text} · {image['uploaded_at']} EAT · {image['shift_name']} shift {image['shift_date']}"
        with st.expander(title):
            st.image(image["image_data"], caption=image["filename"], use_container_width=True)
            st.caption(
                f"Photo #{image['id']} · uploaded by {image['uploaded_by']} · "
                f"{image['mime_type']} · {image['filename']}"
            )

st.divider()
st.header("Oven-temperature image archive")
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
render_footer()
