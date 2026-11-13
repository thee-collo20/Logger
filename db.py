"""SQLite persistence helpers for shift-based wood lamination production logs."""

from __future__ import annotations

import io
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from openpyxl import Workbook

DB_PATH = Path(__file__).resolve().parent / "production_logs.db"
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
SHIFT_NAMES = ("Day", "Night")

# Keep the requested report columns unchanged. Timestamp and shift metadata are
# supplemental database fields and are not added to the exact XLSX layout.
COLUMNS = (
    "id", "name", "right_resin", "center_resin", "left_resin", "gsm",
    "output", "oven_1", "oven_2", "oven_3", "oven_4", "oven_5",
    "oven_6", "line_speed", "log_time",
)


def get_connection() -> sqlite3.Connection:
    """Return a configured SQLite connection; caller/context manager closes it."""
    connection = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def shift_for_datetime(value: datetime) -> tuple[str, str]:
    """Return (shift start date, shift name) in EAT for a local or aware datetime.

    Day shift is 07:00 inclusive to 19:00 exclusive. Night shift is 19:00 to
    07:00; after midnight, its shift date remains the date it started.
    """
    local = value.replace(tzinfo=FACTORY_TIMEZONE) if value.tzinfo is None else value.astimezone(FACTORY_TIMEZONE)
    clock = local.time().replace(tzinfo=None)
    if time(7, 0) <= clock < time(19, 0):
        return local.date().isoformat(), "Day"
    shift_date = local.date() if clock >= time(19, 0) else local.date() - timedelta(days=1)
    return shift_date.isoformat(), "Night"


def init_db() -> None:
    """Create the log table and migrate timestamp/shift fields on older databases."""
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                right_resin REAL,
                center_resin REAL,
                left_resin REAL,
                gsm REAL,
                output REAL,
                oven_1 REAL,
                oven_2 REAL,
                oven_3 REAL,
                oven_4 REAL,
                oven_5 REAL,
                oven_6 REAL,
                line_speed REAL,
                log_time TEXT,
                created_at TEXT,
                shift_date TEXT,
                shift_name TEXT
            )"""
        )
        existing = {row["name"] for row in connection.execute("PRAGMA table_info(logs)")}
        for column in ("created_at", "shift_date", "shift_name"):
            if column not in existing:
                connection.execute(f"ALTER TABLE logs ADD COLUMN {column} TEXT")
        # Legacy rows are intentionally left unassigned; their date/shift cannot
        # be inferred reliably from the old time-only field.


def get_next_id() -> int:
    """Return the next visible roll ID; SQLite allocates the ID on insert."""
    with get_connection() as connection:
        row = connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM logs").fetchone()
        return int(row[0])


def get_all_rolls() -> list[tuple[int, str]]:
    """Return roll IDs and names, newest first, for station selectors."""
    with get_connection() as connection:
        rows = connection.execute("SELECT id, name FROM logs ORDER BY id DESC").fetchall()
    return [(int(row["id"]), row["name"] or "") for row in rows]


def insert_roll(name: str, gsm: float, output: float) -> int:
    """Create a roll and assign it to the shift active at creation in EAT."""
    now = datetime.now(FACTORY_TIMEZONE)
    created_at = now.isoformat(timespec="seconds")
    shift_date, shift_name = shift_for_datetime(now)
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO logs (name, gsm, output, created_at, shift_date, shift_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, gsm, output, created_at, shift_date, shift_name),
        )
        return int(cursor.lastrowid)


def update_roll_fields(roll_id: int, values: Mapping[str, Any]) -> bool:
    """Update explicitly allow-listed production fields; shift tags are admin-editable."""
    editable = (set(COLUMNS) - {"id"}) | {"shift_date", "shift_name"}
    if not values or not set(values).issubset(editable):
        raise ValueError("No fields supplied or unsupported field name.")
    assignments = ", ".join(f'"{column}" = ?' for column in values)
    parameters = [values[column] for column in values]
    parameters.append(int(roll_id))
    with get_connection() as connection:
        cursor = connection.execute(f"UPDATE logs SET {assignments} WHERE id = ?", parameters)
        return cursor.rowcount > 0


def delete_roll(roll_id: int) -> bool:
    """Delete one roll by its ID."""
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM logs WHERE id = ?", (int(roll_id),))
        return cursor.rowcount > 0


def get_all_logs(descending: bool = True) -> list[dict[str, Any]]:
    """Return records with timestamp and shift metadata, ordered by roll ID."""
    order = "DESC" if descending else "ASC"
    columns = ", ".join((*COLUMNS, "created_at", "shift_date", "shift_name"))
    with get_connection() as connection:
        rows = connection.execute(f"SELECT {columns} FROM logs ORDER BY id {order}").fetchall()
    return [dict(row) for row in rows]


def _build_workbook(records: list[sqlite3.Row]) -> io.BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Production Logs"
    sheet.append(["", "", "Resin Content"])
    sheet.append([
        "ID", "Name", "Right", "Center", "Left", "GSM", "Output", "", "", "", "",
        "oven 1", "Oven 2", "oven 3", "oven 4", "0ven 5", "Oven 6", "L/S", "Time",
    ])
    for record in records:
        sheet.append([
            record["id"], record["name"], record["right_resin"], record["center_resin"],
            record["left_resin"], record["gsm"], record["output"], "", "", "", "",
            record["oven_1"], record["oven_2"], record["oven_3"], record["oven_4"],
            record["oven_5"], record["oven_6"], record["line_speed"], record["log_time"],
        ])
    sheet.freeze_panes = "A3"
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def generate_exact_xlsx() -> io.BytesIO:
    """Build the legacy all-record exact-layout report."""
    with get_connection() as connection:
        records = connection.execute(f"SELECT {', '.join(COLUMNS)} FROM logs ORDER BY id ASC").fetchall()
    return _build_workbook(records)


def generate_shift_xlsx(shift_date: str, shift_name: str) -> io.BytesIO:
    """Build an exact-layout workbook containing only one date and shift."""
    if shift_name not in SHIFT_NAMES:
        raise ValueError("shift_name must be 'Day' or 'Night'.")
    # Validate canonical ISO date before using the date string as a query value.
    if date.fromisoformat(shift_date).isoformat() != shift_date:
        raise ValueError("shift_date must be an ISO date (YYYY-MM-DD).")
    with get_connection() as connection:
        records = connection.execute(
            f"SELECT {', '.join(COLUMNS)} FROM logs WHERE shift_date = ? AND shift_name = ? ORDER BY id ASC",
            (shift_date, shift_name),
        ).fetchall()
    return _build_workbook(records)
