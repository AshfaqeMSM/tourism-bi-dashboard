"""
pages/0_Home.py

Home / landing content for the Sri Lanka Tourism BI Dashboard.
Routed to by app.py via st.navigation -- this file does NOT call
st.set_page_config() itself, since app.py already does that once for the
whole app.
"""

import base64
import io
import os
import sys

import pandas as pd
import streamlit as st
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.news.fetch_news import fetch_headlines, filter_travel_relevant

FORECAST_CSV = os.path.join("data", "processed", "arrivals_forecast.csv")
WORLDBANK_CSV = os.path.join("data", "processed", "worldbank_sri_lanka.csv")


@st.cache_data(show_spinner=False)
def img_to_base64(path, max_width=1200, quality=72):
    """Resize + JPEG-compress an image before base64-encoding it for inline
    HTML. The source photos are camera-resolution (one is 5669x7559, 8.7MB)
    and were previously encoded at FULL size, TWICE (once for the hero,
    once for the destination grid) -- roughly 30-40MB of base64 text
    shipped to the browser on every single home page load, which was the
    real cause of the slow load time. Downscaling to a sane display width
    and re-compressing brings each image down to tens of KB instead, and
    st.cache_data means the resize only happens once per server process,
    not on every rerun.
    """
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            if im.width > max_width:
                new_height = int(im.height * (max_width / im.width))
                im = im.resize((max_width, new_height), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
    except (FileNotFoundError, OSError):
        return None


def render_news_ticker():
    headlines = fetch_headlines(limit=15)
    headlines = filter_travel_relevant(headlines)

    if isinstance(headlines, dict) and "error" in headlines:
        st.caption("Live news unavailable right now -- refresh to try again.")
        return
    if not headlines:
        return

    ticker_items = " &nbsp;\u2022&nbsp; ".join(h["title"] for h in headlines)
    st.markdown(
        f"""
        <style>
        .news-ticker-wrap {{
            width: 100%; overflow: hidden; background: #eef4ee;
            border-radius: 8px; padding: 0.5rem 0; margin-bottom: 1rem;
            border: 1px solid #d9e6d9;
        }}
        .news-ticker-track {{
            display: inline-block; white-space: nowrap;
            animation: tickerScroll 150s linear infinite;
            padding-left: 100%;
        }}
        .news-ticker-track span {{ color: #333; font-size: 0.9rem; }}
        @keyframes tickerScroll {{
            0% {{ transform: translateX(0); }}
            100% {{ transform: translateX(-100%); }}
        }}
        </style>
        <div class="news-ticker-wrap">
            <div class="news-ticker-track">
                <span>{ticker_items} &nbsp;\u2022&nbsp; {ticker_items}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Live headlines relevant to tourism and tourism-dependent businesses, refreshed every 15 minutes.")


@st.cache_data
def load_summary_stats():
    stats = {}
    if os.path.exists(FORECAST_CSV):
        df = pd.read_csv(FORECAST_CSV, parse_dates=["date"])
        actual = df.dropna(subset=["actual_arrivals"])
        if not actual.empty:
            latest = actual.iloc[-1]
            stats["latest_month"] = latest["date"].strftime("%B %Y")
            stats["latest_arrivals"] = int(latest["actual_arrivals"])
            ytd = actual[actual["date"].dt.year == latest["date"].year]
            stats["ytd_total"] = int(ytd["actual_arrivals"].sum())
            stats["ytd_year"] = int(latest["date"].year)
            stats["years_covered"] = f"{actual['date'].dt.year.min()}\u2013{actual['date'].dt.year.max()}"
    if os.path.exists(WORLDBANK_CSV):
        wb = pd.read_csv(WORLDBANK_CSV)
        if wb["gdp_growth_pct"].notna().any():
            wb_latest = wb.dropna(subset=["gdp_growth_pct"]).iloc[-1]
            stats["gdp_growth"] = round(wb_latest["gdp_growth_pct"], 1)
            stats["gdp_year"] = int(wb_latest["year"])
    return stats


def main():
    hero_images = ["sigiriya.jpg", "galle_fort.jpg", "tea_hills.jpg", "mirissa_beach.jpg"]
    encoded = [b64 for f in hero_images if (b64 := img_to_base64(os.path.join("assets", "images", f), max_width=1400, quality=72))]

    if encoded:
        n = len(encoded)
        duration = n * 6
        slides_css, keyframes = "", ""
        for i, b64 in enumerate(encoded):
            slides_css += f""".hero-slide:nth-child({i + 1}) {{
                background-image: url(data:image/jpeg;base64,{b64});
                animation: heroFade{i} {duration}s infinite;
            }}"""
            start, fade_in = (i / n) * 100, ((i + 0.15) / n) * 100
            fade_out, end = ((i + 0.85) / n) * 100, ((i + 1) / n) * 100
            keyframes += f"""@keyframes heroFade{i} {{
                0% {{ opacity: 0; }} {start:.1f}% {{ opacity: 0; }}
                {fade_in:.1f}% {{ opacity: 1; }} {fade_out:.1f}% {{ opacity: 1; }}
                {end:.1f}% {{ opacity: 0; }} 100% {{ opacity: 0; }}
            }}"""

        st.markdown(
            f"""
            <style>
            .hero-container {{ position: relative; width: 100%; height: 420px;
                border-radius: 14px; overflow: hidden; margin-bottom: 1.5rem; }}
            .hero-slide {{ position: absolute; top:0; left:0; width:100%; height:100%;
                background-size: cover; background-position: center; opacity: 0; }}
            .hero-overlay {{ position: absolute; top:0; left:0; width:100%; height:100%;
                background: linear-gradient(90deg, rgba(20,50,35,0.65) 0%, rgba(20,50,35,0.3) 55%, rgba(20,50,35,0.05) 100%);
                display: flex; flex-direction: column; justify-content: center; padding: 2.5rem 3rem; }}
            .hero-overlay h1 {{ color: white; font-size: 2.4rem; margin-bottom: 0.4rem; }}
            .hero-overlay h5 {{ color: #eee; font-weight: 400; margin-bottom: 0.8rem; }}
            .hero-overlay p {{ color: #ddd; max-width: 600px; }}
            {slides_css}
            {keyframes}
            </style>
            <div class="hero-container">
                {''.join('<div class="hero-slide"></div>' for _ in encoded)}
                <div class="hero-overlay">
                    <h1>Sri Lanka Tourism BI Dashboard</h1>
                    <h5>Open-source demand forecasting and destination insight for Sri Lankan tourism SMEs</h5>
                    <p>Built on official SLTDA monthly arrival reports and World Bank economic
                    indicators, with tools for both travelers planning a visit and local
                    businesses that depend on tourism revenue.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.title("Sri Lanka Tourism BI Dashboard")
        st.markdown("##### Open-source demand forecasting and destination insight for Sri Lankan tourism SMEs")
        st.info("Add photos to `assets/images/` (sigiriya.jpg, galle_fort.jpg, tea_hills.jpg, mirissa_beach.jpg) for the full hero banner.")

    btn_col1, btn_col2, _ = st.columns([1, 1, 3])
    with btn_col1:
        st.page_link("pages/1_Forecast.py", label="View Arrivals Forecast", icon=":material/trending_up:", use_container_width=True)
    with btn_col2:
        st.page_link("pages/2_Plan_Your_Trip.py", label="Plan Your Trip", icon=":material/explore:", use_container_width=True)

    st.divider()

    # ---- Booking.com-style "sign in" banner, adapted for our audience:
    # tourism-dependent businesses, not travelers with points to redeem ----
    st.markdown(
        """
        <style>
        .signin-banner {
            display: flex; align-items: center; justify-content: space-between;
            background: #eef4ee; border: 1px solid #d9e6d9; border-radius: 12px;
            padding: 1.3rem 1.6rem; margin-bottom: 0.5rem;
        }
        .signin-banner h4 { margin: 0 0 0.2rem 0; color: #1a1a1a; }
        .signin-banner p { margin: 0; color: #555; font-size: 0.92rem; }
        </style>
        <div class="signin-banner">
            <div>
                <h4>Own a tourism-dependent business?</h4>
                <p>Sign in for national demand trends and live competitor density in your sector \u2014 free, one click from here.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link("pages/3_Business_Login.py", label="Sign in / Create a business account", icon=":material/storefront:")

    st.divider()
    render_news_ticker()

    stats = load_summary_stats()
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        if "latest_arrivals" in stats:
            col1.metric(f"Latest month ({stats['latest_month']})", f"{stats['latest_arrivals']:,}")
        if "ytd_total" in stats:
            col2.metric(f"{stats['ytd_year']} YTD arrivals", f"{stats['ytd_total']:,}")
        if "years_covered" in stats:
            col3.metric("Data coverage", stats["years_covered"])
        if "gdp_growth" in stats:
            col4.metric(f"GDP growth ({stats['gdp_year']})", f"{stats['gdp_growth']}%")

    st.divider()

    st.markdown(
        """
        <style>
        .dest-card {
            border-radius: 12px; overflow: hidden; margin-bottom: 0.9rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            transition: box-shadow 0.15s ease, transform 0.15s ease;
        }
        .dest-card:hover { box-shadow: 0 6px 16px rgba(0,0,0,0.14); transform: translateY(-2px); }
        .dest-card img { width: 100%; height: 190px; object-fit: cover; display: block; }
        .dest-card-body { padding: 0.7rem 0.85rem 0.9rem 0.85rem; background: #fff; }
        .dest-card-name { font-weight: 700; font-size: 1.02rem; color: #1a1a1a; margin-bottom: 0.15rem; }
        .dest-card-desc { font-size: 0.83rem; color: #666; line-height: 1.35; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("Explore Sri Lanka")
    st.caption("These popular destinations have a lot to offer")
    destinations = [
        ("sigiriya.jpg", "Sigiriya", "Ancient rock fortress and UNESCO World Heritage Site."),
        ("galle_fort.jpg", "Galle Fort", "17th-century Dutch colonial fort by the sea."),
        ("tea_hills.jpg", "Ella & the Hill Country", "Rolling tea plantations and mountain rail journeys."),
        ("mirissa_beach.jpg", "Mirissa Beach", "Whale watching and golden-sand southern coast."),
    ]
    cols = st.columns(4)
    for col, (filename, name, desc) in zip(cols, destinations):
        with col:
            b64 = img_to_base64(os.path.join("assets", "images", filename), max_width=480, quality=75)
            img_html = f'<img src="data:image/jpeg;base64,{b64}" />' if b64 else (
                f'<div style="height:190px; background:#eef4ee; display:flex; '
                f'align-items:center; justify-content:center; color:#9aa08c; '
                f'font-size:0.85rem;">{filename}</div>'
            )
            st.markdown(
                f"""
                <div class="dest-card">
                    {img_html}
                    <div class="dest-card-body">
                        <div class="dest-card-name">{name}</div>
                        <div class="dest-card-desc">{desc}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.page_link("pages/2_Plan_Your_Trip.py", label="Plan a trip to any of these", icon=":material/arrow_forward:")

    st.divider()

    st.markdown(
        """
        <style>
        .feature-card {
            background: #fff; border: 1px solid #e6e2d6; border-radius: 12px;
            padding: 1.3rem 1.4rem; height: 100%;
        }
        .feature-card h4 { margin: 0 0 0.6rem 0; color: #1a1a1a; }
        .feature-card ul { margin: 0; padding-left: 1.1rem; color: #444; font-size: 0.92rem; }
        .feature-card li { margin-bottom: 0.4rem; }
        .feature-flagship {
            background: linear-gradient(120deg, #1f6f5c 0%, #2d8a71 100%); color: white;
            border: none;
        }
        .feature-flagship h4, .feature-flagship p { color: white; }
        .feature-tag {
            display: inline-block; background: rgba(255,255,255,0.18);
            padding: 0.2rem 0.7rem; border-radius: 20px; font-size: 0.72rem;
            font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
            margin-bottom: 0.6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("What's in this dashboard")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            """
            <div class="feature-card">
                <h4>For tourists</h4>
                <ul>
                    <li><b>Arrivals Forecast</b> -- seasonal trends and a 12-month forward forecast, with known shock periods flagged</li>
                    <li><b>Plan Your Trip</b> -- climate-based timing and live nearby recommendations, from your current location or any region</li>
                    <li><b>Live news</b> -- tourism/business-relevant headlines</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("pages/1_Forecast.py", label="Go to Forecast", icon=":material/arrow_forward:")
        st.page_link("pages/2_Plan_Your_Trip.py", label="Go to Plan Your Trip", icon=":material/arrow_forward:")
    with col_b:
        st.markdown(
            """
            <div class="feature-card feature-flagship">
                <span class="feature-tag">Signature feature</span>
                <h4>Expansion Insights</h4>
                <p style="font-size:0.92rem; margin:0;">
                National tourist demand trend + live competitor density per
                region, so tourism-dependent businesses can make an
                informed call on where a new branch might make sense --
                not a guess, a starting point grounded in real data.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("pages/3_Business_Login.py", label="Sign in to see it", icon=":material/arrow_forward:")
    with col_c:
        st.markdown(
            """
            <div class="feature-card">
                <h4>For tourism-dependent businesses</h4>
                <ul>
                    <li><b>Business Portal</b> -- one sign-in for food, accommodation, retail, and vendor accounts</li>
                    <li><b>Expansion Insights</b> -- opens automatically right after you log in, no extra clicks</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("pages/3_Business_Login.py", label="Go to Business Portal", icon=":material/arrow_forward:")

    st.divider()
    st.caption(
        "Data sources: Sri Lanka Tourism Development Authority (SLTDA) monthly "
        "arrival reports, 2019\u20132026; World Bank Open Data; Google Places."
    )


main()
