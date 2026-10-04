import networkx as nx


# ===================================================
# HELPER FUNCTIONS
# ===================================================

def calculate_route_distance_km(
    graph,
    route
):

    total_distance_meters = 0.0

    for i in range(
        len(route) - 1
    ):

        from_node = int(
            route[i]["osm_node"]
        )

        to_node = int(
            route[i + 1]["osm_node"]
        )

        try:

            distance_meters = (
                nx.shortest_path_length(
                    graph,
                    source=from_node,
                    target=to_node,
                    weight="length"
                )
            )

            total_distance_meters += (
                distance_meters
            )

        except (
            nx.NetworkXNoPath,
            nx.NodeNotFound
        ):

            pass

    return (
        total_distance_meters
        / 1000.0
    )


def calculate_route_time_minutes(
    route
):

    if len(route) == 0:

        return 0

    return int(
        route[-1][
            "arrival_time"
        ]
    )


def calculate_delay_metrics(
    route
):

    total_delay = 0

    late_orders = 0

    very_late_orders = 0

    delivered_orders = 0


    for stop in route:

        if (
            stop["order_id"]
            == "Restaurant"
        ):

            continue


        delivered_orders += 1


        deadline = (
            stop[
                "original_deadline"
            ]
        )

        arrival = (
            stop[
                "arrival_time"
            ]
        )


        if deadline is None:

            continue


        delay = max(
            0,
            arrival - deadline
        )


        total_delay += (
            delay
        )


        if delay > 0:

            late_orders += 1


        if delay > 10:

            very_late_orders += 1


    return {

        "delivered_orders":
            delivered_orders,

        "total_delay":
            total_delay,

        "late_orders":
            late_orders,

        "very_late_orders":
            very_late_orders
    }


# ===================================================
# BUILD ORDER LOCATION LOOKUP
# ===================================================

def build_order_location_lookup(
    optimized_routes
):

    location_lookup = {}


    for vehicle in optimized_routes:

        for stop in vehicle[
            "route"
        ]:

            order_id = (
                stop[
                    "order_id"
                ]
            )


            if (
                order_id
                == "Restaurant"
            ):

                continue


            location_lookup[
                int(order_id)
            ] = {

                "latitude":
                    float(
                        stop[
                            "latitude"
                        ]
                    ),

                "longitude":
                    float(
                        stop[
                            "longitude"
                        ]
                    ),

                "osm_node":
                    int(
                        stop[
                            "osm_node"
                        ]
                    )
            }


    return location_lookup


# ===================================================
# EVALUATE ROUTES
# ===================================================

def evaluate_optimized_routes(
    graph,
    routes
):

    total_time = 0

    total_distance = 0.0

    total_delay = 0

    late_orders = 0

    very_late_orders = 0

    total_orders = 0


    for vehicle in routes:

        route = (
            vehicle[
                "route"
            ]
        )


        route_time = (
            calculate_route_time_minutes(
                route
            )
        )


        route_distance = (
            calculate_route_distance_km(
                graph,
                route
            )
        )


        delay_metrics = (
            calculate_delay_metrics(
                route
            )
        )


        total_time += (
            route_time
        )


        total_distance += (
            route_distance
        )


        total_delay += (
            delay_metrics[
                "total_delay"
            ]
        )


        late_orders += (
            delay_metrics[
                "late_orders"
            ]
        )


        very_late_orders += (
            delay_metrics[
                "very_late_orders"
            ]
        )


        total_orders += (
            delay_metrics[
                "delivered_orders"
            ]
        )


    return {

        "total_orders":
            total_orders,

        "total_driving_time_min":
            round(
                total_time,
                2
            ),

        "total_driving_distance_km":
            round(
                total_distance,
                2
            ),

        "total_delay_min":
            round(
                total_delay,
                2
            ),

        "late_orders":
            late_orders,

        "orders_over_10_min_late":
            very_late_orders
    }


# ===================================================
# CREATE BASELINE ROUTES
# ===================================================

