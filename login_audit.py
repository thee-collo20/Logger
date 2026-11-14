"""Write successful login events to a separate CSV audit file."""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
AUDIT_FILE = Path(__file__).resolve().parent / "login_activity.csv"
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")


def record_login(username: str, rank: str) -> bool:
    """Append a successful login's username, rank, and local timestamp to CSV."""
    try:
        needs_header = not AUDIT_FILE.exists() or AUDIT_FILE.stat().st_size == 0
        with AUDIT_FILE.open("a", newline="", encoding="utf-8") as audit_file:
            writer = csv.writer(audit_file)
            if needs_header:
                writer.writerow(["username", "rank", "logged_in_at_eat"])
            writer.writerow([
                username,
                rank,
                datetime.now(FACTORY_TIMEZONE).isoformat(timespec="seconds"),
            ])
        return True
    except OSError:
        # Login is more important than audit-file availability; never log passwords.
        LOGGER.exception("Unable to append to login audit CSV")
        return False


def get_login_audit_csv() -> bytes | None:
    """Read the login audit CSV for an authorized download, when present."""
    try:
        if not AUDIT_FILE.exists():
            return None
        return AUDIT_FILE.read_bytes()
    except OSError:
        LOGGER.exception("Unable to read login audit CSV")
        return None
