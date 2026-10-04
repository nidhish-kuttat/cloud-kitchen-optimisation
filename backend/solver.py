import math
import pandas as pd
import osmnx as ox
import networkx as nx

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

from .evaluation import compare_routes


# ===================================================
# CONFIGURATION
# ===================================================

CSV_PATH = "data/orders.csv"

RESTAURANT_ADDRESS = (
    "Vile Parle West, Mumbai, Maharashtra, India"
)

NUM_VEHICLES = 3

VEHICLE_CAPACITIES = [
    4,
    3,
    4
]

TRAFFIC_FACTOR = 1.6666

LOADING_TIME_MIN = 1

LATE_PENALTY_PER_MINUTE = 1000

DEADLINE_EXTENSION_STEP = 5
MAX_DEADLINE_EXTENSION = 60

MAX_ROUTE_TIME = 300

MAX_SNAP_DISTANCE_METERS = 350


# ===================================================
# GEOCODING FALLBACKS
# ===================================================

GEOCODE_FALLBACKS = {

    "Irla, Vile Parle West, Mumbai, Maharashtra, India": [
        "Irla, Mumbai, Maharashtra, India"
    ],

    "Juhu Scheme, Mumbai, Maharashtra, India": [
        "Juhu, Mumbai, Maharashtra, India"
    ],

    "DN Nagar, Andheri West, Mumbai, Maharashtra, India": [
        "D N Nagar, Mumbai, Maharashtra, India",
        "Andheri West, Mumbai, Maharashtra, India"
    ],

    "Four Bungalows, Andheri West, Mumbai, Maharashtra, India": [
        "Four Bungalows, Mumbai, Maharashtra, India"
    ],

    "Azad Nagar, Andheri West, Mumbai, Maharashtra, India": [
        "Azad Nagar, Mumbai, Maharashtra, India"
    ],

    "Versova, Mumbai, Maharashtra, India": [
        "Versova, Andheri West, Mumbai, Maharashtra, India"
    ],

    "Lokhandwala Complex, Andheri West, Mumbai, Maharashtra, India": [
        "Lokhandwala, Andheri West, Mumbai, Maharashtra, India",
        "Lokhandwala Complex, Mumbai, Maharashtra, India"
    ],

    "Sher E Punjab Colony, Andheri East, Mumbai, Maharashtra, India": [
        "Sher-E-Punjab Colony, Mumbai, Maharashtra, India",
        "Sher E Punjab, Mumbai, Maharashtra, India"
    ],

    "Mahakali Caves Road, Andheri East, Mumbai, Maharashtra, India": [
        "Mahakali, Andheri East, Mumbai, Maharashtra, India"
    ],

    "MIDC, Andheri East, Mumbai, Maharashtra, India": [
        "Andheri MIDC, Mumbai, Maharashtra, India",
        "MIDC Andheri, Mumbai, Maharashtra, India"
    ],

    "SEEPZ, Andheri East, Mumbai, Maharashtra, India": [
        "SEEPZ, Mumbai, Maharashtra, India"
    ]
}


# ===================================================
# OSMNX SETTINGS
# ===================================================

ox.settings.use_cache = True
ox.settings.log_console = False


# ===================================================
# LOAD ORDERS
# ===================================================

def load_orders():

    df = pd.read_csv(
        CSV_PATH
    )

    required_columns = [
        "order_id",
        "address",
        "zone",
        "deadline",
        "demand",
        "ready_time"
    ]

    for column in required_columns:

        if column not in df.columns:

            raise ValueError(
                f"Missing required column: {column}"
            )


    df["zone"] = (
        df["zone"]
        .astype(str)
        .str.upper()
        .str.strip()
    )


    invalid_zones = df[
        ~df["zone"].isin(
            [
                "WEST",
                "EAST"
            ]
        )
    ]


    if len(
        invalid_zones
    ) > 0:

        raise ValueError(
            "Every order zone must be WEST or EAST."
        )


    west_demand = (
        df[
            df["zone"]
            == "WEST"
        ]["demand"].sum()
    )


    east_demand = (
        df[
            df["zone"]
            == "EAST"
        ]["demand"].sum()
    )


    west_capacity = (
        VEHICLE_CAPACITIES[0]
        +
        VEHICLE_CAPACITIES[1]
    )


    east_capacity = (
        VEHICLE_CAPACITIES[2]
    )


    if (
        west_demand
        >
        west_capacity
    ):

        raise ValueError(
            "WEST demand exceeds WEST vehicle capacity."
        )


    if (
        east_demand
        >
        east_capacity
    ):

        raise ValueError(
            "EAST demand exceeds EAST vehicle capacity."
        )


    return df


