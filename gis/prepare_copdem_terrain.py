#!/usr/bin/env python3
"""Clip Copernicus GLO-30 tiles to a ward plus a small display buffer.

This creates a visualization terrain raster only. It does not produce a
bare-earth DTM or a hydrologically conditioned surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject
from rasterio.features import geometry_mask


ATTRIBUTION = (
    "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 "
    "provided under COPERNICUS by the European Union and ESA; all rights reserved"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ward", type=Path, required=True)
    parser.add_argument("--tiles", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--buffer-metres", type=float, default=1000)
    parser.add_argument("--resolution-metres", type=float, default=30)
    args = parser.parse_args()

    ward = gpd.read_file(args.ward)
    if ward.empty or ward.crs is None:
        raise ValueError("Ward file must contain geometry and a declared CRS")
    metric = ward.to_crs("EPSG:32643")
    area = metric.geometry.union_all().buffer(args.buffer_metres)
    min_x, min_y, max_x, max_y = area.bounds
    resolution = args.resolution_metres
    left = math.floor(min_x / resolution) * resolution
    top = math.ceil(max_y / resolution) * resolution
    width = math.ceil((max_x - left) / resolution)
    height = math.ceil((top - min_y) / resolution)
    transform = from_origin(left, top, resolution, resolution)

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    nodata = -9999.0
    destination = np.full((height, width), nodata, dtype=np.float32)

    # Warp each source tile directly into the small local projected output grid.
    # The two tiles meet at the latitude edge; their overlap has identical
    # source-release semantics, so source order only resolves shared pixels.
    for tile_path in args.tiles:
        with rasterio.open(tile_path) as source:
            reproject(
                source=rasterio.band(source, 1),
                destination=destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform,
                dst_crs="EPSG:32643",
                dst_nodata=nodata,
                resampling=Resampling.bilinear,
                init_dest_nodata=False,
            )

    mask = geometry_mask(
        [area.__geo_interface__],
        out_shape=destination.shape,
        transform=transform,
        invert=True,
    )
    destination[~mask] = nodata
    valid = destination != nodata
    if not valid.any():
        raise RuntimeError("No source elevation pixels intersect the buffered ward")

    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32643",
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
    }
    with rasterio.open(output, "w", **profile) as target:
        target.write(destination, 1)
        target.set_band_description(1, "Copernicus GLO-30 DSM elevation")
        target.update_tags(
            source="Copernicus DEM GLO-30 Public, 2021 release",
            source_type="Digital Surface Model (DSM), not bare-earth DTM",
            attribution=ATTRIBUTION,
            processing="Warped to EPSG:32643 at nominal 30 m and clipped to ward + buffer",
            buffer_metres=str(args.buffer_metres),
            source_resolution="1/3 arc-second; nominal 30 m",
            intended_use="3D visualization and regional terrain context only",
            prohibited_inference="Not a validated flood-depth or street-drainage input",
        )

    manifest = {
        "schema": "india-sim-derived-raster/1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": output.name,
        "sha256": sha256(output),
        "source_tiles": [
            {"path": str(path), "sha256": sha256(path)} for path in args.tiles
        ],
        "source": "Copernicus DEM GLO-30 Public, 2021 release; DSM (not DTM)",
        "source_attribution": ATTRIBUTION,
        "source_terms": "https://copernicus-dem-30m.s3.amazonaws.com/readme.html",
        "spatial_resolution_metres_nominal": resolution,
        "crs": "EPSG:32643",
        "buffer_metres": args.buffer_metres,
        "valid_pixel_count": int(valid.sum()),
        "nodata_pixel_count": int((~valid).sum()),
        "valid_elevation_range_metres": [float(destination[valid].min()), float(destination[valid].max())],
        "intended_use": "3D visualization and regional terrain context only",
        "limitations": [
            "DSM includes surface objects such as buildings and vegetation.",
            "Nominal 30 m spacing cannot resolve urban drains or street-scale water flow.",
            "No vertical-datum harmonization, hydrologic conditioning, or flood validation is performed.",
            "This product is not a flood depth map or a flood model input approved for prediction.",
        ],
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
