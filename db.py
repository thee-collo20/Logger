"""SQLite persistence helpers for the wood lamination production logger."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from openpyxl import Workbook

DB_PATH = Path(__file__).resolve().parent / "production_logs.db"

COLUMNS = (
    "id",
    "name",
    "right_resin",
    "center_resin",
    "left_resin",
    "gsm",
    "output",
    "oven_1",
    "oven_2",
    "oven_3",
    "oven_4",
    "oven_5",
    "oven_6",
    "line_speed",
    "log_time",
)


def get_connection() -> sqlite3.Connection:
    """Return a configured connection; callers are responsible for closing it."""
    connection = sqlite3.connect(
        DB_PATH, timeout=15, check_same_thread=False
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def init_db() -> None:
    """Create the production log table if it does not already exist."""
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
                log_time TEXT
            )"""
        )


def get_next_id() -> int:
    """Return the next visible roll ID. Inserts still use SQLite's AUTOINCREMENT."""
    with get_connection() as connection:
        result = connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM logs"
        ).fetchone()
        return int(result[0])


def get_all_rolls() -> list[tuple[int, str]]:
    """Return roll IDs and names, newest first, for station selectors."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name FROM logs ORDER BY id DESC"
        ).fetchall()
    return [(int(row["id"]), row["name"] or "") for row in rows]


def insert_roll(name: str, gsm: float, output: float) -> int:
    """Create a roll and return the ID allocated by SQLite."""
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO logs (name, gsm, output) VALUES (?, ?, ?)",
            (name, gsm, output),
        )
        return int(cursor.lastrowid)


def update_roll_fields(roll_id: int, values: Mapping[str, Any]) -> bool:
    """Update a safe, explicitly allow-listed subset of columns on a roll."""
    editable = set(COLUMNS) - {"id"}
    if not values or not set(values).issubset(editable):
        raise ValueError("No fields supplied or unsupported field name.")
    assignments = ", ".join(f'"{column}" = ?' for column in values)
    parameters = [values[column] for column in values]
    parameters.append(int(roll_id))
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE logs SET {assignments} WHERE id = ?", parameters
        )
        return cursor.rowcount > 0


def delete_roll(roll_id: int) -> bool:
    """Delete one roll by its ID."""
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM logs WHERE id = ?", (int(roll_id),))
        return cursor.rowcount > 0


def get_all_logs(descending: bool = True) -> list[dict[str, Any]]:
    """Return all production records as dictionaries."""
    order = "DESC" if descending else "ASC"
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT {', '.join(COLUMNS)} FROM logs ORDER BY id {order}"
        ).fetchall()
    return [dict(row) for row in rows]


def generate_exact_xlsx() -> io.BytesIO:
    """Build the requested Excel report in memory, preserving its exact layout."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Production Logs"
    sheet.append(["", "", "Resin Content"])
    sheet.append(
        [
            "ID", "Name", "Right", "Center", "Left", "GSM", "Output", "", "", "", "",
            "oven 1", "Oven 2", "oven 3", "oven 4", "0ven 5", "Oven 6", "L/S", "Time",
        ]
    )
    with get_connection() as connection:
        records = connection.execute(
            f"SELECT {', '.join(COLUMNS)} FROM logs ORDER BY id ASC"
        ).fetchall()
    for record in records:
        row = [
            record["id"],
            record["name"],
            record["right_resin"],
            record["center_resin"],
            record["left_resin"],
            record["gsm"],
            record["output"],
            "", "", "", "",
            record["oven_1"],
            record["oven_2"],
            record["oven_3"],
            record["oven_4"],
            record["oven_5"],
            record["oven_6"],
            record["line_speed"],
            record["log_time"],
        ]
        sheet.append(row)
    sheet.freeze_panes = "A3"
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output
