"""
src/news/fetch_news.py

Fetches current Sri Lanka headlines relevant to tourism/tourism-dependent
businesses. Combines two free, no-key-required sources:
  1. Ada Derana Business (bizenglish.adaderana.lk) -- a dedicated business/
     economy feed, which naturally skews toward hospitality, forex, and SME
     -relevant stories rather than general news.
  2. Ada Derana main feed (adaderana.lk) -- general headlines, kept as a
     broader pool and filtered by tourism/travel keywords.

Business-feed items are prioritized since that source is inherently more
relevant to this dashboard's audience; general-feed items only fill in if
the business feed doesn't return enough on its own.
"""

import xml.etree.ElementTree as ET

import requests
import streamlit as st

MAIN_RSS_URL = "https://www.adaderana.lk/rss.php"
BUSINESS_RSS_URL = "https://bizenglish.adaderana.lk/feed/"

# Tier 1: directly about tourism / tourism-dependent business -- tried first
TOURISM_BUSINESS_KEYWORDS = [
    "tourist", "tourism", "tourists", "visitor", "arrivals",
    "hotel", "resort", "guesthouse", "restaurant", "beach",
    "airline", "airport", "sltda", "forex", "revenue", "hospitality",
]

# Tier 2: broader travel/safety/economic context -- used if Tier 1 is thin
TRAVEL_RELEVANT_KEYWORDS = TOURISM_BUSINESS_KEYWORDS + [
    "flight", "visa", "border", "immigration", "cuisine",
    "weather", "advisory", "warning", "storm", "flood", "cyclone", "rain", "monsoon",
    "strike", "protest", "curfew", "closure", "closed", "shutdown", "fuel",
    "health", "outbreak", "alert", "security", "economy", "inflation",
]


def _fetch_rss(url, limit, headers):
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        category = item.findtext("category", "other").strip()
        if title:
            items.append({"title": title, "link": link, "category": category})
    return items


@st.cache_data(ttl=900, show_spinner=False)  # refresh every 15 minutes
def fetch_headlines(limit=15):
    """Return a list of {title, link, category} dicts, business feed first,
    or {"error": "..."} only if BOTH sources fail."""
    headers = {"User-Agent": "tourism-bi-dashboard/1.0 (student research project)"}

    business_items, main_items = [], []
    business_error, main_error = None, None

    try:
        business_items = _fetch_rss(BUSINESS_RSS_URL, limit, headers)
    except (requests.exceptions.RequestException, ET.ParseError) as e:
        business_error = str(e)

    try:
        main_items = _fetch_rss(MAIN_RSS_URL, limit, headers)
    except (requests.exceptions.RequestException, ET.ParseError) as e:
        main_error = str(e)

    combined = business_items + main_items
    if not combined:
        return {"error": business_error or main_error or "Both news sources unavailable."}

    # de-duplicate by title in case both feeds cover the same story
    seen = set()
    unique = []
    for item in combined:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
    return unique[:limit]


def filter_travel_relevant(headlines, min_results=5):
    """Prefer tourism/business headlines (Tier 1); widen to general travel
    context (Tier 2) if too few; fall back to all headlines if still short,
    so the ticker is never near-empty."""
    if isinstance(headlines, dict):
        return headlines  # pass through errors unchanged

    tier1 = [h for h in headlines if any(kw in h["title"].lower() for kw in TOURISM_BUSINESS_KEYWORDS)]
    if len(tier1) >= min_results:
        return tier1

    tier2 = [h for h in headlines if any(kw in h["title"].lower() for kw in TRAVEL_RELEVANT_KEYWORDS)]
    return tier2 if len(tier2) >= min_results else headlines
