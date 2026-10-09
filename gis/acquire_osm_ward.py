#!/usr/bin/env python3
"""Acquire a bounded OSM road/context extract around an approved ward polygon.

The output is local, ODbL-licensed source/derived data. Review license obligations
before any public redistribution. This script does not imply official completeness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon


FACILITY_AMENITIES = ["hospital", "clinic", "doctors", "fire_station", "police", "shelter"]


def _stable_for_gpkg(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normalize mixed OSM tag types that otherwise fail GeoPackage schema creation."""
    result = frame.copy()
    geometry_name = result.geometry.name
    for column in result.columns:
        if column == geometry_name or result[column].dtype != "object":
            continue

        def as_text(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, float) and value != value:
                return None
            if isinstance(value, (list, tuple, dict)):
                return json.dumps(value, ensure_ascii=False, sort_keys=True)
            return str(value)

        result[column] = result[column].map(as_text)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, required=True, help="Ward polygon GeoJSON or GeoPackage")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory; keep it out of a public repo until reviewed")
    parser.add_argument("--buffer-metres", type=float, default=1000.0, help="Context buffer for routing and facilities")
    parser.add_argument("--boundary-name-field", default="NAME", help="Ward name property")
    parser.add_argument("--boundary-name", default="F/S", help="Ward name value to select")
    args = parser.parse_args()

    boundaries = gpd.read_file(args.boundary)
    if boundaries.crs is None:
        raise ValueError("Ward boundary has no CRS; refusing to guess coordinates")
    if args.boundary_name_field not in boundaries.columns:
        raise ValueError(f"Boundary field is missing: {args.boundary_name_field}")
    selected = boundaries.loc[boundaries[args.boundary_name_field].astype(str) == args.boundary_name]
    if len(selected) != 1:
        raise ValueError(f"Expected one {args.boundary_name_field}={args.boundary_name!r} feature; found {len(selected)}")

    ward = selected.to_crs("EPSG:32643").geometry.iloc[0]
    if ward is None or ward.is_empty or not ward.is_valid:
        raise ValueError("Selected ward geometry is empty or invalid; fix upstream and retain a repair record")
    if args.buffer_metres < 0:
        raise ValueError("Buffer distance must be non-negative")

    query_area = gpd.GeoSeries([ward.buffer(args.buffer_metres)], crs="EPSG:32643").to_crs("EPSG:4326").iloc[0]
    if not isinstance(query_area, Polygon):
        raise TypeError("Expected a single polygon query area")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(args.output_dir / "cache")
    ox.settings.log_console = False
    ox.settings.timeout = 240

    graph = ox.graph_from_polygon(
        query_area,
        network_type="drive",
        simplify=True,
        retain_all=True,
        truncate_by_edge=True,
    )
    nodes, edges = ox.graph_to_gdfs(graph, nodes=True, edges=True, fill_edge_geometry=True)
    if nodes.empty or edges.empty:
        raise RuntimeError("OSM returned an empty drive graph for the buffered ward")

    context = ox.features_from_polygon(
        query_area,
        tags={"building": True, "amenity": FACILITY_AMENITIES},
    )
    if context.empty:
        buildings = context.copy()
        facilities = context.copy()
    else:
        buildings = context.loc[context["building"].notna()].copy() if "building" in context.columns else context.iloc[0:0].copy()
        amenities = context.get("amenity")
        facilities = context.loc[amenities.isin(FACILITY_AMENITIES)].copy() if amenities is not None else context.iloc[0:0].copy()

    output = args.output_dir / "mumbai_fs_osm.gpkg"
    if output.exists():
        output.unlink()
    _stable_for_gpkg(nodes).to_file(output, layer="drive_nodes", driver="GPKG", index=True)
    _stable_for_gpkg(edges).to_file(output, layer="drive_edges", driver="GPKG", index=True)
    roads_path = args.output_dir / "roads.geojson"
    edges.to_crs("EPSG:4326").to_file(roads_path, driver="GeoJSON", index=True)
    if not buildings.empty:
        _stable_for_gpkg(buildings).to_file(args.output_dir / "buildings.geojson", driver="GeoJSON", index=True)
    if not facilities.empty:
        _stable_for_gpkg(facilities).to_file(args.output_dir / "emergency_facilities.geojson", driver="GeoJSON", index=True)

    bounds = [float(value) for value in gpd.GeoSeries([query_area], crs="EPSG:4326").total_bounds]
    manifest: dict[str, Any] = {
        "dataset_id": "osm_fs_context",
        "source": "OpenStreetMap contributors via OSMnx/Overpass",
        "source_url": "https://www.openstreetmap.org/copyright",
        "license": "Open Database License 1.0 (ODbL)",
        "attribution": "© OpenStreetMap contributors (https://www.openstreetmap.org/copyright)",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_boundary": str(args.boundary),
        "ward_name": args.boundary_name,
        "query_buffer_metres": args.buffer_metres,
        "query_bounds_wgs84": bounds,
        "network_type": "drive",
        "counts": {
            "drive_nodes": int(len(nodes)),
            "drive_edges": int(len(edges)),
            "buildings": int(len(buildings)),
            "emergency_facilities": int(len(facilities)),
        },
        "outputs": [output.name, roads_path.name, "buildings.geojson", "emergency_facilities.geojson"],
        "output_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [output, roads_path, args.output_dir / "buildings.geojson", args.output_dir / "emergency_facilities.geojson"]
        },
        "limitations": [
            "OpenStreetMap is community-contributed and may be incomplete or outdated.",
            "The drive graph follows available access and one-way tags; it is not a traffic or emergency-response-time model.",
            "Facility tags are mapped features, not a verified operational inventory.",
            "Derived database output retains ODbL obligations; attribution and share-alike review is required before publication.",
        ],
    }
    (args.output_dir / "osm_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
