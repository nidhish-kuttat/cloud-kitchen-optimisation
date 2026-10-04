import pandas as pd
import simpy


# ===================================================
# CONFIGURATION
# ===================================================

TRAFFIC_FACTOR = 1.6666

ORDERS_FILE = "data/orders.csv"

LOADING_TIME_MIN = 1


# ===================================================
# LOAD ORDER TIMING DATA
# ===================================================

def load_order_timing_data():

    df = pd.read_csv(
        ORDERS_FILE
    )

    timing_data = {}

    for _, row in df.iterrows():

        order_id = int(
            row["order_id"]
        )

        timing_data[order_id] = {

            "deadline":
                float(
                    row["deadline"]
                ),

            "ready_time":
                float(
                    row["ready_time"]
                )
        }

    return timing_data


# ===================================================
# ORDER MODEL
# ===================================================

class Order:

    def __init__(
        self,
        order_id,
        deadline,
        ready_time
    ):

        self.order_id = order_id

        self.deadline = deadline

        self.ready_time = ready_time

        self.status = "COOKING"

        self.assigned_vehicle = None

        self.delivery_time = None

        self.delay = 0


# ===================================================
# VEHICLE MODEL
# ===================================================

class Vehicle:

    def __init__(
        self,
        vehicle_id
    ):

        self.vehicle_id = vehicle_id

        self.status = "READY"

        self.current_order = None

        self.total_driving_time = 0

        self.dispatch_time = None

        self.return_time = None


# ===================================================
# EVENT LOGGER
# ===================================================

class EventLogger:

    def __init__(self):

        self.events = []


    def log(
        self,
        time,
        message
    ):

        event = {

            "time":
                round(
                    float(time),
                    2
                ),

            "message":
                message
        }

        self.events.append(
            event
        )

        print(
            f"[{float(time):6.2f} min] "
            f"{message}"
        )


# ===================================================
# ORDER COOKING / READY PROCESS
# ===================================================

def order_ready_process(
    env,
    order,
    logger
):

    logger.log(
        env.now,
        (
            f"Order {order.order_id} "
            f"is COOKING"
        )
    )


    if (
        order.ready_time
        >
        env.now
    ):

        yield env.timeout(
            order.ready_time
            - env.now
        )


    order.status = "READY"


    logger.log(
        env.now,
        (
            f"Order {order.order_id} "
            f"is READY"
        )
    )


# ===================================================
# VEHICLE DELIVERY PROCESS
# ===================================================