def create_baseline_routes(
    orders_df,
    location_nodes,
    time_matrix,
    restaurant_lat,
    restaurant_lon,
    optimized_routes
):

    # ---------------------------------------------------
    # BASELINE LOGIC
    # ---------------------------------------------------
    #
    # WEST orders:
    # first four -> Vehicle 1
    # next three -> Vehicle 2
    #
    # EAST orders:
    # all four -> Vehicle 3
    #
    # Within each vehicle, orders are delivered
    # in original order-ID sequence.
    #
    # This provides a simple non-optimised baseline.
    # ---------------------------------------------------


    location_lookup = (
        build_order_location_lookup(
            optimized_routes
        )
    )


    west_orders = (
        orders_df[
            orders_df["zone"]
            == "WEST"
        ]
        .sort_values(
            "order_id"
        )
        .reset_index(
            drop=True
        )
    )


    east_orders = (
        orders_df[
            orders_df["zone"]
            == "EAST"
        ]
        .sort_values(
            "order_id"
        )
        .reset_index(
            drop=True
        )
    )


    vehicle_order_sets = [

        west_orders.iloc[
            0:4
        ],

        west_orders.iloc[
            4:7
        ],

        east_orders
    ]


    baseline_routes = []


    for vehicle_id, vehicle_orders in enumerate(
        vehicle_order_sets
    ):

        route = []


        # ---------------------------------------------------
        # START AT RESTAURANT
        # ---------------------------------------------------

        current_time = 0

        current_node = 0

        current_load = 0


        route.append(
            {

                "node":
                    0,

                "order_id":
                    "Restaurant",

                "address":
                    "Restaurant",

                "zone":
                    "DEPOT",

                "arrival_time":
                    0,

                "original_deadline":
                    None,

                "ready_time":
                    0,

                "load":
                    0,

                "latitude":
                    float(
                        restaurant_lat
                    ),

                "longitude":
                    float(
                        restaurant_lon
                    ),

                "osm_node":
                    int(
                        location_nodes[
                            0
                        ]
                    )
            }
        )


        # ---------------------------------------------------
        # DELIVER ORDERS IN ORDER-ID SEQUENCE
        # ---------------------------------------------------

        for _, order_row in (
            vehicle_orders.iterrows()
        ):

            order_id = int(
                order_row[
                    "order_id"
                ]
            )


            matching_indexes = (
                orders_df.index[
                    orders_df[
                        "order_id"
                    ]
                    == order_id
                ].tolist()
            )


            if not matching_indexes:

                continue


            dataframe_index = (
                matching_indexes[
                    0
                ]
            )


            customer_node = (
                dataframe_index
                + 1
            )


            # -----------------------------------------------
            # GET COORDINATES FROM OPTIMISED ROUTE DATA
            # -----------------------------------------------

            if (
                order_id
                not in location_lookup
            ):

                raise KeyError(
                    f"Could not find coordinates "
                    f"for Order {order_id}"
                )


            customer_location = (
                location_lookup[
                    order_id
                ]
            )


            # -----------------------------------------------
            # TRAVEL TIME
            # -----------------------------------------------

            travel_time = (
                time_matrix[
                    current_node
                ][
                    customer_node
                ]
            )


            current_time += (
                travel_time
            )


            current_load += int(
                order_row[
                    "demand"
                ]
            )


            route.append(
                {

                    "node":
                        customer_node,

                    "order_id":
                        order_id,

                    "address":
                        order_row[
                            "address"
                        ],

                    "zone":
                        order_row[
                            "zone"
                        ],

                    "arrival_time":
                        current_time,

                    "original_deadline":
                        int(
                            order_row[
                                "deadline"
                            ]
                        ),

                    "ready_time":
                        int(
                            order_row[
                                "ready_time"
                            ]
                        ),

                    "load":
                        current_load,

                    "latitude":
                        customer_location[
                            "latitude"
                        ],

                    "longitude":
                        customer_location[
                            "longitude"
                        ],

                    "osm_node":
                        customer_location[
                            "osm_node"
                        ]
                }
            )


            current_node = (
                customer_node
            )


        # ---------------------------------------------------
        # RETURN TO RESTAURANT
        # ---------------------------------------------------

        return_time = (
            time_matrix[
                current_node
            ][0]
        )


        current_time += (
            return_time
        )


        route.append(
            {

                "node":
                    0,

                "order_id":
                    "Restaurant",

                "address":
                    "Restaurant",

                "zone":
                    "DEPOT",

                "arrival_time":
                    current_time,

                "original_deadline":
                    None,

                "ready_time":
                    0,

                "load":
                    current_load,

                "latitude":
                    float(
                        restaurant_lat
                    ),

                "longitude":
                    float(
                        restaurant_lon
                    ),

                "osm_node":
                    int(
                        location_nodes[
                            0
                        ]
                    )
            }
        )


        baseline_routes.append(
            {

                "vehicle":
                    vehicle_id,

                "assigned_zone":
                    (
                        "WEST"
                        if vehicle_id
                        in [
                            0,
                            1
                        ]
                        else
                        "EAST"
                    ),

                "route":
                    route
            }
        )


    return (
        baseline_routes
    )


# ===================================================
# COMPLETE COMPARISON
# ===================================================

def compare_routes(
    graph,
    optimized_routes,
    orders_df,
    location_nodes,
    time_matrix,
    restaurant_lat,
    restaurant_lon
):

    baseline_routes = (
        create_baseline_routes(
            orders_df=
                orders_df,

            location_nodes=
                location_nodes,

            time_matrix=
                time_matrix,

            restaurant_lat=
                restaurant_lat,

            restaurant_lon=
                restaurant_lon,

            optimized_routes=
                optimized_routes
        )
    )


    baseline_metrics = (
        evaluate_optimized_routes(
            graph,
            baseline_routes
        )
    )


    optimized_metrics = (
        evaluate_optimized_routes(
            graph,
            optimized_routes
        )
    )


    return {

        "baseline_routes":
            baseline_routes,

        "optimized_routes":
            optimized_routes,

        "baseline":
            baseline_metrics,

        "optimized":
            optimized_metrics
    }