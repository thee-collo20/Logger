"""Supabase PostgreSQL database layer for Logger."""

from __future__ import annotations

import base64
import io
import logging
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import Client, create_client

LOGGER = logging.getLogger(__name__)
FACTORY_TIMEZONE = ZoneInfo("Africa/Nairobi")

LOG_COLUMNS = [
    "id",
    "timestamp",
    "batch_id",
    "roll_id",
    "product_type",
    "paper_color",
    "paper_gsm",
    "glue_type",
    "line_speed_m_min",
    "oven_zone_1_c",
    "oven_zone_2_c",
    "oven_zone_3_c",
    "oven_zone_4_c",
    "oven_zone_5_c",
    "oven_zone_6_c",
    "oven_zone_7_c",
    "exhaust_fan_1_hz",
    "exhaust_fan_2_hz",
    "exhaust_fan_3_hz",
    "air_blower_1_hz",
    "air_blower_2_hz",
    "air_blower_3_hz",
    "air_blower_4_hz",
    "air_blower_5_hz",
    "air_blower_6_hz",
    "air_blower_7_hz",
    "resin_batch",
    "resin_viscosity_sec",
    "resin_ph",
    "resin_temp_c",
    "resin_solid_content_pct",
    "hardener_dosage_pct",
    "wetting_agent_pct",
    "release_agent_pct",
    "pre_impregnation_weight_g_m2",
    "final_weight_g_m2",
    "resin_pick_up_pct",
    "volatile_content_pct",
    "residual_moisture_pct",
    "curing_degree_pct",
    "board_grade",
    "operator_name",
    "shift",
    "downtime_minutes",
    "downtime_reason",
    "notes",
    "created_by",
    "updated_at",
]