def vehicle_delivery_process(
    env,
    vehicle,
    assigned_route,
    logger
):

    customer_stops = [

        stop

        for stop
        in assigned_route

        if stop["order_id"]
        != "Restaurant"
    ]


    if not customer_stops:

        return


    # ===================================================
    # SOLVER PLANNED START TIME
    # ===================================================

    planned_start_time = float(
        assigned_route[0][
            "arrival_time"
        ]
    )


    # ===================================================
    # WAIT UNTIL THE ASSIGNED BATCH IS READY
    # ===================================================

    batch_ready_time = max(

        stop[
            "order_object"
        ].ready_time

        for stop
        in customer_stops
    )


    actual_start_time = max(
        planned_start_time,
        batch_ready_time
    )


    if (
        actual_start_time
        >
        env.now
    ):

        vehicle.status = (
            "WAITING_FOR_ORDERS"
        )


        logger.log(
            env.now,
            (
                f"Vehicle "
                f"{vehicle.vehicle_id} "
                f"WAITING for batch orders"
            )
        )


        yield env.timeout(
            actual_start_time
            - env.now
        )


    # ===================================================
    # ASSIGN ORDERS
    # ===================================================

    for stop in customer_stops:

        order = (
            stop[
                "order_object"
            ]
        )

        order.status = "ASSIGNED"

        order.assigned_vehicle = (
            vehicle.vehicle_id
        )


        logger.log(
            env.now,
            (
                f"Order "
                f"{order.order_id} "
                f"ASSIGNED to "
                f"Vehicle "
                f"{vehicle.vehicle_id}"
            )
        )


    # ===================================================
    # LOADING
    # ===================================================

    vehicle.status = "LOADING"


    logger.log(
        env.now,
        (
            f"Vehicle "
            f"{vehicle.vehicle_id} "
            f"is LOADING"
        )
    )


    yield env.timeout(
        LOADING_TIME_MIN
    )


    # ===================================================
    # DISPATCH
    # ===================================================

    vehicle.status = "DISPATCHED"

    vehicle.dispatch_time = float(
        env.now
    )


    for stop in customer_stops:

        stop[
            "order_object"
        ].status = "DISPATCHED"


    logger.log(
        env.now,
        (
            f"Vehicle "
            f"{vehicle.vehicle_id} "
            f"DISPATCHED"
        )
    )


    # ===================================================
    # DELIVERY LOOP
    # ===================================================

    previous_planned_time = (
        planned_start_time
    )


    first_customer = True


    for stop in customer_stops:

        order = (
            stop[
                "order_object"
            ]
        )


        vehicle.status = (
            "EN_ROUTE"
        )

        vehicle.current_order = (
            order.order_id
        )

        order.status = (
            "EN_ROUTE"
        )


        planned_arrival = float(
            stop[
                "arrival_time"
            ]
        )


        segment_time = (
            planned_arrival
            -
            previous_planned_time
        )


        # Solver adds loading time to the
        # restaurant -> first customer arc.
        # SimPy already simulated loading separately,
        # so remove that one minute here.
        if first_customer:

            segment_time -= (
                LOADING_TIME_MIN
            )

            first_customer = False


        segment_time = max(
            1,
            segment_time
        )


        logger.log(
            env.now,
            (
                f"Vehicle "
                f"{vehicle.vehicle_id} "
                f"travelling to "
                f"Order "
                f"{order.order_id} "
                f"(ETA "
                f"{segment_time:.0f} min)"
            )
        )


        yield env.timeout(
            segment_time
        )


        vehicle.total_driving_time += (
            segment_time
        )


        order.status = (
            "DELIVERED"
        )


        order.delivery_time = float(
            env.now
        )


        order.delay = max(
            0,
            (
                order.delivery_time
                -
                order.deadline
            )
        )


        logger.log(
            env.now,
            (
                f"Order "
                f"{order.order_id} "
                f"DELIVERED by "
                f"Vehicle "
                f"{vehicle.vehicle_id} "
                f"(deadline "
                f"{order.deadline:.0f} min, "
                f"delay "
                f"{order.delay:.2f} min)"
            )
        )


        previous_planned_time = (
            planned_arrival
        )


    # ===================================================
    # RETURN TO RESTAURANT
    # ===================================================

    vehicle.status = (
        "RETURNING"
    )

    vehicle.current_order = None


    logger.log(
        env.now,
        (
            f"Vehicle "
            f"{vehicle.vehicle_id} "
            f"RETURNING to restaurant"
        )
    )


    planned_return_time = float(
        assigned_route[
            -1
        ][
            "arrival_time"
        ]
    )


    last_customer_time = float(
        customer_stops[
            -1
        ][
            "arrival_time"
        ]
    )


    return_leg_time = max(
        1,
        (
            planned_return_time
            -
            last_customer_time
        )
    )


    yield env.timeout(
        return_leg_time
    )


    vehicle.total_driving_time += (
        return_leg_time
    )


    vehicle.status = (
        "READY"
    )


    vehicle.return_time = float(
        env.now
    )


    logger.log(
        env.now,
        (
            f"Vehicle "
            f"{vehicle.vehicle_id} "
            f"RETURNED and is READY"
        )
    )


# ===================================================
# ATTACH ORDER OBJECTS
# ===================================================

def attach_order_objects(
    routes,
    order_objects
):

    order_lookup = {

        order.order_id:
            order

        for order
        in order_objects
    }


    simulation_routes = []


    for vehicle in routes:

        new_route = []


        for stop in vehicle[
            "route"
        ]:

            new_stop = (
                stop.copy()
            )


            if (
                stop[
                    "order_id"
                ]
                == "Restaurant"
            ):

                new_stop[
                    "order_object"
                ] = None

            else:

                new_stop[
                    "order_object"
                ] = (
                    order_lookup[
                        int(
                            stop[
                                "order_id"
                            ]
                        )
                    ]
                )


            new_route.append(
                new_stop
            )


        simulation_routes.append(
            {

                "vehicle":
                    vehicle[
                        "vehicle"
                    ],

                "assigned_zone":
                    vehicle.get(
                        "assigned_zone"
                    ),

                "route":
                    new_route
            }
        )


    return simulation_routes


