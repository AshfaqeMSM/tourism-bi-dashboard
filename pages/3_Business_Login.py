"""
pages/3_Business_Login.py

Login/signup for tourism-dependent businesses (food, accommodation, retail,
local vendors). Uses a local SQLite database -- no external service needed,
appropriate for a student project. Passwords are hashed with bcrypt, never
stored in plain text.

On successful login, sets st.session_state["business_user"] so other pages
(e.g. a future Business Insights page) can check who's logged in via:
    if st.session_state.get("business_user"): ...
"""

import os
import re
import sqlite3

import bcrypt
import streamlit as st



DB_PATH = os.path.join("data", "processed", "businesses.db")
BUSINESS_TYPES = ["Food & Beverage", "Accommodation / Hotel", "Retail / Shop", "Tour Guide / Local Vendor", "Other"]
REGIONS = ["Galle", "Mirissa", "Ella", "Kandy", "Sigiriya", "Nuwara Eliya",
           "Arugam Bay", "Colombo", "Trincomalee", "Jaffna", "Other"]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            business_type TEXT NOT NULL,
            region TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def create_account(business_name, business_type, region, email, password):
    conn = get_connection()
    try:
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute(
            "INSERT INTO businesses (business_name, business_type, region, email, password_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (business_name, business_type, region, email.lower().strip(), password_hash),
        )
        conn.commit()
        return True, "Account created -- you can log in now."
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    finally:
        conn.close()


def verify_login(email, password):
    conn = get_connection()
    row = conn.execute(
        "SELECT business_name, business_type, region, password_hash FROM businesses WHERE email = ?",
        (email.lower().strip(),),
    ).fetchone()
    conn.close()

    if row is None:
        return None
    business_name, business_type, region, password_hash = row
    if bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8")):
        return {"business_name": business_name, "business_type": business_type, "region": region, "email": email.lower().strip()}
    return None


def find_registered_business(place_name, region):
    """Look for a registered CeylonPulse business whose signup name matches a
    Google Places result, within the same region. Used by Plan Your Trip to
    badge cards that belong to a business that has an account here -- this is
    a plain name/region match against the signup table, NOT a new field or a
    live geocoding match, since that's all the data we actually collect at
    signup.

    Matching is deliberately loose (case-insensitive substring, either
    direction) since a business might sign up as "Mirissa Beach Cafe" while
    Google lists it as "Mirissa Beach Cafe & Bar" or vice versa.
    """
    if not place_name or not os.path.exists(DB_PATH):
        return None

    conn = get_connection()
    rows = conn.execute(
        "SELECT business_name, business_type, email FROM businesses WHERE region = ?",
        (region,),
    ).fetchall()
    conn.close()

    place_norm = place_name.strip().lower()
    for business_name, business_type, email in rows:
        biz_norm = business_name.strip().lower()
        if biz_norm and (biz_norm in place_norm or place_norm in biz_norm):
            return {"business_name": business_name, "business_type": business_type, "email": email}
    return None


def render_signup_form():
    with st.form("signup_form"):
        business_name = st.text_input("Business name")
        business_type = st.selectbox("Business type", BUSINESS_TYPES)
        region = st.selectbox("Region", REGIONS)
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True)

        if submitted:
            if not business_name.strip():
                st.error("Please enter a business name.")
            elif not EMAIL_PATTERN.match(email.strip()):
                st.error("Please enter a valid email address.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != confirm_password:
                st.error("Passwords don't match.")
            else:
                success, message = create_account(business_name.strip(), business_type, region, email, password)
                if success:
                    st.success(message)
                else:
                    st.error(message)


def render_login_form():
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                user = verify_login(email, password)
                if user:
                    st.session_state["business_user"] = user
                    st.switch_page("pages/4_Expansion_Insights.py")
                else:
                    st.error("Incorrect email or password.")


def main():
    st.title("🏪 Business Login")

    if st.session_state.get("business_user"):
        st.switch_page("pages/4_Expansion_Insights.py")
        return

    st.caption(
        "For food, accommodation, retail, and other businesses that rely on "
        "tourism revenue. Log in or create an account to access tourist "
        "flow and destination insights for your sector."
    )

    tab_login, tab_signup = st.tabs(["Log in", "Create account"])
    with tab_login:
        render_login_form()
    with tab_signup:
        render_signup_form()


if __name__ == "__main__":
    main()
