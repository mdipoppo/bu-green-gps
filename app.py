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
    G = ox.load_graphml("2BU_green_graph.graphml")

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
    # Reset the selected route here so it clears every time we go to the page
    st.session_state.selected_route = None

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

    # --- CUSTOM CSS TO MAKE BUTTONS GREEN ---
    st.markdown("""
        <style>
        div.stButton > button:first-child {
            background-color: #28a745 !important;
            color: white !important;
            border: none;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("BU Green GPS")

    col1, col2 = st.columns(2)
    with col1:
        start_building = st.selectbox("Start building", building_names)
    with col2:
        end_building = st.selectbox("End building", building_names)

    st.session_state.start = start_building
    st.session_state.end = end_building

    # --- CONDITIONAL LOGIC FOR BUTTON/WARNING ---
    if start_building == end_building:
        st.warning("Start and End cannot be the same building. Please choose two different buildings.")
    else:
        # Now this will be green!
        st.button("Confirm Destinations", on_click=go_to_routes, use_container_width=True)

    # --- MAP RENDERING ---
    start_lat, start_lon = buildings[start_building]
    end_lat, end_lon = buildings[end_building]
    
    # ... (Rest of your existing map code: df_points, point_layer, etc.)
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

    center_lat = (start_lat + end_lat) / 2
    center_lon = (start_lon + end_lon) / 2

    lat_diff = abs(start_lat - end_lat)
    lon_diff = abs(start_lon - end_lon)
    max_diff = max(lat_diff, lon_diff)

    if max_diff < 0.001:
        zoom = 16
    elif max_diff < 0.005:
        zoom = 15
    elif max_diff < 0.01:
        zoom = 14
    elif max_diff < 0.02:
        zoom = 13
    else:
        zoom = 12

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

# -----------------------------
# PAGE 2 — ROUTES (CLICK TO PREVIEW)
# -----------------------------
elif st.session_state.page == "routes":

    # --- RESET LOGIC ---
    # Store the current buildings in a tuple
    current_pair = (st.session_state.start, st.session_state.end)
    
    # If the app doesn't know the last pair, or if the user changed the buildings,
    # reset the selected_route to None so the map starts fresh.
    if "last_pair" not in st.session_state or st.session_state.last_pair != current_pair:
        st.session_state.selected_route = None
        st.session_state.last_pair = current_pair

    # Toggle helper
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

        # --- ADD THIS BLOCK ---
    def bearing(lat1, lon1, lat2, lon2):
        y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
        x = math.cos(math.radians(lat1))*math.sin(math.radians(lat2)) - \
            math.sin(math.radians(lat1))*math.cos(math.radians(lat2))*math.cos(math.radians(lon2 - lon1))
        brng = math.degrees(math.atan2(y, x))
        return (brng + 360) % 360

    def turn_direction(prev_bearing, new_bearing):
        diff = (new_bearing - prev_bearing + 360) % 360
        if diff < 30 or diff > 330: return "Continue straight"
        elif diff < 180: return "Turn right"
        else: return "Turn left"

    def get_route_steps(G, route):
        steps = []
        prev_bearing = None
        for i in range(len(route)-1):
            u, v = route[i], route[i+1]
            data = G.get_edge_data(u, v)[0]
            # Look for 'resolved_name', if missing look for 'name', if that's missing, use 'highway' type, otherwise default
            street = data.get("resolved_name") or data.get("name") or data.get("highway", "Sidewalk")
            length = data.get("length", 0)
            br = bearing(G.nodes[u]['y'], G.nodes[u]['x'], G.nodes[v]['y'], G.nodes[v]['x'])
            action = "Start" if prev_bearing is None else turn_direction(prev_bearing, br)
            steps.append({'action': action, 'street': street, 'dist': length, 'node_idx': i})
            prev_bearing = br
        merged = []
        curr = None
        for s in steps:
            if curr is None: curr = s
            elif s['street'] == curr['street']: curr['dist'] += s['dist']
            else:
                merged.append(curr); curr = s
        merged.append(curr)
        return [s for s in merged if s['dist'] >= 5]
    # ----------------------

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
    # BUTTONS WITH STATS BELOW
    # -----------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        st.button(
            "🔴 Preview Fastest",
            on_click=toggle_route,
            args=("fast",),
            use_container_width=True,
        )
        if selected == "fast":
            st.markdown(f"**{fast_dist:.1f} m — {time_from_meters(fast_dist)} min**")
        else:
            st.write(f"{fast_dist:.1f} m — {time_from_meters(fast_dist)} min")

    with col2:
        st.button(
            "🟢 Preview Mild Green",
            on_click=toggle_route,
            args=("mild",),
            use_container_width=True,
        )
        if selected == "mild":
            st.markdown(f"**{mild_dist:.1f} m — {time_from_meters(mild_dist)} min**")
        else:
            st.write(f"{mild_dist:.1f} m — {time_from_meters(mild_dist)} min")

    with col3:
        st.button(
            "🔵 Preview Super Green",
            on_click=toggle_route,
            args=("super",),
            use_container_width=True,
        )
        if selected == "super":
            st.markdown(f"**{super_dist:.1f} m — {time_from_meters(super_dist)} min**")
        else:
            st.write(f"{super_dist:.1f} m — {time_from_meters(super_dist)} min")

    # -----------------------------
    # NAV BUTTONS
    # -----------------------------
    if not selected:
        st.warning("Please select a route before confirming.")

    route_emoji = {"fast": "🔴", "mild": "🟢", "super": "🔵"}.get(selected, "")
    confirm_label = f"✅ Confirm Route {route_emoji}" if route_emoji else "✅ Confirm Route"
    if st.button(confirm_label, disabled=not selected, use_container_width=True):
        if st.session_state.selected_route == "fast": route = fastest
        elif st.session_state.selected_route == "mild": route = mild_green
        else: route = super_green
        st.session_state.route_nodes = route
        st.session_state.steps = get_route_steps(G, route)
        st.session_state.current_step_idx = 0
        st.session_state.page = "navigate"
        st.rerun()

    st.button("⬅️ Back", on_click=go_to_select)

# -----------------------------
# PAGE 3 — NAVIGATION
# -----------------------------
elif st.session_state.page == "navigate":
    st.title("Directions")
    idx = st.session_state.current_step_idx
    steps = st.session_state.steps
    
    # --- 1. PROGRESS BAR ---
    # Calculate progress (0.0 to 1.0)
    # We use min() to ensure it doesn't go over 100% when at the "Arrived" state
    total_steps = len(steps) if len(steps) > 0 else 1
    progress_val = min(1.0, idx / total_steps)
    st.progress(progress_val)
    
    # --- 2. DETERMINE DOT & PATH DATA ---
    layers = []
    
    if idx >= len(steps):
        # ARRIVED STATE
        dot_node = st.session_state.route_nodes[-1]
        dot_color = [0, 0, 255] # Blue
        dot_radius = 25
        path_coords = None 
    else:
        # NAVIGATION STATE
        curr = steps[idx]
        dot_node = st.session_state.route_nodes[curr['node_idx']]
        dot_color = [255, 0, 0] # Red
        dot_radius = 10
        # Calculate remaining path
        remaining = st.session_state.route_nodes[curr['node_idx']:]
        path_coords = [[G.nodes[n]["x"], G.nodes[n]["y"]] for n in remaining]

    # --- 3. ADD LAYERS CONDITIONALLY ---
    if path_coords:
        layers.append(pdk.Layer(
            "PathLayer", 
            data=[{"path": path_coords}], 
            get_path="path", 
            get_color=[0, 255, 0], 
            width_min_pixels=8
        ))
    
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": G.nodes[dot_node]['y'], "lon": G.nodes[dot_node]['x']}],
        get_position="[lon, lat]",
        get_fill_color=dot_color,
        get_radius=dot_radius,
    ))

    # --- 4. RENDER MAP ---
    st.pydeck_chart(pdk.Deck(
        layers=layers, 
        initial_view_state=pdk.ViewState(
            latitude=G.nodes[dot_node]['y'], 
            longitude=G.nodes[dot_node]['x'], 
            zoom=17, pitch=45
        )
    ))

    # --- 5. TEXT & CONTROLS ---
    if idx >= len(steps):
        st.success("You have arrived!")
        if st.button("Finish", use_container_width=True): 
            st.session_state.page = "select"
            st.rerun()
    else:
        curr = steps[idx]
        street_display = f" on {curr['street']}" if curr['street'] != "Unnamed Path" else ""
        st.subheader(f"Step {idx+1}: {curr['action']}{street_display}")
        st.write(f"Continue for {curr['dist']:.0f} meters.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Last Direction", use_container_width=True):
                if st.session_state.current_step_idx > 0:
                    st.session_state.current_step_idx -= 1
                    st.rerun()
        with col2:
            if st.button("Next Step ➡️", use_container_width=True):
                st.session_state.current_step_idx += 1
                st.rerun()
        
        if st.button("Cancel Navigation", use_container_width=True): 
            st.session_state.page = "select"
            st.rerun()