# ===================================================
# GEOCODING
# ===================================================

def geocode_address(
    address
):

    candidates = [
        address
    ]


    if (
        address
        in GEOCODE_FALLBACKS
    ):

        candidates.extend(
            GEOCODE_FALLBACKS[
                address
            ]
        )


    last_error = None


    for query in candidates:

        try:

            lat, lon = (
                ox.geocode(
                    query
                )
            )

            print(
                f"  ✓ {query}"
            )

            return (
                float(lat),
                float(lon)
            )


        except Exception as error:

            last_error = error

            print(
                f"  ✗ Could not geocode: {query}"
            )


    raise RuntimeError(
        "\nCould not geocode location:\n"
        f"{address}\n\n"
        f"Last error: {last_error}"
    )


# ===================================================
# HAVERSINE DISTANCE
# ===================================================

def haversine_distance_meters(
    lat1,
    lon1,
    lat2,
    lon2
):

    radius = 6371000


    lat1 = math.radians(
        lat1
    )

    lat2 = math.radians(
        lat2
    )


    dlat = (
        lat2
        - lat1
    )

    dlon = math.radians(
        lon2
        - lon1
    )


    a = (
        math.sin(
            dlat / 2
        ) ** 2
        +
        math.cos(
            lat1
        )
        *
        math.cos(
            lat2
        )
        *
        math.sin(
            dlon / 2
        ) ** 2
    )


    c = (
        2
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(
                1 - a
            )
        )
    )


    return (
        radius
        * c
    )


# ===================================================
# GEOCODE LOCATIONS
# ===================================================

def geocode_locations(
    orders_df
):

    print(
        "\n===================================="
    )

    print(
        "GEOCODING LOCATIONS"
    )

    print(
        "===================================="
    )


    restaurant_lat, restaurant_lon = (
        geocode_address(
            RESTAURANT_ADDRESS
        )
    )


    print(
        f"\nRestaurant: "
        f"{restaurant_lat:.6f}, "
        f"{restaurant_lon:.6f}"
    )


    geocoded_orders = (
        orders_df.copy()
    )


    customer_lats = []
    customer_lons = []


    all_latitudes = [
        restaurant_lat
    ]

    all_longitudes = [
        restaurant_lon
    ]


    for _, row in (
        geocoded_orders.iterrows()
    ):

        order_id = int(
            row[
                "order_id"
            ]
        )


        print(
            f"\nOrder {order_id}:"
        )


        lat, lon = (
            geocode_address(
                row[
                    "address"
                ]
            )
        )


        customer_lats.append(
            lat
        )

        customer_lons.append(
            lon
        )


        all_latitudes.append(
            lat
        )

        all_longitudes.append(
            lon
        )


    geocoded_orders[
        "latitude"
    ] = customer_lats


    geocoded_orders[
        "longitude"
    ] = customer_lons


    return (
        geocoded_orders,
        restaurant_lat,
        restaurant_lon,
        all_latitudes,
        all_longitudes
    )


# ===================================================
# CREATE ROAD NETWORK
# ===================================================

