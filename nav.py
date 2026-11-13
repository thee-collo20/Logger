"""Shared top navigation for the production logger."""

import streamlit as st


def render_nav() -> None:
    """Render navigation to pages registered in Streamlit's pages directory."""
    links = [
        ("app.py", "Dashboard", "📊"),
        ("pages/1_Paper_ID.py", "Paper ID", "🪵"),
        ("pages/2_Resin_Content.py", "Resin Content", "🧪"),
        ("pages/3_Ovens_Line.py", "Ovens & Line", "🔥"),
        ("pages/4_Admin.py", "Admin", "📋"),
    ]
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
    columns = st.columns(len(links))
    for column, (page, label, icon) in zip(columns, links):
        with column:
            st.page_link(page, label=label, icon=icon, use_container_width=True)
    st.divider()
