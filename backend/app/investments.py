from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
from fastapi import HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import mapping
from shapely.ops import linemerge, unary_union

from .accessibility import ANALYSIS_CRS, _distance_map, _load_network
from .flood import SCREEN_GRID_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_PATH = PROJECT_ROOT / "data" / "runs" / "investments"


class InvestmentPlanRequest(BaseModel):
    budget_crore: float = Field(gt=0, le=1000)
    drainage_site_allowance_inr: float = Field(gt=0, le=100_000_000)
    streetlight_site_allowance_inr: float = Field(gt=0, le=100_000_000)
    health_access_site_allowance_inr: float = Field(gt=0, le=100_000_000)
    streetlight_spacing_m: float = Field(default=100, gt=0, le=1000)


def _feature(geometry: Any, properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": mapping(geometry), "properties": properties}


def _grid_cell_candidates() -> list[dict[str, Any]]:
    try:
        data = json.loads(SCREEN_GRID_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="Local ward review-cell data is unavailable.") from error
    features = [feature for feature in data.get("features", []) if (feature.get("properties") or {}).get("review_candidate")]
    features.sort(key=lambda item: (
        (item.get("properties") or {}).get("dsm_p10_m") is None,
        (item.get("properties") or {}).get("dsm_p10_m") or math.inf,
        (item.get("properties") or {}).get("existing_drain_density_km_per_km2") or 0,
        str((item.get("properties") or {}).get("cell_id", "")),
    ))
    result = []
    for feature in features:
        props = feature.get("properties") or {}
        result.append({
            "type": "Feature",
            "geometry": feature.get("geometry"),
            "properties": {
                "workstream": "drainage",
                "site_name": str(props.get("cell_id", "Ward review cell")),
                "candidate_basis": "Relative lower-terrain and lower mapped Existing-drain-density screen; field verification only.",
                "dsm_p10_m": props.get("dsm_p10_m"),
                "existing_drain_length_m": props.get("existing_drain_length_m"),
                "nearest_named_road": props.get("nearest_named_road"),
            },
        })
    return result


def _road_site_candidates(network: dict[str, Any], streetlight_spacing_m: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    graph = network["graph"]
    cells: dict[tuple[int, int], list[int | str]] = {}
    for node in network["nodes_inside"]:
        point = graph.nodes[node]["geometry"]
        key = (math.floor(point.x / 250), math.floor(point.y / 250))
        cells.setdefault(key, []).append(node)

    streetlight_sites: list[tuple[str, Any, str]] = []
    seen_site_coordinates: set[tuple[float, float]] = set()
    for road_name, edges in sorted(network["named_road_edges"].items(), key=lambda item: item[0].casefold()):
        lines_by_wkb = {}
        for edge in edges:
            geometry = edge["geometry"].normalize()
            lines_by_wkb.setdefault(geometry.wkb, geometry)
        if not lines_by_wkb:
            continue
        merged = unary_union(list(lines_by_wkb.values()))
        if merged.geom_type != "LineString":
            merged = linemerge(merged)
        lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for line in lines:
            if line.geom_type != "LineString" or line.length <= 0:
                continue
            distance = streetlight_spacing_m / 2
            while distance < line.length:
                point = line.interpolate(distance)
                if network["ward"].covers(point):
                    coordinate_key = (round(point.x, 1), round(point.y, 1))
                    if coordinate_key not in seen_site_coordinates:
                        seen_site_coordinates.add(coordinate_key)
                        streetlight_sites.append((road_name, point, f"{road_name} · {round(distance)} m along mapped road"))
                distance += streetlight_spacing_m

    distances = _distance_map(graph, network["facility_nodes"])
    health_nodes = []
    for key, nodes in cells.items():
        reachable = [node for node in nodes if node in distances]
        if not reachable:
            continue
        node = max(reachable, key=lambda item: distances[item])
        health_nodes.append((distances[node], graph.nodes[node]["geometry"], node, distances[node]))

    def point_features(rows: list[tuple[float, Any, int | str, float | None]], workstream: str, basis: str) -> list[dict[str, Any]]:
        ordered = sorted(rows, key=lambda row: (-row[0], str(row[2])))
        projected = gpd.GeoSeries([row[1] for row in ordered], crs=ANALYSIS_CRS).to_crs("EPSG:4326") if ordered else []
        result = []
        for row, geometry in zip(ordered, projected, strict=True):
            score, _, node, distance = row
            props: dict[str, Any] = {
                "workstream": workstream,
                "site_name": f"Road point {node}",
                "road_node_id": str(node),
                "candidate_basis": basis,
            }
            if workstream == "streetlights":
                props["connected_road_edges"] = int(score)
            else:
                props["network_distance_to_mapped_health_m"] = round(float(distance or 0), 1)
            result.append(_feature(geometry, props))
        return result

    light_points = gpd.GeoSeries([row[1] for row in streetlight_sites], crs=ANALYSIS_CRS).to_crs("EPSG:4326") if streetlight_sites else []
    lights = [
        _feature(geometry, {
            "workstream": "streetlights",
            "site_name": name,
            "road_name": road_name,
            "spacing_m_assumption": streetlight_spacing_m,
            "candidate_basis": "Demo proposal placed along an OSM road; assumed spacing is editable and no installed-light inventory is available.",
        })
        for (road_name, _, name), geometry in zip(streetlight_sites, light_points, strict=True)
    ]
    access = point_features(
        health_nodes,
        "health_access",
        "The road point with the longest mapped network distance to an OSM health feature in its 250 m grid cell; a review priority, not a predicted improvement.",
    )
    return lights, access


def create_investment_plan(request: InvestmentPlanRequest) -> dict[str, Any]:
    grid_features = _grid_cell_candidates()
    network = _load_network()
    streetlight_features, health_features = _road_site_candidates(network, request.streetlight_spacing_m)
    budget = round(request.budget_crore * 10_000_000, 2)
    rates = {
        "drainage": request.drainage_site_allowance_inr,
        "streetlights": request.streetlight_site_allowance_inr,
        "health_access": request.health_access_site_allowance_inr,
    }
    definitions = [
        ("drainage", "Drainage review and works design", "Review mapped drains in lower-terrain / sparse mapped-drain cells before selecting repair or extension works.", grid_features,
         "Prioritizes real ward cells using the available terrain/drainage screen.", "The cell screen is not flood prediction; drain connectivity, condition and hydraulic capacity are unknown.", "Editable demo allowance; no comparable verified municipal rate is loaded."),
        ("streetlights", "Streetlight candidate locations", "Place demo lighting proposals along mapped OSM road segments.", streetlight_features,
         f"Generates proposed locations along real OSM road geometry at the editable {request.streetlight_spacing_m:g} m demo spacing.", "No current streetlight inventory, illumination survey, safety data or engineering design is available.", "BMC M&E SOR 2023 item R3-ME-5-6-e: ₹45,707 per listed 24W solar system, excluding GST; reference only, verify current tender and site suitability."),
        ("health_access", "Health-access road review", "Review road points with the longest mapped network distance to a mapped health facility.", health_features,
         "Uses the local road graph and mapped health features to identify review locations.", "Distance is not travel time; road nodes are not people, and facilities are not verified operational.", "Editable demo allowance; no comparable verified road-improvement rate is loaded."),
    ]

    options = []
    for workstream, name, summary, candidates, supported_basis, unknowns, rate_basis in definitions:
        rate = rates[workstream]
        planned = min(len(candidates), math.floor(budget / rate))
        estimated_cost = round(planned * rate, 2)
        selected = candidates[:planned]
        options.append({
            "id": workstream,
            "workstream": workstream,
            "name": name,
            "summary": summary,
            "supported_basis": supported_basis,
            "unknowns": unknowns,
            "available_count": len(candidates),
            "planned_count": planned,
            "unit_allowance_inr": rate,
            "rate_basis": rate_basis,
            "estimated_cost_inr": estimated_cost,
            "remaining_budget_inr": round(budget - estimated_cost, 2),
            "feature_collection": {"type": "FeatureCollection", "features": selected},
        })

    record = {
        "run_id": str(uuid.uuid4()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_type": "ward_government_investment_tradeoffs",
        "model_version": "mapped-investment-screen-v1",
        "inputs": {**request.model_dump(), "budget_inr": budget, "allowance_basis": "Editable demonstration allowances; not official MCGM rates, quotes, tender rates or engineering estimates."},
        "options": options,
        "sources": {
            "relative_terrain_drainage_cells": {"path": str(SCREEN_GRID_PATH.relative_to(PROJECT_ROOT)), "sha256": hashlib.sha256(SCREEN_GRID_PATH.read_bytes()).hexdigest(), "candidate_count": len(grid_features)},
            "osm_road_and_health_network": {"path": "data/raw/osm/mumbai_fs_osm.gpkg", "retrieved_at_utc": network["retrieved_at"], "sha256": network["source_checksum"], "road_node_count": len(network["nodes_inside"]), "mapped_health_feature_count": network["facility_count"]},
        },
        "method": "Each card spends the same entered budget at its own editable per-location allowance, up to the number of mapped candidate locations. The map shows only proposed review locations. Remaining budget is shown when local candidate locations run out.",
        "limitations": [
            "All rates are editable demonstration assumptions, not official municipal prices or procurement estimates.",
            "The map shows candidate locations for review; it does not show completed works or measured public benefits.",
            "Streetlight inventory, illumination, safety outcomes and engineering suitability are not available.",
            "Health-access priorities use shortest OSM network distance only, not travel time, population, demand or facility operations.",
            "Drainage review cells are a relative terrain/mapped-drain screen, not confirmed flood impacts or hydraulic capacity.",
            "F/S Ward boundary and source reuse status remain under review; this is an exploratory planning scenario.",
        ],
    }
    try:
        RUNS_PATH.mkdir(parents=True, exist_ok=True)
        path = RUNS_PATH / f"{record['run_id']}.json"
        temporary = RUNS_PATH / f".{record['run_id']}.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Could not save the investment comparison.") from error
    return record


def read_investment_plan(run_id: str) -> dict[str, Any]:
    try:
        canonical_id = str(uuid.UUID(run_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Investment comparison was not found.") from error
    path = RUNS_PATH / f"{canonical_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Investment comparison was not found.")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="Investment comparison could not be read.") from error
    if record.get("scenario_type") != "ward_government_investment_tradeoffs":
        raise HTTPException(status_code=422, detail="The selected record is not an investment comparison.")
    return record
