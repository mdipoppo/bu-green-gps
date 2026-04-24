import json
import math

import streamlit as st
import pandas as pd
import pydeck as pdk
import osmnx as ox
import networkx as nx


# -----------------------------
# Load buildings
# -----------------------------
@st.cache_data
def load_buildings():
    with open("bu_buildings.json", "r") as f:
        return json.load(f)

# -----------------------------
# Load graph (MUST be floats)
# -----------------------------
@st.cache_resource
def load_graph():
    G = ox.load_graphml("BU_green_graph.graphml")

    for u, v, k, data in G.edges(keys=True, data=True):
        for key in ["length", "ndvi", "ndvi_norm", "green_cost_mild", "green_cost_super"]:
            if key in data:
                try:
                    data[key] = float(data[key])
                except:
                    data[key] = 0.0
    return G

buildings = load_buildings()
G = load_graph()
building_names = sorted(buildings.keys())

# -----------------------------
# Page navigation
# -----------------------------
if "page" not in st.session_state:
    st.session_state.page = "select"

def go_to_select():
    st.session_state.page = "select"
    st.session_state.selected_route = None

def go_to_routes():
    st.session_state.page = "routes"

# -----------------------------
# Helper: fit-bounds zoom
# -----------------------------
def compute_view_for_points(lats, lons):
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    max_diff = max(max_lat - min_lat, max_lon - min_lon)

    if max_diff < 1e-6:
        zoom = 17
    else:
        zoom = math.log2(360 / (max_diff * 400))  # 400 tuned for BU scale
        zoom = max(13, min(zoom, 18))             # clamp between 13–18

    return center_lat, center_lon, zoom

# -----------------------------
# PAGE 1 — SELECT LOCATIONS
# -----------------------------
if st.session_state.page == "select":

    st.title("BU Green GPS")

    col1, col2 = st.columns(2)
    with col1:
        start_building = st.selectbox("Start building", building_names)
    with col2:
        end_building = st.selectbox("End building", building_names)

    st.session_state.start = start_building
    st.session_state.end = end_building

    start_lat, start_lon = buildings[start_building]
    end_lat, end_lon = buildings[end_building]

    same_building = start_building == end_building
    if same_building:
        st.warning("Start and End cannot be the same building. Please choose two different buildings.")

    df_points = pd.DataFrame([
        {"lat": start_lat, "lon": start_lon, "label": "Start", "color": [0, 150, 255]},
        {"lat": end_lat, "lon": end_lon, "label": "End", "color": [255, 0, 0]},
    ])

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_points,
        get_position="[lon, lat]",
        get_color="color",
        get_radius=12,
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=df_points,
        get_position="[lon, lat]",
        get_text="label",
        get_color=[0, 0, 0],
        get_size=20,
        get_alignment_baseline="'bottom'",
    )

    center_lat, center_lon, zoom = compute_view_for_points(
        [start_lat, end_lat],
        [start_lon, end_lon],
    )

    # Force zoomed-out view on first load (when start == end)
    if start_building == end_building:
        zoom = 14

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        pitch=45,
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        pitch=45,
    )

    st.pydeck_chart(pdk.Deck(
        layers=[point_layer, text_layer],
        initial_view_state=view_state
    ))

    st.button("Confirm Destinations", on_click=go_to_routes, disabled=same_building)