def create_road_network(
    latitudes,
    longitudes
):

    center_lat = (
        sum(latitudes)
        /
        len(latitudes)
    )


    center_lon = (
        sum(longitudes)
        /
        len(longitudes)
    )


    max_lat_diff = max(
        abs(
            lat
            - center_lat
        )
        for lat
        in latitudes
    )


    max_lon_diff = max(
        abs(
            lon
            - center_lon
        )
        for lon
        in longitudes
    )


    approximate_radius = max(
        max_lat_diff
        * 111000,

        max_lon_diff
        * 105000
    )


    graph_radius = max(
        int(
            approximate_radius
            + 2000
        ),
        4500
    )


    print(
        "\n===================================="
    )

    print(
        "LOADING OPENSTREETMAP ROAD NETWORK"
    )

    print(
        "===================================="
    )


    print(
        f"Graph radius: "
        f"{graph_radius} m"
    )


    graph = (
        ox.graph.graph_from_point(
            (
                center_lat,
                center_lon
            ),
            dist=
                graph_radius,
            network_type=
                "drive",
            simplify=
                True
        )
    )


    graph = (
        ox.routing.add_edge_speeds(
            graph
        )
    )


    graph = (
        ox.routing.add_edge_travel_times(
            graph
        )
    )


    print(
        "Road network ready."
    )


    return graph


# ===================================================
# SNAP LOCATIONS TO ROAD NETWORK
# ===================================================

def get_location_nodes(
    graph,
    orders_df,
    restaurant_lat,
    restaurant_lon
):

    print(
        "\n===================================="
    )

    print(
        "VALIDATING ROAD LOCATIONS"
    )

    print(
        "===================================="
    )


    location_nodes = []


    restaurant_node = (
        ox.distance.nearest_nodes(
            graph,
            X=
                restaurant_lon,
            Y=
                restaurant_lat
        )
    )


    location_nodes.append(
        restaurant_node
    )


    for _, row in (
        orders_df.iterrows()
    ):

        order_id = int(
            row[
                "order_id"
            ]
        )


        latitude = float(
            row[
                "latitude"
            ]
        )


        longitude = float(
            row[
                "longitude"
            ]
        )


        nearest_node = (
            ox.distance.nearest_nodes(
                graph,
                X=
                    longitude,
                Y=
                    latitude
            )
        )


        node_data = (
            graph.nodes[
                nearest_node
            ]
        )


        snap_distance = (
            haversine_distance_meters(
                latitude,
                longitude,
                node_data[
                    "y"
                ],
                node_data[
                    "x"
                ]
            )
        )


        print(
            f"Order "
            f"{order_id}: "
            f"{row['zone']} | "
            f"snap = "
            f"{snap_distance:.1f} m"
        )


        if (
            snap_distance
            >
            MAX_SNAP_DISTANCE_METERS
        ):

            raise ValueError(
                "\nSuspicious delivery location.\n"
                f"Order: {order_id}\n"
                f"Address: {row['address']}\n"
                f"Road snap distance: "
                f"{snap_distance:.1f} m"
            )


        location_nodes.append(
            nearest_node
        )


    return location_nodes


# ===================================================
# RAW OSM TIME MATRIX
# ===================================================

def build_raw_time_matrix(
    graph,
    location_nodes
):

    print(
        "\nCalculating OSM road travel times..."
    )


    size = len(
        location_nodes
    )


    matrix = []


    for i in range(
        size
    ):

        row = []


        for j in range(
            size
        ):

            if i == j:

                row.append(
                    0
                )

                continue


            try:

                seconds = (
                    nx.shortest_path_length(
                        graph,
                        source=
                            location_nodes[
                                i
                            ],
                        target=
                            location_nodes[
                                j
                            ],
                        weight=
                            "travel_time"
                    )
                )


                minutes = max(
                    1,
                    round(
                        seconds
                        /
                        60
                    )
                )


                row.append(
                    minutes
                )


            except nx.NetworkXNoPath:

                row.append(
                    999
                )


        matrix.append(
            row
        )


    print(
        "Raw OSM travel-time matrix complete."
    )


    return matrix


# ===================================================
# APPLY TRAFFIC FACTOR
# ===================================================

def apply_traffic_factor(
    raw_matrix
):

    adjusted_matrix = []


    for i, row in enumerate(
        raw_matrix
    ):

        adjusted_row = []


        for j, value in enumerate(
            row
        ):

            if i == j:

                adjusted_row.append(
                    0
                )


            elif value >= 999:

                adjusted_row.append(
                    999
                )


            else:

                adjusted_row.append(
                    max(
                        1,
                        round(
                            value
                            *
                            TRAFFIC_FACTOR
                        )
                    )
                )


        adjusted_matrix.append(
            adjusted_row
        )


    print(
        f"Traffic factor applied: "
        f"{TRAFFIC_FACTOR}"
    )


    return adjusted_matrix


