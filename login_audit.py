"""Audit file for login events without storing passwords."""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
AUDIT_FILE = Path(__file__).resolve().parent / "login_activity.csv"
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")


def _audit_path() -> Path:
    return AUDIT_FILE


def _append_event(username: str, rank: str, status: str, at_time: datetime | None = None) -> bool:
    """Append a login event row for success or failure without storing a password."""
    timing = at_time or datetime.now(FACTORY_TIMEZONE)
    try:
        needs_header = not _audit_path().exists() or _audit_path().stat().st_size == 0
        with _audit_path().open("a", newline="", encoding="utf-8") as audit_file:
            writer = csv.writer(audit_file)
            if needs_header:
                writer.writerow(["username", "rank", "status", "logged_at_eat"])
            writer.writerow([
                username,
                rank,
                status,
                timing.isoformat(timespec="seconds"),
            ])
        return True
    except OSError:
        LOGGER.exception("Unable to append to login audit CSV")
        return False


def record_login(username: str, rank: str) -> bool:
    """Append a successful login event."""
    return _append_event(username, rank, "success")


def record_failed_login(username: str, rank: str = "Unknown") -> bool:
    """Append a failed login event; rank is known only when supplied by the app."""
    return _append_event(username, rank, "failed")


def get_login_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent rows from the login audit CSV, newest first."""
    if not _audit_path().exists():
        return []
    try:
        with _audit_path().open("r", newline="", encoding="utf-8") as audit_file:
            reader = csv.DictReader(audit_file)
            rows = list(reader)
    except (OSError, csv.Error):
        LOGGER.exception("Unable to read login audit CSV")
        return []
    history = []
    for row in rows:
        if not row:
            continue
        history.append({
            "username": row.get("username", ""),
            "rank": row.get("rank", ""),
            "status": row.get("status", "unknown"),
            "logged_at_eat": row.get("logged_at_eat", ""),
        })
    return history[: max(1, int(limit))]


def get_last_successful_login() -> dict[str, str] | None:
    """Read the most recent successful login event."""
    for row in reversed(get_login_history(limit=200)):
        if row.get("status") == "success":
            return row
    return None


def get_login_audit_csv() -> bytes | None:
    """Read the login audit CSV for an authorized download, when present."""
    try:
        if not _audit_path().exists():
            return None
        return _audit_path().read_bytes()
    except OSError:
        LOGGER.exception("Unable to read login audit CSV")
        return None
