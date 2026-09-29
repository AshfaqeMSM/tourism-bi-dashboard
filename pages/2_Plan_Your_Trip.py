"""
pages/2_Plan_Your_Trip.py

Tourist-facing trip planning page (v4):
  1. Choose a region OR "Use my current location" (real browser GPS, via
     the streamlit-js-eval component -- see note on resolve_current_location
     below for why this replaced an earlier query-param/reload approach
     that could hang on "Requesting your location...")
  2. Climate-based timing guidance -- when to visit each region
  3. A live Google Map, front and centre, with custom color-coded pin
     markers (not the default flat dots) for every recommended place
  4. Real nearby food / hotel / shop recommendations with photos, ratings,
     review counts, and a direct action button per card (Book on
     Booking.com for hotels, View on Google Maps for everything -- only
     shown when that link is actually available for a given place)

Requires GOOGLE_PLACES_API_KEY in .streamlit/secrets.toml
Requires the streamlit-js-eval package (see requirements.txt) for the
"use my current location" option.
"""

import json
import os
import sys
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.places.google_places import nearby_search, format_place
from src.ui.theme import banner_html

# NOTE: st.set_page_config() is called once in app.py (the router) --
# it can't be called again here or Streamlit raises an error.

CURRENT_LOCATION_LABEL = "\U0001F4CD Use my current location"

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

BEST_TIME = {
    "south-west coast": ("December \u2013 March", "SW monsoon (Yala) brings rain May\u2013Sep; driest and calmest Dec\u2013Mar."),
    "south coast": ("December \u2013 March", "Same SW monsoon pattern; best for whale watching Dec\u2013Apr."),
    "hill country": ("Jan\u2013Mar / Jul\u2013Sep", "Two drier windows between the two monsoon systems; cool, misty evenings year-round."),
    "cultural triangle / dry zone": ("May \u2013 September", "Drier through the SW monsoon months since this zone is more sheltered."),
    "east coast / north": ("April \u2013 September", "NE monsoon (Maha) brings rain Oct\u2013Jan; opposite season to the south/west coast."),
    "west coast": ("December \u2013 March", "Colombo is visitable year-round but nicest in this window."),
    "north": ("May \u2013 September", "NE monsoon brings rain Oct\u2013Jan; drier and hotter the rest of the year."),
    "your current location": ("Year-round", "Seasonal guidance is region-specific -- pick a named region above for a monsoon-based recommendation."),
}

# Category color + emoji glyph used to build the custom pin markers on the
# map (see build_pin_icon) -- replaces Google's flat default dot icons.
CATEGORY_COLOR = {"Food": "#c0622d", "Hotels": "#1f6f5c", "Shops": "#8a6d3b"}
CATEGORY_GLYPH = {"Food": "\U0001F374", "Hotels": "\U0001F6CF", "Shops": "\U0001F6CD"}


