import os

import streamlit as st
import requests
import pandas as pd
import folium
import osmnx as ox
import networkx as nx
import altair as alt

from streamlit_folium import st_folium
from folium.features import DivIcon


# ===================================================
# CONFIGURATION
# ===================================================

API_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000"
)

ORDERS_FILE = "data/orders.csv"

GRAPH_FILE = "data/mumbai_road_graph.graphml"

VEHICLE_COLORS = [
    "red",
    "blue",
    "green"
]


st.set_page_config(
    page_title="Cloud Kitchen Optimisation",
    page_icon="🍽️",
    layout="wide"
)


# ===================================================
# OSMNX SETTINGS
# ===================================================

ox.settings.use_cache = True
ox.settings.log_console = False


# ===================================================
# SESSION STATE
# ===================================================

if "evaluation_result" not in st.session_state:
    st.session_state.evaluation_result = None

if "simulation_result" not in st.session_state:
    st.session_state.simulation_result = None

if "road_graph" not in st.session_state:
    st.session_state.road_graph = None


# ===================================================
# HELPER: LABELED BAR CHART
# ===================================================

def create_bar_chart(
    dataframe,
    category_column,
    value_column,
    title,
    y_axis_title,
    decimals=0
):

    if decimals == 0:
        text_format = ".0f"
    else:
        text_format = ".2f"

    bars = (
        alt.Chart(dataframe)
        .mark_bar(
            cornerRadiusTopLeft=5,
            cornerRadiusTopRight=5
        )
        .encode(
            x=alt.X(
                f"{category_column}:N",
                title="Scenario",
                sort=[
                    "Baseline",
                    "Optimised"
                ],
                axis=alt.Axis(
                    labelAngle=0
                )
            ),

            y=alt.Y(
                f"{value_column}:Q",
                title=y_axis_title,
                scale=alt.Scale(
                    zero=True
                )
            ),

            tooltip=[
                alt.Tooltip(
                    f"{category_column}:N",
                    title="Scenario"
                ),

                alt.Tooltip(
                    f"{value_column}:Q",
                    title=y_axis_title,
                    format=text_format
                )
            ]
        )
    )

    labels = (
        alt.Chart(dataframe)
        .mark_text(
            dy=-12,
            fontSize=17,
            fontWeight="bold",
            color="white"
        )
        .encode(
            x=alt.X(
                f"{category_column}:N",
                sort=[
                    "Baseline",
                    "Optimised"
                ]
            ),

            y=alt.Y(
                f"{value_column}:Q"
            ),

            text=alt.Text(
                f"{value_column}:Q",
                format=text_format
            )
        )
    )

    return (
        bars
        + labels
    ).properties(
        title=title,
        height=380
    ).configure_title(
        fontSize=22,
        anchor="start"
    ).configure_axis(
        labelFontSize=14,
        titleFontSize=15
    )


# ===================================================
# HELPER: COMPARISON TEXT
# ===================================================

def show_comparison_text(
    baseline_value,
    optimized_value,
    lower_is_better=True
):

    if baseline_value == 0:

        st.markdown(
            """
            <div style="
                color:#aaaaaa;
                font-size:16px;
                font-weight:600;
                margin-top:-8px;
            ">
                No baseline comparison available
            </div>
            """,
            unsafe_allow_html=True
        )

        return


    difference_percent = (
        abs(
            optimized_value
            - baseline_value
        )
        / baseline_value
        * 100
    )


    if optimized_value < baseline_value:

        wording = (
            f"{difference_percent:.1f}% lower than baseline"
        )

        if lower_is_better:
            color = "#2ecc71"
        else:
            color = "#ff4b4b"


    elif optimized_value > baseline_value:

        wording = (
            f"{difference_percent:.1f}% higher than baseline"
        )

        if lower_is_better:
            color = "#ff4b4b"
        else:
            color = "#2ecc71"


    else:

        wording = "Same as baseline"
        color = "#aaaaaa"


    st.markdown(
        f"""
        <div style="
            color:{color};
            font-size:16px;
            font-weight:600;
            margin-top:-8px;
        ">
            {wording}
        </div>
        """,
        unsafe_allow_html=True
    )


# ===================================================
# PAGE HEADER
# ===================================================

st.title(
    "Cloud Kitchen Delivery Optimisation System"
)

