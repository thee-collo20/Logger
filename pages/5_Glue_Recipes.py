"""Glue chef workspace for maintaining multiple named paper glue recipes."""

import sqlite3

import pandas as pd
import streamlit as st

from auth import require_role
from db import get_glue_recipes, init_db, save_glue_recipe
from nav import render_nav

st.set_page_config(page_title="Glue Recipes | Lamination Logger", page_icon="🧴", layout="wide")
user = require_role({"Admin", "Glue Chef"})
render_nav()
init_db()

st.title("🧴 Paper Glue Recipes")
st.caption("Create and maintain multiple recipes. Changes are attributed to the signed-in glue chef.")
recipes = get_glue_recipes()

if recipes:
    st.subheader("Recipe library")
    summary = pd.DataFrame([
        {"Recipe": recipe["name"], "Last updated by": recipe["updated_by"], "Updated at (EAT)": recipe["updated_at"]}
        for recipe in recipes
    ])
    st.dataframe(summary, use_container_width=True, hide_index=True)
    selected_id = st.selectbox(
        "Choose a recipe to view or update",
        options=[recipe["id"] for recipe in recipes],
        format_func=lambda recipe_id: next(item["name"] for item in recipes if item["id"] == recipe_id),
    )
    selected = next(recipe for recipe in recipes if recipe["id"] == selected_id)
    with st.expander(f"Current recipe: {selected['name']}", expanded=True):
        st.markdown("**Ingredients / proportions**")
        st.text(selected["ingredients"])
        st.markdown("**Mixing instructions**")
        st.write(selected["instructions"])
        st.caption(f"Created by {selected['created_by']} · last updated by {selected['updated_by']} at {selected['updated_at']} EAT")
else:
    selected_id = None
    selected = None
    st.info("No glue recipes yet. Add the first recipe below; you can create as many named recipes as needed.")

st.divider()
st.subheader("Add a recipe" if selected is None else "Update selected recipe or add another")
mode = st.radio("Recipe action", ["Add a new recipe", "Update selected recipe"], horizontal=True, key="glue_recipe_action")
editing = mode == "Update selected recipe" and selected is not None
with st.form("glue_recipe_form", clear_on_submit=not editing):
    name = st.text_input("Recipe name", value=selected["name"] if editing else "", placeholder="e.g. Standard Paper Glue")
    ingredients = st.text_area(
        "Ingredients and proportions",
        value=selected["ingredients"] if editing else "",
        placeholder="List each ingredient and its quantity or ratio on a separate line.", height=150,
    )
    instructions = st.text_area(
        "Mixing instructions",
        value=selected["instructions"] if editing else "",
        placeholder="Describe the mixing order, time, and any handling notes.", height=180,
    )
    submitted = st.form_submit_button("Save recipe", type="primary", use_container_width=True)
if submitted:
    if not name.strip() or not ingredients.strip() or not instructions.strip():
        st.error("Enter a recipe name, ingredients/proportions, and mixing instructions.")
    else:
        try:
            save_glue_recipe(name, ingredients, instructions, user["username"], recipe_id=selected_id if editing else None)
        except sqlite3.IntegrityError:
            st.error("A recipe with that name already exists. Choose a different name or update the existing recipe.")
        except ValueError as error:
            st.error(str(error))
        else:
            st.success(f"Recipe '{name.strip()}' saved.")
            st.rerun()
