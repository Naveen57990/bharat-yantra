from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Point, mapping
from .paths import PROJECT_ROOT, RUNS_ROOT


GRAPH_PATH = PROJECT_ROOT / "data" / "raw" / "osm" / "mumbai_fs_osm.gpkg"
FACILITIES_PATH = PROJECT_ROOT / "data" / "raw" / "osm" / "emergency_facilities.geojson"
WARD_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "fs_ward_boundary.geojson"
OSM_MANIFEST_PATH = PROJECT_ROOT / "data" / "raw" / "osm" / "osm_manifest.json"
RUNS_PATH = RUNS_ROOT / "accessibility"
ANALYSIS_CRS = "EPSG:32643"


class AccessMetrics(BaseModel):
    road_nodes_evaluated: int
    road_nodes_with_route: int
    road_nodes_without_route: int
    route_coverage_percent: float
    mean_network_distance_m: float | None
    median_network_distance_m: float | None
    p90_network_distance_m: float | None
    mapped_facility_features: int
    unique_snapped_road_nodes: int
    median_facility_snap_distance_m: float | None
    maximum_facility_snap_distance_m: float | None


class AccessSummary(BaseModel):
    source: str
    source_retrieved_at: str
    source_checksum: str
    boundary_status: str
    road_graph_nodes_buffered: int
    road_graph_directed_edges_buffered: int
    road_edges_intersecting_ward: int
    road_nodes_inside_ward: int
    weakly_connected_components_buffered: int
    strongly_connected_components_buffered: int
    ward_nodes_in_largest_weak_component: int
    mapped_health_facilities_inside_ward: int
    health_facility_geometry_types: dict[str, int]
    baseline: AccessMetrics
    metric_definition: str
    validation_status: str
    limitations: list[str]


class ClosureOption(BaseModel):
    road_name: str
    directed_edges_intersecting_ward: int
    highway_classes: list[str]


class AccessRunRequest(BaseModel):
    road_name: str | None = None
    road_names: list[str] = Field(default_factory=list, max_length=8)


