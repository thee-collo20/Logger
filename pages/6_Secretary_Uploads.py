"""SQLite persistence helpers for shift-based wood lamination production logs."""

from __future__ import annotations

import io
import json
import logging
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from openpyxl import Workbook

DB_PATH = Path(__file__).resolve().parent / "production_logs.db"
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
SHIFT_NAMES = ("Day", "Night")
IMAGE_CATEGORIES = {"hmi", "oven_temperature"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
OVEN_COLUMNS = tuple(f"oven_{index}" for index in range(1, 7))
COLUMNS = (
    "id", "name", "right_resin", "center_resin", "left_resin", "gsm",
    "output", "oven_1", "oven_2", "oven_3", "oven_4", "oven_5",
    "oven_6", "line_speed", "log_time",
)
LOGGER = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Return a configured SQLite connection; caller/context manager closes it."""
    connection = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def shift_for_datetime(value: datetime) -> tuple[str, str]:
    """Return the shift-start date and shift name in factory local time."""
    local = value.replace(tzinfo=FACTORY_TIMEZONE) if value.tzinfo is None else value.astimezone(FACTORY_TIMEZONE)
    clock = local.time().replace(tzinfo=None)
    if time(7, 0) <= clock < time(19, 0):
        return local.date().isoformat(), "Day"
    shift_date = local.date() if clock >= time(19, 0) else local.date() - timedelta(days=1)
    return shift_date.isoformat(), "Night"


def init_db() -> None:
    """Create production/recipe/upload tables and migrate existing databases safely."""
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, right_resin REAL,
                center_resin REAL, left_resin REAL, gsm REAL, output REAL,
                oven_1 REAL, oven_2 REAL, oven_3 REAL, oven_4 REAL, oven_5 REAL,
                oven_6 REAL, line_speed REAL, log_time TEXT, created_at TEXT,
                shift_date TEXT, shift_name TEXT, logged_by TEXT, updated_by TEXT, updated_at TEXT
            )"""
        )
        existing = {row["name"] for row in connection.execute("PRAGMA table_info(logs)")}
        for column in ("created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"):
            if column not in existing:
                connection.execute(f"ALTER TABLE logs ADD COLUMN {column} TEXT")

        connection.execute(
            """CREATE TABLE IF NOT EXISTS log_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT, roll_id INTEGER NOT NULL,
                actor TEXT NOT NULL, rank TEXT NOT NULL, station TEXT NOT NULL,
                action TEXT NOT NULL, changed_fields TEXT NOT NULL, created_at TEXT NOT NULL,
                shift_date TEXT, shift_name TEXT
            )"""
        )
        activity_columns = {row["name"] for row in connection.execute("PRAGMA table_info(log_activity)")}
        for column in ("shift_date", "shift_name"):
            if column not in activity_columns:
                connection.execute(f"ALTER TABLE log_activity ADD COLUMN {column} TEXT")
        connection.execute(
            """UPDATE log_activity
               SET shift_date = (SELECT shift_date FROM logs WHERE logs.id = log_activity.roll_id),
                   shift_name = (SELECT shift_name FROM logs WHERE logs.id = log_activity.roll_id)
               WHERE shift_date IS NULL AND shift_name IS NULL"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS glue_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                ingredients TEXT NOT NULL, instructions TEXT NOT NULL, created_by TEXT NOT NULL,
                updated_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS image_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL CHECK (category IN ('hmi', 'oven_temperature')),
                filename TEXT NOT NULL, mime_type TEXT NOT NULL, image_data BLOB NOT NULL,
                uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL,
                extracted_numbers TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS oven_hourly_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_date TEXT NOT NULL,
                hour_label TEXT NOT NULL,
                oven_1 REAL,
                oven_2 REAL,
                oven_3 REAL,
                oven_4 REAL,
                oven_5 REAL,
                oven_6 REAL,
                source_image_id INTEGER,
                source_filename TEXT,
                raw_text TEXT,
                uploaded_by TEXT NOT NULL,
                captured_at TEXT NOT NULL
            )"""
        )


def _extract_numeric_candidates(text: str) -> list[float]:
    """Conservative OCR value extraction for oven temperatures."""
    raw = text or ""
    matches = re.findall(r"\d+(?:\.\d+)?", raw)
    values: list[float] = []
    for token in matches:
        try:
            value = float(token)
        except ValueError:
            continue
        if 0 <= value <= 500:
            values.append(round(value, 1))
    return values


