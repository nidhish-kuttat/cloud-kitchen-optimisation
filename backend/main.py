from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .solver import (
    solve_vrptw,
    solve_with_evaluation
)

from simulator.simulation import (
    run_simulation
)


# ===================================================
# FASTAPI APPLICATION
# ===================================================

app = FastAPI(
    title="Cloud Kitchen Optimisation API",

    description=(
        "Cloud kitchen delivery optimisation using "
        "Google OR-Tools, OpenStreetMap, OSMnx and SimPy"
    ),

    version="3.0.0"
)


# ===================================================
# CORS
# ===================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "*"
    ],

    allow_credentials=True,

    allow_methods=[
        "*"
    ],

    allow_headers=[
        "*"
    ]
)


# ===================================================
# HOME
# ===================================================

@app.get("/")
def home():

    return {

        "message":
            "Cloud Kitchen API is running",

        "version":
            "3.0.0",

        "components": [
            "VRPTW Optimisation",
            "OpenStreetMap Routing",
            "Baseline Evaluation",
            "SimPy Delivery Simulation"
        ]
    }


# ===================================================
# HEALTH CHECK
# ===================================================

@app.get("/health")
def health_check():

    return {

        "status":
            "healthy",

        "service":
            "Cloud Kitchen Optimisation API"
    }


# ===================================================
# OPTIMISED ROUTES ONLY
# ===================================================

@app.get("/optimize")
def optimize_routes():

    try:

        routes = (
            solve_vrptw()
        )


        if routes is None:

            return {

                "status":
                    "failed",

                "message":
                    "No valid routing solution found",

                "routes":
                    []
            }


        return {

            "status":
                "success",

            "message":
                "Delivery routes optimised successfully",

            "routes":
                routes
        }


    except Exception as error:

        return {

            "status":
                "error",

            "message":
                str(
                    error
                ),

            "routes":
                []
        }


# ===================================================
# BASELINE VS OPTIMISED EVALUATION
# ===================================================

@app.get("/evaluate")
def evaluate_routes():

    try:

        comparison = (
            solve_with_evaluation()
        )


        if comparison is None:

            return {

                "status":
                    "failed",

                "message":
                    "No valid routing solution found"
            }


        return {

            "status":
                "success",

            "message":
                "Evaluation completed successfully",

            "baseline":
                comparison[
                    "baseline"
                ],

            "optimized":
                comparison[
                    "optimized"
                ],

            "baseline_routes":
                comparison[
                    "baseline_routes"
                ],

            "optimized_routes":
                comparison[
                    "optimized_routes"
                ],

            "deadline_extension_used":
                comparison[
                    "deadline_extension_used"
                ]
        }


    except Exception as error:

        return {

            "status":
                "error",

            "message":
                str(
                    error
                )
        }


# ===================================================
# SIMULATE BASELINE + OPTIMISED ROUTES
# ===================================================

@app.get("/simulate")
def simulate_routes():

    try:

        # ---------------------------------------------------
        # FIRST CREATE BOTH ROUTING PLANS
        # ---------------------------------------------------

        comparison = (
            solve_with_evaluation()
        )


        if comparison is None:

            return {

                "status":
                    "failed",

                "message":
                    "No valid routing solution found"
            }


        baseline_routes = (
            comparison[
                "baseline_routes"
            ]
        )


        optimized_routes = (
            comparison[
                "optimized_routes"
            ]
        )


        # ---------------------------------------------------
        # RUN BASELINE THROUGH SIMPY
        # ---------------------------------------------------

        baseline_simulation = (
            run_simulation(
                baseline_routes
            )
        )


        # ---------------------------------------------------
        # RUN OPTIMISED ROUTES THROUGH SIMPY
        # ---------------------------------------------------

        optimized_simulation = (
            run_simulation(
                optimized_routes
            )
        )


        # ---------------------------------------------------
        # SIMULATION IMPROVEMENT METRICS
        # ---------------------------------------------------

        baseline_time = float(
            baseline_simulation[
                "total_driving_time_min"
            ]
        )


        optimized_time = float(
            optimized_simulation[
                "total_driving_time_min"
            ]
        )


        baseline_delay = float(
            baseline_simulation[
                "total_delay_min"
            ]
        )


        optimized_delay = float(
            optimized_simulation[
                "total_delay_min"
            ]
        )


        if baseline_time > 0:

            driving_time_improvement = (

                (
                    baseline_time
                    - optimized_time
                )

                /

                baseline_time

                * 100
            )

        else:

            driving_time_improvement = 0


        if baseline_delay > 0:

            delay_improvement = (

                (
                    baseline_delay
                    - optimized_delay
                )

                /

                baseline_delay

                * 100
            )

        else:

            delay_improvement = 0


        # ---------------------------------------------------
        # RETURN RESPONSE
        # ---------------------------------------------------

        return {

            "status":
                "success",

            "message":
                "Simulation completed successfully",

            "traffic_factor":
                1.6666,

            "deadline_extension_used":
                comparison[
                    "deadline_extension_used"
                ],

            "baseline_simulation":
                baseline_simulation,

            "optimized_simulation":
                optimized_simulation,

            "improvement": {

                "driving_time_reduction_percent":
                    round(
                        driving_time_improvement,
                        2
                    ),

                "delay_reduction_percent":
                    round(
                        delay_improvement,
                        2
                    ),

                "baseline_late_orders":
                    baseline_simulation[
                        "late_orders"
                    ],

                "optimized_late_orders":
                    optimized_simulation[
                        "late_orders"
                    ],

                "baseline_orders_over_10_min_late":
                    baseline_simulation[
                        "orders_over_10_min_late"
                    ],

                "optimized_orders_over_10_min_late":
                    optimized_simulation[
                        "orders_over_10_min_late"
                    ]
            }
        }


    except Exception as error:

        return {

            "status":
                "error",

            "message":
                str(
                    error
                )
        }


# ===================================================
# SIMULATE ONLY OPTIMISED ROUTING
# ===================================================

@app.get("/simulate/optimized")
def simulate_optimized_routes():

    try:

        comparison = (
            solve_with_evaluation()
        )


        if comparison is None:

            return {

                "status":
                    "failed",

                "message":
                    "No valid routing solution found"
            }


        optimized_routes = (
            comparison[
                "optimized_routes"
            ]
        )


        simulation = (
            run_simulation(
                optimized_routes
            )
        )


        return {

            "status":
                "success",

            "message":
                "Optimised route simulation completed",

            "traffic_factor":
                1.6666,

            "simulation":
                simulation
        }


    except Exception as error:

        return {

            "status":
                "error",

            "message":
                str(
                    error
                )
        }