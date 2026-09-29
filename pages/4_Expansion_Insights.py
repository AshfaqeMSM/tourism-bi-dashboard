"""
pages/4_Expansion_Insights.py

Business-facing insights page: opens automatically right after a business
logs in (see pages/3_Business_Login.py). This is the core novelty of the
research -- an evidence-based, explainable regional expansion recommendation
for tourism SMEs, built from three real, obtainable regional signals rather
than assuming data that doesn't exist:

  1. Competitor density -- how many same-sector businesses already operate
     in a region (Google Places nearby search count).
  2. Tourist-engagement proxy -- how much review volume those same-sector
     businesses have accumulated in that region (sum of Google Places
     userRatingCount across the returned listings). Review count is not a
     perfect substitute for footfall or spend, but it is a genuine,
     obtainable, defensible signal that tourists are actually engaging with
     that business category in that region -- unlike raw competitor count
     alone, which says nothing about whether anyone is visiting those
     competitors in the first place.
  3. Review sentiment -- VADER sentiment analysis run on the actual text of
     Google Places reviews (English-language only; Google tags each
     review's language, and non-English reviews are skipped rather than
     scored unreliably by an English-tuned lexicon). This distinguishes
     "lots of engagement, and people like it" from "lots of engagement,
     but reviews are poor" -- a distinction competitor count and review
     volume alone cannot make.

Combining (1) and (2) into a single "demand per competitor" opportunity
score (total review volume / competitor count) is what turns this page
from a one-dimensional "fewest competitors" ranking into a genuine
opportunity analysis. Sentiment (3) is deliberately kept SEPARATE from
that score rather than blended into it -- shown as supporting evidence and
a caution flag instead, consistent with this project's design principle
of never collapsing distinct evidence into one opaque number.

IMPORTANT DATA HONESTY NOTE (see project discussion): we still do NOT have
GPS-tracked tourist itineraries, purchase records, or booking/stay data --
that would need survey or check-in data that hasn't been collected. All
three signals used here are genuinely obtainable today from Google Places;
national demand trend is genuinely obtainable today from SLTDA data.
Nothing below is inferred from data that doesn't exist -- that caveat is
shown on the page itself, not just in this comment.

Google Places API (New) nearby search caps results at 15 per call, so a
competitor count of "15" is shown as "15+", and its review-volume sum is
therefore a floor, not an exact total, for regions that hit the cap.
Review text (`reviews`) is a separate, opt-in field requested only by this
page via nearby_search(..., include_reviews=True) -- see
src/places/google_places.py for why Plan Your Trip does not request it.
"""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.places.google_places import nearby_search, count_competitors_accurate
from src.ui.theme import banner_html

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _SENTIMENT_ANALYZER = SentimentIntensityAnalyzer()
except ImportError:
    _SENTIMENT_ANALYZER = None

FORECAST_CSV = os.path.join("data", "processed", "arrivals_forecast.csv")
SEARCH_RADIUS_M = 5000  # 5km around each region's centre point

REGIONS = {
    "Galle": (6.0329, 80.2168),
    "Mirissa": (5.9483, 80.4589),
    "Ella": (6.8667, 81.0466),
    "Kandy": (7.2906, 80.6337),
    "Sigiriya": (7.9570, 80.7603),
    "Nuwara Eliya": (6.9497, 80.7891),
    "Arugam Bay": (6.8400, 81.8360),
    "Colombo": (6.9271, 79.8612),
    "Trincomalee": (8.5874, 81.2152),
    "Jaffna": (9.6615, 80.0255),
}

# Maps business signup categories to the Places-API category labels used
# by src/places/google_places.py's CATEGORY_TYPES. "Tour Guide / Local
# Vendor" and "Other" have no direct Places equivalent, so they fall back
# to "Shops" as the closest general-retail/vendor proxy -- flagged to the
# user in that case rather than silently guessing.
BUSINESS_TYPE_TO_CATEGORY = {
    "Food & Beverage": "Food",
    "Accommodation / Hotel": "Hotels",
    "Retail / Shop": "Shops",
    "Tour Guide / Local Vendor": "Shops",
    "Other": "Shops",
}


