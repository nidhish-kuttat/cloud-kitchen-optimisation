import math
import os

import networkx as nx
import osmnx as ox
import pandas as pd

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

from .evaluation import compare_routes


# =========================================================
# CONFIGURATION
# =========================================================

CSV_PATH = "data/orders.csv"

GRAPH_PATH = "data/mumbai_road_graph.graphml"

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


# =========================================================
# FALLBACK COORDINATES
# =========================================================

FALLBACK_COORDINATES = {

    "Vile Parle West, Mumbai, Maharashtra, India":
        (19.10391, 72.84030),

    "Irla, Vile Parle West, Mumbai, Maharashtra, India":
        (19.1085, 72.8372),

    "Juhu Scheme, Mumbai, Maharashtra, India":
        (19.1123, 72.8261),

    "DN Nagar, Andheri West, Mumbai, Maharashtra, India":
        (19.1255, 72.8310),

    "Four Bungalows, Andheri West, Mumbai, Maharashtra, India":
        (19.1306, 72.8249),

    "Azad Nagar, Andheri West, Mumbai, Maharashtra, India":
        (19.1279, 72.8373),

    "Versova, Mumbai, Maharashtra, India":
        (19.1357, 72.8146),

    "Lokhandwala Complex, Andheri West, Mumbai, Maharashtra, India":
        (19.1438, 72.8240),

    "Sher E Punjab Colony, Andheri East, Mumbai, Maharashtra, India":
        (19.1260, 72.8662),

    "Mahakali Caves Road, Andheri East, Mumbai, Maharashtra, India":
        (19.1197, 72.8709),

    "MIDC, Andheri East, Mumbai, Maharashtra, India":
        (19.1171, 72.8797),

    "SEEPZ, Mumbai, Maharashtra, India":
        (19.1267, 72.8756)
}


# =========================================================
# LOAD ORDERS
# =========================================================

