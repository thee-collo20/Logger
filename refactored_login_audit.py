"""Supabase PostgreSQL audit log for login events without storing passwords."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from db import get_supabase_client

LOGGER = logging.getLogger(__name__)
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")


def _append_event(
    username: str, rank: str, status: str, at_time: datetime | None = None
) -> bool:
    """Insert a login event row for success or failure without storing a password."""
    timing = at_time or datetime.now(FACTORY_TIMEZONE)
    try:
        client = get_supabase_client()
        payload = {
            "username": username,
            "rank": rank,
            "status": status,
            "logged_at_eat": timing.isoformat(timespec="seconds"),
        }
        client.table("login_activity").insert(payload).execute()
        return True
    except Exception:
        LOGGER.exception("Unable to insert login audit event into Supabase")
        return False


def record_login(username: str, rank: str) -> bool:
    """Record a successful login event."""
    return _append_event(username, rank, "success")


def record_failed_login(username: str, rank: str = "Unknown") -> bool:
    """Record a failed login event; rank is known only when supplied by the app."""
    return _append_event(username, rank, "failed")


def get_login_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent rows from login_activity, newest first."""
    try:
        client = get_supabase_client()
        res = (
            client.table("login_activity")
            .select("username,rank,status,logged_at_eat")
            .order("logged_at_eat", desc=True)
            .limit(max(1, int(limit)))
            .execute()
        )
    except Exception:
        LOGGER.exception("Unable to read login audit history from Supabase")
        return []

    history: list[dict[str, Any]] = []
    for row in res.data or []:
        history.append(
            {
                "username": row.get("username", ""),
                "rank": row.get("rank", ""),
                "status": row.get("status", "unknown"),
                "logged_at_eat": row.get("logged_at_eat", ""),
            }
        )
    return history


def get_last_successful_login() -> dict[str, str] | None:
    """Read the most recent successful login event."""
    try:
        client = get_supabase_client()
        res = (
            client.table("login_activity")
            .select("username,rank,status,logged_at_eat")
            .eq("status", "success")
            .order("logged_at_eat", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return {
                "username": str(row.get("username", "")),
                "rank": str(row.get("rank", "")),
                "status": str(row.get("status", "success")),
                "logged_at_eat": str(row.get("logged_at_eat", "")),
            }
    except Exception:
        LOGGER.exception("Unable to fetch last successful login from Supabase")
    return None


def get_login_audit_csv() -> bytes | None:
    """Generate an in-memory CSV of login audit events for authorized admin downloads."""
    rows = get_login_history(limit=5000)
    if not rows:
        return None
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["username", "rank", "status", "logged_at_eat"])
    for row in rows:
        writer.writerow(
            [
                row.get("username", ""),
                row.get("rank", ""),
                row.get("status", ""),
                row.get("logged_at_eat", ""),
            ]
        )
    return buf.getvalue().encode("utf-8")