class FacilityRoutesRequest(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    radius_m: int = Field(default=5000, ge=500, le=10000)
    closed_road_names: list[str] = Field(default_factory=list, max_length=8)


class FacilityRoutesResult(BaseModel):
    selected_point: dict[str, float]
    snapped_point: dict[str, float]
    snap_distance_m: float
    radius_m: int
    facilities_found: int
    nearest_facility_osm_id: str
    facilities: list[dict[str, Any]]
    routes_geojson: dict[str, Any]
    facilities_geojson: dict[str, Any]
    applied_closures: list[str] = Field(default_factory=list)
    closed_edges_geojson: dict[str, Any] = Field(default_factory=lambda: {"type": "FeatureCollection", "features": []})
    source_retrieved_at: str
    assumptions: list[str]


class AccessRunResult(BaseModel):
    run_id: str
    created_at: str
    scenario_label: str
    facility_type: str
    road_name: str
    road_names: list[str] = Field(default_factory=list)
    closed_directed_edges: int
    closed_edge_ids: list[str]
    baseline: AccessMetrics
    scenario: AccessMetrics
    change: dict[str, int | float]
    closed_edges_geojson: dict[str, Any]
    newly_unreachable_nodes_geojson: dict[str, Any]
    source_retrieved_at: str
    source_checksum: str
    assumptions: list[str]
    limitations: list[str]


def _node_id(value: Any) -> int | str:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _road_names(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        values = parsed if isinstance(parsed, list) else [value]
    else:
        values = []
    return list(dict.fromkeys(item.strip() for item in values if isinstance(item, str) and item.strip()))


@lru_cache(maxsize=1)
def _load_network() -> dict[str, Any]:
    for path in (GRAPH_PATH, FACILITIES_PATH, WARD_PATH, OSM_MANIFEST_PATH):
        if not path.is_file():
            raise HTTPException(status_code=503, detail=f"Required local source is unavailable: {path.name}.")

    try:
        node_frame = gpd.read_file(GRAPH_PATH, layer="drive_nodes").to_crs(ANALYSIS_CRS)
        edge_frame = gpd.read_file(GRAPH_PATH, layer="drive_edges").to_crs(ANALYSIS_CRS)
        ward_frame = gpd.read_file(WARD_PATH).to_crs(ANALYSIS_CRS)
        facility_frame = gpd.read_file(FACILITIES_PATH).to_crs(ANALYSIS_CRS)
        manifest = json.loads(OSM_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Local road/facility sources could not be loaded.") from error

    if ward_frame.empty or ward_frame.geometry.isna().all():
        raise HTTPException(status_code=503, detail="The provisional ward geometry is unavailable.")
    ward = ward_frame.geometry.union_all()
    graph = nx.MultiDiGraph()
    for row in node_frame.itertuples():
        if row.geometry is None or row.geometry.is_empty:
            continue
        graph.add_node(_node_id(row.osmid), geometry=row.geometry)

    valid_edges: list[dict[str, Any]] = []
    for row in edge_frame.itertuples():
        u, v, key = _node_id(row.u), _node_id(row.v), _node_id(row.key)
        if u not in graph or v not in graph or row.geometry is None or row.geometry.is_empty:
            continue
        length = float(row.length)
        if not math.isfinite(length) or length <= 0:
            continue
        road_names = _road_names(row.name)
        road_name = road_names[0] if road_names else None
        highway = row.highway if isinstance(row.highway, str) else "unknown"
        graph.add_edge(u, v, key=key, length_m=length, road_names=road_names, highway=highway, geometry=row.geometry)
        valid_edges.append({"u": u, "v": v, "key": key, "road_names": road_names, "highway": highway, "geometry": row.geometry})

    health_types = {"hospital", "clinic", "doctors"}
    health = facility_frame[
        facility_frame.geometry.notna()
        & facility_frame.geometry.within(ward)
        & facility_frame.get("amenity", "").fillna("").isin(health_types)
    ]
    # Some OSM facilities are mapped as building polygons. A representative
    # point provides a reproducible network snap without claiming an entrance.
    facility_points = [geometry if geometry.geom_type == "Point" else geometry.representative_point() for geometry in health.geometry]
    nodes = list(graph.nodes)
    node_geometries = [graph.nodes[node]["geometry"] for node in nodes]
    facility_nodes: set[int | str] = set()
    snap_distances: list[float] = []
    facility_records: list[dict[str, Any]] = []
    facility_route_records: list[dict[str, Any]] = []
    for (_, facility), point in zip(health.iterrows(), facility_points, strict=True):
        nearest_index = min(range(len(nodes)), key=lambda index: node_geometries[index].distance(point))
        snapped_node = nodes[nearest_index]
        facility_nodes.add(snapped_node)
        snap_distance = float(node_geometries[nearest_index].distance(point))
        snap_distances.append(snap_distance)
        def safe_text(value: Any) -> str | None:
            return value.strip()[:180] if isinstance(value, str) and value.strip() else None
        record = {
            "osm_element": safe_text(facility.get("element")),
            "osm_id": str(facility.get("id")) if facility.get("id") is not None else None,
            "name": safe_text(facility.get("name")) or safe_text(facility.get("name:en")),
            "amenity": safe_text(facility.get("amenity")),
            "healthcare": safe_text(facility.get("healthcare")),
            "geometry_type": str(facility.geometry.geom_type),
            "nearest_road_node": str(snapped_node),
            "snap_distance_m": round(snap_distance, 1),
        }
        facility_records.append(record)
        facility_route_records.append({"road_node": snapped_node, "point": point, "record": record})

    nodes_inside = [node for node in graph.nodes if ward.covers(graph.nodes[node]["geometry"])]
    edges_inside = [edge for edge in valid_edges if edge["geometry"].intersects(ward)]
    weak_components = list(nx.weakly_connected_components(graph))
    largest_weak_component = max(weak_components, key=len) if weak_components else set()
    strongly_connected_components = nx.number_strongly_connected_components(graph)
    named_road_edges: dict[str, list[dict[str, Any]]] = {}
    for edge in edges_inside:
        for road_name in edge["road_names"]:
            named_road_edges.setdefault(road_name, []).append(edge)

    try:
        manifest_checksum = manifest["output_sha256"]["mumbai_fs_osm.gpkg"]
        retrieved_at = manifest["retrieved_at_utc"]
    except (KeyError, TypeError) as error:
        raise HTTPException(status_code=503, detail="OSM source manifest is missing its version/checksum.") from error

    return {
        "graph": graph,
        "ward": ward,
        "nodes_inside": nodes_inside,
        "weak_component_count": len(weak_components),
        "strong_component_count": strongly_connected_components,
        "ward_nodes_in_largest_weak_component": sum(node in largest_weak_component for node in nodes_inside),
        "edges_inside": edges_inside,
        "named_road_edges": named_road_edges,
        "facility_nodes": facility_nodes,
        "health_facilities": facility_records,
        "facility_route_records": facility_route_records,
        "facility_count": len(health),
        "facility_geometry_types": {str(key): int(value) for key, value in health.geometry.geom_type.value_counts().items()},
        "snap_distances": snap_distances,
        "manifest": manifest,
        "source_checksum": manifest_checksum,
        "retrieved_at": retrieved_at,
    }


def _distance_map(graph: nx.MultiDiGraph, targets: set[int | str]) -> dict[int | str, float]:
    if not targets:
        return {}
    return nx.multi_source_dijkstra_path_length(
        graph.reverse(copy=False), targets, weight="length_m"
    )


def _metrics(network: dict[str, Any], distances: dict[int | str, float]) -> AccessMetrics:
    nodes = network["nodes_inside"]
    lengths = sorted(float(distances[node]) for node in nodes if node in distances)
    evaluated = len(nodes)
    reachable = len(lengths)

    def percentile(fraction: float) -> float | None:
        if not lengths:
            return None
        return lengths[round((len(lengths) - 1) * fraction)]

    snap_distances = network["snap_distances"]
    return AccessMetrics(
        road_nodes_evaluated=evaluated,
        road_nodes_with_route=reachable,
        road_nodes_without_route=evaluated - reachable,
        route_coverage_percent=round(100 * reachable / evaluated, 2) if evaluated else 0.0,
        mean_network_distance_m=round(sum(lengths) / reachable, 1) if reachable else None,
        median_network_distance_m=round(percentile(0.5), 1) if reachable else None,
        p90_network_distance_m=round(percentile(0.9), 1) if reachable else None,
        mapped_facility_features=network["facility_count"],
        unique_snapped_road_nodes=len(network["facility_nodes"]),
        median_facility_snap_distance_m=round(sorted(snap_distances)[len(snap_distances) // 2], 1) if snap_distances else None,
        maximum_facility_snap_distance_m=round(max(snap_distances), 1) if snap_distances else None,
    )


def _baseline(network: dict[str, Any]) -> tuple[dict[int | str, float], AccessMetrics]:
    distance_map = _distance_map(network["graph"], network["facility_nodes"])
    return distance_map, _metrics(network, distance_map)


def get_summary() -> AccessSummary:
    network = _load_network()
    _, baseline = _baseline(network)
    return AccessSummary(
        source="OpenStreetMap drive graph and mapped health facilities via OSMnx/Overpass",
        source_retrieved_at=network["retrieved_at"],
        source_checksum=network["source_checksum"],
        boundary_status="F/S Ward is a provisional local candidate; boundary terms and vintage are unresolved.",
        road_graph_nodes_buffered=network["graph"].number_of_nodes(),
        road_graph_directed_edges_buffered=network["graph"].number_of_edges(),
        road_edges_intersecting_ward=len(network["edges_inside"]),
        road_nodes_inside_ward=len(network["nodes_inside"]),
        weakly_connected_components_buffered=network["weak_component_count"],
        strongly_connected_components_buffered=network["strong_component_count"],
        ward_nodes_in_largest_weak_component=network["ward_nodes_in_largest_weak_component"],
        mapped_health_facilities_inside_ward=network["facility_count"],
        health_facility_geometry_types=network["facility_geometry_types"],
        baseline=baseline,
        metric_definition=(
            "For each OSM road-graph node inside the provisional ward, shortest directed road-network distance "
            "to the nearest OSM-mapped hospital, clinic, or doctors feature inside the ward. Distances use OSMnx "
            "edge length in metres; nodes are unweighted, not population-weighted."
        ),
        validation_status="not validated against observed trips, access records, or an authoritative facility inventory",
        limitations=[
            "OpenStreetMap road/facility coverage and currentness are not verified; unmapped roads/facilities may be missing.",
            "The local OSM extract covers the ward plus a 1 km buffer; paths can be truncated at the extract edge.",
            "Facility points snap to the nearest graph node; this does not verify an entrance, driveway, opening status, or service capability.",
            "Results describe road-network distance only; no traffic, speed, emergency priority, travel time, or population exposure is modeled.",
            "F/S boundary vintage and reuse terms are unresolved; these outputs remain local exploratory derivatives pending review.",
        ],
    )


def get_closure_options() -> list[ClosureOption]:
    network = _load_network()
    output = []
    for road_name, edges in network["named_road_edges"].items():
        output.append(
            ClosureOption(
                road_name=road_name,
                directed_edges_intersecting_ward=len(edges),
                highway_classes=sorted({edge["highway"] for edge in edges}),
            )
        )
    return sorted(output, key=lambda item: (item.road_name.casefold(), item.road_name))


def get_nearby_facility_routes(request: FacilityRoutesRequest) -> FacilityRoutesResult:
    """Return shortest directed OSM road paths from a selected ward point to nearby mapped facilities."""
    network = _load_network()
    selected_wgs84 = Point(request.longitude, request.latitude)
    selected_projected = gpd.GeoSeries([selected_wgs84], crs="EPSG:4326").to_crs(ANALYSIS_CRS).iloc[0]
    if not network["ward"].covers(selected_projected):
        raise HTTPException(status_code=422, detail="Choose a point inside the F/S Ward boundary.")

    selected_closures = list(dict.fromkeys(name.strip() for name in request.closed_road_names if name.strip()))
    if len(selected_closures) > 8:
        raise HTTPException(status_code=422, detail="Choose up to eight roads to close in this what-if.")
    graph: nx.MultiDiGraph = network["graph"].copy() if selected_closures else network["graph"]
    closure_edges_by_id: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for name in selected_closures:
        edges = network["named_road_edges"].get(name)
        if not edges:
            raise HTTPException(status_code=422, detail=f"{name} is not in the mapped road-closure options.")
        closure_edges_by_id.update({(edge["u"], edge["v"], edge["key"]): edge for edge in edges})
        for edge in edges:
            if graph.has_edge(edge["u"], edge["v"], edge["key"]):
                graph.remove_edge(edge["u"], edge["v"], edge["key"])
    closure_edges = list(closure_edges_by_id.values())
    node_ids = list(graph.nodes)
    node_geometries = [graph.nodes[node]["geometry"] for node in node_ids]
    source_index = min(range(len(node_ids)), key=lambda index: node_geometries[index].distance(selected_projected))
    source_node = node_ids[source_index]
    snap_distance = float(node_geometries[source_index].distance(selected_projected))
    distances, paths = nx.single_source_dijkstra(graph, source_node, weight="length_m")
    baseline_distances = distances if not selected_closures else nx.single_source_dijkstra(network["graph"], source_node, weight="length_m")[0]

    candidates = []
    for route_record in network["facility_route_records"]:
        facility = route_record["record"]
        target = route_record["road_node"]
        distance = distances.get(target)
        if distance is None or distance > request.radius_m:
            continue
        baseline_distance = baseline_distances.get(target)
        candidates.append((float(distance), facility, paths[target], route_record["point"], float(baseline_distance) if baseline_distance is not None else None))
    candidates.sort(key=lambda item: (item[0], item[1].get("name") or "", item[1].get("osm_id") or ""))
    if not candidates:
        raise HTTPException(status_code=404, detail="No mapped health facility is reachable within that road-distance range.")

    def path_coordinates(path: list[int | str]) -> list[tuple[float, float]]:
        coordinates: list[tuple[float, float]] = []
        for start, end in zip(path, path[1:]):
            edge_data = graph.get_edge_data(start, end) or {}
            edge = min(edge_data.values(), key=lambda item: float(item.get("length_m", float("inf"))))
            geometry = edge.get("geometry")
            if geometry is None or geometry.is_empty:
                segment = [graph.nodes[start]["geometry"], graph.nodes[end]["geometry"]]
                segment_coords = [(point.x, point.y) for point in segment]
            else:
                parts = list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]
                segment_coords = []
                for part in parts:
                    part_coords = list(part.coords)
                    start_geom = graph.nodes[start]["geometry"]
                    if Point(part_coords[-1]).distance(start_geom) < Point(part_coords[0]).distance(start_geom):
                        part_coords.reverse()
                    if segment_coords and part_coords and segment_coords[-1] == part_coords[0]:
                        segment_coords.extend(part_coords[1:])
                    else:
                        segment_coords.extend(part_coords)
            if coordinates and segment_coords and coordinates[-1] == segment_coords[0]:
                coordinates.extend(segment_coords[1:])
            else:
                coordinates.extend(segment_coords)
        if len(path) == 1:
            point = graph.nodes[path[0]]["geometry"]
            coordinates = [(point.x, point.y)]
        return coordinates

    projected_lines = []
    route_features = []
    facility_features = []
    facilities = []
    nearest_id = candidates[0][1].get("osm_id") or candidates[0][1].get("nearest_road_node")
    for index, (distance, facility, path, facility_point, baseline_distance) in enumerate(candidates):
        coords = path_coordinates(path)
        from shapely.geometry import LineString
        line = LineString(coords) if len(coords) > 1 else LineString([coords[0], coords[0]])
        projected_lines.append(line)
        is_nearest = index == 0
        properties = {
            "osm_id": facility.get("osm_id"),
            "name": facility.get("name") or "Unnamed mapped health facility",
            "amenity": facility.get("amenity"),
            "healthcare": facility.get("healthcare"),
            "distance_m": round(distance),
            "baseline_distance_m": round(baseline_distance) if baseline_distance is not None else None,
            "distance_change_m": round(distance - baseline_distance) if baseline_distance is not None else None,
            "is_nearest": is_nearest,
        }
        route_features.append({"type": "Feature", "properties": properties, "geometry": mapping(line)})
        facility_features.append({"type": "Feature", "properties": properties, "geometry": mapping(facility_point)})
        facilities.append({**properties, "geometry_type": facility.get("geometry_type"), "snap_distance_m": facility.get("snap_distance_m")})

    routes_wgs84 = gpd.GeoSeries(projected_lines, crs=ANALYSIS_CRS).to_crs("EPSG:4326")
    for feature, geometry in zip(route_features, routes_wgs84, strict=True):
        feature["geometry"] = mapping(geometry)
    facilities_wgs84 = gpd.GeoSeries([item[3] for item in candidates], crs=ANALYSIS_CRS).to_crs("EPSG:4326")
    for feature, geometry in zip(facility_features, facilities_wgs84, strict=True):
        feature["geometry"] = mapping(geometry)
    snapped_wgs84 = gpd.GeoSeries([node_geometries[source_index]], crs=ANALYSIS_CRS).to_crs("EPSG:4326").iloc[0]
    grouped_closure_edges: dict[tuple[str, bytes], list[dict[str, Any]]] = {}
    for edge in closure_edges:
        edge_name = next((name for name in selected_closures if name in edge["road_names"]), selected_closures[0])
        grouped_closure_edges.setdefault((edge_name, edge["geometry"].normalize().wkb), []).append(edge)
    closure_features = []
    for (road_name, _), edges in grouped_closure_edges.items():
        geom = gpd.GeoSeries([edges[0]["geometry"]], crs=ANALYSIS_CRS).to_crs("EPSG:4326").iloc[0]
        closure_features.append({"type": "Feature", "properties": {"road_name": road_name}, "geometry": mapping(geom)})
    return FacilityRoutesResult(
        selected_point={"longitude": request.longitude, "latitude": request.latitude},
        snapped_point={"longitude": snapped_wgs84.x, "latitude": snapped_wgs84.y},
        snap_distance_m=round(snap_distance, 1),
        radius_m=request.radius_m,
        facilities_found=len(facilities),
        nearest_facility_osm_id=str(nearest_id),
        facilities=facilities,
        routes_geojson={"type": "FeatureCollection", "features": route_features},
        facilities_geojson={"type": "FeatureCollection", "features": facility_features},
        applied_closures=selected_closures,
        closed_edges_geojson={"type": "FeatureCollection", "features": closure_features},
        source_retrieved_at=network["retrieved_at"],
        assumptions=[
            "Routes follow the directed OSM road graph and are ranked by mapped road length, not travel time.",
            "Selected named roads are removed from the graph for this what-if; facility route distances are compared with those same roads open.",
            "The map click is snapped to the nearest road node; facility points may represent building centroids rather than entrances.",
            "All reachable mapped facilities inside the chosen road-distance range are shown.",
            "OSM mapping does not verify that a facility is open, staffed, or able to provide a requested service.",
        ],
    )


def run_road_closure(road_name: str | list[str]) -> AccessRunResult:
    selected_names = [road_name.strip()] if isinstance(road_name, str) else list(dict.fromkeys(name.strip() for name in road_name if name.strip()))
    if not selected_names or len(selected_names) > 8 or any(len(name) > 200 for name in selected_names):
        raise HTTPException(status_code=422, detail="Choose between one and eight mapped road names from the supplied closure options.")
    network = _load_network()
    invalid_names = [name for name in selected_names if not network["named_road_edges"].get(name)]
    if invalid_names:
        raise HTTPException(status_code=422, detail=f"These road names are not in the mapped closure options: {', '.join(invalid_names)}.")
    closure_edges_by_id = {(edge["u"], edge["v"], edge["key"]): edge for name in selected_names for edge in network["named_road_edges"][name]}
    closure_edges = list(closure_edges_by_id.values())

    graph = network["graph"].copy()
    for edge in closure_edges:
        if graph.has_edge(edge["u"], edge["v"], edge["key"]):
            graph.remove_edge(edge["u"], edge["v"], edge["key"])

    baseline_distances, baseline_metrics = _baseline(network)
    scenario_distances = _distance_map(graph, network["facility_nodes"])
    scenario_metrics = _metrics(network, scenario_distances)
    common_nodes = [
        node for node in network["nodes_inside"]
        if node in baseline_distances and node in scenario_distances
    ]
    mean_change = None
    if common_nodes:
        before = sum(baseline_distances[node] for node in common_nodes) / len(common_nodes)
        after = sum(scenario_distances[node] for node in common_nodes) / len(common_nodes)
        mean_change = round(after - before, 1)

    baseline_reachable = {node for node in network["nodes_inside"] if node in baseline_distances}
    scenario_reachable = {node for node in network["nodes_inside"] if node in scenario_distances}
    newly_unreachable = sorted(baseline_reachable - scenario_reachable, key=str)
    newly_unreachable_geometries = [network["graph"].nodes[node]["geometry"] for node in newly_unreachable]
    newly_unreachable_wgs84 = gpd.GeoSeries(newly_unreachable_geometries, crs=ANALYSIS_CRS).to_crs("EPSG:4326")
    impact_features = [
        {
            "type": "Feature",
            "id": str(node),
            "properties": {"status": "newly_unreachable_road_node"},
            "geometry": mapping(geometry),
        }
        for node, geometry in zip(newly_unreachable, newly_unreachable_wgs84, strict=True)
    ]
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    display_geometries: dict[tuple[str, bytes], list[dict[str, Any]]] = {}
    for edge in closure_edges:
        edge_name = next((name for name in selected_names if name in edge["road_names"]), selected_names[0])
        normalized_geometry = edge["geometry"].normalize()
        display_geometries.setdefault((edge_name, normalized_geometry.wkb), []).append(edge)
    features = []
    for (display_road_name, _), duplicate_group in display_geometries.items():
        edge = duplicate_group[0]
        geom_wgs84 = gpd.GeoSeries([edge["geometry"]], crs=ANALYSIS_CRS).to_crs("EPSG:4326").iloc[0]
        edge_ids = [f'{item["u"]}:{item["v"]}:{item["key"]}' for item in duplicate_group]
        features.append({
            "type": "Feature",
            "id": edge_ids[0],
            "properties": {"road_name": display_road_name, "edge_ids": edge_ids, "directed_edge_count": len(edge_ids)},
            "geometry": mapping(geom_wgs84),
        })

    result = AccessRunResult(
        run_id=run_id,
        created_at=created_at,
        scenario_label=f"Hypothetical closure of {', '.join(selected_names)} within F/S Ward",
        facility_type="OSM-mapped health facilities (hospital, clinic, doctors)",
        road_name=", ".join(selected_names),
        road_names=selected_names,
        closed_directed_edges=len(closure_edges),
        closed_edge_ids=[f'{edge["u"]}:{edge["v"]}:{edge["key"]}' for edge in closure_edges],
        baseline=baseline_metrics,
        scenario=scenario_metrics,
        change={
            "newly_unreachable_road_nodes": len(newly_unreachable),
            "newly_reachable_road_nodes": len(scenario_reachable - baseline_reachable),
            "common_reachable_road_nodes": len(common_nodes),
            "mean_distance_change_on_common_nodes_m": mean_change if mean_change is not None else 0.0,
        },
        closed_edges_geojson={"type": "FeatureCollection", "features": features},
        newly_unreachable_nodes_geojson={"type": "FeatureCollection", "features": impact_features},
        source_retrieved_at=network["retrieved_at"],
        source_checksum=network["source_checksum"],
        assumptions=[
            "This is a hypothetical closure, not a report of a real road closure.",
            "All directed OSM graph segments with each selected name intersecting the F/S polygon are removed; segments outside the polygon stay open.",
            "Every road-graph node is weighted equally; no population or trip-demand weighting is available.",
        ],
        limitations=[
            "The road and facility network is community-mapped, may be incomplete, and is not an authoritative operational inventory.",
            "The metric is shortest network distance, not travel time, emergency response performance, or safety advice.",
            "The local network is clipped to a 1 km buffer, so a path that would detour beyond the extract may be missing.",
            "The ward boundary and OSM-derived output reuse terms remain unresolved; this run is stored locally only.",
        ],
    )

    try:
        RUNS_PATH.mkdir(parents=True, exist_ok=True)
        temp_path = RUNS_PATH / f".{run_id}.tmp"
        final_path = RUNS_PATH / f"{run_id}.json"
        temp_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        temp_path.replace(final_path)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Could not persist the accessibility run manifest.") from error

    return result


def read_access_run(run_id: str) -> AccessRunResult:
    try:
        parsed_id = str(uuid.UUID(run_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Accessibility run was not found.") from error
    path = RUNS_PATH / f"{parsed_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Accessibility run was not found.")
    try:
        return AccessRunResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Accessibility run manifest could not be read.") from error