# ===================================================
# ATTEMPT VRPTW SOLUTION
# ===================================================

def attempt_solution(
    data
):

    manager = (
        pywrapcp.RoutingIndexManager(
            len(
                data[
                    "time_matrix"
                ]
            ),
            NUM_VEHICLES,
            0
        )
    )


    routing = (
        pywrapcp.RoutingModel(
            manager
        )
    )


    solver = (
        routing.solver()
    )


    # ===================================================
    # TRAVEL-TIME CALLBACK
    # ===================================================

    def time_callback(
        from_index,
        to_index
    ):

        from_node = (
            manager.IndexToNode(
                from_index
            )
        )


        to_node = (
            manager.IndexToNode(
                to_index
            )
        )


        travel_time = (
            data[
                "time_matrix"
            ][
                from_node
            ][
                to_node
            ]
        )


        # Loading takes place before the vehicle
        # leaves the restaurant.
        if (
            from_node == 0
            and
            to_node != 0
        ):

            travel_time += (
                LOADING_TIME_MIN
            )


        return travel_time


    transit_callback_index = (
        routing.RegisterTransitCallback(
            time_callback
        )
    )


    routing.SetArcCostEvaluatorOfAllVehicles(
        transit_callback_index
    )


    # ===================================================
    # TIME DIMENSION
    # ===================================================

    routing.AddDimension(
        transit_callback_index,
        0,
        MAX_ROUTE_TIME,
        False,
        "Time"
    )


    time_dimension = (
        routing.GetDimensionOrDie(
            "Time"
        )
    )


    # ===================================================
    # CUSTOMER WINDOWS + LATENESS PENALTIES
    # ===================================================

    for customer_node in range(
        1,
        len(
            data[
                "time_matrix"
            ]
        )
    ):

        routing_index = (
            manager.NodeToIndex(
                customer_node
            )
        )


        order_row = (
            data[
                "orders_df"
            ].iloc[
                customer_node
                - 1
            ]
        )


        ready_time = int(
            order_row[
                "ready_time"
            ]
        )


        original_deadline = int(
            order_row[
                "deadline"
            ]
        )


        extended_deadline = int(
            original_deadline
            +
            data[
                "deadline_extension"
            ]
        )


        # Hard constraint:
        # order cannot be delivered before it is ready,
        # and cannot exceed the current extended deadline.
        time_dimension.CumulVar(
            routing_index
        ).SetRange(
            ready_time,
            extended_deadline
        )


        # Soft objective:
        # every minute after the ORIGINAL deadline
        # is strongly penalised.
        time_dimension.SetCumulVarSoftUpperBound(
            routing_index,
            original_deadline,
            LATE_PENALTY_PER_MINUTE
        )


    # ===================================================
    # VEHICLE START TIMES
    # ===================================================

    for vehicle_id in range(
        NUM_VEHICLES
    ):

        start_index = (
            routing.Start(
                vehicle_id
            )
        )


        time_dimension.CumulVar(
            start_index
        ).SetRange(
            0,
            MAX_ROUTE_TIME
        )


    # ===================================================
    # CAPACITY
    # ===================================================

    def demand_callback(
        from_index
    ):

        node = (
            manager.IndexToNode(
                from_index
            )
        )


        return (
            data[
                "demands"
            ][
                node
            ]
        )


    demand_callback_index = (
        routing.RegisterUnaryTransitCallback(
            demand_callback
        )
    )


    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        VEHICLE_CAPACITIES,
        True,
        "Capacity"
    )


    # ===================================================
    # ZONE RESTRICTIONS
    # ===================================================

    for customer_node in range(
        1,
        len(
            data[
                "time_matrix"
            ]
        )
    ):

        order_row = (
            data[
                "orders_df"
            ].iloc[
                customer_node
                - 1
            ]
        )


        zone = (
            order_row[
                "zone"
            ]
        )


        routing_index = (
            manager.NodeToIndex(
                customer_node
            )
        )


        vehicle_var = (
            routing.VehicleVar(
                routing_index
            )
        )


        if zone == "WEST":

            solver.Add(
                vehicle_var
                != 2
            )


        elif zone == "EAST":

            solver.Add(
                vehicle_var
                == 2
            )


    # ===================================================
    # BATCH READY-TIME CONSTRAINTS
    # ===================================================

    for customer_node in range(
        1,
        len(
            data[
                "time_matrix"
            ]
        )
    ):

        order_row = (
            data[
                "orders_df"
            ].iloc[
                customer_node
                - 1
            ]
        )


        ready_time = int(
            order_row[
                "ready_time"
            ]
        )


        routing_index = (
            manager.NodeToIndex(
                customer_node
            )
        )


        vehicle_var = (
            routing.VehicleVar(
                routing_index
            )
        )


        for vehicle_id in range(
            NUM_VEHICLES
        ):

            assigned_to_vehicle = (
                solver.IsEqualCstVar(
                    vehicle_var,
                    vehicle_id
                )
            )


            start_index = (
                routing.Start(
                    vehicle_id
                )
            )


            start_time = (
                time_dimension.CumulVar(
                    start_index
                )
            )


            solver.Add(
                start_time
                >=
                ready_time
                *
                assigned_to_vehicle
            )


    # ===================================================
    # SEARCH PARAMETERS
    # ===================================================

    search_parameters = (
        pywrapcp.DefaultRoutingSearchParameters()
    )


    search_parameters.first_solution_strategy = (
        routing_enums_pb2
        .FirstSolutionStrategy
        .PATH_CHEAPEST_ARC
    )


    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2
        .LocalSearchMetaheuristic
        .GUIDED_LOCAL_SEARCH
    )


    search_parameters.time_limit.seconds = (
        8
    )


    solution = (
        routing.SolveWithParameters(
            search_parameters
        )
    )


    if not solution:

        return None


    # ===================================================
    # EXTRACT SOLUTION
    # ===================================================

    routes = []


    for vehicle_id in range(
        NUM_VEHICLES
    ):

        index = (
            routing.Start(
                vehicle_id
            )
        )


        vehicle_route = []

        route_load = 0


        while not routing.IsEnd(
            index
        ):

            node = (
                manager.IndexToNode(
                    index
                )
            )


            arrival = (
                solution.Value(
                    time_dimension.CumulVar(
                        index
                    )
                )
            )


            route_load += (
                data[
                    "demands"
                ][
                    node
                ]
            )


            if node == 0:

                order_id = (
                    "Restaurant"
                )

                address = (
                    RESTAURANT_ADDRESS
                )

                zone = (
                    "DEPOT"
                )

                deadline = (
                    None
                )

                ready_time = (
                    None
                )

                latitude = (
                    data[
                        "restaurant_lat"
                    ]
                )

                longitude = (
                    data[
                        "restaurant_lon"
                    ]
                )


            else:

                row = (
                    data[
                        "orders_df"
                    ].iloc[
                        node
                        - 1
                    ]
                )


                order_id = int(
                    row[
                        "order_id"
                    ]
                )


                address = (
                    row[
                        "address"
                    ]
                )


                zone = (
                    row[
                        "zone"
                    ]
                )


                deadline = int(
                    row[
                        "deadline"
                    ]
                )


                ready_time = int(
                    row[
                        "ready_time"
                    ]
                )


                latitude = float(
                    row[
                        "latitude"
                    ]
                )


                longitude = float(
                    row[
                        "longitude"
                    ]
                )


            vehicle_route.append(
                {

                    "node":
                        node,

                    "order_id":
                        order_id,

                    "address":
                        address,

                    "zone":
                        zone,

                    "arrival_time":
                        arrival,

                    "original_deadline":
                        deadline,

                    "ready_time":
                        ready_time,

                    "load":
                        route_load,

                    "latitude":
                        latitude,

                    "longitude":
                        longitude,

                    "osm_node":
                        int(
                            data[
                                "location_nodes"
                            ][
                                node
                            ]
                        )
                }
            )


            index = (
                solution.Value(
                    routing.NextVar(
                        index
                    )
                )
            )


        return_arrival = (
            solution.Value(
                time_dimension.CumulVar(
                    index
                )
            )
        )


        vehicle_route.append(
            {

                "node":
                    0,

                "order_id":
                    "Restaurant",

                "address":
                    RESTAURANT_ADDRESS,

                "zone":
                    "DEPOT",

                "arrival_time":
                    return_arrival,

                "original_deadline":
                    None,

                "ready_time":
                    None,

                "load":
                    route_load,

                "latitude":
                    data[
                        "restaurant_lat"
                    ],

                "longitude":
                    data[
                        "restaurant_lon"
                    ],

                "osm_node":
                    int(
                        data[
                            "location_nodes"
                        ][0]
                    )
            }
        )


        assigned_zone = (
            "WEST"
            if vehicle_id
            in [
                0,
                1
            ]
            else
            "EAST"
        )


        routes.append(
            {

                "vehicle":
                    vehicle_id,

                "assigned_zone":
                    assigned_zone,

                "vehicle_capacity":
                    VEHICLE_CAPACITIES[
                        vehicle_id
                    ],

                "route":
                    vehicle_route
            }
        )


    return routes


