"""
pages/9_Admin.py

Internal admin view -- deliberately NOT part of the normal navigation (see
app.py). Only reachable by opening the app with ?admin=1 in the URL, and
gated by a password stored in .streamlit/secrets.toml as ADMIN_PASSWORD.

This does not call st.set_page_config() -- app.py already does that once
for the whole app.
"""

import os
import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = os.path.join("data", "processed", "businesses.db")


def check_password():
    if st.session_state.get("admin_authed"):
        return True

    st.title("Admin")
    password = st.text_input("Admin password", type="password")
    if st.button("Enter"):
        try:
            correct = st.secrets["ADMIN_PASSWORD"]
        except (KeyError, FileNotFoundError):
            st.error("No ADMIN_PASSWORD set in .streamlit/secrets.toml -- add one to use this page.")
            return False
        if password == correct:
            st.session_state["admin_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


def main():
    if not check_password():
        return

    st.title("Admin")
    st.caption("Internal view -- not linked anywhere in the public app.")

    if not os.path.exists(DB_PATH):
        st.info("No businesses have signed up yet -- businesses.db doesn't exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT business_name, business_type, region, email, created_at FROM businesses ORDER BY created_at DESC",
        conn,
    )
    conn.close()

    st.metric("Total registered businesses", len(df))
    st.dataframe(df, use_container_width=True)

    if st.button("Log out"):
        del st.session_state["admin_authed"]
        st.rerun()


main()