@st.cache_resource
def get_supabase_client() -> Client:
    """Initialize and cache a single Supabase client across Streamlit reruns."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def init_db() -> None:
    """Verify Supabase connectivity (schema is managed via SQL migrations)."""
    try:
        client = get_supabase_client()
        client.table("logs").select("id").limit(1).execute()
    except Exception:
        LOGGER.exception("Failed to verify Supabase connection during init_db")
        raise


def get_shift_window_eat(
    shift_date: date | None = None, shift_name: str | None = None
) -> tuple[datetime, datetime, str, date]:
    """Compute [start, end) timestamps in Africa/Nairobi for Day (07:00-19:00) or Night (19:00-07:00)."""
    now_eat = datetime.now(FACTORY_TIMEZONE)
    if shift_name is None:
        if 7 <= now_eat.hour < 19:
            shift_name = "Day"
            target_date = shift_date or now_eat.date()
        else:
            shift_name = "Night"
            if shift_date is not None:
                target_date = shift_date
            elif now_eat.hour < 7:
                target_date = (now_eat - timedelta(days=1)).date()
            else:
                target_date = now_eat.date()
    else:
        target_date = shift_date or now_eat.date()

    if shift_name.lower().startswith("day"):
        start_dt = datetime.combine(target_date, time(7, 0), tzinfo=FACTORY_TIMEZONE)
        end_dt = datetime.combine(target_date, time(19, 0), tzinfo=FACTORY_TIMEZONE)
        normalized_shift = "Day"
    else:
        start_dt = datetime.combine(target_date, time(19, 0), tzinfo=FACTORY_TIMEZONE)
        end_dt = datetime.combine(
            target_date + timedelta(days=1), time(7, 0), tzinfo=FACTORY_TIMEZONE
        )
        normalized_shift = "Night"

    return start_dt, end_dt, normalized_shift, target_date


def record_activity(
    log_id: int | None, action: str, actor: str, details: str = ""
) -> None:
    """Insert an audit record into log_activity."""
    client = get_supabase_client()
    payload = {
        "log_id": log_id,
        "action": action,
        "actor": actor or "system",
        "details": details,
        "created_at": datetime.now(FACTORY_TIMEZONE).isoformat(),
    }
    try:
        client.table("log_activity").insert(payload).execute()
    except Exception:
        LOGGER.exception("Unable to record log activity")


def insert_log(data: dict[str, Any], actor: str = "operator") -> int:
    """Insert a new production/oven log row and return its new ID."""
    client = get_supabase_client()
    now_iso = datetime.now(FACTORY_TIMEZONE).isoformat()

    row = {k: v for k, v in data.items() if k in LOG_COLUMNS and k != "id"}
    row.setdefault("timestamp", now_iso)
    row["updated_at"] = now_iso
    if actor and not row.get("created_by"):
        row["created_by"] = actor

    res = client.table("logs").insert(row).execute()
    inserted = res.data[0] if res.data else {}
    new_id = int(inserted["id"])

    record_activity(
        log_id=new_id,
        action="CREATE",
        actor=actor,
        details=f"Created log for batch {row.get('batch_id', '')} / roll {row.get('roll_id', '')}",
    )
    return new_id


def update_log(log_id: int, updates: dict[str, Any], actor: str = "operator") -> bool:
    """Update an existing log row by ID."""
    client = get_supabase_client()
    clean_updates = {
        k: v for k, v in updates.items() if k in LOG_COLUMNS and k not in {"id", "created_by"}
    }
    if not clean_updates:
        return False

    clean_updates["updated_at"] = datetime.now(FACTORY_TIMEZONE).isoformat()
    res = client.table("logs").update(clean_updates).eq("id", int(log_id)).execute()
    if res.data:
        record_activity(
            log_id=int(log_id),
            action="UPDATE",
            actor=actor,
            details=f"Updated fields: {', '.join(clean_updates.keys())}",
        )
        return True
    return False


def delete_log(log_id: int, actor: str = "admin") -> bool:
    """Delete a log row by ID and log the deletion."""
    client = get_supabase_client()
    res = client.table("logs").delete().eq("id", int(log_id)).execute()
    if res.data:
        record_activity(
            log_id=None,
            action="DELETE",
            actor=actor,
            details=f"Deleted log ID {log_id}",
        )
        return True
    return False


def fetch_logs(
    limit: int = 500,
    batch_id: str | None = None,
    roll_id: str | None = None,
    shift: str | None = None,
    start_ts: datetime | str | None = None,
    end_ts: datetime | str | None = None,
) -> pd.DataFrame:
    """Query logs from Supabase and return a pandas DataFrame ordered newest-first."""
    client = get_supabase_client()
    query = client.table("logs").select("*").order("timestamp", desc=True)

    if batch_id:
        query = query.ilike("batch_id", f"%{batch_id.strip()}%")
    if roll_id:
        query = query.ilike("roll_id", f"%{roll_id.strip()}%")
    if shift and shift.lower() != "all":
        query = query.eq("shift", shift)
    if start_ts is not None:
        start_iso = start_ts.isoformat() if isinstance(start_ts, datetime) else str(start_ts)
        query = query.gte("timestamp", start_iso)
    if end_ts is not None:
        end_iso = end_ts.isoformat() if isinstance(end_ts, datetime) else str(end_ts)
        query = query.lt("timestamp", end_iso)

    res = query.limit(max(1, int(limit))).execute()
    rows = res.data or []
    if not rows:
        return pd.DataFrame(columns=LOG_COLUMNS)

    df = pd.DataFrame(rows)
    for col in LOG_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[LOG_COLUMNS]


def fetch_shift_logs(
    shift_date: date | None = None, shift_name: str | None = None
) -> pd.DataFrame:
    """Fetch logs belonging to a specific EAT shift window."""
    start_dt, end_dt, _, _ = get_shift_window_eat(shift_date=shift_date, shift_name=shift_name)
    return fetch_logs(limit=1000, start_ts=start_dt, end_ts=end_dt)


def fetch_activity(limit: int = 100) -> pd.DataFrame:
    """Return recent entries from log_activity."""
    client = get_supabase_client()
    res = (
        client.table("log_activity")
        .select("*")
        .order("created_at", desc=True)
        .limit(max(1, int(limit)))
        .execute()
    )
    rows = res.data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["id", "log_id", "action", "actor", "details", "created_at"]
    )


def upsert_glue_recipe(recipe: dict[str, Any], actor: str = "operator") -> dict[str, Any]:
    """Insert or update a glue recipe keyed by recipe_name."""
    client = get_supabase_client()
    payload = {
        "recipe_name": recipe["recipe_name"].strip(),
        "glue_type": recipe.get("glue_type"),
        "resin_ratio": recipe.get("resin_ratio"),
        "hardener_pct": recipe.get("hardener_pct"),
        "wetting_agent_pct": recipe.get("wetting_agent_pct"),
        "release_agent_pct": recipe.get("release_agent_pct"),
        "water_pct": recipe.get("water_pct"),
        "target_viscosity_sec": recipe.get("target_viscosity_sec"),
        "target_ph": recipe.get("target_ph"),
        "notes": recipe.get("notes"),
        "updated_by": actor,
        "updated_at": datetime.now(FACTORY_TIMEZONE).isoformat(),
    }
    res = (
        client.table("glue_recipes")
        .upsert(payload, on_conflict="recipe_name")
        .execute()
    )
    return res.data[0] if res.data else payload


def fetch_glue_recipes() -> pd.DataFrame:
    """Fetch all saved glue recipes ordered by recipe_name."""
    client = get_supabase_client()
    res = client.table("glue_recipes").select("*").order("recipe_name").execute()
    rows = res.data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=[
            "id",
            "recipe_name",
            "glue_type",
            "resin_ratio",
            "hardener_pct",
            "wetting_agent_pct",
            "release_agent_pct",
            "water_pct",
            "target_viscosity_sec",
            "target_ph",
            "notes",
            "updated_by",
            "updated_at",
        ]
    )


def delete_glue_recipe(recipe_id: int) -> bool:
    """Delete a glue recipe by ID."""
    client = get_supabase_client()
    res = client.table("glue_recipes").delete().eq("id", int(recipe_id)).execute()
    return bool(res.data)


def save_image_upload(
    filename: str,
    mime_type: str,
    image_bytes: bytes,
    category: str = "general",
    shift_date: date | str | None = None,
    shift_name: str | None = None,
    roll_id: str | None = None,
    notes: str | None = None,
    uploaded_by: str | None = None,
) -> int:
    """Persist an uploaded image to Supabase image_uploads."""
    client = get_supabase_client()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    shift_date_str = (
        shift_date.isoformat() if isinstance(shift_date, date) else shift_date
    )
    payload = {
        "filename": filename,
        "mime_type": mime_type,
        "category": category,
        "shift_date": shift_date_str,
        "shift_name": shift_name,
        "roll_id": roll_id,
        "notes": notes,
        "uploaded_by": uploaded_by,
        "image_data_b64": encoded,
        "created_at": datetime.now(FACTORY_TIMEZONE).isoformat(),
    }
    res = client.table("image_uploads").insert(payload).execute()
    return int(res.data[0]["id"])


def fetch_image_uploads(
    category: str | None = None,
    shift_date: date | str | None = None,
    limit: int = 100,
    include_bytes: bool = False,
) -> list[dict[str, Any]]:
    """Retrieve uploaded image metadata (and optionally decoded image bytes)."""
    client = get_supabase_client()
    cols = (
        "id,filename,mime_type,category,shift_date,shift_name,roll_id,notes,uploaded_by,created_at,image_data_b64"
        if include_bytes
        else "id,filename,mime_type,category,shift_date,shift_name,roll_id,notes,uploaded_by,created_at"
    )
    query = client.table("image_uploads").select(cols).order("created_at", desc=True)
    if category:
        query = query.eq("category", category)
    if shift_date:
        sd = shift_date.isoformat() if isinstance(shift_date, date) else str(shift_date)
        query = query.eq("shift_date", sd)

    res = query.limit(max(1, int(limit))).execute()
    items = []
    for row in res.data or []:
        entry = dict(row)
        b64 = entry.pop("image_data_b64", None)
        if include_bytes and b64:
            entry["image_data"] = base64.b64decode(b64)
        items.append(entry)
    return items


def get_image_upload_bytes(upload_id: int) -> tuple[bytes, str, str] | None:
    """Return (image_bytes, mime_type, filename) for a single upload ID."""
    client = get_supabase_client()
    res = (
        client.table("image_uploads")
        .select("image_data_b64,mime_type,filename")
        .eq("id", int(upload_id))
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


def delete_image_upload(upload_id: int) -> bool:
    """Delete an uploaded image row by ID."""
    client = get_supabase_client()
    res = client.table("image_uploads").delete().eq("id", int(upload_id)).execute()
    return bool(res.data)


def export_logs_to_excel(df: pd.DataFrame | None = None) -> bytes:
    """Export provided logs DataFrame (or recent logs) to an in-memory XLSX file."""
    target_df = df if df is not None else fetch_logs(limit=5000)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        target_df.to_excel(writer, index=False, sheet_name="Production_Logs")
    return buffer.getvalue()
