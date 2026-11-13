"""Shared top navigation for the production logger."""

import streamlit as st

from auth import PAGE_ROLES, current_user, logout


_LINKS = [
    ("app.py", "Dashboard", "📊", "Dashboard"),
    ("pages/1_Paper_ID.py", "Paper ID", "🪵", "Paper ID"),
    ("pages/2_Resin_Content.py", "Resin Content", "🧪", "Resin Content"),
    ("pages/3_Ovens_Line.py", "Ovens & Line", "🔥", "Ovens & Line"),
    ("pages/4_Admin.py", "Shift Reports", "📋", "Admin"),
    ("pages/5_Glue_Recipes.py", "Glue Recipes", "🧴", "Glue Recipes"),
]


def render_nav() -> None:
    """Render only links that are allowed for the current authenticated rank."""
    user = current_user()
    if not user:
        return
    links = [link for link in _LINKS if user["rank"] in PAGE_ROLES[link[3]]]
    st.markdown(
        """
        <style>
        div[data-testid="stPageLink"] a {
            min-height: 2.8rem;
            border: 1px solid #485459;
            border-radius: 0.6rem;
            font-weight: 600;
            justify-content: center;
        }
        div[data-testid="stPageLink"] a:hover {
            border-color: #F59E0B;
            color: #FBBF24;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    columns = st.columns(len(links) + 1)
    for column, (page, label, icon, _permission) in zip(columns, links):
        with column:
            st.page_link(page, label=label, icon=icon, use_container_width=True)
    with columns[-1]:
        st.caption(f"{user['username']} · {user['rank']}")
        if st.button("Sign out", use_container_width=True):
            logout()
    st.divider()