# ===================================================
# PREPARE ENVIRONMENT
# ===================================================

def prepare_environment():

    orders_df = (
        load_orders()
    )


    (
        orders_df,
        restaurant_lat,
        restaurant_lon,
        latitudes,
        longitudes
    ) = geocode_locations(
        orders_df
    )


    graph = (
        create_road_network(
            latitudes,
            longitudes
        )
    )


    location_nodes = (
        get_location_nodes(
            graph,
            orders_df,
            restaurant_lat,
            restaurant_lon
        )
    )


    raw_time_matrix = (
        build_raw_time_matrix(
            graph,
            location_nodes
        )
    )


    adjusted_time_matrix = (
        apply_traffic_factor(
            raw_time_matrix
        )
    )


    return {

        "orders_df":
            orders_df,

        "restaurant_lat":
            restaurant_lat,

        "restaurant_lon":
            restaurant_lon,

        "graph":
            graph,

        "location_nodes":
            location_nodes,

        "raw_time_matrix":
            raw_time_matrix,

        "time_matrix":
            adjusted_time_matrix
    }


# ===================================================
# BUILD SOLVER DATA
# ===================================================

def build_solver_data(
    environment,
    extension
):

    orders_df = (
        environment[
            "orders_df"
        ]
    )


    time_windows = [
        (
            0,
            MAX_ROUTE_TIME
        )
    ]


    for _, row in (
        orders_df.iterrows()
    ):

        time_windows.append(
            (
                int(
                    row[
                        "ready_time"
                    ]
                ),

                int(
                    row[
                        "deadline"
                    ]
                )
                +
                extension
            )
        )


    demands = [
        0
    ] + [
        int(
            demand
        )
        for demand
        in orders_df[
            "demand"
        ]
    ]


    return {

        "time_matrix":
            environment[
                "time_matrix"
            ],

        "time_windows":
            time_windows,

        "demands":
            demands,

        "orders_df":
            orders_df,

        "location_nodes":
            environment[
                "location_nodes"
            ],

        "restaurant_lat":
            environment[
                "restaurant_lat"
            ],

        "restaurant_lon":
            environment[
                "restaurant_lon"
            ],

        "deadline_extension":
            extension
    }


