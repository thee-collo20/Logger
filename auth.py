"""Shared authentication and rank-based page authorization."""

from __future__ import annotations

import hmac
from typing import Any

import streamlit as st

# Keep roles centralized so navigation and direct page access use the same policy.
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
    """Return users configured in Streamlit secrets, keyed by lowercase username."""
    if "users" not in st.secrets:
        return {}
    configured = st.secrets["users"]
    result: dict[str, dict[str, Any]] = {}
    for username, details in configured.items():
        user = dict(details)
        rank = str(user.get("rank", ""))
        password = str(user.get("password", ""))
        if username and password and rank in VALID_RANKS:
            result[str(username).strip().lower()] = {
                "username": str(username).strip(),
                "password": password,
                "rank": rank,
            }
    return result


def current_user() -> dict[str, str] | None:
    """Return the signed-in user only while their account remains configured."""
    username = st.session_state.get("auth_username")
    if not username:
        return None
    user = _configured_users().get(str(username).lower())
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
        st.error("Authentication is not configured. Add user accounts under `[users.<username>]` in Streamlit secrets; see README.md.")
        st.stop()

    st.title("🔐 Production Logger sign in")
    with st.form("login_form"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        account = users.get(username)
        if account and hmac.compare_digest(password, account["password"]):
            st.session_state["auth_username"] = account["username"]
            st.session_state["auth_rank"] = account["rank"]
            st.rerun()
        st.error("Incorrect username or password.")
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
