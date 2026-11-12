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
            border-radius: 0.6rem;
            font-weight: 600;
            justify-content: center;
        }
        @media (max-width: 700px) {
            div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
            div[data-testid="stHorizontalBlock"] > div { min-width: 30%; }
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
