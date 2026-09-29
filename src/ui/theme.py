"""
src/ui/theme.py

Shared visual theme for CeylonPulse. One place for the color palette,
typography, card/button styling, and small motion touches (hover lift,
fade-in), so every page shares the same look instead of each page
inventing its own ad hoc CSS -- which is part of why pages ended up
looking inconsistent and flat before this.

Usage: call inject_theme() once near the top of app.py (it applies to
every routed page since app.py runs first on every request). Individual
pages can still add their own small CSS blocks for page-specific
components on top of this.
"""

import streamlit as st

PRIMARY = "#1f6f5c"
PRIMARY_DARK = "#15503f"
ACCENT = "#c0622d"
GOLD = "#b9862f"
INK = "#1a1a1a"
MUTED = "#666666"
CARD_BORDER = "#e6e2d6"
SURFACE = "#faf9f5"


def inject_theme():
    st.markdown(
        f"""
        <style>
        /* ---------- Base surface + typography ---------- */
        .stApp {{ background: {SURFACE}; }}
        h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
        p, .stMarkdown, .stCaption {{ color: {INK}; }}

        /* ---------- Gradient page banner (reused across pages) ---------- */
        .cp-banner {{
            background: linear-gradient(120deg, {PRIMARY} 0%, #2d8a71 100%);
            border-radius: 16px; padding: 1.8rem 2.2rem; color: white;
            margin-bottom: 1.2rem; position: relative; overflow: hidden;
            box-shadow: 0 4px 18px rgba(31,111,92,0.22);
        }}
        .cp-banner::after {{
            content: ""; position: absolute; top: -40%; right: -10%;
            width: 260px; height: 260px; border-radius: 50%;
            background: rgba(255,255,255,0.07);
        }}
        .cp-banner h1 {{ color: white; margin: 0 0 0.35rem 0; font-size: 2rem; position: relative; }}
        .cp-banner p {{ color: #e6f2ec; margin: 0; max-width: 720px; font-size: 0.98rem; position: relative; }}
        .cp-banner-tag {{
            display: inline-block; background: rgba(255,255,255,0.18);
            padding: 0.25rem 0.8rem; border-radius: 20px; font-size: 0.74rem;
            font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
            margin-bottom: 0.7rem; position: relative;
        }}

        /* ---------- Generic elevated card ---------- */
        .cp-card {{
            background: #fff; border: 1px solid {CARD_BORDER}; border-radius: 14px;
            padding: 1.25rem 1.4rem; margin-bottom: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            transition: box-shadow 0.15s ease, transform 0.15s ease;
        }}
        .cp-card:hover {{ box-shadow: 0 6px 18px rgba(0,0,0,0.08); }}

        /* ---------- Streamlit metric cards ---------- */
        div[data-testid="stMetric"] {{
            background: #fff; border: 1px solid {CARD_BORDER}; border-radius: 14px;
            padding: 0.9rem 1.1rem 0.7rem 1.1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        div[data-testid="stMetricLabel"] {{ color: {MUTED}; }}

        /* ---------- Buttons ---------- */
        .stButton > button, .stFormSubmitButton > button {{
            border-radius: 8px; font-weight: 600; border: none;
            background: {PRIMARY}; color: white; transition: background 0.15s ease;
        }}
        .stButton > button:hover, .stFormSubmitButton > button:hover {{
            background: {PRIMARY_DARK}; color: white;
        }}

        /* ---------- Tabs ---------- */
        .stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
        .stTabs [aria-selected="true"] {{ color: {PRIMARY} !important; }}

        /* ---------- Recommendation / highlight card ---------- */
        .cp-highlight {{
            background: linear-gradient(120deg, #fff7ec 0%, #fdf1e2 100%);
            border: 1px solid #f0d9b5; border-radius: 14px;
            padding: 1.3rem 1.5rem; margin-bottom: 1rem;
        }}
        .cp-highlight-tag {{
            display: inline-block; background: {GOLD}; color: white;
            padding: 0.2rem 0.7rem; border-radius: 20px; font-size: 0.72rem;
            font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
            margin-bottom: 0.6rem;
        }}
        .cp-highlight h3 {{ margin: 0 0 0.3rem 0; }}

        /* ---------- Section fade-in ---------- */
        .cp-fade {{ animation: cpFadeIn 0.35s ease both; }}
        @keyframes cpFadeIn {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def banner_html(title, description, tag=None):
    """Return the HTML for a standard gradient page banner. Pass to
    st.markdown(..., unsafe_allow_html=True)."""
    tag_html = f'<span class="cp-banner-tag">{tag}</span>' if tag else ""
    return f"""
    <div class="cp-banner cp-fade">
        {tag_html}
        <h1>{title}</h1>
        <p>{description}</p>
    </div>
    """
