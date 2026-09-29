"""
src/places/google_places.py

Wrapper around the Places API (New) -- nearby search + photos.
Uses a field mask on every request to control cost: the New Places API
bills per field category requested, so we only ask for what we display.

Docs: https://developers.google.com/maps/documentation/places/web-service/nearby-search
"""

import time

import requests
import streamlit as st

NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PHOTO_URL_TEMPLATE = "https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={width}&key={key}"

# Maps our category labels to the Places API "included types"
# https://developers.google.com/maps/documentation/places/web-service/place-types
CATEGORY_TYPES = {
    "Food": ["restaurant", "cafe"],
    "Hotels": ["lodging"],
    "Shops": ["store", "shopping_mall"],
}

# Text-query equivalent, used only by count_competitors_accurate() below --
# Text Search (New) takes a free-text query rather than a types list.
CATEGORY_QUERY_TEXT = {
    "Food": "restaurants and cafes",
    "Hotels": "hotels and lodging",
    "Shops": "stores and shops",
}

# Field mask -- keep this tight, each field group has a cost tier.
# id/displayName/location = free (Basic). rating/userRatingCount/photos =
# Pro tier. priceLevel = Pro tier too. reviews = Enterprise tier (pricier).
# Kept as a SEPARATE, opt-in mask (not the default) so Plan Your Trip's
# frequent searches don't pay the Enterprise-tier cost for review text it
# never displays -- only Expansion Insights, which actually uses review
# text for sentiment, requests it (see nearby_search's include_reviews arg).
FIELD_MASK = (
    "places.id,places.displayName,places.location,places.rating,"
    "places.userRatingCount,places.photos,places.priceLevel,"
    "places.primaryTypeDisplayName,places.formattedAddress"
)
FIELD_MASK_WITH_REVIEWS = FIELD_MASK + ",places.reviews"


def _get_api_key():
    try:
        return st.secrets["GOOGLE_PLACES_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def nearby_search(lat, lon, radius_m, category, include_reviews=False):
    """Search for places near (lat, lon) within radius_m, for a given
    category ("Food", "Hotels", "Shops"). Returns a list of place dicts,
    or {"error": "..."}.

    include_reviews=True requests review text too (Enterprise-tier field,
    see FIELD_MASK_WITH_REVIEWS above) -- pass this only where review text
    is actually used (currently: Expansion Insights' sentiment signal),
    not on every routine search.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "No Google Places API key found. Add GOOGLE_PLACES_API_KEY to .streamlit/secrets.toml"}

    included_types = CATEGORY_TYPES.get(category, ["restaurant"])

    body = {
        "includedTypes": included_types,
        "maxResultCount": 15,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius_m,
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK_WITH_REVIEWS if include_reviews else FIELD_MASK,
    }

    try:
        resp = requests.post(NEARBY_SEARCH_URL, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json().get("places", [])
    except requests.exceptions.RequestException as e:
        detail = ""
        if e.response is not None:
            detail = f" ({e.response.status_code}: {e.response.text[:200]})"
        return {"error": f"{e}{detail}"}


@st.cache_data(ttl=3600, show_spinner=False)
def count_competitors_accurate(lat, lon, radius_m, category, max_results=60):
    """More accurate competitor count than nearby_search() alone can give.

    Nearby Search (New) hard-caps at 20 results per call with NO
    pagination support at all (a genuine Google platform limit, not a
    choice made here) -- so a dense area always reports "15+"/"20+"
    regardless of the true count. Text Search (New) DOES support
    pagination via nextPageToken, up to Google's real ceiling of 3 pages
    x 20 = 60 total. This function uses that to get a materially more
    accurate count, requesting ONLY the id field (the cheapest possible
    tier) since a count is all this is for -- the richer per-place data
    (rating, review volume, review text) still comes from the existing
    nearby_search() call, unchanged, so this doesn't duplicate that cost.

    Cost note: each extra page is a separate billable request. A sparse
    region (fewer than 20 matches) still only costs 1 call, since
    pagination stops as soon as a page comes back not-full; a dense
    region can cost up to 3 calls. Used only by Expansion Insights'
    competitor-density count, not by Plan Your Trip, which doesn't need
    a precise count for a handful of displayed cards.

    Returns an int count, or {"error": "..."}.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "No Google Places API key found. Add GOOGLE_PLACES_API_KEY to .streamlit/secrets.toml"}

    query_text = CATEGORY_QUERY_TEXT.get(category, "restaurants")
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,nextPageToken",
    }

    total = 0
    page_token = None
    for page_num in range(3):  # Google's real ceiling: 3 pages x 20 = 60 max
        if page_token:
            # A freshly-issued pageToken isn't always immediately usable --
            # Google's own guidance (carried over from the legacy Places
            # API) is to wait briefly before the next page request, or it
            # can come back as an invalid-argument error.
            time.sleep(2)

        body = {
            "textQuery": query_text,
            "maxResultCount": 20,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": radius_m,
                }
            },
        }
        if page_token:
            body["pageToken"] = page_token

        try:
            resp = requests.post(TEXT_SEARCH_URL, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            if page_num > 0:
                # Keep the count from whatever pages already succeeded
                # rather than discarding real partial data over a later
                # page failing (e.g. a transient timeout).
                break
            detail = ""
            if e.response is not None:
                detail = f" ({e.response.status_code}: {e.response.text[:200]})"
            return {"error": f"{e}{detail}"}

        batch = data.get("places", [])
        total += len(batch)
        page_token = data.get("nextPageToken")
        if not page_token or len(batch) < 20 or total >= max_results:
            break

    return min(total, max_results)


def get_photo_url(photo_name, width=400):
    """Build a display URL for a place photo. photo_name comes from a
    place's photos[i].name field (format: 'places/.../photos/...')."""
    api_key = _get_api_key()
    if not api_key or not photo_name:
        return None
    return PHOTO_URL_TEMPLATE.format(photo_name=photo_name, width=width, key=api_key)


def format_place(place):
    """Extract the fields we care about into a flat, display-friendly dict."""
    place_id = place.get("id")
    name = place.get("displayName", {}).get("text", "Unnamed")
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    address = place.get("formattedAddress", "")
    place_type = place.get("primaryTypeDisplayName", {}).get("text", "")
    location = place.get("location", {})
    lat, lon = location.get("latitude"), location.get("longitude")

    photo_url = None
    photos = place.get("photos", [])
    if photos:
        photo_url = get_photo_url(photos[0].get("name"), width=400)

    price_level_map = {
        "PRICE_LEVEL_FREE": "Free", "PRICE_LEVEL_INEXPENSIVE": "$",
        "PRICE_LEVEL_MODERATE": "$$", "PRICE_LEVEL_EXPENSIVE": "$$$",
        "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
    }
    price = price_level_map.get(place.get("priceLevel"), "")

    # Google's Universal Maps URL scheme accepts a place_id directly --
    # this opens the exact business listing (hours, reviews, directions),
    # not just a pin at its coordinates.
    maps_url = None
    if place_id:
        from urllib.parse import quote
        maps_url = f"https://www.google.com/maps/search/?api=1&query={quote(name)}&query_place_id={place_id}"

    return {
        "name": name,
        "rating": rating,
        "review_count": review_count,
        "address": address,
        "type": place_type,
        "lat": lat,
        "lon": lon,
        "photo_url": photo_url,
        "price": price,
        "place_id": place_id,
        "maps_url": maps_url,
    }
