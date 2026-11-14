"""Rank-protected upload page for HMI and oven-temperature images."""

import streamlit as st

from auth import require_role
from db import get_image_uploads, init_db, save_image_upload
from nav import render_footer, render_nav

st.set_page_config(page_title="Secretary Uploads | Biashara Masters Sawmill", page_icon="📷", layout="wide")
user = require_role({"Admin", "Secretary"})
render_nav()
init_db()

st.title("Secretary image uploads")
st.caption(f"Signed in as {user['username']} · uploads are shared in the global image container.")
st.info(
    "Images are saved with the uploader and timestamp. Automatic number recognition is not enabled yet, "
    "so values shown in an image are not added to production logs automatically."
)

with st.form("secretary_image_upload_form", clear_on_submit=True):
    category_label = st.selectbox("Image type", ["Oven temperatures", "HMI"])
    category = "oven_temperature" if category_label == "Oven temperatures" else "hmi"
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
                upload_id = save_image_upload(
                    category,
                    uploaded.name,
                    uploaded.type or "",
                    uploaded.getvalue(),
                    user["username"],
                )
                saved += 1
                st.success(f"Saved {uploaded.name} to the global {category_label.lower()} container (image #{upload_id}).")
            except ValueError as error:
                st.error(f"Could not save {uploaded.name}: {error}")
        if saved:
            st.rerun()

st.divider()
st.header("Global oven-temperature image container")
st.caption("Shared image archive · newest uploads first · the images are not yet OCR-parsed into numeric logs.")
oven_images = get_image_uploads("oven_temperature")
if not oven_images:
    st.info("No oven-temperature images have been uploaded yet.")
else:
    for image in oven_images:
        with st.expander(f"{image['filename']} · uploaded by {image['uploaded_by']} · {image['uploaded_at']} EAT"):
            st.image(image["image_data"], caption=image["filename"], use_container_width=True)
            st.caption(f"Image #{image['id']} · {image['mime_type']} · uploaded by {image['uploaded_by']}")

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