def _best_oven_values(raw_text: str) -> list[float]:
    """Return six oven values from OCR output when possible."""
    values = _extract_numeric_candidates(raw_text)
    if not values:
        return []
    deduped: list[float] = []
    for value in values:
        if not any(abs(value - existing) < 0.01 for existing in deduped):
            deduped.append(value)
    ordered = deduped[:6]
    if len(ordered) < 6:
        return ordered
    return ordered


def _ocr_image(image_bytes: bytes) -> tuple[list[float], str]:
    """Read a temperature image and attempt OCR extraction."""
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:  # pragma: no cover - depends on optional OCR packages
        LOGGER.exception("OCR dependencies are unavailable")
        return [], f"OCR setup missing: {exc}"
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        image = image.resize((image.width * 2, image.height * 2))
        text = pytesseract.image_to_string(image, config="--psm 6")
    except Exception as exc:  # pragma: no cover - image decoding/ocr failure
        LOGGER.exception("Unable to process uploaded image with OCR")
        return [], f"OCR failed: {exc}"
    values = _best_oven_values(text)
    return values, text


def save_image_upload(category: str, filename: str, mime_type: str, image_data: bytes, actor: str) -> int:
    """Store one validated image in the global image container."""
    if category not in IMAGE_CATEGORIES:
        raise ValueError("Unsupported image category.")
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Upload a JPG, PNG, or WebP image.")
    if not image_data or len(image_data) > MAX_UPLOAD_BYTES:
        raise ValueError("The image must be non-empty and no larger than 10 MB.")
    clean_name = Path(filename).name.strip()[:255] or "upload"
    now = datetime.now(FACTORY_TIMEZONE).isoformat(timespec="seconds")
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO image_uploads
               (category, filename, mime_type, image_data, uploaded_by, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (category, clean_name, mime_type, sqlite3.Binary(image_data), actor, now),
        )
        return int(cursor.lastrowid)


