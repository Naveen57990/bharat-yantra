#!/usr/bin/env python3
"""Render a transparent RGB context image from the local Copernicus DSM.

The output is a display-only elevation context layer, not a flood or flow product.
It is stored under data/processed/, which is ignored and kept local pending terms review.
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from rasterio.enums import Resampling


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/fs_ward/copernicus_glo30_dsm_utm43n.tif"
OUTPUT = ROOT / "data/processed/fs_ward/copernicus_dsm_context.png"
METADATA = ROOT / "data/processed/fs_ward/copernicus_dsm_context.json"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def _write_rgba_png(path: Path, image: np.ndarray) -> None:
    height, width, channels = image.shape
    if channels != 4:
        raise ValueError("Expected an RGBA image.")
    scanlines = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    payload = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(scanlines, level=9)) + _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def render() -> dict[str, object]:
    with rasterio.open(SOURCE) as source:
        data = source.read(1, masked=True)
        source_bounds = source.bounds
        dst_transform, width, height = calculate_default_transform(
            source.crs, "EPSG:4326", source.width, source.height, *source_bounds
        )
        destination = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=source.nodata,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        elevation = np.asarray(destination, dtype=np.float32)
        valid = np.isfinite(elevation)
        if not valid.any():
            raise ValueError("DSM has no valid pixels to display.")
        values = elevation[valid]
        low, high = float(values.min()), float(values.max())
        if high <= low:
            raise ValueError("DSM display range is degenerate.")
        scaled = np.clip(np.nan_to_num((elevation - low) / (high - low), nan=0), 0, 1)
        stops = np.array([[34, 53, 57], [48, 103, 91], [132, 166, 119], [226, 211, 154]], dtype=np.float32)
        positions = scaled * (len(stops) - 1)
        lower = np.floor(positions).astype(np.int16)
        upper = np.minimum(lower + 1, len(stops) - 1)
        fraction = (positions - lower)[..., None]
        rgb = stops[lower] * (1 - fraction) + stops[upper] * fraction
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[..., :3] = np.nan_to_num(rgb, nan=0).astype(np.uint8)
        rgba[..., 3] = np.where(valid, 150, 0).astype(np.uint8)
        bounds = transform_bounds("EPSG:4326", "EPSG:4326", *rasterio.transform.array_bounds(height, width, dst_transform), densify_pts=21)
        # Crop image to the actual reprojection bounds and store exact display extent.
        _write_rgba_png(OUTPUT, rgba)

    metadata = {
        "image": OUTPUT.name,
        "bounds_wgs84": {"west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3]},
        "elevation_range_m": [round(low, 2), round(high, 2)],
        "source": "Copernicus DEM GLO-30 Public 2021 DSM; local F/S ward and 1 km buffer clip",
        "source_sha256": "90b67df112babcba8813006e15491f16d0977a749a59db20b6ab67c53eec5c89",
        "display_only": True,
        "limitations": ["Display-only relative elevation tint; values are a DSM, not bare-earth terrain.", "No hydrologic conditioning, drainage coupling, flood depth, or inundation prediction."],
    }
    METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    metadata = render()
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
