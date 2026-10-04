import osmnx as ox

CENTER_POINT = (19.1136, 72.8697)  # around Vile Parle / Andheri
DIST_METERS = 8000

print("Downloading road network...")

graph = ox.graph_from_point(
    CENTER_POINT,
    dist=DIST_METERS,
    network_type="drive",
    simplify=True
)

graph = ox.routing.add_edge_speeds(graph)
graph = ox.routing.add_edge_travel_times(graph)

ox.save_graphml(
    graph,
    filepath="data/mumbai_road_graph.graphml"
)

print("Saved: data/mumbai_road_graph.graphml")