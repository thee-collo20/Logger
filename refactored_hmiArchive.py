"""Supabase PostgreSQL storage for HMI photo archiving (hourly and after-roll captures)."""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from db import get_shift_window_eat, get_supabase_client

LOGGER = logging.getLogger(__name__)
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
MAX_HMI_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
VALID_CAPTURE_TYPES = {"hourly", "after_roll"}


def init_hmi_archive() -> None:
    """Verify hmi_photo_archive table availability in Supabase."""
    try:
        client = get_supabase_client()
        client.table("hmi_photo_archive").select("id").limit(1).execute()
    except Exception:
        LOGGER.exception("Failed to verify hmi_photo_archive table in Supabase")
        raise


def save_hmi_photo(
    capture_type: str,
    filename: str,
    mime_type: str,
    image_bytes: bytes,
    roll_id: str | None = None,
    shift_date: date | str | None = None,
    shift_name: str | None = None,
    notes: str | None = None,
    uploaded_by: str | None = None,
) -> int:
    """Store an HMI screenshot/photo in Supabase PostgreSQL and return its row ID."""
    normalized_type = capture_type.strip().lower()
    if normalized_type not in VALID_CAPTURE_TYPES:
        raise ValueError(
            f"Invalid capture_type '{capture_type}'. Must be one of {sorted(VALID_CAPTURE_TYPES)}."
        )
    if not image_bytes:
        raise ValueError("Image payload is empty.")
    if len(image_bytes) > MAX_HMI_IMAGE_BYTES:
        raise ValueError(
            f"Image size ({len(image_bytes)} bytes) exceeds maximum limit of {MAX_HMI_IMAGE_BYTES} bytes."
        )

    _, _, inferred_shift, inferred_date = get_shift_window_eat()
    resolved_date = (
        shift_date.isoformat()
        if isinstance(shift_date, date)
        else (shift_date or inferred_date.isoformat())
    )
    resolved_shift = shift_name or inferred_shift

    client = get_supabase_client()
    payload = {
        "capture_type": normalized_type,
        "filename": filename,
        "mime_type": mime_type,
        "roll_id": roll_id.strip() if roll_id else None,
        "shift_date": resolved_date,
        "shift_name": resolved_shift,
        "notes": notes,
        "uploaded_by": uploaded_by,
        "image_data_b64": base64.b64encode(image_bytes).decode("ascii"),
        "captured_at": datetime.now(FACTORY_TIMEZONE).isoformat(),
    }
    res = client.table("hmi_photo_archive").insert(payload).execute()
    return int(res.data[0]["id"])


def list_hmi_photos(
    capture_type: str | None = None,
    shift_date: date | str | None = None,
    shift_name: str | None = None,
    roll_id: str | None = None,
    limit: int = 100,
    include_bytes: bool = False,
) -> list[dict[str, Any]]:
    """Query archived HMI photos from Supabase, newest first."""
    client = get_supabase_client()
    cols = (
        "id,capture_type,filename,mime_type,roll_id,shift_date,shift_name,notes,uploaded_by,captured_at,image_data_b64"
        if include_bytes
        else "id,capture_type,filename,mime_type,roll_id,shift_date,shift_name,notes,uploaded_by,captured_at"
    )
    query = (
        client.table("hmi_photo_archive")
        .select(cols)
        .order("captured_at", desc=True)
    )

    if capture_type and capture_type.lower() != "all":
        query = query.eq("capture_type", capture_type.strip().lower())
    if shift_date:
        sd = shift_date.isoformat() if isinstance(shift_date, date) else str(shift_date)
        query = query.eq("shift_date", sd)
    if shift_name and shift_name.lower() != "all":
        query = query.eq("shift_name", shift_name)
    if roll_id:
        query = query.ilike("roll_id", f"%{roll_id.strip()}%")

    res = query.limit(max(1, int(limit))).execute()
    results = []
    for row in res.data or []:
        item = dict(row)
        b64 = item.pop("image_data_b64", None)
        if include_bytes and b64:
            item["image_data"] = base64.b64decode(b64)
        results.append(item)
    return results


def get_hmi_photo_bytes(photo_id: int) -> tuple[bytes, str, str] | None:
    """Retrieve (image_bytes, mime_type, filename) for a single HMI archive record."""
    client = get_supabase_client()
    res = (
        client.table("hmi_photo_archive")
        .select("image_data_b64,mime_type,filename")
        .eq("id", int(photo_id))
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    return (
        base64.b64decode(row["image_data_b64"]),
        row["mime_type"],
        row["filename"],
    )


def delete_hmi_photo(photo_id: int) -> bool:
    """Delete an archived HMI photo by ID."""
    client = get_supabase_client()
    res = (
        client.table("hmi_photo_archive")
        .delete()
        .eq("id", int(photo_id))
        .execute()
    )
    return bool(res.data)
