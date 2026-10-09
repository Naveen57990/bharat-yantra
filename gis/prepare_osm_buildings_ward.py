"""Clip OSM building footprints to the selected ward for local Cesium preview."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ward", type=Path, required=True, help="Ward boundary vector file")
    parser.add_argument("--buildings", type=Path, required=True, help="OSM building GeoJSON")
    parser.add_argument("--output", type=Path, required=True, help="Output ward-clipped GeoJSON")
    args = parser.parse_args()

    ward = gpd.read_file(args.ward)
    buildings = gpd.read_file(args.buildings)
    if ward.crs is None or buildings.crs is None:
        raise ValueError("Ward and building inputs must declare a CRS.")

    # UTM zone 43N is appropriate for this local Mumbai clipping operation.
    work_crs = "EPSG:32643"
    ward_geometry = ward.to_crs(work_crs).geometry.union_all()
    polygons = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].to_crs(work_crs)
    selected = polygons[polygons.geometry.intersects(ward_geometry)].copy()
    selected.geometry = selected.geometry.intersection(ward_geometry)
    selected = selected[
        ~selected.geometry.is_empty
        & selected.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].to_crs("EPSG:4326")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected.to_file(args.output, driver="GeoJSON")
    manifest = {
        "operation": "exact polygon intersection with selected ward boundary",
        "input_buildings": str(args.buildings),
        "input_buildings_sha256": sha256(args.buildings),
        "input_ward": str(args.ward),
        "input_ward_sha256": sha256(args.ward),
        "working_crs": work_crs,
        "output_crs": "EPSG:4326",
        "input_polygon_features": int(len(polygons)),
        "output_features": int(len(selected)),
        "output_sha256": sha256(args.output),
        "limitations": [
            "OSM footprints may be missing, outdated, or geometrically inaccurate.",
            "This processing step does not verify OSM licensing or clear redistribution.",
            "No building heights or elevations are inferred.",
        ],
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(selected)} ward-clipped footprints to {args.output}")


if __name__ == "__main__":
    main()
