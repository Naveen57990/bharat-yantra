#!/usr/bin/env python3
"""Acquire MCGM drainage features intersecting the local F/S ward polygon.

Output stays under data/raw and must not be redistributed until MCGM reuse
terms and layer vintage are established.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


SERVICE = "https://prsrvgisapp.mcgm.gov.in/server/rest/services/mcgm/MCGMGIS_Departments_Master_All_Layers/MapServer"
LAYERS = {6: "storm_water_manholes", 7: "storm_water_drains"}


def request_json(url: str, params: dict[str, str], timeout: int = 90) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(params).encode("utf-8"),
        headers={"User-Agent": "INDIA-SIM/0.1 (local GIS feasibility acquisition)"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ward", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    collection = json.loads(args.ward.read_text(encoding="utf-8"))
    feature = collection["features"][0]
    geometry = json.dumps(
        {
            "rings": feature["geometry"]["coordinates"],
            "spatialReference": {"wkid": 4326},
        },
        separators=(",", ":"),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset_id": "mcgm_fs_storm_water_network",
        "source_service": SERVICE,
        "source_layers": {},
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection": "features intersecting MCGM service Wards layer 238 F/S polygon",
        "output_crs": "EPSG:4326",
        "rights_status": "local only; reuse and redistribution terms unresolved",
        "limitations": [
            "Layer vintage and update process not established.",
            "Service is not evidence of complete, connected, commissioned or operational drainage.",
            "Existing and Proposal drain records must remain distinct.",
            "Ground-level and invert levels require vertical datum and source-quality checks.",
        ],
    }

    for layer_id, slug in LAYERS.items():
        layer_url = f"{SERVICE}/{layer_id}"
        metadata = request_json(layer_url, {"f": "pjson"})
        base_params = {
            "where": "1=1",
            "geometry": geometry,
            "geometryType": "esriGeometryPolygon",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
        ids_response = request_json(
            f"{layer_url}/query",
            {**base_params, "f": "json", "returnIdsOnly": "true"},
        )
        if "error" in ids_response:
            raise RuntimeError(f"Layer {layer_id} ID query failed: {ids_response['error']}")
        object_ids = ids_response.get("objectIds") or []

        features: list[dict] = []
        for start in range(0, len(object_ids), 250):
            batch = object_ids[start : start + 250]
            response = request_json(
                f"{layer_url}/query",
                {
                    "f": "geojson",
                    "objectIds": ",".join(map(str, batch)),
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326",
                },
            )
            if "error" in response:
                raise RuntimeError(f"Layer {layer_id} feature query failed: {response['error']}")
            features.extend(response.get("features", []))

        geojson = {
            "type": "FeatureCollection",
            "name": slug,
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
            "features": features,
        }
        output_path = args.output_dir / f"{slug}.geojson"
        output_path.write_text(json.dumps(geojson, ensure_ascii=False) + "\n", encoding="utf-8")
        status_counts = Counter(
            str(item.get("properties", {}).get("USER_TEXT2") or "(blank)")
            for item in features
        )
        manifest["source_layers"][str(layer_id)] = {
            "name": metadata.get("name"),
            "geometry_type": metadata.get("geometryType"),
            "fields": [field["name"] for field in metadata.get("fields", [])],
            "service_extent_crs": (metadata.get("extent") or {}).get("spatialReference"),
            "feature_count": len(features),
            "status_counts_if_present": dict(status_counts) if layer_id == 7 else None,
            "output": str(output_path),
            "sha256": sha256(output_path),
        }
        print(f"{metadata.get('name')}: {len(features)} features -> {output_path}")
        if layer_id == 7:
            print(f"Drain USER_TEXT2 values: {dict(status_counts)}")

    manifest_path = args.output_dir / "mcgm_drainage_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifest -> {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
