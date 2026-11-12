"""Supervisor dashboard for the wood lamination production logger."""

import pandas as pd
import streamlit as st

from db import COLUMNS, delete_roll, generate_exact_xlsx, get_all_logs, init_db, update_roll_fields

st.set_page_config(page_title="Production Logs | Supervisor", page_icon="🪵", layout="wide")
init_db()

st.title("🪵 Wood Lamination — Production Logs")
st.caption("Supervisor dashboard · live production records")

if "refresh_counter" not in st.session_state:
    st.session_state.refresh_counter = 0

refresh_col, download_col = st.columns([1, 2])
with refresh_col:
    if st.button("↻ Refresh Data", use_container_width=True):
        st.session_state.refresh_counter += 1
        st.rerun()
with download_col:
    st.download_button(
        "⬇ Download Exact XLSX Report",
        data=generate_exact_xlsx(),
        file_name="wood_lamination_production.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

records = get_all_logs(descending=True)
if records:
    st.dataframe(pd.DataFrame(records, columns=COLUMNS), use_container_width=True, hide_index=True)
else:
    st.info("No production logs yet. Records entered at the stations will appear here.")

st.divider()
st.subheader("Correct or remove a record")
if not records:
    st.caption("There are no records to edit or delete.")
else:
    record_by_id = {int(row["id"]): row for row in records}
    selected_id = st.selectbox(
        "Select roll ID",
        options=list(record_by_id),
        format_func=lambda roll_id: f"ID #{roll_id} — {record_by_id[roll_id]['name'] or '(unnamed)'}",
    )
    current = record_by_id[selected_id]
    with st.expander(f"Edit roll #{selected_id}"):
        with st.form("edit_record_form"):
            name = st.text_input("Name", value=current["name"] or "")
            a, b, c = st.columns(3)
            with a:
                right = st.number_input("Right resin", value=float(current["right_resin"] or 0.0), format="%.3f")
                left = st.number_input("Left resin", value=float(current["left_resin"] or 0.0), format="%.3f")
                gsm = st.number_input("GSM", value=float(current["gsm"] or 0.0), format="%.2f")
                output = st.number_input("Output", value=float(current["output"] or 0.0), format="%.2f")
                speed = st.number_input("Line speed (L/S)", value=float(current["line_speed"] or 0.0), format="%.2f")
            with b:
                center = st.number_input("Center resin", value=float(current["center_resin"] or 0.0), format="%.3f")
                oven_1 = st.number_input("Oven 1", value=float(current["oven_1"] or 0.0), format="%.2f")
                oven_2 = st.number_input("Oven 2", value=float(current["oven_2"] or 0.0), format="%.2f")
                oven_3 = st.number_input("Oven 3", value=float(current["oven_3"] or 0.0), format="%.2f")
            with c:
                oven_4 = st.number_input("Oven 4", value=float(current["oven_4"] or 0.0), format="%.2f")
                oven_5 = st.number_input("Oven 5", value=float(current["oven_5"] or 0.0), format="%.2f")
                oven_6 = st.number_input("Oven 6", value=float(current["oven_6"] or 0.0), format="%.2f")
                log_time = st.text_input("Time", value=current["log_time"] or "")
            save = st.form_submit_button("Save changes", type="primary", use_container_width=True)
        if save:
            cleaned_name = name.strip()
            if not cleaned_name:
                st.error("Name cannot be blank.")
            else:
                update_roll_fields(
                    selected_id,
                    {
                        "name": cleaned_name,
                        "right_resin": right,
                        "center_resin": center,
                        "left_resin": left,
                        "gsm": gsm,
                        "output": output,
                        "oven_1": oven_1,
                        "oven_2": oven_2,
                        "oven_3": oven_3,
                        "oven_4": oven_4,
                        "oven_5": oven_5,
                        "oven_6": oven_6,
                        "line_speed": speed,
                        "log_time": log_time.strip(),
                    },
                )
                st.success(f"Roll #{selected_id} updated.")
                st.rerun()

    with st.expander(f"Delete roll #{selected_id}"):
        st.warning("Deleting a record is permanent and removes it from future reports.")
        confirm = st.checkbox(f"I understand — delete roll #{selected_id}", key=f"confirm_delete_{selected_id}")
        if st.button("Delete selected record", type="secondary", disabled=not confirm):
            if delete_roll(selected_id):
                st.success(f"Roll #{selected_id} deleted.")
                st.rerun()
            st.error("That record no longer exists; refresh and try again.")