st.write(
    "VRPTW-based food delivery route optimisation "
    "using Google OR-Tools, OpenStreetMap and SimPy"
)


# ===================================================
# LOAD ORDERS
# ===================================================

try:

    orders_df = pd.read_csv(
        ORDERS_FILE
    )

except Exception as error:

    st.error(
        f"Could not load orders.csv: {error}"
    )

    st.stop()


# ===================================================
# BACKEND CHECK
# ===================================================

backend_connected = False

try:

    response = requests.get(
        f"{API_URL}/health",
        timeout=5
    )

    if response.status_code == 200:

        backend_connected = True

        st.success(
            "Backend API Connected"
        )

    else:

        st.warning(
            "Backend API responded with an error"
        )

except requests.exceptions.RequestException:

    st.error(
        "Backend API is not running. "
        f"Expected backend at: {API_URL}"
    )


st.divider()


# ===================================================
# SYSTEM OVERVIEW
# ===================================================

c1, c2, c3 = st.columns(3)

with c1:

    st.metric(
        "Available Vehicles",
        "3"
    )

with c2:

    st.metric(
        "Customer Orders",
        len(orders_df)
    )

with c3:

    st.metric(
        "Vehicle Capacity",
        "4 / 3 / 4"
    )


st.divider()


# ===================================================
# CUSTOMER ORDERS
# ===================================================

st.subheader(
    "Customer Orders"
)

display_df = (
    orders_df.rename(
        columns={
            "order_id":
                "Order ID",

            "address":
                "Address",

            "zone":
                "Zone",

            "deadline":
                "Deadline (min)",

            "demand":
                "Demand Units",

            "ready_time":
                "Ready Time (min)"
        }
    )
)

st.table(
    display_df
)

st.caption(
    "Ready Time indicates when cooking is completed "
    "and the order becomes available for loading. "
    "Demand represents the number of vehicle-capacity "
    "units consumed by the order."
)


st.divider()


# ===================================================
# RUN OPTIMISATION + SIMULATION
# ===================================================

st.subheader(
    "Delivery Route Optimisation"
)

st.write(
    "Run route optimisation, baseline evaluation "
    "and discrete-event delivery simulation."
)


if st.button(
    "Optimise Deliveries",
    type="primary"
):

    if not backend_connected:

        st.error(
            "Backend is not connected."
        )

    else:

        try:

            with st.spinner(
                "Optimising routes and evaluating performance..."
            ):

                evaluation_response = requests.get(
                    f"{API_URL}/evaluate",
                    timeout=180
                )

            evaluation_result = (
                evaluation_response.json()
            )

            if (
                evaluation_result.get(
                    "status"
                )
                != "success"
            ):

                st.error(
                    evaluation_result.get(
                        "message",
                        "Evaluation failed"
                    )
                )

                st.stop()


            with st.spinner(
                "Running traffic-adjusted "
                "SimPy delivery simulation..."
            ):

                simulation_response = requests.get(
                    f"{API_URL}/simulate",
                    timeout=180
                )

            simulation_result = (
                simulation_response.json()
            )

            if (
                simulation_result.get(
                    "status"
                )
                != "success"
            ):

                st.error(
                    simulation_result.get(
                        "message",
                        "Simulation failed"
                    )
                )

                st.stop()


            st.session_state.evaluation_result = (
                evaluation_result
            )

            st.session_state.simulation_result = (
                simulation_result
            )

            st.session_state.road_graph = None


        except Exception as error:

            st.error(
                f"Error: {error}"
            )


# ===================================================
# ROUTING RESULTS
# ===================================================

