"""SQLite persistence helpers for shift-based wood lamination production logs."""

from __future__ import annotations

import io
import logging
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from openpyxl import Workbook

DB_PATH = Path(__file__).resolve().parent / "production_logs.db"
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")
SHIFT_NAMES = ("Day", "Night")
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
    """Create production/recipe tables and migrate existing databases safely."""
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
        # Backfill activity shift context from the associated production record.
        # Deleted records have no recoverable shift metadata in older databases.
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

    # Older app databases may not yet have the added shift columns. This query
    # intentionally never references those columns on log_activity.
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