@st.cache_data
def load_national_trend():
    """Return a year-over-year comparison: forecasted next 12 months total
    vs. the actual same 12 months one year prior. Deliberately NOT a naive
    "last 6 months vs next 6 months" comparison -- see module docstring
    discussion elsewhere in this project for why that would mostly measure
    seasonality, not real demand trend.
    """
    if not os.path.exists(FORECAST_CSV):
        return None
    df = pd.read_csv(FORECAST_CSV, parse_dates=["date"])
    actual = df.dropna(subset=["actual_arrivals"]).sort_values("date")
    future = df[df["actual_arrivals"].isna()].sort_values("date")

    if actual.empty or future.empty:
        return None

    next_12 = future.head(12)
    if next_12.empty:
        return None

    prior_year_window = next_12["date"] - pd.DateOffset(years=1)
    prior_actual = actual[actual["date"].isin(prior_year_window)]

    if prior_actual.empty:
        prior_actual = actual.tail(len(next_12))

    forecast_total = next_12["forecast_arrivals"].sum()
    prior_total = prior_actual["actual_arrivals"].sum()
    pct_change = ((forecast_total - prior_total) / prior_total) * 100 if prior_total else 0

    return {
        "forecast_total": forecast_total,
        "prior_total": prior_total,
        "pct_change": pct_change,
        "window_label": f"{next_12['date'].min():%b %Y} \u2013 {next_12['date'].max():%b %Y}",
        "prior_label": f"{prior_actual['date'].min():%b %Y} \u2013 {prior_actual['date'].max():%b %Y}",
    }


def _region_sentiment(places):
    """Run sentiment analysis (VADER) on English-language review snippets
    for a list of places, and return (avg_compound_or_None, analyzed_count,
    skipped_non_english_count). VADER is a lexicon-based English sentiment
    scorer -- fast, no model download, no internet call at runtime -- but
    it isn't tuned for Sinhala/Tamil, so non-English reviews are skipped
    rather than scored unreliably. Google tags each review's language via
    the same {"text": ..., "languageCode": ...} structure used elsewhere
    in the API (e.g. displayName), so this uses Google's own language
    metadata rather than guessing."""
    if _SENTIMENT_ANALYZER is None:
        return None, 0, 0

    scores = []
    skipped = 0
    for place in places:
        for review in (place.get("reviews") or []):
            text_obj = review.get("text") or {}
            snippet = text_obj.get("text")
            lang = text_obj.get("languageCode", "")
            if not snippet:
                continue
            if not lang.startswith("en"):
                skipped += 1
                continue
            scores.append(_SENTIMENT_ANALYZER.polarity_scores(snippet)["compound"])

    if not scores:
        return None, 0, skipped
    return sum(scores) / len(scores), len(scores), skipped


def _sentiment_label(compound):
    if compound is None:
        return "n/a"
    if compound >= 0.3:
        return "Positive"
    if compound <= -0.05:
        return "Mixed/Negative"
    return "Neutral"


def _fmt_count(count, capped):
    """Format a competitor count for display. capped=True means this hit
    the accurate-count ceiling (60, via Text Search pagination) or, if
    that call failed and we fell back to the cheaper Nearby Search count,
    15 -- either way, a genuine "at least this many" rather than a made-up
    round number. We only ever show a number we actually counted, capped
    or not -- never an estimate we didn't measure."""
    if count is None:
        return "unavailable"
    return f"{int(count)}+" if capped else str(int(count))