if (
    st.session_state.evaluation_result
    is not None
):

    evaluation = (
        st.session_state.evaluation_result
    )

    routes = (
        evaluation[
            "optimized_routes"
        ]
    )

    st.success(
        "Delivery routes optimised successfully"
    )

    st.divider()


    # ===================================================
    # LOCATION BOUNDS
    # ===================================================

    all_coordinates = []

    for vehicle in routes:

        for stop in vehicle[
            "route"
        ]:

            all_coordinates.append(
                (
                    float(
                        stop[
                            "latitude"
                        ]
                    ),

                    float(
                        stop[
                            "longitude"
                        ]
                    )
                )
            )


    restaurant_lat = float(
        routes[0][
            "route"
        ][0][
            "latitude"
        ]
    )

    restaurant_lon = float(
        routes[0][
            "route"
        ][0][
            "longitude"
        ]
    )


    # ===================================================
    # LOAD PRECOMPUTED ROAD GRAPH
    # ===================================================

    st.subheader(
        "Optimised Delivery Map"
    )

    if (
        st.session_state.road_graph
        is None
    ):

        if not os.path.exists(
            GRAPH_FILE
        ):

            st.error(
                f"Road graph file not found: "
                f"{GRAPH_FILE}"
            )

            st.stop()


        with st.spinner(
            "Loading precomputed road network..."
        ):

            try:

                graph = (
                    ox.load_graphml(
                        GRAPH_FILE
                    )
                )

                st.session_state.road_graph = (
                    graph
                )

            except Exception as error:

                st.error(
                    f"Could not load road graph: "
                    f"{error}"
                )

                st.stop()


    graph = (
        st.session_state.road_graph
    )


    # ===================================================
    # MAP
    # ===================================================

    delivery_map = folium.Map(
        location=[
            restaurant_lat,
            restaurant_lon
        ],
        zoom_start=13,
        tiles="OpenStreetMap"
    )

    bounds = []


    # ===================================================
    # RESTAURANT MARKER
    # ===================================================

    folium.CircleMarker(
        [
            restaurant_lat,
            restaurant_lon
        ],
        radius=12,
        color="black",
        weight=3,
        fill=True,
        fill_color="yellow",
        fill_opacity=1,
        tooltip="Restaurant"
    ).add_to(
        delivery_map
    )


    folium.Marker(
        [
            restaurant_lat,
            restaurant_lon
        ],
        icon=DivIcon(
            icon_size=(
                30,
                30
            ),
            icon_anchor=(
                10,
                10
            ),
            html="""
            <div style="
                font-size:14px;
                font-weight:bold;
                color:black;
                text-align:center;
            ">
                R
            </div>
            """
        )
    ).add_to(
        delivery_map
    )


    bounds.append(
        [
            restaurant_lat,
            restaurant_lon
        ]
    )


    # ===================================================
    # DELIVERY ROUTES
    # ===================================================

    for vehicle in routes:

        vehicle_id = (
            vehicle[
                "vehicle"
            ]
            + 1
        )

        zone = (
            vehicle[
                "assigned_zone"
            ]
        )

        color = (
            VEHICLE_COLORS[
                vehicle[
                    "vehicle"
                ]
            ]
        )

        route = (
            vehicle[
                "route"
            ]
        )

        stop_number = 0


        for stop in route:

            if (
                stop[
                    "order_id"
                ]
                == "Restaurant"
            ):

                continue


            stop_number += 1


            lat = float(
                stop[
                    "latitude"
                ]
            )

            lon = float(
                stop[
                    "longitude"
                ]
            )


            folium.CircleMarker(
                [
                    lat,
                    lon
                ],
                radius=12,
                color="white",
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=1,

                tooltip=(
                    f"Vehicle "
                    f"{vehicle_id} | "
                    f"Stop "
                    f"{stop_number} | "
                    f"Order "
                    f"{stop['order_id']}"
                ),

                popup=(
                    f"<b>Vehicle "
                    f"{vehicle_id}</b><br>"
                    f"Zone: {zone}<br>"
                    f"Stop: "
                    f"{stop_number}<br>"
                    f"Order: "
                    f"{stop['order_id']}<br>"
                    f"Address: "
                    f"{stop['address']}<br>"
                    f"Planned Arrival: "
                    f"{stop['arrival_time']} min<br>"
                    f"Deadline: "
                    f"{stop['original_deadline']} min"
                )

            ).add_to(
                delivery_map
            )


            folium.Marker(
                [
                    lat,
                    lon
                ],

                icon=DivIcon(
                    icon_size=(
                        24,
                        24
                    ),

                    icon_anchor=(
                        8,
                        9
                    ),

                    html=f"""
                    <div style="
                        width:22px;
                        height:22px;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        color:white;
                        font-size:13px;
                        font-weight:bold;
                    ">
                        {stop_number}
                    </div>
                    """
                )

            ).add_to(
                delivery_map
            )


            bounds.append(
                [
                    lat,
                    lon
                ]
            )


        # ===================================================
        # ROAD PATH
        # ===================================================

        for index in range(
            len(route)
            - 1
        ):

            from_node = int(
                route[
                    index
                ][
                    "osm_node"
                ]
            )

            to_node = int(
                route[
                    index
                    + 1
                ][
                    "osm_node"
                ]
            )


            try:

                path = (
                    nx.shortest_path(
                        graph,
                        source=
                            from_node,
                        target=
                            to_node,
                        weight=
                            "travel_time"
                    )
                )

                coordinates = []

                for node in path:

                    node_data = (
                        graph.nodes[
                            node
                        ]
                    )

                    coordinates.append(
                        [
                            node_data[
                                "y"
                            ],
                            node_data[
                                "x"
                            ]
                        ]
                    )


                folium.PolyLine(
                    coordinates,
                    color=color,
                    weight=6,
                    opacity=0.9
                ).add_to(
                    delivery_map
                )


            except (
                nx.NetworkXNoPath,
                nx.NodeNotFound
            ):

                pass


    delivery_map.fit_bounds(
        bounds,
        padding=[
            40,
            40
        ]
    )


    # ===================================================
    # MAP LEGEND
    # ===================================================

    legend_html = """
    <div style="
        position: fixed;
        bottom: 35px;
        left: 35px;
        width: 240px;
        z-index: 9999;
        background: white;
        border: 2px solid #333333;
        border-radius: 10px;
        padding: 12px 15px;
        font-family: Arial;
        font-size: 14px;
        color: #111111;
    ">

    <b style="font-size:16px;">
        Route Legend
    </b>

    <br><br>

    🔴 Vehicle 1 — WEST<br><br>
    🔵 Vehicle 2 — WEST<br><br>
    🟢 Vehicle 3 — EAST<br><br>
    🟡 Restaurant

    <hr>

    Number inside marker =
    delivery stop order

    </div>
    """


    delivery_map.get_root().html.add_child(
        folium.Element(
            legend_html
        )
    )


    st_folium(
        delivery_map,
        width=1200,
        height=650,
        returned_objects=[]
    )


    st.caption(
        "Optimised routes follow "
        "the precomputed OpenStreetMap road network."
    )


    st.divider()


    # ===================================================
    # ROUTE TABLES
    # ===================================================

    st.subheader(
        "Optimised Vehicle Routes"
    )


    for vehicle in routes:

        vehicle_id = (
            vehicle[
                "vehicle"
            ]
            + 1
        )

        zone = (
            vehicle[
                "assigned_zone"
            ]
        )

        route = (
            vehicle[
                "route"
            ]
        )


        st.markdown(
            f"### Vehicle "
            f"{vehicle_id} — "
            f"{zone}"
        )


        route_data = []

        route_text = []


        for stop in route:

            if (
                stop[
                    "order_id"
                ]
                == "Restaurant"
            ):

                location = (
                    "Restaurant"
                )

                deadline_text = (
                    "-"
                )

            else:

                location = (
                    f"Order "
                    f"{stop['order_id']}"
                )

                deadline_text = (
                    f"{stop['original_deadline']} min"
                )


            route_text.append(
                location
            )


            route_data.append(
                {

                    "Location":
                        location,

                    "Zone":
                        stop[
                            "zone"
                        ],

                    "Address":
                        stop[
                            "address"
                        ],

                    "Planned Arrival":
                        stop[
                            "arrival_time"
                        ],

                    "Deadline":
                        deadline_text,

                    "Vehicle Load":
                        stop[
                            "load"
                        ]
                }
            )


        st.write(
            "**Route:** "
            +
            " → ".join(
                route_text
            )
        )


        st.dataframe(
            pd.DataFrame(
                route_data
            ),
            use_container_width=True,
            hide_index=True
        )


        route_time = (
            route[
                -1
            ][
                "arrival_time"
            ]
        )


        max_load = max(
            stop[
                "load"
            ]
            for stop
            in route
        )


        deliveries = sum(
            1
            for stop
            in route
            if stop[
                "order_id"
            ]
            != "Restaurant"
        )


        r1, r2, r3, r4 = (
            st.columns(
                4
            )
        )


        with r1:

            st.metric(
                "Zone",
                zone
            )


        with r2:

            st.metric(
                "Orders Delivered",
                deliveries
            )


        with r3:

            st.metric(
                "Route Time",
                f"{route_time} min"
            )


        with r4:

            st.metric(
                "Maximum Load",
                max_load
            )


        st.divider()


