"""Shared authentication and rank-based page authorization."""

from __future__ import annotations

import hmac
import logging
from typing import Any

import streamlit as st

from login_audit import record_failed_login, record_login

LOGGER = logging.getLogger(__name__)
PAGE_ROLES = {
    "Dashboard": {"Admin", "Supervisor", "Production Manager"},
    "Paper ID": {"Admin", "Supervisor", "Operator", "Secretary", "Production Manager"},
    "Resin Content": {"Admin", "Supervisor", "Operator", "Production Manager"},
    "Ovens & Line": {"Admin", "Supervisor", "Operator", "Production Manager"},
    "Admin": {"Admin", "Supervisor", "Production Manager"},
    "Glue Recipes": {"Admin", "Glue Chef", "Production Manager"},
    "Karani Uploads": {"Admin", "Secretary", "Production Manager"},
    "Production OCR": {"Admin", "Secretary", "Production Manager"},
}
_PAGE_PATHS = {
    "Dashboard": "app.py",
    "Paper ID": "pages/1_Paper_ID.py",
    "Resin Content": "pages/2_Resin_Content.py",
    "Ovens & Line": "pages/3_Ovens_Line.py",
    "Admin": "pages/4_Admin.py",
    "Glue Recipes": "pages/5_Glue_Recipes.py",
    "Karani Uploads": "pages/6_Secretary_Uploads.py",
    "Production OCR": "pages/7_Production_OCR.py",
}
VALID_RANKS = {rank for ranks in PAGE_ROLES.values() for rank in ranks}


def _configured_users() -> dict[str, dict[str, Any]]:
    """Load supported accounts from Streamlit secrets without exposing passwords."""
    try:
        configured = st.secrets.get("users", {})
    except Exception:
        LOGGER.exception("Unable to read Streamlit users secrets")
        return {}
    result: dict[str, dict[str, Any]] = {}
    if not hasattr(configured, "items"):
        LOGGER.error("The Streamlit [users] secret must be a table of username tables")
        return {}
    for username, details in configured.items():
        try:
            user = dict(details)
        except (TypeError, ValueError):
            LOGGER.warning("Ignoring malformed account entry in Streamlit secrets")
            continue
        rank_value = str(user.get("rank", "")).strip().casefold()
        rank = next((known for known in VALID_RANKS if known.casefold() == rank_value), None)
        password = str(user.get("password", ""))
        clean_username = str(username).strip()
        if clean_username and password and rank:
            result[clean_username.casefold()] = {"username": clean_username, "password": password, "rank": rank}
        elif clean_username:
            LOGGER.warning("Ignoring account '%s': password or supported rank is missing", clean_username)
    try:
        legacy_password = str(st.secrets.get("admin_password", ""))
    except Exception:
        legacy_password = ""
    if legacy_password and "admin" not in result:
        result["admin"] = {"username": "admin", "password": legacy_password, "rank": "Admin"}
    return result


def current_user() -> dict[str, str] | None:
    """Return the signed-in user only while their account remains configured."""
    username = st.session_state.get("auth_username")
    if not username:
        return None
    user = _configured_users().get(str(username).casefold())
    if not user or st.session_state.get("auth_rank") != user["rank"]:
        st.session_state.pop("auth_username", None)
        st.session_state.pop("auth_rank", None)
        return None
    return {"username": user["username"], "rank": user["rank"]}


def _handle_login_submit() -> None:
    """Authenticate submitted credentials and clear input widgets after each attempt."""
    username = str(st.session_state.get("login_username", "")).strip().casefold()
    password = str(st.session_state.get("login_password", ""))
    account = _configured_users().get(username)
    if account and hmac.compare_digest(password, account["password"]):
        st.session_state["auth_username"] = account["username"]
        st.session_state["auth_rank"] = account["rank"]
        st.session_state["login_error"] = ""
        record_login(account["username"], account["rank"])
    else:
        record_failed_login(username or "unknown")
        st.session_state["login_error"] = (
            "Sign-in failed. Usernames are case-insensitive, passwords are case-sensitive. "
            "For the legacy `admin_password` secret, use username `admin`; otherwise check "
            "the account values in this app's deployed Streamlit Secrets."
        )
    st.session_state["login_username"] = ""
    st.session_state["login_password"] = ""


def render_login() -> dict[str, str] | None:
    """Render the credentials form and return the authenticated account, if any."""
    user = current_user()
    if user:
        return user
    users = _configured_users()
    if not users:
        st.error(
            "No valid accounts were loaded. In Streamlit Cloud, check App settings → Secrets. "
            "Use `[users.admin]` with `password = \"...\"` and `rank = \"Admin\"`, then save and restart."
        )
        st.stop()
    st.session_state.setdefault("login_username", "")
    st.session_state.setdefault("login_password", "")
    st.title("🔐 Biashara Masters Sawmill sign in")
    with st.form("login_form", clear_on_submit=True):
        st.text_input("Username", key="login_username")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign in", type="primary", use_container_width=True, on_click=_handle_login_submit)
    error = st.session_state.pop("login_error", "")
    if error:
        st.error(error)
    return current_user()


def require_role(
    allowed_ranks: set[str] | tuple[str, ...] | list[str],
    *,
    allow_production_manager: bool = False,
) -> dict[str, str]:
    """Require an allowed rank and redirect unauthorized users to an accessible page."""
    user = render_login()
    if not user:
        st.stop()
    if user["rank"] not in allowed_ranks:
        destination = next(
            (path for page, path in _PAGE_PATHS.items() if user["rank"] in PAGE_ROLES[page]),
            None,
        )
        if destination:
            st.switch_page(destination)
        st.stop()
    return user


def logout() -> None:
    st.session_state.pop("auth_username", None)
    st.session_state.pop("auth_rank", None)
    st.rerun()
