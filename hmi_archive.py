"""SQLite-backed archive for hourly and per-roll HMI photos."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from db import FACTORY_TIMEZONE, MAX_UPLOAD_BYTES, get_connection

HMI_CAPTURE_TYPES = {"hourly", "after_roll"}
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def ensure_hmi_archive() -> None:
    """Create the HMI archive table without changing existing production data."""
    with get_connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS hmi_photo_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capture_type TEXT NOT NULL CHECK (capture_type IN ('hourly', 'after_roll')),
                roll_id INTEGER,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                image_data BLOB NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                shift_date TEXT NOT NULL,
                shift_name TEXT NOT NULL
            )"""
        )


def save_hmi_photo(
    image_data: bytes,
    filename: str,
    mime_type: str,
    actor: str,
    capture_type: str,
    roll_id: int | None = None,
) -> int:
    """Validate and archive an HMI photo with its capture time, shift, and roll context."""
    if capture_type not in HMI_CAPTURE_TYPES:
        raise ValueError("Choose either an hourly capture or an after-roll capture.")
    if capture_type == "after_roll" and roll_id is None:
        raise ValueError("Select the roll associated with this after-roll HMI photo.")
    if roll_id is not None:
        with get_connection() as connection:
            exists = connection.execute("SELECT 1 FROM logs WHERE id = ?", (int(roll_id),)).fetchone()
        if not exists:
            raise ValueError("The selected roll no longer exists. Refresh and try again.")
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise ValueError("Capture or upload a JPG, PNG, or WebP image.")
    if not image_data or len(image_data) > MAX_UPLOAD_BYTES:
        raise ValueError("The image must be non-empty and no larger than 10 MB.")

    now = datetime.now(FACTORY_TIMEZONE)
    if now.hour >= 19:
        shift_date = now.date().isoformat()
        shift_name = "Night"
    elif now.hour < 7:
        from datetime import timedelta

        shift_date = (now.date() - timedelta(days=1)).isoformat()
        shift_name = "Night"
    else:
        shift_date = now.date().isoformat()
        shift_name = "Day"
    clean_name = Path(filename).name.strip()[:255] or f"hmi-{now:%Y%m%d-%H%M%S}.jpg"
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO hmi_photo_archive
               (capture_type, roll_id, filename, mime_type, image_data, uploaded_by,
                uploaded_at, shift_date, shift_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (capture_type, int(roll_id) if roll_id is not None else None, clean_name,
             mime_type, sqlite3.Binary(image_data), actor,
             now.isoformat(timespec="seconds"), shift_date, shift_name),
        )
        return int(cursor.lastrowid)


def get_hmi_photos(
    capture_type: str | None = None,
    roll_id: int | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Fetch newest archived photos, optionally filtered by capture type or roll."""
    if capture_type is not None and capture_type not in HMI_CAPTURE_TYPES:
        raise ValueError("Unsupported HMI capture type.")
    safe_limit = max(1, min(int(limit), 2000))
    conditions: list[str] = []
    parameters: list[Any] = []
    if capture_type:
        conditions.append("capture_type = ?")
        parameters.append(capture_type)
    if roll_id is not None:
        conditions.append("roll_id = ?")
        parameters.append(int(roll_id))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    parameters.append(safe_limit)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM hmi_photo_archive {where} ORDER BY id DESC LIMIT ?", parameters
        ).fetchall()
    return [dict(row) for row in rows]