# ===================================================
# BASELINE VS OPTIMISED EVALUATION
# ===================================================

if (
    st.session_state.evaluation_result
    is not None
):

    evaluation = (
        st.session_state.evaluation_result
    )


    baseline = (
        evaluation[
            "baseline"
        ]
    )


    optimized = (
        evaluation[
            "optimized"
        ]
    )


    st.subheader(
        "Baseline vs Optimised Evaluation"
    )


    baseline_time = float(
        baseline[
            "total_driving_time_min"
        ]
    )


    optimized_time = float(
        optimized[
            "total_driving_time_min"
        ]
    )


    baseline_distance = float(
        baseline[
            "total_driving_distance_km"
        ]
    )


    optimized_distance = float(
        optimized[
            "total_driving_distance_km"
        ]
    )


    e1, e2, e3, e4 = (
        st.columns(
            4
        )
    )


    with e1:

        st.metric(
            "Driving Time",
            f"{optimized_time:.0f} min"
        )

        show_comparison_text(
            baseline_time,
            optimized_time,
            lower_is_better=True
        )


    with e2:

        st.metric(
            "Driving Distance",
            f"{optimized_distance:.2f} km"
        )

        show_comparison_text(
            baseline_distance,
            optimized_distance,
            lower_is_better=True
        )


    with e3:

        st.metric(
            "Total Delay",
            f"{optimized['total_delay_min']} min"
        )


    with e4:

        st.metric(
            "Late Orders",
            optimized[
                "late_orders"
            ]
        )


    # ===================================================
    # PERFORMANCE TABLE
    # ===================================================

    comparison_df = pd.DataFrame(
        {

            "Metric": [

                "Total Driving Time (min)",
                "Total Driving Distance (km)",
                "Total Delay (min)",
                "Orders After Deadline",
                "Orders >10 min Late"

            ],

            "Baseline": [

                baseline[
                    "total_driving_time_min"
                ],

                baseline[
                    "total_driving_distance_km"
                ],

                baseline[
                    "total_delay_min"
                ],

                baseline[
                    "late_orders"
                ],

                baseline[
                    "orders_over_10_min_late"
                ]

            ],

            "Optimised": [

                optimized[
                    "total_driving_time_min"
                ],

                optimized[
                    "total_driving_distance_km"
                ],

                optimized[
                    "total_delay_min"
                ],

                optimized[
                    "late_orders"
                ],

                optimized[
                    "orders_over_10_min_late"
                ]
            ]
        }
    )


    st.markdown(
        "### Performance Comparison"
    )


    st.table(
        comparison_df
    )


    # ===================================================
    # DRIVING TIME GRAPH
    # ===================================================

    time_df = pd.DataFrame(
        {

            "Scenario": [
                "Baseline",
                "Optimised"
            ],

            "Driving Time": [
                baseline_time,
                optimized_time
            ]
        }
    )


    st.altair_chart(
        create_bar_chart(
            time_df,
            "Scenario",
            "Driving Time",
            "Driving Time Comparison",
            "Driving time (minutes)",
            0
        ),
        use_container_width=True
    )


    # ===================================================
    # DISTANCE GRAPH
    # ===================================================

    distance_df = pd.DataFrame(
        {

            "Scenario": [
                "Baseline",
                "Optimised"
            ],

            "Driving Distance": [
                baseline_distance,
                optimized_distance
            ]
        }
    )


    st.altair_chart(
        create_bar_chart(
            distance_df,
            "Scenario",
            "Driving Distance",
            "Driving Distance Comparison",
            "Driving distance (km)",
            2
        ),
        use_container_width=True
    )


    st.divider()


