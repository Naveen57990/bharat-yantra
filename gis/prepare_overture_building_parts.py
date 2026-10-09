#!/usr/bin/env python3
"""Clip OSM-sourced Overture building parts to F/S for 3D massing context."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ward", type=Path, required=True)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overture-release", required=True)
    args = parser.parse_args()

    ward_doc = json.loads(args.ward.read_text(encoding="utf-8"))
    ward = shape(ward_doc["features"][0]["geometry"])
    project = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform
    ward = transform(project, ward)
    source = json.loads(args.parts.read_text(encoding="utf-8"))
    output_features = []
    for feature in source.get("features", []):
        properties = feature.get("properties") or {}
        source_rows = properties.get("sources") or []
        osm = next((row for row in source_rows if row.get("dataset") == "OpenStreetMap"), None)
        if osm is None:
            continue
        geometry = transform(project, shape(feature["geometry"]))
        if not geometry.intersects(ward):
            continue
        clipped = geometry.intersection(ward)
        if clipped.is_empty or clipped.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        floors = properties.get("num_floors") or 0
        source_height = properties.get("height")
        output_features.append({
            "type": "Feature",
            "id": feature.get("id"),
            "properties": {
                "source_dataset": "OpenStreetMap building part via Overture Maps",
                "source_record_id": osm.get("record_id"),
                "building_id": properties.get("building_id"),
                "num_floors": floors or None,
                "height": source_height,
                "estimated_height_m": source_height or (floors * 3 if floors > 0 else None),
                "is_underground": properties.get("is_underground", False),
                "overture_release": args.overture_release,
                "source_license": "ODbL 1.0; project clearance pending",
            },
            "geometry": mapping(transform(to_wgs84, clipped)),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"type": "FeatureCollection", "features": output_features}, separators=(",", ":")) + "\n", encoding="utf-8")
    manifest = {
        "schema": "india-sim-derived-vector/1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": args.output.name,
        "output_sha256": sha256(args.output),
        "input_parts": str(args.parts),
        "input_parts_sha256": sha256(args.parts),
        "input_ward": str(args.ward),
        "input_ward_sha256": sha256(args.ward),
        "overture_release": args.overture_release,
        "output_features": len(output_features),
        "attribution": "© OpenStreetMap contributors via Overture Maps Foundation building_parts data.",
        "limitations": [
            "The OSM-tagged number of floors is preserved, not a surveyed total building height.",
            "3 m per mapped floor is a visualization estimate only; no explicit height is present on this feature.",
            "Only the building-part geometry is shown; do not assume it represents every part of the parent building.",
            "OSM-derived database output and attribution obligations require review before publication.",
        ],
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
