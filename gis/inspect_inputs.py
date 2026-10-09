#!/usr/bin/env python3
"""Read-only structural inspection of local GIS inputs.

This tool reports file metadata; it does not determine licensing, accuracy,
hydrologic suitability, or whether a dataset is authoritative.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _json_value(value: Any) -> Any:
    """Convert common numpy/pandas scalar values into JSON-safe Python values."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def inspect_vector(path: Path) -> dict[str, Any]:
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError("GeoPandas is required to inspect vector files") from exc

    frame = gpd.read_file(path)
    geom_col = frame.geometry.name if frame.geometry is not None else None
    geometry_types = Counter(
        str(kind) for kind in frame.geometry.geom_type.dropna().tolist()
    ) if geom_col else Counter()
    bounds = None
    if not frame.empty and geom_col:
        raw_bounds = frame.total_bounds.tolist()
        bounds = [_json_value(v) for v in raw_bounds]

    null_counts = {
        str(column): int(count)
        for column, count in frame.isna().sum().items()
        if int(count) > 0
    }
    invalid_geometries = None
    if geom_col and not frame.empty:
        invalid_geometries = int((~frame.geometry.is_valid & frame.geometry.notna()).sum())

    return {
        "path": str(path),
        "kind": "vector",
        "feature_count": int(len(frame)),
        "crs": frame.crs.to_string() if frame.crs else None,
        "bounds_in_source_crs": bounds,
        "geometry_column": geom_col,
        "geometry_types": dict(geometry_types),
        "invalid_geometry_count": invalid_geometries,
        "null_counts": null_counts,
        "columns": [str(column) for column in frame.columns],
        "notes": [
            "Structural inspection only; authority, date, licensing and positional accuracy are not evaluated.",
            "Bounds are in source CRS and are not assumed to be metres.",
        ],
    }


def inspect_raster(path: Path) -> dict[str, Any]:
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("Rasterio is required to inspect raster files") from exc

    import numpy as np

    with rasterio.open(path) as dataset:
        valid_fractions: list[float | None] = []
        for band_index in range(1, dataset.count + 1):
            mask = dataset.read_masks(band_index)
            valid_fractions.append(float(np.count_nonzero(mask) / mask.size) if mask.size else None)

        return {
            "path": str(path),
            "kind": "raster",
            "driver": dataset.driver,
            "width_pixels": int(dataset.width),
            "height_pixels": int(dataset.height),
            "band_count": int(dataset.count),
            "crs": dataset.crs.to_string() if dataset.crs else None,
            "bounds_in_source_crs": [float(value) for value in dataset.bounds],
            "pixel_size_in_source_units": [float(dataset.res[0]), float(dataset.res[1])],
            "dtype_by_band": list(dataset.dtypes),
            "nodata_by_band": [_json_value(value) for value in dataset.nodatavals],
            "valid_data_fraction_by_band": valid_fractions,
            "descriptions": list(dataset.descriptions),
            "units": list(dataset.units),
            "tags": dataset.tags(),
            "notes": [
                "Structural inspection only; vertical datum, accuracy and licensing require source metadata.",
                "Pixel size is reported in raster CRS units and is not automatically metres.",
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vector", type=Path, action="append", default=[], help="Vector dataset path; may be repeated")
    parser.add_argument("--raster", type=Path, action="append", default=[], help="Raster dataset path; may be repeated")
    parser.add_argument("--output", type=Path, required=True, help="JSON report output path")
    args = parser.parse_args()

    inputs = [("vector", path) for path in args.vector] + [("raster", path) for path in args.raster]
    if not inputs:
        parser.error("provide at least one --vector or --raster input")

    report: dict[str, Any] = {
        "report_schema": "india-sim-input-inspection/1.0",
        "disclaimer": "Structural inspection only. This report does not certify source authority, licensing, accuracy, or suitability for simulation.",
        "datasets": [],
    }
    for kind, path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"Input does not exist or is not a file: {path}")
        report["datasets"].append(inspect_vector(path) if kind == "vector" else inspect_raster(path))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote structural input report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
