#!/usr/bin/env python3
"""Clip Google Open Buildings footprints sourced through Overture to a ward."""

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
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overture-release", required=True)
    args = parser.parse_args()

    ward_doc = json.loads(args.ward.read_text(encoding="utf-8"))
    ward_wgs84 = shape(ward_doc["features"][0]["geometry"])
    project = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True).transform
    ward_utm = transform(project, ward_wgs84)

    source = json.loads(args.buildings.read_text(encoding="utf-8"))
    output_features = []
    confidence_values: list[float] = []
    dropped_non_google = 0
    for feature in source.get("features", []):
        properties = feature.get("properties") or {}
        source_rows = properties.get("sources") or []
        google_source = next((row for row in source_rows if row.get("dataset") == "Google Open Buildings"), None)
        if google_source is None:
            dropped_non_google += 1
            continue
        geometry = transform(project, shape(feature["geometry"]))
        if not geometry.intersects(ward_utm):
            continue
        clipped = geometry.intersection(ward_utm)
        if clipped.is_empty or clipped.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        confidence = google_source.get("confidence")
        if isinstance(confidence, (float, int)):
            confidence_values.append(float(confidence))
        output_properties = {
            "source_dataset": "Google Open Buildings v3",
            "source_provider": "Google Research",
            "source_record_id": google_source.get("record_id"),
            "source_update_time": google_source.get("update_time"),
            "source_confidence": confidence,
            "source_license": "CC BY 4.0 or ODbL 1.0; project clearance pending",
            "overture_release": args.overture_release,
            "height": properties.get("height"),
            "num_floors": properties.get("num_floors"),
            "is_underground": properties.get("is_underground", False),
        }
        output_features.append({"type": "Feature", "properties": output_properties, "geometry": mapping(transform(to_wgs84, clipped))})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    document = {"type": "FeatureCollection", "name": args.output.stem, "features": output_features}
    args.output.write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8")
    manifest = {
        "schema": "india-sim-derived-vector/1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": args.output.name,
        "output_sha256": sha256(args.output),
        "input_buildings": str(args.buildings),
        "input_buildings_sha256": sha256(args.buildings),
        "input_ward": str(args.ward),
        "input_ward_sha256": sha256(args.ward),
        "overture_release": args.overture_release,
        "provider_subset": "Google Open Buildings only; Overture OSM-sourced features omitted to avoid duplication of the separate OSM layer",
        "operation": "exact footprint intersection with F/S ward in EPSG:32643; output EPSG:4326",
        "source_bbox_features": len(source.get("features", [])),
        "dropped_non_google_features": dropped_non_google,
        "ward_intersecting_google_features": len(output_features),
        "confidence_range": [min(confidence_values), max(confidence_values)] if confidence_values else None,
        "confidence_threshold_applied": None,
        "vertical_attributes": {"height": 0, "num_floors": 0},
        "attribution": "Google Research, Open Buildings v3, accessed through Overture Maps Foundation building data.",
        "source_license": "Google Open Buildings is published under CC BY 4.0 or ODbL 1.0; Overture source records did not include a per-feature license for this subset. Project review pending.",
        "limitations": [
            "Machine-detected building footprints from satellite imagery; not surveyed building outlines.",
            "Confidence values are source model scores; no local precision threshold has been applied.",
            "Source imagery is not included; this dataset is not street-view imagery.",
            "No height or floor attributes were present in the selected Google Open Buildings features; render footprints only.",
            "Not evidence of current occupancy, structural condition, or flood vulnerability.",
            "Review exact attribution, Overture obligations, and redistribution terms before publication.",
        ],
    }
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