@st.cache_data(ttl=3600, show_spinner=False)
def regional_opportunity_table(category):
    """Query Google Places for every region and compute the three regional
    signals this recommendation is built from: competitor count, total
    review volume (a tourist-engagement proxy), and average review
    sentiment (a tourist-satisfaction proxy, English-language reviews
    only -- see _region_sentiment). Reuses the same cached nearby_search()
    call Plan Your Trip uses for the count/volume signals, but requests
    review text specifically for this page (include_reviews=True), since
    that's an Enterprise-tier field Plan Your Trip doesn't need.

    Returns (DataFrame, first_error_message_or_None). The error message is
    Google's actual response detail (e.g. "403: API_KEY_INVALID" or a
    billing/quota message) -- surfaced to the UI rather than discarded, so
    a total failure is diagnosable instead of just "couldn't reach it"."""
    rows = []
    first_error = None
    for region_name, (lat, lon) in REGIONS.items():
        raw = nearby_search(lat, lon, SEARCH_RADIUS_M, category, include_reviews=True)
        if isinstance(raw, dict) and "error" in raw:
            if first_error is None:
                first_error = raw["error"]
            rows.append({
                "Region": region_name, "_count": None, "_reviews": None, "_avg_rating": None,
                "_sentiment": None, "_sentiment_n": 0, "_sentiment_skipped": 0, "_count_capped": None,
            })
            continue

        places = raw or []
        # Accurate count via paginated Text Search (up to 60, see
        # count_competitors_accurate) -- falls back to the Nearby Search
        # count (capped at 15) if the accurate count call itself fails,
        # so one failed call doesn't blank out an otherwise-good region.
        accurate_count = count_competitors_accurate(lat, lon, SEARCH_RADIUS_M, category)
        if isinstance(accurate_count, dict) and "error" in accurate_count:
            count = len(places)
            count_capped = count >= 15
        else:
            count = accurate_count
            count_capped = count >= 60

        review_counts = [p.get("userRatingCount") or 0 for p in places]
        total_reviews = sum(review_counts)
        ratings = [p.get("rating") for p in places if p.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else None
        sentiment, sentiment_n, sentiment_skipped = _region_sentiment(places)

        rows.append({
            "Region": region_name,
            "_count": count,
            "_count_capped": count_capped,
            "_reviews": total_reviews,
            "_avg_rating": avg_rating,
            "_sentiment": sentiment,
            "_sentiment_n": sentiment_n,
            "_sentiment_skipped": sentiment_skipped,
        })
    df = pd.DataFrame(rows)

    # Opportunity score = review volume ("tourist engagement") per
    # competitor. A region with 0 competitors but nonzero reviews from the
    # wider search area is treated as maximally attractive (no direct
    # same-sector competition at all); a region with 0 competitors AND 0
    # reviews has no evidence of tourist engagement in this category and is
    # scored 0, not infinity -- absence of competitors isn't opportunity if
    # nobody is visiting the category there either. Sentiment is deliberately
    # NOT blended into this score (see design note in Section 5.5.5 / the
    # module docstring) -- it's shown as separate supporting evidence and a
    # caution flag, not folded into one opaque number.
    def score(row):
        if pd.isna(row["_count"]):
            return None
        if row["_count"] == 0:
            return float(row["_reviews"]) if row["_reviews"] else 0.0
        return row["_reviews"] / row["_count"]

    df["_score"] = df.apply(score, axis=1)
    return df, first_error


def render_recommendation(df, trend, business_type, api_error=None):
    """The actual advice: lead with the region with the strongest
    opportunity score (tourist engagement per competitor), framed against
    the national demand trend."""
    available = df[df["_score"].notna()].sort_values("_score", ascending=False).reset_index(drop=True)
    if available.empty:
        if api_error:
            st.error(f"Couldn't reach Google Places for any region. Google's response: {api_error}")
            st.caption(
                "Common causes: the API key in .streamlit/secrets.toml is missing/invalid, "
                "the 'Places API (New)' isn't enabled for your Google Cloud project, billing "
                "isn't enabled on that project (required even within the free tier), or the "
                "key has restrictions blocking this request."
            )
        else:
            st.warning("Couldn't reach Google Places for any region right now -- try again shortly.")
        return

    top = available.iloc[0]
    runners_up = available.iloc[1:3]

    if trend is not None:
        if trend["pct_change"] >= 0:
            trend_line = (
                f"National tourist demand is trending <b>up {trend['pct_change']:+.1f}%</b> "
                f"year-over-year, which supports considering new locations now."
            )
        else:
            trend_line = (
                f"National tourist demand is currently trending <b>down "
                f"{trend['pct_change']:.1f}%</b> year-over-year -- worth watching "
                f"before committing to a new location."
            )
    else:
        trend_line = "National demand trend data isn't available right now."

    runner_ups_text = ", ".join(
        f"{row['Region']} (score {row['_score']:.0f})" for _, row in runners_up.iterrows()
    )

    sentiment_label = _sentiment_label(top["_sentiment"])
    if top["_sentiment"] is None:
        sentiment_line = "No English-language review text was available to assess sentiment for this region."
    elif sentiment_label == "Mixed/Negative":
        sentiment_line = (
            f"<b style='color:#b3541e;'>Caution:</b> review sentiment for this category in "
            f"{top['Region']} is currently <b>{sentiment_label.lower()}</b> "
            f"(based on {int(top['_sentiment_n'])} English-language reviews) -- high engagement "
            f"doesn't necessarily mean satisfied customers. Worth reading a sample of reviews "
            f"yourself before deciding."
        )
    else:
        sentiment_line = (
            f"Review sentiment for this category in {top['Region']} is currently "
            f"<b>{sentiment_label.lower()}</b> (based on {int(top['_sentiment_n'])} "
            f"English-language reviews), which supports this as a genuine opportunity "
            f"rather than just high traffic."
        )

    st.markdown(
        f"""
        <div class="cp-highlight cp-fade">
            <span class="cp-highlight-tag">Ranked #1 overall</span>
            <h3>{top['Region']} currently ranks highest</h3>
            <p style="margin:0 0 0.6rem 0;">
                {top['Region']} currently has the <b>strongest opportunity score</b> for
                {business_type.lower()} of the 10 regions checked: roughly
                <b>{top['_score']:.0f} reviews of tourist engagement per competitor</b>
                ({int(top['_reviews']):,} total reviews across {_fmt_count(top['_count'], top['_count_capped'])}
                same-sector listings within 5km) -- meaning tourists are actively engaging
                with this category there, relative to how many businesses are already
                serving them.
            </p>
            <p style="margin:0 0 0.6rem 0; font-size:0.9rem; color:#555;">{sentiment_line}</p>
            <p style="margin:0 0 0.6rem 0; font-size:0.9rem; color:#555;">{trend_line}</p>
            <p style="margin:0; font-size:0.88rem; color:#666;">
                Other strong candidates: {runner_ups_text if runner_ups_text else "n/a"}.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Opportunity score = total review volume for this category in the region, "
        "divided by the number of competitors -- a proxy for tourist engagement per "
        "existing business, not a guarantee of demand. Sentiment is shown separately "
        "as supporting evidence, not blended into the score, and covers only "
        "English-language reviews (Google reports each review's language; "
        "Sinhala/Tamil reviews are not scored). Built only from live, obtainable "
        "regional signals; SLTDA arrivals data isn't broken down by region, so pair "
        "this with local knowledge, not as a final answer."
    )


def render_opportunity_chart(df, business_type):
    """A ranked horizontal bar chart -- one bar per region, sorted by
    opportunity score, colored by sentiment. Replaces an earlier scatter
    ("quadrant") chart that plotted competitor count against review volume
    with a text label per point: with 10 regions the labels overlapped and
    the axes required explanation before the chart meant anything. A
    sorted bar chart needs no explanation -- longer bar, better score,
    color tells you the sentiment context -- and is the same underlying
    data, just presented so it can be read at a glance."""
    plot_df = df[df["_score"].notna()].copy().sort_values("_score", ascending=True)
    if plot_df.empty:
        return

    def color_for(s):
        if pd.isna(s):
            return "#9aa08c"
        if s >= 0.3:
            return "#1f6f5c"
        if s <= -0.05:
            return "#c0622d"
        return "#b9862f"

    colors = plot_df["_sentiment"].apply(color_for)
    sentiment_labels = plot_df["_sentiment"].apply(lambda s: _sentiment_label(s))

    fig = go.Figure(go.Bar(
        x=plot_df["_score"], y=plot_df["Region"], orientation="h",
        marker=dict(color=colors),
        text=plot_df["_score"].apply(lambda s: f"{s:.0f}"),
        textposition="outside",
        customdata=sentiment_labels,
        hovertemplate="<b>%{y}</b><br>Opportunity score: %{x:.0f}<br>Sentiment: %{customdata}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Opportunity score by region -- {business_type}",
        xaxis_title="Opportunity score (review volume per competitor -- higher is better)",
        yaxis_title=None,
        height=max(320, 34 * len(plot_df)), margin=dict(t=50, b=40, l=10, r=40),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "🟢 Positive sentiment &nbsp; 🟡 Neutral &nbsp; 🟠 Mixed/Negative &nbsp; "
        "⚪ No English-language reviews scored. Bar length = opportunity score "
        "(review volume ÷ competitor count)."
    )


def render_region_check(df, region_name, business_type):
    """Let the business owner check a SPECIFIC region they're already
    considering -- not just the algorithm's single top pick. Shows that
    region's own numbers and where it ranks among all 10, so a business
    owner isn't limited to whichever region the ranking favours (which,
    for a general commercial hub like Colombo, can be inflated by
    non-tourism review volume -- see the caveat in main())."""
    row = df[df["Region"] == region_name]
    if row.empty or pd.isna(row.iloc[0]["_score"]):
        st.warning(f"No data available for {region_name} right now.")
        return
    row = row.iloc[0]

    ranked = df[df["_score"].notna()].sort_values("_score", ascending=False).reset_index(drop=True)
    rank = ranked[ranked["Region"] == region_name].index[0] + 1
    total = len(ranked)

    sentiment_label = _sentiment_label(row["_sentiment"])
    count_label = _fmt_count(row["_count"], row["_count_capped"])

    st.markdown(f"#### {region_name} -- rank {rank} of {total} for {business_type}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Opportunity score", f"{row['_score']:.0f}")
    c2.metric("Competitors (5km)", count_label)
    c3.metric("Total reviews", f"{int(row['_reviews']):,}")
    c4.metric("Sentiment", sentiment_label)

    if rank == 1:
        st.success(f"{region_name} is currently the strongest-scoring region of the 10 checked for this sector.")
    elif rank <= 3:
        st.info(f"{region_name} is a solid candidate -- close to the top of the ranking, not just an also-ran.")
    else:
        st.warning(
            f"{region_name} ranks {rank} of {total} for this sector right now -- lower engagement "
            f"relative to competitors than the top candidates. Not disqualifying, but worth weighing "
            f"against why you're specifically considering this region (existing customer base, "
            f"lower rent, personal familiarity, etc. aren't captured by this score)."
        )


def main():
    if not st.session_state.get("business_user"):
        st.warning("This page is for logged-in businesses. Please log in first.")
        st.page_link("pages/3_Business_Login.py", label="Go to Business Login \u2192")
        return

    user = st.session_state["business_user"]

    st.markdown(
        banner_html(
            "Expansion Insights",
            f"Showing insights for <b>{user['business_name']}</b> "
            f"({user['business_type']}, currently based in {user['region']}) "
            f"-- where to expand next, based on national demand trend, live "
            f"competitor density, tourist-engagement volume, and review "
            f"sentiment per region.",
            tag="For businesses",
        ),
        unsafe_allow_html=True,
    )

    with st.expander("Why not real tourist movement data?"):
        st.write(
            "We don't have GPS-tracked tourist itineraries, purchase records, or "
            "booking/stay data -- that would need survey or check-in data we "
            "haven't collected. What's shown below combines four things we DO "
            "have: national tourist demand trend (SLTDA), live competitor counts "
            "per region (Google Places), live review-volume per region (Google "
            "Places) as a proxy for how much tourists engage with that business "
            "category there, and review-text sentiment for the same category "
            "(English-language reviews only -- Google reports each review's "
            "language, and non-English reviews are skipped rather than scored "
            "unreliably). Sentiment is shown as supporting evidence and a "
            "caution flag, not blended into the opportunity score, so a region "
            "with high traffic but poor reviews doesn't get silently ranked as "
            "if it were a strong opportunity."
        )

    api_key = st.secrets.get("GOOGLE_PLACES_API_KEY") if hasattr(st, "secrets") else None
    category = BUSINESS_TYPE_TO_CATEGORY.get(user["business_type"], "Shops")
    trend = load_national_trend()

    if not api_key:
        st.warning("Add GOOGLE_PLACES_API_KEY to .streamlit/secrets.toml to generate a recommendation.")
        return

    # Runs automatically on page load -- a business owner should see actual
    # data the moment they land here, not a button asking them to fetch it
    # themselves. Cached for an hour, so this is fast on repeat visits.
    with st.spinner("Analyzing competitor density and tourist engagement across all 10 regions..."):
        opp_df, api_error = regional_opportunity_table(category)

    if st.button("\U0001F504 Recalculate"):
        regional_opportunity_table.clear()
        st.rerun()

    st.divider()

    # ---- Region exploration comes FIRST: the business owner picks a
    # region they're already considering and sees its own opportunity/
    # threat profile, rather than being handed one algorithm-picked answer
    # before they've had a chance to look at anything themselves. The
    # ranked "top region overall" callout (below) is supporting context,
    # not the first or only thing shown -- this also directly addresses
    # Colombo tending to dominate a single top-pick-first layout (see the
    # caveat attached to that section).
    st.markdown('<div class="cp-card cp-fade">', unsafe_allow_html=True)
    st.subheader("Check a region")
    st.caption("Pick any region to see its own opportunity and competitive picture for your business type.")
    region_choice = st.selectbox("Region", list(REGIONS.keys()), key="region_check_choice")
    render_region_check(opp_df, region_choice, user["business_type"])
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="cp-card cp-fade">', unsafe_allow_html=True)
    st.subheader("Top-ranked region overall")
    st.caption("Once you've had a look around, here's how all 10 regions rank against each other for your business type.")
    render_recommendation(opp_df, trend, user["business_type"], api_error=api_error)
    st.caption(
        "⚠️ Note on Colombo specifically: as Sri Lanka's largest general commercial "
        "hub, Colombo's review volume reflects overall city activity (locals, "
        "business travel), not tourism alone -- unlike smaller destinations where "
        "review activity is almost entirely tourism-driven. Its opportunity score "
        "can look strong for that reason even when it isn't specifically a strong "
        "*tourism* opportunity. Use the region check above to compare it directly "
        "against a destination-specific region."
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="cp-card cp-fade">', unsafe_allow_html=True)
    st.subheader("National tourist demand trend")
    if trend is None:
        st.warning("Forecast data not found. Run `src/forecasting/forecast_arrivals.py` first.")
    else:
        t1, t2, t3 = st.columns(3)
        t1.metric(f"Forecast total ({trend['window_label']})", f"{trend['forecast_total']:,.0f}")
        t2.metric(f"Same months last year ({trend['prior_label']})", f"{trend['prior_total']:,.0f}")
        t3.metric("Year-over-year change", f"{trend['pct_change']:+.1f}%")
        st.caption(
            "Compared year-over-year (same calendar months) to cancel out "
            "seasonality. National-level only; SLTDA data isn't broken "
            "down by region."
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="cp-card cp-fade">', unsafe_allow_html=True)
    st.subheader(f"Opportunity ranking ({user['business_type']})")
    if user["business_type"] in ("Tour Guide / Local Vendor", "Other"):
        st.caption(
            f"No exact Google Places category matches '{user['business_type']}' -- "
            "showing general retail/shop listings as the closest proxy."
        )
    render_opportunity_chart(opp_df, user["business_type"])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="cp-card cp-fade">', unsafe_allow_html=True)
    st.subheader("Full regional breakdown")
    display_df = opp_df.copy()
    display_df["Competitors (5km)"] = display_df.apply(
        lambda r: _fmt_count(r["_count"], r["_count_capped"]), axis=1
    )
    display_df["Total reviews"] = display_df["_reviews"].apply(
        lambda r: "unavailable" if pd.isna(r) else f"{int(r):,}"
    )
    display_df["Avg. rating"] = display_df["_avg_rating"].apply(
        lambda r: "n/a" if pd.isna(r) else f"{r:.1f}"
    )
    display_df["Opportunity score"] = display_df["_score"].apply(
        lambda s: "unavailable" if pd.isna(s) else f"{s:.0f}"
    )
    display_df["Review sentiment"] = display_df.apply(
        lambda r: f"{_sentiment_label(r['_sentiment'])} (n={int(r['_sentiment_n'])}, skipped={int(r['_sentiment_skipped'])})"
        if pd.notna(r["_sentiment"]) else "n/a",
        axis=1,
    )
    ranked = display_df[display_df["_score"].notna()].sort_values("_score", ascending=False)
    st.dataframe(
        ranked[["Region", "Opportunity score", "Review sentiment", "Competitors (5km)", "Total reviews", "Avg. rating"]].reset_index(drop=True),
        use_container_width=True,
    )
    st.caption(
        "\"skipped\" = non-English-language reviews found but not scored (VADER is English-only). "
        "If this varies meaningfully by region, sentiment is genuinely being computed per-region "
        "rather than something being stuck/cached."
    )
    if _SENTIMENT_ANALYZER is None:
        st.caption(
            "Sentiment analysis is unavailable: the `vaderSentiment` package isn't "
            "installed. Run `pip install -r requirements.txt` and restart to enable it."
        )
    unavailable = display_df[display_df["_score"].isna()]
    if not unavailable.empty:
        st.caption(f"Couldn't reach Google Places for: {', '.join(unavailable['Region'])}.")
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