# ===================================================
# DELIVERY SIMULATION
# ===================================================

if (
    st.session_state.simulation_result
    is not None
):

    simulation = (
        st.session_state.simulation_result
    )


    baseline_sim = (
        simulation[
            "baseline_simulation"
        ]
    )


    optimized_sim = (
        simulation[
            "optimized_simulation"
        ]
    )


    st.subheader(
        "Delivery Simulation"
    )


    st.write(
        "The planned routes are executed "
        "using a SimPy discrete-event model "
        "with order preparation, vehicle loading "
        "and traffic-adjusted travel times."
    )


    st.info(
        "Traffic adjustment factor: "
        f"{simulation.get('traffic_factor', 1)}"
    )


    # ===================================================
    # SIMULATION METRICS
    # ===================================================

    baseline_drive = float(
        baseline_sim[
            "total_driving_time_min"
        ]
    )


    optimized_drive = float(
        optimized_sim[
            "total_driving_time_min"
        ]
    )


    baseline_completion = float(
        baseline_sim[
            "simulation_time"
        ]
    )


    optimized_completion = float(
        optimized_sim[
            "simulation_time"
        ]
    )


    s1, s2, s3, s4 = (
        st.columns(
            4
        )
    )


    with s1:

        st.metric(
            "Simulated Driving Time",
            f"{optimized_drive:.0f} min"
        )

        show_comparison_text(
            baseline_drive,
            optimized_drive,
            lower_is_better=True
        )


    with s2:

        st.metric(
            "Simulation Completion",
            f"{optimized_completion:.0f} min"
        )

        show_comparison_text(
            baseline_completion,
            optimized_completion,
            lower_is_better=True
        )


    with s3:

        st.metric(
            "Total Delay",
            f"{optimized_sim['total_delay_min']} min"
        )


    with s4:

        st.metric(
            "Late Orders",
            optimized_sim[
                "late_orders"
            ]
        )


    # ===================================================
    # SIMULATION COMPARISON
    # ===================================================

    simulation_comparison_df = pd.DataFrame(
        {

            "Metric": [

                "Total Driving Time (min)",
                "Completion Time (min)",
                "Total Delay (min)",
                "Orders After Deadline",
                "Orders >10 min Late",
                "Delivered Orders"

            ],

            "Baseline": [

                baseline_sim[
                    "total_driving_time_min"
                ],

                baseline_sim[
                    "simulation_time"
                ],

                baseline_sim[
                    "total_delay_min"
                ],

                baseline_sim[
                    "late_orders"
                ],

                baseline_sim[
                    "orders_over_10_min_late"
                ],

                baseline_sim[
                    "delivered_orders"
                ]

            ],

            "Optimised": [

                optimized_sim[
                    "total_driving_time_min"
                ],

                optimized_sim[
                    "simulation_time"
                ],

                optimized_sim[
                    "total_delay_min"
                ],

                optimized_sim[
                    "late_orders"
                ],

                optimized_sim[
                    "orders_over_10_min_late"
                ],

                optimized_sim[
                    "delivered_orders"
                ]
            ]
        }
    )


    st.markdown(
        "### Simulation Performance Comparison"
    )


    st.table(
        simulation_comparison_df
    )


    # ===================================================
    # SIMULATED DRIVING TIME GRAPH
    # ===================================================

    simulated_time_df = pd.DataFrame(
        {

            "Scenario": [
                "Baseline",
                "Optimised"
            ],

            "Driving Time": [
                baseline_drive,
                optimized_drive
            ]
        }
    )


    st.altair_chart(
        create_bar_chart(
            simulated_time_df,
            "Scenario",
            "Driving Time",
            "Simulated Driving Time",
            "Driving time (minutes)",
            0
        ),
        use_container_width=True
    )


    # ===================================================
    # COMPLETION TIME GRAPH
    # ===================================================

    completion_df = pd.DataFrame(
        {

            "Scenario": [
                "Baseline",
                "Optimised"
            ],

            "Completion Time": [
                baseline_completion,
                optimized_completion
            ]
        }
    )


    st.altair_chart(
        create_bar_chart(
            completion_df,
            "Scenario",
            "Completion Time",
            "Simulation Completion Time",
            "Time (minutes)",
            0
        ),
        use_container_width=True
    )


    # ===================================================
    # ORDER DELIVERY RESULTS
    # ===================================================

    st.markdown(
        "### Optimised Order Delivery Results"
    )


    order_rows = []


    for order in optimized_sim[
        "orders"
    ]:

        order_rows.append(
            {

                "Order ID":
                    order[
                        "order_id"
                    ],

                "Vehicle":
                    order[
                        "vehicle"
                    ],

                "Ready Time (min)":
                    order.get(
                        "ready_time"
                    ),

                "Deadline (min)":
                    order[
                        "deadline"
                    ],

                "Delivered At (min)":
                    order[
                        "delivery_time"
                    ],

                "Delay (min)":
                    order[
                        "delay"
                    ],

                "Final Status":
                    order[
                        "status"
                    ]
            }
        )


    order_result_df = (
        pd.DataFrame(
            order_rows
        )
        .sort_values(
            "Order ID"
        )
    )


    st.table(
        order_result_df
    )


    # ===================================================
    # DELAYED ORDERS
    # ===================================================

    delayed_df = (
        order_result_df[
            order_result_df[
                "Delay (min)"
            ]
            >
            0
        ]
    )


    st.markdown(
        "### Delayed Orders"
    )


    if delayed_df.empty:

        st.success(
            "No optimised deliveries exceeded "
            "their deadlines in this simulation."
        )

    else:

        st.table(
            delayed_df
        )


    # ===================================================
    # VEHICLE STATES
    # ===================================================

    st.markdown(
        "### Vehicle Final States"
    )


    vehicle_rows = []


    for vehicle in optimized_sim[
        "vehicles"
    ]:

        vehicle_rows.append(
            {

                "Vehicle":
                    vehicle[
                        "vehicle_id"
                    ],

                "Dispatch Time":
                    vehicle.get(
                        "dispatch_time"
                    ),

                "Return Time":
                    vehicle.get(
                        "return_time"
                    ),

                "Driving Time":
                    vehicle[
                        "total_driving_time"
                    ],

                "Final State":
                    vehicle[
                        "status"
                    ]
            }
        )


    st.table(
        pd.DataFrame(
            vehicle_rows
        )
    )


    # ===================================================
    # EVENT TIMELINE
    # ===================================================

    st.markdown(
        "### Simulation Event Timeline"
    )


    st.caption(
        "The timeline records cooking, order readiness, "
        "assignment, vehicle dispatch, travel, delivery "
        "and vehicle return events."
    )


    event_rows = []


    for event in optimized_sim[
        "events"
    ]:

        event_rows.append(
            {

                "Time (min)":
                    event[
                        "time"
                    ],

                "Event":
                    event[
                        "message"
                    ]
            }
        )


    event_df = pd.DataFrame(
        event_rows
    )


    st.dataframe(
        event_df,
        use_container_width=True,
        hide_index=True,
        height=550
    )


    st.divider()