# -----------------------------
# PAGE 2 — ROUTES (CLICK TO PREVIEW)
# -----------------------------
elif st.session_state.page == "routes":

    # Initialize selection state
    if "selected_route" not in st.session_state:
        st.session_state.selected_route = None

    # Toggle helper (handles all button logic cleanly)
    def toggle_route(route_name):
        if st.session_state.selected_route == route_name:
            st.session_state.selected_route = None
        else:
            st.session_state.selected_route = route_name

    st.title("Choose Your Route")

    start = st.session_state.start
    end = st.session_state.end

    start_lat, start_lon = buildings[start]
    end_lat, end_lon = buildings[end]

    start_node = ox.nearest_nodes(G, start_lon, start_lat)
    end_node = ox.nearest_nodes(G, end_lon, end_lat)

    # Compute routes
    fastest = nx.shortest_path(G, start_node, end_node, weight="length")
    mild_green = nx.shortest_path(G, start_node, end_node, weight="green_cost_mild")
    super_green = nx.shortest_path(G, start_node, end_node, weight="green_cost_super")

    # Distances
    def route_distance(G, route):
        gdf = ox.routing.route_to_gdf(G, route)
        return float(gdf["length"].sum())

    fast_dist = route_distance(G, fastest)
    mild_dist = route_distance(G, mild_green)
    super_dist = route_distance(G, super_green)

    def time_from_meters(m):
        return round((m / 1.4) / 60, 1)

    def route_to_df(route):
        coords = []
        for node in route:
            coords.append([G.nodes[node]["y"], G.nodes[node]["x"]])
        return pd.DataFrame(coords, columns=["lat", "lon"])

    df_fast = route_to_df(fastest)
    df_mild = route_to_df(mild_green)
    df_super = route_to_df(super_green)

    # Read current selection (updated via on_click BEFORE rerun)
    selected = st.session_state.selected_route

    # -----------------------------
    # BUILD MAP LAYERS
    # -----------------------------
    def make_layer(df, color, opacity=0.6, width=4):
        path = df[["lon", "lat"]].values.tolist()
        return pdk.Layer(
            "PathLayer",
            data=[{"path": path}],
            get_path="path",
            get_color=color,
            width_scale=1,
            width_min_pixels=width,
            opacity=opacity,
            pickable=True,
            auto_highlight=True
        )

    if selected == "fast":
        layers = [
            make_layer(df_fast, [255, 0, 0], opacity=1.0, width=7),
            make_layer(df_mild, [0, 200, 0], opacity=0.3, width=2),
            make_layer(df_super, [0, 0, 255], opacity=0.3, width=2),
        ]
    elif selected == "mild":
        layers = [
            make_layer(df_fast, [255, 0, 0], opacity=0.3, width=2),
            make_layer(df_mild, [0, 200, 0], opacity=1.0, width=7),
            make_layer(df_super, [0, 0, 255], opacity=0.3, width=2),
        ]
    elif selected == "super":
        layers = [
            make_layer(df_fast, [255, 0, 0], opacity=0.3, width=2),
            make_layer(df_mild, [0, 200, 0], opacity=0.3, width=2),
            make_layer(df_super, [0, 0, 255], opacity=1.0, width=7),
        ]
    else:
        layers = [
            make_layer(df_fast, [255, 0, 0]),
            make_layer(df_mild, [0, 200, 0]),
            make_layer(df_super, [0, 0, 255]),
        ]

    # Auto-fit all routes
    all_points = pd.concat([df_fast, df_mild, df_super])
    center_lat, center_lon, zoom = compute_view_for_points(
        all_points["lat"].tolist(),
        all_points["lon"].tolist(),
    )

    view_state = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        pitch=45,
    )

    # -----------------------------
    # MAP
    # -----------------------------
    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=view_state
    ))

    # -----------------------------
    # STATS
    # -----------------------------
    st.write(f"🔴 **Fastest Route:** {fast_dist:.1f} m — {time_from_meters(fast_dist)} min")
    st.write(f"🟢 **Mild Green Route:** {mild_dist:.1f} m — {time_from_meters(mild_dist)} min")
    st.write(f"🔵 **Super Green Route:** {super_dist:.1f} m — {time_from_meters(super_dist)} min")

    # Optional: show current selection
    st.write(f"**Selected Route:** {selected if selected else 'None'}")

    # -----------------------------
    # BUTTONS (NOW BELOW STATS)
    # -----------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        st.button(
            "🔴 Preview Fastest",
            on_click=toggle_route,
            args=("fast",)
        )

    with col2:
        st.button(
            "🟢 Preview Mild Green",
            on_click=toggle_route,
            args=("mild",)
        )

    with col3:
        st.button(
            "🔵 Preview Super Green",
            on_click=toggle_route,
            args=("super",)
        )

    # -----------------------------
    # NAV BUTTONS
    # -----------------------------
    if st.button("✅ Confirm Route"):
        st.session_state.page = "confirm"

    st.button("⬅️ Back", on_click=go_to_select)
