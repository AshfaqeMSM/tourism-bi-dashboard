"""
src/geo/osm_places.py

Shared OpenStreetMap Overpass API helper. Used by both
pages/2_Plan_Your_Trip.py (recommendations for tourists) and
pages/4_Expansion_Insights.py (competitor density for businesses) so the
mirror list, retry logic, and query shape live in exactly one place.
"""

import streamlit as st
import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Well-known tourist regions with approximate centre coordinates.
# (name, lat, lon, monsoon_zone)
REGIONS = {
    "Galle": (6.0329, 80.2168, "south-west coast"),
    "Mirissa": (5.9483, 80.4589, "south coast"),
    "Ella": (6.8667, 81.0466, "hill country"),
    "Kandy": (7.2906, 80.6337, "hill country"),
    "Sigiriya": (7.9570, 80.7603, "cultural triangle / dry zone"),
    "Nuwara Eliya": (6.9497, 80.7891, "hill country"),
    "Arugam Bay": (6.8400, 81.8360, "east coast"),
    "Colombo": (6.9271, 79.8612, "west coast"),
    "Trincomalee": (8.5874, 81.2152, "east coast / north"),
    "Jaffna": (9.6615, 80.0255, "north"),
}

CATEGORY_TAGS = {
    "Food": '"amenity"="restaurant"',
    "Hotels": '"tourism"="hotel"',
    "Shops": '"shop"',
}

# Maps a business account's "business_type" (from signup) to the OSM tag
# filter used for competitor-density lookups.
BUSINESS_TYPE_TO_TAG = {
    "Food & Beverage": '"amenity"="restaurant"',
    "Accommodation / Hotel": '"tourism"="hotel"',
    "Retail / Shop": '"shop"',
    "Tour Guide / Local Vendor": '"tourism"="information"',
    "Other": '"shop"',
}


@st.cache_data(ttl=3600, show_spinner=False)
def query_overpass(lat, lon, radius_m, tag_filter):
    """Query Overpass for nodes matching tag_filter within radius_m of (lat, lon).

    Tries multiple free public mirrors with a short per-mirror timeout so a
    slow/dead mirror fails fast instead of hanging the whole page.
    Returns a list of OSM elements, or {"error": "..."} on total failure.
    """
    query = f"""
    [out:json][timeout:10];
    (
      node[{tag_filter}](around:{radius_m},{lat},{lon});
    );
    out center 20;
    """
    headers = {"User-Agent": "tourism-bi-dashboard/1.0 (student research project)"}
    last_error = None

    mirror_order = OVERPASS_URLS
    if "working_overpass_mirror" in st.session_state:
        preferred = st.session_state["working_overpass_mirror"]
        mirror_order = [preferred] + [u for u in OVERPASS_URLS if u != preferred]

    for url in mirror_order:
        try:
            resp = requests.post(url, data={"data": query}, headers=headers, timeout=(4, 9))
            resp.raise_for_status()
            st.session_state["working_overpass_mirror"] = url
            return resp.json().get("elements", [])
        except requests.exceptions.RequestException as e:
            last_error = e
            continue
    return {"error": str(last_error)}


def count_named_places(elements):
    """Return the count of named places from an Overpass result, or None on error."""
    if isinstance(elements, dict) and "error" in elements:
        return None
    return len([e for e in elements if e.get("tags", {}).get("name")])
