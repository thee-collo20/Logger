"""Shared top navigation for the production logger."""

import streamlit as st


def render_nav() -> None:
    """Render links to every app page in a touch-friendly horizontal bar."""
    links = [
        ("app.py", "Dashboard", "📊"),
        ("pages/1_Paper_ID.py", "Paper ID", "🪵"),
        ("pages/2_Resin_Content.py", "Resin Content", "🧪"),
        ("pages/3_Ovens_Line.py", "Ovens & Line", "🔥"),
        ("admin.py", "Admin", "📋"),
    ]
    st.markdown(
        """
        <style>
        div[data-testid="stPageLink"] a {
            min-height: 2.8rem;
            border-radius: 0.6rem;
            font-weight: 600;
            justify-content: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    columns = st.columns(len(links))
    for column, (page, label, icon) in zip(columns, links):
        with column:
            st.page_link(page, label=label, icon=icon, use_container_width=True)
    st.divider()
