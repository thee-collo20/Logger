"""Shared authentication and rank-based page authorization."""

from __future__ import annotations

import hmac
from typing import Any

import streamlit as st

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
    """Return valid users from Streamlit secrets, keyed by lowercase username."""
    try:
        configured = st.secrets.get("users", {})
    except Exception:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for username, details in configured.items():
        try:
            user = dict(details)
        except (TypeError, ValueError):
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
    # Backward compatibility: the previous app accepted one admin_password.
    # This account is only added if no explicit admin username is configured.
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


def render_login() -> dict[str, str] | None:
    """Render a credentials form and return the authenticated user, if any."""
    user = current_user()
    if user:
        return user
    users = _configured_users()
    if not users:
        st.error(
            "No accounts are configured. In Streamlit Cloud, add `[users.admin]` with `password` and `rank = \"Admin\"` under App settings → Secrets."
        )
        st.stop()

    st.title("🔐 Biashara Masters Sawmill sign in")
    with st.form("login_form"):
        username = st.text_input("Username").strip().casefold()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        account = users.get(username)
        if account and hmac.compare_digest(password, account["password"]):
            st.session_state["auth_username"] = account["username"]
            st.session_state["auth_rank"] = account["rank"]
            st.rerun()
        st.error("Incorrect username or password. Usernames are case-insensitive; check the deployed app's Secrets and save/restart after changes.")
    return None


def require_role(allowed_ranks: set[str] | tuple[str, ...] | list[str]) -> dict[str, str]:
    """Require a signed-in user with one of the specified ranks, stopping otherwise."""
    user = render_login()
    if not user:
        st.stop()
    if user["rank"] not in allowed_ranks:
        st.error("Your rank does not have access to this page.")
        st.stop()
    return user


def logout() -> None:
    """Clear the current authenticated session."""
    st.session_state.pop("auth_username", None)
    st.session_state.pop("auth_rank", None)
    st.rerun()