# ===================================================
# FIND VALID SOLUTION
# ===================================================

def find_solution(
    environment
):

    extension = 0


    while (
        extension
        <=
        MAX_DEADLINE_EXTENSION
    ):

        print(
            "\n===================================="
        )

        print(
            f"TRYING DEADLINE EXTENSION: "
            f"{extension} MINUTES"
        )

        print(
            "===================================="
        )


        data = (
            build_solver_data(
                environment,
                extension
            )
        )


        routes = (
            attempt_solution(
                data
            )
        )


        if routes is not None:

            print(
                "\nVALID SOLUTION FOUND"
            )

            print(
                f"Deadline extension used: "
                f"{extension} minutes"
            )


            return (
                routes,
                extension
            )


        extension += (
            DEADLINE_EXTENSION_STEP
        )


    return (
        None,
        None
    )


# ===================================================
# SOLVE ROUTES ONLY
# ===================================================

def solve_vrptw():

    environment = (
        prepare_environment()
    )


    routes, _ = (
        find_solution(
            environment
        )
    )


    return routes


# ===================================================
# SOLVE + EVALUATE
# ===================================================

def solve_with_evaluation():

    environment = (
        prepare_environment()
    )


    optimized_routes, extension = (
        find_solution(
            environment
        )
    )


    if (
        optimized_routes
        is None
    ):

        return None


    comparison = (
        compare_routes(

            environment[
                "graph"
            ],

            optimized_routes,

            environment[
                "orders_df"
            ],

            environment[
                "location_nodes"
            ],

            environment[
                "time_matrix"
            ],

            environment[
                "restaurant_lat"
            ],

            environment[
                "restaurant_lon"
            ]
        )
    )


    comparison[
        "deadline_extension_used"
    ] = extension


    comparison[
        "traffic_factor"
    ] = (
        TRAFFIC_FACTOR
    )


    return comparison