def get_image_uploads(category: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Return the newest shared image uploads, optionally filtered by category."""
    if category is not None and category not in IMAGE_CATEGORIES:
        raise ValueError("Unsupported image category.")
    safe_limit = max(1, min(int(limit), 500))
    with get_connection() as connection:
        if category:
            rows = connection.execute(
                "SELECT * FROM image_uploads WHERE category = ? ORDER BY id DESC LIMIT ?",
                (category, safe_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM image_uploads ORDER BY id DESC LIMIT ?", (safe_limit,)
            ).fetchall()
    return [dict(row) for row in rows]


def save_oven_hourly_reading(
    reading_date: str,
    hour_label: str,
    oven_values: list[float],
    source_image_id: int | None,
    source_filename: str,
    raw_text: str,
    actor: str,
) -> int:
    """Persist one hourly oven reading; keep all entries for the day so they remain available."""
    if len(oven_values) != 6:
        raise ValueError("OCR should produce six oven values before storing an hourly reading.")
    safe_hour = str(hour_label).strip() or datetime.now(FACTORY_TIMEZONE).strftime("%H:00")
    now = datetime.now(FACTORY_TIMEZONE).isoformat(timespec="seconds")
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO oven_hourly_readings
               (reading_date, hour_label, oven_1, oven_2, oven_3, oven_4, oven_5, oven_6,
                source_image_id, source_filename, raw_text, uploaded_by, captured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reading_date,
                safe_hour,
                float(oven_values[0]),
                float(oven_values[1]),
                float(oven_values[2]),
                float(oven_values[3]),
                float(oven_values[4]),
                float(oven_values[5]),
                source_image_id,
                source_filename,
                raw_text[:4000],
                actor,
                now,
            ),
        )
        return int(cursor.lastrowid)


def get_hourly_oven_readings(reading_date: str | None = None, limit: int = 48) -> list[dict[str, Any]]:
    """Return stored hourly oven readings for a selected date, newest first."""
    safe_limit = max(1, min(int(limit), 1000))
    date_filter = reading_date if reading_date else datetime.now(FACTORY_TIMEZONE).date().isoformat()
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT * FROM oven_hourly_readings
               WHERE reading_date = ?
               ORDER BY captured_at DESC, id DESC
               LIMIT ?""",
            (date_filter, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def process_uploaded_oven_image(filename: str, mime_type: str, image_data: bytes, actor: str) -> dict[str, Any]:
    """Upload an oven image, OCR the numbers, and store the hourly reading if values are found."""
    upload_id = save_image_upload("oven_temperature", filename, mime_type, image_data, actor)
    values, raw_text = _ocr_image(image_data)
    payload: dict[str, Any] = {
        "image_id": upload_id,
        "upload_filename": filename,
        "oven_values": values,
        "raw_text": raw_text,
        "reading_date": datetime.now(FACTORY_TIMEZONE).date().isoformat(),
        "hour_label": datetime.now(FACTORY_TIMEZONE).strftime("%H:00"),
    }
    with get_connection() as connection:
        connection.execute(
            "UPDATE image_uploads SET extracted_numbers = ? WHERE id = ?",
            (json.dumps(values), upload_id),
        )
    if values:
        payload["reading_id"] = save_oven_hourly_reading(
            payload["reading_date"],
            payload["hour_label"],
            values,
            upload_id,
            filename,
            raw_text,
            actor,
        )
    return payload


def get_next_id() -> int:
    with get_connection() as connection:
        return int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM logs").fetchone()[0])


def get_all_rolls() -> list[tuple[int, str]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT id, name FROM logs ORDER BY id DESC").fetchall()
    return [(int(row["id"]), row["name"] or "") for row in rows]


def _record_activity(
    connection: sqlite3.Connection,
    roll_id: int,
    actor: str,
    rank: str,
    station: str,
    action: str,
    changed_fields: str,
    created_at: str,
    shift_date: str | None,
    shift_name: str | None,
) -> None:
    """Insert exactly one activity event with the roll's shift at event time."""
    connection.execute(
        """INSERT INTO log_activity
           (roll_id, actor, rank, station, action, changed_fields, created_at, shift_date, shift_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (roll_id, actor, rank, station, action, changed_fields, created_at, shift_date, shift_name),
    )


def insert_roll(name: str, gsm: float, output: float, actor: str = "Unknown", rank: str = "Unknown") -> int:
    now = datetime.now(FACTORY_TIMEZONE)
    created_at = now.isoformat(timespec="seconds")
    shift_date, shift_name = shift_for_datetime(now)
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO logs (name, gsm, output, created_at, shift_date, shift_name, logged_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, gsm, output, created_at, shift_date, shift_name, actor),
        )
        roll_id = int(cursor.lastrowid)
        _record_activity(connection, roll_id, actor, rank, "Paper ID", "Created roll",
                         "name, gsm, output", created_at, shift_date, shift_name)
    return roll_id


def update_roll_fields(
    roll_id: int,
    values: Mapping[str, Any],
    actor: str = "Unknown",
    rank: str = "Unknown",
    station: str = "Production",
) -> bool:
    editable = (set(COLUMNS) - {"id"}) | {"shift_date", "shift_name"}
    if not values or not set(values).issubset(editable):
        raise ValueError("No fields supplied or unsupported field name.")
    now = datetime.now(FACTORY_TIMEZONE).isoformat(timespec="seconds")
    assignments = ", ".join(f'"{column}" = ?' for column in values)
    parameters = [values[column] for column in values]
    parameters.extend((actor, now, int(roll_id)))
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE logs SET {assignments}, updated_by = ?, updated_at = ? WHERE id = ?", parameters
        )
        if not cursor.rowcount:
            return False
        shift = connection.execute(
            "SELECT shift_date, shift_name FROM logs WHERE id = ?", (int(roll_id),)
        ).fetchone()
        _record_activity(
            connection, int(roll_id), actor, rank, station, "Updated production log",
            ", ".join(values), now, shift["shift_date"], shift["shift_name"],
        )
    return True


def delete_roll(roll_id: int, actor: str = "Unknown", rank: str = "Unknown") -> bool:
    """Record an attributed deletion with shift context before removing the roll."""
    now = datetime.now(FACTORY_TIMEZONE).isoformat(timespec="seconds")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT shift_date, shift_name FROM logs WHERE id = ?", (int(roll_id),)
        ).fetchone()
        if not row:
            return False
        _record_activity(
            connection, int(roll_id), actor, rank, "Admin", "Deleted roll", ", ".join(COLUMNS),
            now, row["shift_date"], row["shift_name"],
        )
        connection.execute("DELETE FROM logs WHERE id = ?", (int(roll_id),))
        return True


def get_recent_activity(limit: int = 500) -> list[dict[str, Any]]:
    """Return activity, falling back to a legacy-compatible query on schema errors."""
    safe_limit = max(1, min(int(limit), 5000))
    try:
        with get_connection() as connection:
            rows = connection.execute(
                """SELECT a.created_at, a.roll_id, a.shift_date, a.shift_name,
                          a.actor, a.rank, a.station, a.action, a.changed_fields
                   FROM log_activity AS a
                   ORDER BY a.id DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.Error, OSError):
        LOGGER.exception("Could not load shift activity with the current schema; trying legacy-safe fallback")

    try:
        with get_connection() as connection:
            rows = connection.execute(
                """SELECT a.created_at, a.roll_id, l.shift_date, l.shift_name,
                          a.actor, a.rank, a.station, a.action, a.changed_fields
                   FROM log_activity AS a
                   LEFT JOIN logs AS l ON l.id = a.roll_id
                   ORDER BY a.id DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.Error, OSError):
        LOGGER.exception("Could not load activity history; returning an empty history")
        return []


def get_all_logs(descending: bool = True) -> list[dict[str, Any]]:
    order = "DESC" if descending else "ASC"
    columns = ", ".join((*COLUMNS, "created_at", "shift_date", "shift_name", "logged_by", "updated_by", "updated_at"))
    with get_connection() as connection:
        rows = connection.execute(f"SELECT {columns} FROM logs ORDER BY id {order}").fetchall()
    return [dict(row) for row in rows]


def get_glue_recipes() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM glue_recipes ORDER BY name COLLATE NOCASE").fetchall()
    return [dict(row) for row in rows]


def save_glue_recipe(name: str, ingredients: str, instructions: str, actor: str,
                     recipe_id: int | None = None) -> int:
    clean_name = name.strip()
    if not clean_name or not ingredients.strip() or not instructions.strip():
        raise ValueError("Recipe name, ingredients, and mixing instructions are required.")
    now = datetime.now(FACTORY_TIMEZONE).isoformat(timespec="seconds")
    with get_connection() as connection:
        if recipe_id is None:
            cursor = connection.execute(
                """INSERT INTO glue_recipes
                   (name, ingredients, instructions, created_by, updated_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (clean_name, ingredients.strip(), instructions.strip(), actor, actor, now, now),
            )
            return int(cursor.lastrowid)
        cursor = connection.execute(
            """UPDATE glue_recipes SET name = ?, ingredients = ?, instructions = ?,
               updated_by = ?, updated_at = ? WHERE id = ?""",
            (clean_name, ingredients.strip(), instructions.strip(), actor, now, int(recipe_id)),
        )
        if not cursor.rowcount:
            raise ValueError("The selected recipe no longer exists. Refresh and try again.")
        return int(recipe_id)


def _build_workbook(records: list[sqlite3.Row]) -> io.BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Production Logs"
    sheet.append(["", "", "Resin Content"])
    sheet.append(["ID", "Name", "Right", "Center", "Left", "GSM", "Output", "", "", "", "",
                  "oven 1", "Oven 2", "oven 3", "oven 4", "0ven 5", "Oven 6", "L/S", "Time"])
    for record in records:
        sheet.append([record["id"], record["name"], record["right_resin"], record["center_resin"],
                      record["left_resin"], record["gsm"], record["output"], "", "", "", "",
                      record["oven_1"], record["oven_2"], record["oven_3"], record["oven_4"],
                      record["oven_5"], record["oven_6"], record["line_speed"], record["log_time"]])
    sheet.freeze_panes = "A3"
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def generate_exact_xlsx() -> io.BytesIO:
    with get_connection() as connection:
        records = connection.execute(f"SELECT {', '.join(COLUMNS)} FROM logs ORDER BY id ASC").fetchall()
    return _build_workbook(records)


def generate_shift_xlsx(shift_date: str, shift_name: str) -> io.BytesIO:
    if shift_name not in SHIFT_NAMES:
        raise ValueError("shift_name must be 'Day' or 'Night'.")
    if date.fromisoformat(shift_date).isoformat() != shift_date:
        raise ValueError("shift_date must be an ISO date (YYYY-MM-DD).")
    with get_connection() as connection:
        records = connection.execute(
            f"SELECT {', '.join(COLUMNS)} FROM logs WHERE shift_date = ? AND shift_name = ? ORDER BY id ASC",
            (shift_date, shift_name),
        ).fetchall()
    return _build_workbook(records)
