"""OCR helpers for per-roll oven temperatures and production resin/output images."""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime
from typing import Any

from db import FACTORY_TIMEZONE, get_connection, save_image_upload, update_roll_fields

LOGGER = logging.getLogger(__name__)
OVEN_FIELDS = tuple(f"oven_{number}" for number in range(1, 7))
PRODUCTION_FIELDS = ("right_resin", "center_resin", "left_resin", "output")
LABELS = {
    "right_resin": ("right resin", "right", "resin right"),
    "center_resin": ("center resin", "centre resin", "center", "centre", "resin center", "resin centre"),
    "left_resin": ("left resin", "left", "resin left"),
    "output": ("output", "out put", "production output"),
}
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?")


def run_ocr(image_bytes: bytes) -> str:
    """Return OCR text for an image; raise a clear error if Tesseract is unavailable."""
    try:
        from PIL import Image, ImageOps, ImageEnhance
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("OCR packages are missing. Install requirements.txt and restart the app.") from exc
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        image = ImageOps.autocontrast(image)
        image = ImageEnhance.Sharpness(image).enhance(1.5)
        image = image.resize((max(1, image.width * 2), max(1, image.height * 2)))
        return pytesseract.image_to_string(image, config="--psm 6")
    except Exception as exc:
        LOGGER.exception("Image OCR failed")
        raise RuntimeError(
            "Could not read the image. Confirm it is a valid image and that the Tesseract system binary is installed."
        ) from exc


def _number_after(text: str, position: int) -> float | None:
    match = NUMBER_RE.search(text[position:])
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_production_values(text: str) -> dict[str, float]:
    """Extract explicitly labelled Right/Center/Left resin and Output values."""
    lines = [line.strip().casefold() for line in (text or "").splitlines() if line.strip()]
    result: dict[str, float] = {}
    for field, aliases in LABELS.items():
        for index, line in enumerate(lines):
            selected: tuple[int, str] | None = None
            for alias in aliases:
                match = re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", line)
                if match and (selected is None or match.start() < selected[0]):
                    selected = (match.start(), alias)
            if selected is None:
                continue
            value = _number_after(line, selected[0] + len(selected[1]))
            if value is None and index + 1 < len(lines):
                # OCR often places column headings and values on separate lines.
                next_line = lines[index + 1]
                if not any(re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", next_line)
                           for other_aliases in LABELS.values() for alias in other_aliases):
                    value = _number_after(next_line, 0)
            if value is not None and value >= 0:
                result[field] = round(value, 4)
                break
    return result


def _temperature_candidates(text: str) -> list[float]:
    values: list[float] = []
    for token in NUMBER_RE.findall(text or ""):
        try:
            value = float(token.replace(",", "."))
        except ValueError:
            continue
        # Temperatures outside this range are unlikely to be oven readings.
        if 0 <= value <= 500:
            values.append(round(value, 1))
    return values


def ensure_oven_readings_table() -> None:
    """Keep the legacy hourly table available so existing readings remain accessible."""
    with get_connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS oven_hourly_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_date TEXT NOT NULL, hour_label TEXT NOT NULL,
                oven_1 REAL, oven_2 REAL, oven_3 REAL, oven_4 REAL, oven_5 REAL, oven_6 REAL,
                source_image_id INTEGER, source_filename TEXT, raw_text TEXT,
                uploaded_by TEXT NOT NULL, captured_at TEXT NOT NULL
            )"""
        )


def process_oven_image(
    filename: str, mime_type: str, image_bytes: bytes, actor: str, rank: str, roll_id: int
) -> dict[str, Any]:
    """Archive an oven image and save its six OCR readings against the selected roll."""
    image_id = save_image_upload("oven_temperature", filename, mime_type, image_bytes, actor)
    text = run_ocr(image_bytes)
    values = _temperature_candidates(text)[:6]
    with get_connection() as connection:
        connection.execute(
            "UPDATE image_uploads SET extracted_numbers = ? WHERE id = ?",
            (json.dumps(values), image_id),
        )

    saved_to_roll = False
    if len(values) == 6:
        saved_to_roll = update_roll_fields(
            int(roll_id), dict(zip(OVEN_FIELDS, values)), actor=actor, rank=rank,
            station="Oven Temperature OCR",
        )
    return {
        "image_id": image_id,
        "roll_id": int(roll_id) if saved_to_roll else None,
        "values": values,
        "raw_text": text,
    }


def get_hourly_oven_readings(reading_date: str, limit: int = 48) -> list[dict[str, Any]]:
    """Get retained legacy hourly readings for a date; new captures are saved per roll."""
    ensure_oven_readings_table()
    safe_limit = max(1, min(int(limit), 1000))
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM oven_hourly_readings WHERE reading_date = ? ORDER BY captured_at, id LIMIT ?",
            (reading_date, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def save_production_ocr_values(roll_id: int, values: dict[str, float], actor: str, rank: str) -> bool:
    """Apply reviewed OCR values to an existing roll and retain activity attribution."""
    changes = {field: values[field] for field in PRODUCTION_FIELDS if field in values}
    if not changes:
        raise ValueError("Enter at least one production value before saving.")
    return update_roll_fields(roll_id, changes, actor=actor, rank=rank, station="Production OCR")