# ===================================================
# PRINT ROUTES
# ===================================================

def print_routes(
    routes
):

    print(
        "\n========================================"
    )

    print(
        "OPTIMISED DELIVERY ROUTES"
    )

    print(
        "========================================"
    )


    for vehicle in routes:

        print(
            f"\nVehicle "
            f"{vehicle['vehicle'] + 1} "
            f"| Zone: "
            f"{vehicle['assigned_zone']}"
        )


        print(
            "-" * 80
        )


        for stop in vehicle[
            "route"
        ]:

            print(
                f"Order: "
                f"{stop['order_id']} | "

                f"Arrival: "
                f"{stop['arrival_time']} min | "

                f"Ready: "
                f"{stop['ready_time']} | "

                f"Deadline: "
                f"{stop['original_deadline']} | "

                f"Load: "
                f"{stop['load']}"
            )


# ===================================================
# PRINT EVALUATION
# ===================================================

def print_evaluation(
    comparison
):

    baseline = (
        comparison[
            "baseline"
        ]
    )


    optimized = (
        comparison[
            "optimized"
        ]
    )


    print(
        "\n========================================"
    )

    print(
        "BASELINE VS OPTIMISED"
    )

    print(
        "========================================"
    )


    print(
        "\nTOTAL DRIVING TIME"
    )

    print(
        f"Baseline:  "
        f"{baseline['total_driving_time_min']} min"
    )

    print(
        f"Optimised: "
        f"{optimized['total_driving_time_min']} min"
    )


    print(
        "\nTOTAL DRIVING DISTANCE"
    )

    print(
        f"Baseline:  "
        f"{baseline['total_driving_distance_km']} km"
    )

    print(
        f"Optimised: "
        f"{optimized['total_driving_distance_km']} km"
    )


    print(
        "\nTOTAL DELAY"
    )

    print(
        f"Baseline:  "
        f"{baseline['total_delay_min']} min"
    )

    print(
        f"Optimised: "
        f"{optimized['total_delay_min']} min"
    )


    print(
        "\nORDERS AFTER DEADLINE"
    )

    print(
        f"Baseline:  "
        f"{baseline['late_orders']}"
    )

    print(
        f"Optimised: "
        f"{optimized['late_orders']}"
    )


    print(
        "\nORDERS >10 MIN LATE"
    )

    print(
        f"Baseline:  "
        f"{baseline['orders_over_10_min_late']}"
    )

    print(
        f"Optimised: "
        f"{optimized['orders_over_10_min_late']}"
    )


    print(
        "\nDeadline extension used:"
    )

    print(
        f"{comparison['deadline_extension_used']} minutes"
    )


# ===================================================
# DIRECT RUN
# ===================================================

if __name__ == "__main__":

    comparison = (
        solve_with_evaluation()
    )


    if comparison is None:

        print(
            "\nNo valid routing solution found."
        )

    else:

        print_routes(
            comparison[
                "optimized_routes"
            ]
        )


        print_evaluation(
            comparison
        )