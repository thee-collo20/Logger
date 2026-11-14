"""Shared authentication and rank-based page authorization."""

from __future__ import annotations

import hmac
import logging
from typing import Any

import streamlit as st

from login_audit import record_failed_login, record_login

LOGGER = logging.getLogger(__name__)
PAGE_ROLES = {
    "Dashboard": {"Admin", "Supervisor"},
    "Paper ID": {"Admin", "Supervisor", "Operator"},
    "Resin Content": {"Admin", "Supervisor", "Operator"},
    "Ovens & Line": {"Admin", "Supervisor", "Operator"},
    "Admin": {"Admin", "Supervisor"},
    "Glue Recipes": {"Admin", "Glue Chef"},
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
            result[clean_username.casefold()] = {
                "username": clean_username,
                "password": password,
                "rank": rank,
            }
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
        attempted_user = username or "unknown"
        record_failed_login(attempted_user)
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

    st.title("🔐 Biashara Masters Sawmill sign in")
    with st.form("login_form", clear_on_submit=True):
        st.text_input("Username", placeholder="admin", key="login_username")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button(
            "Sign in", type="primary", use_container_width=True, on_click=_handle_login_submit
        )

    error = st.session_state.pop("login_error", "")
    if error:
        st.error(error)
    return current_user()


def require_role(allowed_ranks: set[str] | tuple[str, ...] | list[str]) -> dict[str, str]:
    user = render_login()
    if not user:
        st.stop()
    if user["rank"] not in allowed_ranks:
        st.error("Your rank does not have access to this page.")
        st.stop()
    return user


def logout() -> None:
    st.session_state.pop("auth_username", None)
    st.session_state.pop("auth_rank", None)
    st.rerun()
