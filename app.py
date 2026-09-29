"""
app.py

Entry point / router for the Sri Lanka Tourism BI Dashboard.
Uses st.navigation for a top navigation bar (instead of the default
sidebar) and to give every page a clean custom title -- this also removes
the old "app" label that used to show up in the sidebar automatically.

Admin is intentionally NOT part of the navigation list below, so it never
appears in the top bar or anywhere else a visitor can browse to. It's only
reachable by opening this app with ?admin=1 in the URL, and even then it's
gated by a password (see pages/9_Admin.py). This is a standard pattern for
keeping an internal panel out of public view without a separate login
system for it.
"""

import os
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from src.ui.theme import inject_theme

st.set_page_config(
    page_title="Ceylon Pulse | Sri Lanka Tourism BI Dashboard",
    page_icon="🌴",
    layout="wide",
)

st.logo("assets/images/logo.png", size="large")
inject_theme()

st.markdown("""
<style>

/* ==============================
   CeylonPulse Brand
   ============================== */

.ceylonpulse-name {
    position: fixed;
    top: 15px;
    left: 55px;
    font-size: 20px;
    font-weight: 700;
    white-space: nowrap;
    z-index: 999999;
}

.ceylon {
    color: #1f2937;
}

.pulse {
    color: #16856f;
}


/* ==============================
   Move Explore + For Businesses
   ============================== */

.stAppHeader .rc-overflow {
    margin-left: 130px !important;
    justify-content: flex-start !important;
}

</style>

<div class="ceylonpulse-name">
    <span class="ceylon">Ceylon</span><span class="pulse">Pulse</span>
</div>
""", unsafe_allow_html=True)

# ---- Hidden admin route ----
# Reached only via .../?admin=1 -- never linked from anywhere in the UI.
if st.query_params.get("admin") == "1":
    admin_page = st.Page("pages/9_Admin.py", title="Admin", default=True)
    nav = st.navigation([admin_page], position="hidden")
    nav.run()
    st.stop()

# ---- Normal visitor navigation ----
# icon uses Streamlit's built-in Material Symbols (":material/name:") --
# these render as clean line-icons, not emoji.
home = st.Page("pages/0_Home.py", title="Home", icon=":material/home:", default=True)
forecast = st.Page("pages/1_Forecast.py", title="Forecast", icon=":material/trending_up:")
plan_trip = st.Page("pages/2_Plan_Your_Trip.py", title="Plan Your Trip", icon=":material/explore:")
business_login = st.Page("pages/3_Business_Login.py", title="Business Portal", icon=":material/storefront:")
# Expansion Insights is reached automatically after logging in via the
# Business Portal (see pages/3_Business_Login.py) -- it's kept out of the
# top nav so there's a single "For Businesses" entry point instead of two,
# but the page itself still works fine if opened directly (it just prompts
# a login first).
expansion = st.Page("pages/4_Expansion_Insights.py", title="Expansion Insights", icon=":material/insights:")

nav = st.navigation(
    {
        "Explore": [home, forecast, plan_trip],
        "For Businesses": [business_login, expansion],
    },
    position="top",
)

# ---- Keep "Expansion Insights" out of the visible top bar ----
# It MUST be registered in st.navigation above (otherwise st.switch_page()
# to it fails silently -- that was the earlier bug), but we still only
# want ONE visible "For Businesses" entry point (Business Portal), with
# Expansion Insights reached automatically after login. Since st.navigation
# has no per-page "hidden but switchable" flag, this hides just that one
# link by matching its text, the same window.parent DOM-reach pattern
# already used for geolocation/map JS elsewhere in this app.
components.html(
    """
    <script>
    (function() {
        function hideExpansionLink() {
            const doc = window.parent.document;
            const nodes = doc.querySelectorAll('a, span, p, div');
            nodes.forEach(function(el) {
                if (el.children.length === 0 && el.textContent.trim() === 'Expansion Insights') {
                    const item = el.closest('li') || el.closest('a') || el;
                    item.style.display = 'none';
                }
            });
        }
        hideExpansionLink();
        new MutationObserver(hideExpansionLink).observe(window.parent.document.body, {childList: true, subtree: true});
    })();
    </script>
    """,
    height=0,
)

nav.run()