def load_orders():

    if not os.path.exists(CSV_PATH):

        raise FileNotFoundError(
            f"Orders file not found: {CSV_PATH}"
        )

    orders_df = pd.read_csv(
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

    missing_columns = [
        column
        for column
        in required_columns
        if column not in orders_df.columns
    ]

    if missing_columns:

        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )


    valid_zones = {
        "WEST",
        "EAST"
    }

    invalid_zones = (
        set(
            orders_df["zone"]
            .astype(str)
            .str.upper()
        )
        - valid_zones
    )

    if invalid_zones:

        raise ValueError(
            "Invalid zones found: "
            + ", ".join(
                sorted(
                    invalid_zones
                )
            )
        )


    orders_df["zone"] = (
        orders_df["zone"]
        .astype(str)
        .str.upper()
    )


    total_capacity = sum(
        VEHICLE_CAPACITIES
    )

    total_demand = int(
        orders_df["demand"].sum()
    )

    if total_demand > total_capacity:

        raise ValueError(
            f"Total demand {total_demand} exceeds "
            f"vehicle capacity {total_capacity}"
        )


    west_demand = int(
        orders_df[
            orders_df["zone"] == "WEST"
        ]["demand"].sum()
    )

    east_demand = int(
        orders_df[
            orders_df["zone"] == "EAST"
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


    if west_demand > west_capacity:

        raise ValueError(
            f"WEST demand {west_demand} exceeds "
            f"WEST vehicle capacity {west_capacity}"
        )


    if east_demand > east_capacity:

        raise ValueError(
            f"EAST demand {east_demand} exceeds "
            f"EAST vehicle capacity {east_capacity}"
        )


    return orders_df


# =========================================================
# GEOCODING
# =========================================================

def geocode_address(address):

    if address in FALLBACK_COORDINATES:

        return FALLBACK_COORDINATES[address]


    try:

        latitude, longitude = (
            ox.geocoder.geocode(
                address
            )
        )

        return (
            float(latitude),
            float(longitude)
        )


    except Exception as error:

        raise RuntimeError(
            f"Could not geocode address: {address}. "
            f"Error: {error}"
        )


def geocode_locations(orders_df):

    locations = []


    restaurant_lat, restaurant_lon = (
        geocode_address(
            RESTAURANT_ADDRESS
        )
    )


    locations.append(
        {
            "order_id":
                "Restaurant",

            "address":
                RESTAURANT_ADDRESS,

            "zone":
                "DEPOT",

            "deadline":
                MAX_ROUTE_TIME,

            "ready_time":
                0,

            "demand":
                0,

            "latitude":
                restaurant_lat,

            "longitude":
                restaurant_lon
        }
    )


    for _, row in orders_df.iterrows():

        latitude, longitude = (
            geocode_address(
                row["address"]
            )
        )


        locations.append(
            {
                "order_id":
                    int(
                        row["order_id"]
                    ),

                "address":
                    row["address"],

                "zone":
                    row["zone"],

                "deadline":
                    int(
                        row["deadline"]
                    ),

                "ready_time":
                    int(
                        row["ready_time"]
                    ),

                "demand":
                    int(
                        row["demand"]
                    ),

                "latitude":
                    latitude,

                "longitude":
                    longitude
            }
        )


    return locations


# =========================================================
# DISTANCE
# =========================================================

def haversine_distance_meters(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371000

    phi1 = math.radians(
        lat1
    )

    phi2 = math.radians(
        lat2
    )

    delta_phi = math.radians(
        lat2 - lat1
    )

    delta_lambda = math.radians(
        lon2 - lon1
    )


    a = (
        math.sin(
            delta_phi / 2
        ) ** 2
        +
        math.cos(phi1)
        *
        math.cos(phi2)
        *
        math.sin(
            delta_lambda / 2
        ) ** 2
    )


    c = (
        2
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


    return (
        earth_radius
        *
        c
    )


# =========================================================
# ROAD NETWORK
# =========================================================

def create_road_network(*args, **kwargs):

    if not os.path.exists(
        GRAPH_PATH
    ):

        raise FileNotFoundError(
            f"Precomputed road graph not found: "
            f"{GRAPH_PATH}. "
            f"Run prepare_graph.py locally first."
        )


    graph = ox.load_graphml(
        GRAPH_PATH
    )


    return graph


# =========================================================
# SNAP LOCATIONS TO OSM
# =========================================================

def get_location_nodes(
    graph,
    locations
):

    location_nodes = []


    for location in locations:

        nearest_node = (
            ox.distance.nearest_nodes(
                graph,
                X=
                    location[
                        "longitude"
                    ],
                Y=
                    location[
                        "latitude"
                    ]
            )
        )


        node_data = (
            graph.nodes[
                nearest_node
            ]
        )


        node_lat = float(
            node_data["y"]
        )

        node_lon = float(
            node_data["x"]
        )


        snap_distance = (
            haversine_distance_meters(
                location[
                    "latitude"
                ],

                location[
                    "longitude"
                ],

                node_lat,

                node_lon
            )
        )


        if (
            snap_distance
            >
            MAX_SNAP_DISTANCE_METERS
        ):

            raise ValueError(
                f"Location '{location['address']}' "
                f"is {snap_distance:.0f} m from "
                f"nearest drivable road. "
                f"Maximum allowed is "
                f"{MAX_SNAP_DISTANCE_METERS} m."
            )


        location_nodes.append(
            int(
                nearest_node
            )
        )


    return location_nodes


# =========================================================
# RAW ROAD TIME MATRIX
# =========================================================

def build_raw_time_matrix(
    graph,
    location_nodes
):

    matrix = []


    for source_node in location_nodes:

        row = []


        for target_node in location_nodes:

            if source_node == target_node:

                row.append(
                    0
                )

                continue


            try:

                seconds = (
                    nx.shortest_path_length(
                        graph,
                        source=
                            source_node,
                        target=
                            target_node,
                        weight=
                            "travel_time"
                    )
                )


                minutes = max(
                    1,
                    int(
                        round(
                            seconds / 60
                        )
                    )
                )


                row.append(
                    minutes
                )


            except nx.NetworkXNoPath:

                row.append(
                    MAX_ROUTE_TIME
                )


        matrix.append(
            row
        )


    return matrix


# =========================================================
# TRAFFIC-ADJUSTED TIME MATRIX
# =========================================================

def apply_traffic_factor(
    raw_time_matrix
):

    traffic_matrix = []


    for row in raw_time_matrix:

        traffic_row = []


        for value in row:

            if value == 0:

                traffic_row.append(
                    0
                )

            else:

                adjusted = int(
                    round(
                        value
                        *
                        TRAFFIC_FACTOR
                    )
                )


                traffic_row.append(
                    max(
                        1,
                        adjusted
                    )
                )


        traffic_matrix.append(
            traffic_row
        )


    return traffic_matrix


# =========================================================
# OR-TOOLS SOLVER ATTEMPT
# =========================================================

def attempt_solution(
    locations,
    location_nodes,
    time_matrix,
    deadline_extension
):

    manager = (
        pywrapcp.RoutingIndexManager(
            len(locations),
            NUM_VEHICLES,
            0
        )
    )


    routing = (
        pywrapcp.RoutingModel(
            manager
        )
    )


    # -----------------------------------------------------
    # TIME CALLBACK
    # -----------------------------------------------------

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
            time_matrix[
                from_node
            ][
                to_node
            ]
        )


        if (
            from_node == 0
            and
            to_node != 0
        ):

            travel_time += (
                LOADING_TIME_MIN
            )


        return int(
            travel_time
        )


    transit_callback_index = (
        routing.RegisterTransitCallback(
            time_callback
        )
    )


    routing.SetArcCostEvaluatorOfAllVehicles(
        transit_callback_index
    )


    # -----------------------------------------------------
    # TIME DIMENSION
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CUSTOMER TIME WINDOWS
    # -----------------------------------------------------

    for location_index in range(
        1,
        len(locations)
    ):

        routing_index = (
            manager.NodeToIndex(
                location_index
            )
        )


        ready_time = int(
            locations[
                location_index
            ][
                "ready_time"
            ]
        )


        original_deadline = int(
            locations[
                location_index
            ][
                "deadline"
            ]
        )


        hard_deadline = (
            original_deadline
            +
            deadline_extension
        )


        time_dimension.CumulVar(
            routing_index
        ).SetRange(
            ready_time,
            hard_deadline
        )


        time_dimension.SetCumulVarSoftUpperBound(
            routing_index,
            original_deadline,
            LATE_PENALTY_PER_MINUTE
        )


    # -----------------------------------------------------
    # VEHICLE START WINDOWS
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # CAPACITY CALLBACK
    # -----------------------------------------------------

    def demand_callback(
        from_index
    ):

        node = (
            manager.IndexToNode(
                from_index
            )
        )


        return int(
            locations[
                node
            ][
                "demand"
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


    capacity_dimension = (
        routing.GetDimensionOrDie(
            "Capacity"
        )
    )


    # -----------------------------------------------------
    # ZONE RESTRICTIONS
    # -----------------------------------------------------

    solver = routing.solver()


    for location_index in range(
        1,
        len(locations)
    ):

        routing_index = (
            manager.NodeToIndex(
                location_index
            )
        )


        vehicle_var = (
            routing.VehicleVar(
                routing_index
            )
        )


        zone = (
            locations[
                location_index
            ][
                "zone"
            ]
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


    # -----------------------------------------------------
    # BATCH READY CONSTRAINTS
    # -----------------------------------------------------

    for location_index in range(
        1,
        len(locations)
    ):

        routing_index = (
            manager.NodeToIndex(
                location_index
            )
        )


        ready_time = int(
            locations[
                location_index
            ][
                "ready_time"
            ]
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


            vehicle_start_time = (
                time_dimension.CumulVar(
                    start_index
                )
            )


            solver.Add(
                vehicle_start_time
                >=
                ready_time
                *
                assigned_to_vehicle
            )


    # -----------------------------------------------------
    # SEARCH PARAMETERS
    # -----------------------------------------------------

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


    search_parameters.time_limit.seconds = 8


    # -----------------------------------------------------
    # SOLVE
    # -----------------------------------------------------

    solution = routing.SolveWithParameters(
        search_parameters
    )


    if solution is None:

        return None


    # -----------------------------------------------------
    # EXTRACT ROUTES
    # -----------------------------------------------------

    routes = []


    for vehicle_id in range(
        NUM_VEHICLES
    ):

        index = routing.Start(
            vehicle_id
        )


        vehicle_route = []


        assigned_zone = (
            "EAST"
            if vehicle_id == 2
            else "WEST"
        )


        while not routing.IsEnd(
            index
        ):

            node = (
                manager.IndexToNode(
                    index
                )
            )


            location = (
                locations[
                    node
                ]
            )


            arrival_time = (
                solution.Value(
                    time_dimension.CumulVar(
                        index
                    )
                )
            )


            vehicle_load = (
                solution.Value(
                    capacity_dimension.CumulVar(
                        index
                    )
                )
            )


            vehicle_route.append(
                {

                    "order_id":
                        location[
                            "order_id"
                        ],

                    "address":
                        location[
                            "address"
                        ],

                    "zone":
                        location[
                            "zone"
                        ],

                    "arrival_time":
                        int(
                            arrival_time
                        ),

                    "original_deadline":
                        int(
                            location[
                                "deadline"
                            ]
                        ),

                    "ready_time":
                        int(
                            location[
                                "ready_time"
                            ]
                        ),

                    "load":
                        int(
                            vehicle_load
                        ),

                    "latitude":
                        float(
                            location[
                                "latitude"
                            ]
                        ),

                    "longitude":
                        float(
                            location[
                                "longitude"
                            ]
                        ),

                    "osm_node":
                        int(
                            location_nodes[
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


        end_node = (
            manager.IndexToNode(
                index
            )
        )


        end_location = (
            locations[
                end_node
            ]
        )


        end_arrival_time = (
            solution.Value(
                time_dimension.CumulVar(
                    index
                )
            )
        )


        end_load = (
            solution.Value(
                capacity_dimension.CumulVar(
                    index
                )
            )
        )


        vehicle_route.append(
            {

                "order_id":
                    end_location[
                        "order_id"
                    ],

                "address":
                    end_location[
                        "address"
                    ],

                "zone":
                    end_location[
                        "zone"
                    ],

                "arrival_time":
                    int(
                        end_arrival_time
                    ),

                "original_deadline":
                    int(
                        end_location[
                            "deadline"
                        ]
                    ),

                "ready_time":
                    int(
                        end_location[
                            "ready_time"
                        ]
                    ),

                "load":
                    int(
                        end_load
                    ),

                "latitude":
                    float(
                        end_location[
                            "latitude"
                        ]
                    ),

                "longitude":
                    float(
                        end_location[
                            "longitude"
                        ]
                    ),

                "osm_node":
                    int(
                        location_nodes[
                            end_node
                        ]
                    )
            }
        )


        routes.append(
            {

                "vehicle":
                    vehicle_id,

                "assigned_zone":
                    assigned_zone,

                "route":
                    vehicle_route
            }
        )


    return routes


# =========================================================
# PREPARE ENVIRONMENT
# =========================================================

def prepare_environment():

    orders_df = (
        load_orders()
    )


    locations = (
        geocode_locations(
            orders_df
        )
    )


    graph = (
        create_road_network()
    )


    location_nodes = (
        get_location_nodes(
            graph,
            locations
        )
    )


    raw_time_matrix = (
        build_raw_time_matrix(
            graph,
            location_nodes
        )
    )


    traffic_time_matrix = (
        apply_traffic_factor(
            raw_time_matrix
        )
    )


    return {

        "orders_df":
            orders_df,

        "locations":
            locations,

        "graph":
            graph,

        "location_nodes":
            location_nodes,

        "raw_time_matrix":
            raw_time_matrix,

        "time_matrix":
            traffic_time_matrix
    }


# =========================================================
# FIND FEASIBLE SOLUTION
# =========================================================

def find_solution(
    locations,
    location_nodes,
    time_matrix
):

    for deadline_extension in range(
        0,
        MAX_DEADLINE_EXTENSION
        +
        DEADLINE_EXTENSION_STEP,
        DEADLINE_EXTENSION_STEP
    ):

        routes = (
            attempt_solution(
                locations,
                location_nodes,
                time_matrix,
                deadline_extension
            )
        )


        if routes is not None:

            return (
                routes,
                deadline_extension
            )


    return (
        None,
        None
    )


# =========================================================
# BUILD SOLVER DATA
# =========================================================

def build_solver_data():

    environment = (
        prepare_environment()
    )


    routes, deadline_extension = (
        find_solution(
            environment[
                "locations"
            ],

            environment[
                "location_nodes"
            ],

            environment[
                "time_matrix"
            ]
        )
    )


    if routes is None:

        raise RuntimeError(
            "No valid routing solution found."
        )


    return {

        **environment,

        "routes":
            routes,

        "deadline_extension":
            deadline_extension
    }


# =========================================================
# PUBLIC SOLVER FUNCTION
# =========================================================

def solve_vrptw():

    solver_data = (
        build_solver_data()
    )


    return solver_data[
        "routes"
    ]


# =========================================================
# SOLVER + EVALUATION
# =========================================================

def solve_with_evaluation():

    solver_data = (
        build_solver_data()
    )


    graph = (
        solver_data[
            "graph"
        ]
    )


    routes = (
        solver_data[
            "routes"
        ]
    )


    orders_df = (
        solver_data[
            "orders_df"
        ]
    )


    location_nodes = (
        solver_data[
            "location_nodes"
        ]
    )


    time_matrix = (
        solver_data[
            "time_matrix"
        ]
    )


    locations = (
        solver_data[
            "locations"
        ]
    )


    restaurant_lat = float(
        locations[0][
            "latitude"
        ]
    )


    restaurant_lon = float(
        locations[0][
            "longitude"
        ]
    )


    comparison = (
        compare_routes(
            graph=
                graph,

            optimized_routes=
                routes,

            orders_df=
                orders_df,

            location_nodes=
                location_nodes,

            time_matrix=
                time_matrix,

            restaurant_lat=
                restaurant_lat,

            restaurant_lon=
                restaurant_lon
        )
    )


    comparison[
        "optimized_routes"
    ] = routes


    comparison[
        "deadline_extension_used"
    ] = (
        solver_data[
            "deadline_extension"
        ]
    )


    comparison[
        "traffic_factor"
    ] = (
        TRAFFIC_FACTOR
    )


    return comparison


# =========================================================
# PRINT ROUTES
# =========================================================

def print_routes(
    routes
):

    print(
        "\nOPTIMISED ROUTES\n"
    )


    for vehicle in routes:

        print(
            f"Vehicle "
            f"{vehicle['vehicle'] + 1} "
            f"({vehicle['assigned_zone']})"
        )


        for stop in vehicle[
            "route"
        ]:

            print(
                f"  {stop['order_id']} "
                f"| arrival={stop['arrival_time']} "
                f"| deadline={stop['original_deadline']} "
                f"| ready={stop['ready_time']} "
                f"| load={stop['load']}"
            )


        print()


# =========================================================
# PRINT EVALUATION
# =========================================================

def print_evaluation(
    comparison
):

    print(
        "\nBASELINE VS OPTIMISED\n"
    )


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
        "Baseline:"
    )

    for key, value in baseline.items():

        print(
            f"  {key}: {value}"
        )


    print(
        "\nOptimised:"
    )

    for key, value in optimized.items():

        print(
            f"  {key}: {value}"
        )


    print(
        "\nDeadline extension used:",
        comparison[
            "deadline_extension_used"
        ]
    )


    print(
        "Traffic factor:",
        comparison[
            "traffic_factor"
        ]
    )


# =========================================================
# DIRECT EXECUTION
# =========================================================

if __name__ == "__main__":

    try:

        result = (
            solve_with_evaluation()
        )


        print_routes(
            result[
                "optimized_routes"
            ]
        )


        print_evaluation(
            result
        )


    except Exception as error:

        print(
            f"\nERROR: {error}\n"
        )