# ===================================================
# FINAL SUMMARY
# ===================================================

if (
    st.session_state.evaluation_result
    is not None
):

    routes = (
        st.session_state.evaluation_result[
            "optimized_routes"
        ]
    )


    st.subheader(
        "Optimisation Summary"
    )


    total_orders = sum(
        1

        for vehicle
        in routes

        for stop
        in vehicle[
            "route"
        ]

        if stop[
            "order_id"
        ]
        != "Restaurant"
    )


    planned_time = sum(

        vehicle[
            "route"
        ][
            -1
        ][
            "arrival_time"
        ]

        for vehicle
        in routes
    )


    f1, f2, f3 = (
        st.columns(
            3
        )
    )


    with f1:

        st.metric(
            "Total Orders",
            total_orders
        )


    with f2:

        st.metric(
            "Vehicles Used",
            len(routes)
        )


    with f3:

        st.metric(
            "Planned Combined Route Time",
            f"{planned_time} min"
        )


    # ===================================================
    # RAW RESULTS
    # ===================================================

    with st.expander(
        "Raw Evaluation API Response"
    ):

        st.json(
            st.session_state.evaluation_result
        )


    if (
        st.session_state.simulation_result
        is not None
    ):

        with st.expander(
            "Raw Simulation API Response"
        ):

            st.json(
                st.session_state.simulation_result
            )


    # ===================================================
    # CLEAR RESULTS
    # ===================================================

    if st.button(
        "Clear Optimisation Results"
    ):

        st.session_state.evaluation_result = None
        st.session_state.simulation_result = None
        st.session_state.road_graph = None

        st.rerun()


st.divider()


# ===================================================
# ABOUT
# ===================================================

st.subheader(
    "About the System"
)


st.write(
    """
    The implementation combines a Vehicle Routing Problem
    with Time Windows solver, real road-network routing,
    baseline evaluation, and discrete-event delivery
    simulation.

    Google OR-Tools determines vehicle assignments and
    delivery sequences.

    OpenStreetMap and OSMnx provide the precomputed road
    network, route geometry and distance calculations.

    SimPy models order preparation, readiness, vehicle
    loading, dispatch, traffic-adjusted driving,
    customer delivery and vehicle return.
    """
)