# ===================================================
# RUN SIMULATION
# ===================================================

def run_simulation(
    routes
):

    timing_data = (
        load_order_timing_data()
    )


    env = (
        simpy.Environment()
    )


    logger = (
        EventLogger()
    )


    # ===================================================
    # BUILD ORDER OBJECTS
    # ===================================================

    order_objects = []

    seen_orders = set()


    for vehicle in routes:

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


            order_id = int(
                order_id
            )


            if (
                order_id
                in seen_orders
            ):

                continue


            seen_orders.add(
                order_id
            )


            order_objects.append(
                Order(

                    order_id=
                        order_id,

                    deadline=
                        timing_data[
                            order_id
                        ][
                            "deadline"
                        ],

                    ready_time=
                        timing_data[
                            order_id
                        ][
                            "ready_time"
                        ]
                )
            )


    # ===================================================
    # VEHICLES
    # ===================================================

    vehicle_objects = [

        Vehicle(
            vehicle_id=
                vehicle[
                    "vehicle"
                ]
                + 1
        )

        for vehicle
        in routes
    ]


    # ===================================================
    # ATTACH OBJECTS
    # ===================================================

    simulation_routes = (
        attach_order_objects(
            routes,
            order_objects
        )
    )


    # ===================================================
    # START ORDER PROCESSES
    # ===================================================

    for order in order_objects:

        env.process(
            order_ready_process(
                env,
                order,
                logger
            )
        )


    # ===================================================
    # START VEHICLES
    # ===================================================

    for vehicle_data in (
        simulation_routes
    ):

        vehicle_index = (
            vehicle_data[
                "vehicle"
            ]
        )


        env.process(
            vehicle_delivery_process(
                env,

                vehicle_objects[
                    vehicle_index
                ],

                vehicle_data[
                    "route"
                ],

                logger
            )
        )


    # ===================================================
    # RUN SIMULATION
    # ===================================================

    env.run()


    # ===================================================
    # METRICS
    # ===================================================

    total_delay = sum(
        order.delay
        for order
        in order_objects
    )


    late_orders = sum(
        1
        for order
        in order_objects
        if order.delay
        > 0
    )


    over_10_min_late = sum(
        1
        for order
        in order_objects
        if order.delay
        > 10
    )


    total_driving_time = sum(
        vehicle.total_driving_time
        for vehicle
        in vehicle_objects
    )


    delivered_orders = sum(
        1
        for order
        in order_objects
        if order.status
        == "DELIVERED"
    )


    return {

        "simulation_time":
            round(
                float(
                    env.now
                ),
                2
            ),

        "traffic_factor":
            TRAFFIC_FACTOR,

        "total_orders":
            len(
                order_objects
            ),

        "delivered_orders":
            delivered_orders,

        "total_driving_time_min":
            round(
                total_driving_time,
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
            over_10_min_late,

        "orders": [

            {

                "order_id":
                    order.order_id,

                "status":
                    order.status,

                "ready_time":
                    order.ready_time,

                "deadline":
                    order.deadline,

                "delivery_time":
                    order.delivery_time,

                "delay":
                    round(
                        order.delay,
                        2
                    ),

                "vehicle":
                    order.assigned_vehicle
            }

            for order
            in order_objects
        ],

        "vehicles": [

            {

                "vehicle_id":
                    vehicle.vehicle_id,

                "status":
                    vehicle.status,

                "dispatch_time":
                    vehicle.dispatch_time,

                "return_time":
                    vehicle.return_time,

                "total_driving_time":
                    round(
                        vehicle.total_driving_time,
                        2
                    )
            }

            for vehicle
            in vehicle_objects
        ],

        "events":
            logger.events
    }


# ===================================================
# DIRECT RUN
# ===================================================

if __name__ == "__main__":

    print(
        "Run the simulation through "
        "the FastAPI /simulate endpoint."
    )