def inject_styles():
    st.markdown(
        """
        <style>
        .search-card {
            background: #fff; border: 1px solid #e6e2d6; border-radius: 14px;
            padding: 1.3rem 1.5rem 0.6rem 1.5rem; margin-bottom: 1.2rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }
        .place-card {
            display: flex; gap: 1rem; background: #ffffff;
            border: 1px solid #e6e2d6; border-radius: 12px;
            padding: 0.9rem; margin-bottom: 0.8rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            transition: box-shadow 0.15s ease, transform 0.15s ease;
        }
        .place-card:hover { box-shadow: 0 8px 20px rgba(0,0,0,0.10); transform: translateY(-2px); }
        .place-card img {
            width: 110px; height: 110px; object-fit: cover;
            border-radius: 8px; flex-shrink: 0;
        }
        .place-card-noimg {
            width: 110px; height: 110px; border-radius: 8px; flex-shrink: 0;
            background: linear-gradient(135deg, #eef4ee 0%, #e3ece2 100%);
            display:flex; align-items:center; justify-content:center;
            font-size: 2.1rem; border: 1px solid #dfe6dc;
        }
        .place-name { font-weight: 600; font-size: 1.02rem; margin-bottom: 0.15rem; color:#1a1a1a; }
        .place-meta { font-size: 0.85rem; color: #6b6b6b; margin-bottom: 0.2rem; }
        .place-rating { color: #b9862f; font-weight: 600; }
        .region-pill {
            display: inline-block; padding: 0.35rem 1rem; border-radius: 20px;
            background: #eef4ee; color: #1f6f5c; font-weight: 700; font-size: 0.9rem;
        }
        .place-actions { margin-top: 0.5rem; display: flex; gap: 0.6rem; flex-wrap: wrap; }
        .place-btn {
            display: inline-block; padding: 0.35rem 0.85rem; border-radius: 7px;
            font-size: 0.82rem; font-weight: 600; text-decoration: none !important;
            transition: opacity 0.15s ease;
        }
        .place-btn:hover { opacity: 0.85; }
        .place-btn-book { background: #003580; color: #ffffff !important; }
        .place-btn-maps { background: #eef4ee; color: #1f6f5c !important; border: 1px solid #cfe3d6; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def booking_search_url(place_name, region_label):
    """Booking.com has no public affiliate-free 'exact property' API, so this
    links to a pre-filled Booking.com search for the place name + region --
    one click closer than a bare Google search, without needing a paid
    Booking.com partner account (out of scope for a student project)."""
    query = f"{place_name}, {region_label}, Sri Lanka" if region_label else f"{place_name}, Sri Lanka"
    return f"https://www.booking.com/searchresults.html?ss={quote(query)}"


def render_place_card(place, category, region_label):
    stars = f'<span class="place-rating">{place["rating"]:.1f} \u2605</span> ({place["review_count"] or 0} reviews)' if place.get("rating") else '<span style="color:#999;">No ratings yet</span>'
    price = f" &nbsp;\u00b7&nbsp; {place['price']}" if place.get("price") else ""
    img_html = f'<img src="{place["photo_url"]}" />' if place.get("photo_url") else f'<div class="place-card-noimg">{CATEGORY_GLYPH.get(category, "\U0001F4CD")}</div>'

    buttons = []
    if category == "Hotels":
        book_url = booking_search_url(place["name"], region_label)
        buttons.append(f'<a class="place-btn place-btn-book" href="{book_url}" target="_blank">Book on Booking.com</a>')
    if place.get("maps_url"):
        buttons.append(f'<a class="place-btn place-btn-maps" href="{place["maps_url"]}" target="_blank">View on Google Maps</a>')
    actions_html = f'<div class="place-actions">{"".join(buttons)}</div>' if buttons else ""

    st.markdown(
        f"""
        <div class="place-card">
            {img_html}
            <div>
                <div class="place-name">{place['name']}</div>
                <div class="place-meta">{place.get('type','')}{price}</div>
                <div class="place-meta">{stars}</div>
                <div class="place-meta">{place.get('address','')}</div>
                {actions_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_pin_icon(color, glyph):
    """Build a small teardrop pin SVG (category color + emoji glyph) as a
    data: URI for use as a google.maps.Marker icon -- replaces the flat,
    plain-colored dot icons Google's default marker set uses, which read
    as cluttered/generic on a map with three categories at once."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
      <path d="M17 0C7.6 0 0 7.6 0 17c0 12.2 17 27 17 27s17-14.8 17-27C34 7.6 26.4 0 17 0z" fill="{color}" stroke="#ffffff" stroke-width="1.5"/>
      <circle cx="17" cy="17" r="11" fill="#ffffff"/>
      <text x="17" y="22" font-size="13" text-anchor="middle">{glyph}</text>
    </svg>"""
    # SVG has non-Latin1 chars (emoji), so plain base64 needs the escape/
    # encodeURIComponent dance -- do it here in Python instead, simpler.
    import base64
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def render_google_map(center_lat, center_lon, places_by_category, api_key, center_is_user):
    """Embed a real Google Map (not st.map's OSM tiles) with custom
    color-coded pin markers per category. If center_is_user is True, the
    map centers on and marks the visitor's own live location (already
    resolved via streamlit-js-eval before this is called); otherwise it
    centers on the selected region's point and still shows a 'you are
    here' dot if the browser grants permission."""

    pin_icons = {cat: build_pin_icon(CATEGORY_COLOR[cat], CATEGORY_GLYPH[cat]) for cat in CATEGORY_COLOR}

    markers_js = []
    for category, places in places_by_category.items():
        for p in places:
            if p.get("lat") and p.get("lon"):
                rating_txt = f"{p['rating']:.1f} \u2605 ({p['review_count'] or 0})" if p.get("rating") else "No ratings yet"
                markers_js.append({
                    "lat": p["lat"], "lng": p["lon"],
                    "title": p["name"].replace('"', "'"),
                    "icon": pin_icons.get(category, pin_icons["Food"]),
                    "rating": rating_txt,
                    "mapsUrl": p.get("maps_url") or "",
                })

    markers_json = json.dumps(markers_js)

    user_marker_js = f"""
        new google.maps.Marker({{
          position: {{lat: {center_lat}, lng: {center_lon}}},
          map: map,
          title: "You are here",
          zIndex: 999,
          icon: {{
            path: google.maps.SymbolPath.CIRCLE, scale: 8,
            fillColor: "#4285F4", fillOpacity: 1,
            strokeColor: "#ffffff", strokeWeight: 2,
          }},
        }});
    """ if center_is_user else """
        if (navigator.geolocation) {
          navigator.geolocation.getCurrentPosition(function(pos) {
            const userPos = {lat: pos.coords.latitude, lng: pos.coords.longitude};
            new google.maps.Marker({
              position: userPos, map: map, title: "You are here", zIndex: 999,
              icon: {
                path: google.maps.SymbolPath.CIRCLE, scale: 8,
                fillColor: "#4285F4", fillOpacity: 1,
                strokeColor: "#ffffff", strokeWeight: 2,
              },
            });
          });
        }
    """

    html = f"""
    <div id="map" style="width:100%; height:480px; border-radius:12px;"></div>
    <script>
      function initMap() {{
        const center = {{lat: {center_lat}, lng: {center_lon}}};
        const map = new google.maps.Map(document.getElementById("map"), {{
          zoom: 14,
          center: center,
        }});

        const places = {markers_json};
        const infoWindow = new google.maps.InfoWindow();
        places.forEach(function(p) {{
          const marker = new google.maps.Marker({{
            position: {{lat: p.lat, lng: p.lng}},
            map: map,
            title: p.title,
            icon: {{ url: p.icon, scaledSize: new google.maps.Size(30, 39), anchor: new google.maps.Point(15, 39) }},
          }});
          marker.addListener("click", function() {{
            const linkHtml = p.mapsUrl
              ? '<a href="' + p.mapsUrl + '" target="_blank" style="color:#1f6f5c;font-weight:600;">View on Google Maps &rarr;</a>'
              : '';
            infoWindow.setContent(
              '<div style="font-family:sans-serif;">' +
              '<strong>' + p.title + '</strong><br/>' +
              '<span style="color:#b9862f;">' + p.rating + '</span><br/>' +
              linkHtml +
              '</div>'
            );
            infoWindow.open(map, marker);
          }});
        }});

        {user_marker_js}
      }}
    </script>
    <script async
      src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap">
    </script>
    """
    components.html(html, height=490)


def resolve_current_location():
    """Get the visitor's GPS coords via the streamlit-js-eval component.

    This replaced an earlier hand-rolled approach that ran raw JS inside a
    components.html iframe and tried to hand coordinates back to Python by
    reloading the page with them in the URL query string. That reload
    depended on the browser's geolocation call actually completing inside
    a sandboxed iframe -- modern browsers restrict the Geolocation API by
    Permissions-Policy for iframes that don't explicitly get it (via an
    "allow" attribute Streamlit doesn't expose), so the call could fail
    silently before either callback fired, leaving the page stuck showing
    "Requesting your location..." even after the OS-level permission
    prompt was accepted. streamlit-js-eval is a real declared Streamlit
    component (not a raw iframe), so its host frame gets the correct
    permissions and returns the value straight back as a Python dict --
    no page reload needed.
    """
    try:
        from streamlit_js_eval import get_geolocation
    except ImportError:
        st.error(
            "The `streamlit-js-eval` package is required for \u201cUse my "
            "current location\u201d. Install it with `pip install "
            "streamlit-js-eval` and restart the app, or choose a region "
            "from the dropdown instead."
        )
        return None

    if "user_coords" in st.session_state:
        return st.session_state["user_coords"]

    location = get_geolocation(component_key="plan_trip_geolocation")
    if isinstance(location, dict):
        coords_data = location.get("coords")
        if coords_data and coords_data.get("latitude") is not None:
            coords = (coords_data["latitude"], coords_data["longitude"])
            st.session_state["user_coords"] = coords
            return coords

    st.info(
        "Requesting your location \u2014 allow the browser's permission "
        "prompt to continue. If you don't see a prompt, check the address "
        "bar for a blocked-permission icon, allow it there, then refresh."
    )
    st.stop()
    return None


def main():
    inject_styles()

    st.markdown(
        banner_html(
            "Plan Your Trip",
            "Explore where to go, when to go, and what's nearby \u2014 powered by live Google Places data.",
            tag="Trip planner",
        ),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="search-card">', unsafe_allow_html=True)
    region_options = [CURRENT_LOCATION_LABEL] + list(REGIONS.keys())
    search_col1, search_col2 = st.columns([2, 1])
    with search_col1:
        region_choice = st.selectbox("Where to?", region_options)
    with search_col2:
        radius_km = st.slider("Search radius (km)", 1, 15, 2, help="Recommended: 1\u20132km for walkable exploring")
    st.markdown("</div>", unsafe_allow_html=True)

    center_is_user = region_choice == CURRENT_LOCATION_LABEL
    if center_is_user:
        coords = resolve_current_location()
        if coords is None:
            return
        lat, lon = coords
        zone = "your current location"
        region_label = "Your current location"
    else:
        lat, lon, zone = REGIONS[region_choice]
        region_label = region_choice

    top_col1, top_col2 = st.columns([4, 1])
    with top_col1:
        st.markdown(f'<span class="region-pill">{region_label}</span>', unsafe_allow_html=True)
    if center_is_user:
        with top_col2:
            if st.button("\U0001F504 Refresh location"):
                st.session_state.pop("user_coords", None)
                st.rerun()
        st.caption("Showing places around your live GPS location. Switch to a named region above for seasonal timing guidance.")
    st.write("")

    col1, col2 = st.columns([1, 2])
    best_window, note = BEST_TIME.get(zone, ("Year-round", "No strong seasonal pattern for this zone."))
    with col1:
        st.metric("Best time to visit", best_window)
    with col2:
        st.write(note)
    st.caption("Based on Sri Lanka's two monsoon systems (Yala, SW monsoon, and Maha, NE monsoon) \u2014 general seasonal guidance, not live weather.")

    st.divider()

    radius_m = radius_km * 1000

    all_results = {}
    with st.spinner("Finding places nearby..."):
        for category in CATEGORY_COLOR:
            raw = nearby_search(lat, lon, radius_m, category)
            if isinstance(raw, dict) and "error" in raw:
                all_results[category] = {"error": raw["error"]}
            else:
                all_results[category] = [format_place(p) for p in raw] if raw else []

    st.subheader("Map")
    st.caption("\U0001F374 Food &nbsp;&nbsp; \U0001F6CF\uFE0F Hotels &nbsp;&nbsp; \U0001F6CD\uFE0F Shops &nbsp;&nbsp; Blue dot = your location")

    api_key = st.secrets.get("GOOGLE_PLACES_API_KEY") if hasattr(st, "secrets") else None
    map_ready_results = {k: v for k, v in all_results.items() if isinstance(v, list)}
    if api_key:
        render_google_map(lat, lon, map_ready_results, api_key, center_is_user)
    else:
        st.warning("Add GOOGLE_PLACES_API_KEY to .streamlit/secrets.toml to show the live map.")
        map_points = [{"lat": lat, "lon": lon}]
        for places in map_ready_results.values():
            for p in places:
                if p.get("lat") and p.get("lon"):
                    map_points.append({"lat": p["lat"], "lon": p["lon"]})
        st.map(data=map_points, zoom=13)

    st.divider()
    st.subheader(f"Nearby {region_label}")

    tabs = st.tabs(list(CATEGORY_COLOR.keys()))
    for tab, category in zip(tabs, CATEGORY_COLOR.keys()):
        with tab:
            result = all_results.get(category)
            if isinstance(result, dict) and "error" in result:
                st.warning(f"Couldn't load {category.lower()}: {result['error']}")
                continue
            if not result:
                st.caption(f"No {category.lower()} found within {radius_km}km \u2014 try widening the search.")
                continue
            for place in result:
                render_place_card(place, category, region_label)

    st.caption("Place data and photos from Google Places. Ratings and review counts reflect Google's public listings. Booking.com links are a pre-filled search, not a direct listing match.")


if __name__ == "__main__":
    main()
