"""Build a local, non-predictive terrain/drainage evidence grid for F/S Ward."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import box, mapping
from shapely.ops import transform
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
WARD_PATH = ROOT / "data/raw/mcgm/fs_ward_boundary.geojson"
DRAINS_PATH = ROOT / "data/raw/mcgm/drainage/storm_water_drains.geojson"
ROADS_PATH = ROOT / "data/raw/osm/roads.geojson"
DSM_PATH = ROOT / "data/processed/fs_ward/copernicus_glo30_dsm_utm43n.tif"
OUT_PATH = ROOT / "data/processed/fs_ward/relative_flood_screen.geojson"
SUMMARY_PATH = ROOT / "data/processed/fs_ward/relative_flood_screen.json"
CRS_METRIC = "EPSG:32643"
CELL_M = 250


def main() -> None:
    ward = gpd.read_file(WARD_PATH).to_crs(CRS_METRIC).geometry.union_all()
    drains = gpd.read_file(DRAINS_PATH).to_crs(CRS_METRIC)
    roads = gpd.read_file(ROADS_PATH).to_crs(CRS_METRIC)
    existing = drains[drains["USER_TEXT2"].astype(str).str.casefold() == "existing"].copy()
    proposals = drains[drains["USER_TEXT2"].astype(str).str.casefold() == "proposal"].copy()
    named_roads = roads[roads["name"].notna() & (roads["name"].astype(str).str.strip() != "")].copy()
    minx, miny, maxx, maxy = ward.bounds
    x0 = math.floor(minx / CELL_M) * CELL_M
    y0 = math.floor(miny / CELL_M) * CELL_M
    rows = []
    with rasterio.open(DSM_PATH) as dsm:
        for row in range(math.floor((maxy - y0) / CELL_M) + 1):
            for col in range(math.floor((maxx - x0) / CELL_M) + 1):
                cell = box(x0 + col * CELL_M, y0 + row * CELL_M, x0 + (col + 1) * CELL_M, y0 + (row + 1) * CELL_M)
                clipped = cell.intersection(ward)
                if clipped.is_empty or clipped.area < 1:
                    continue
                try:
                    arr, _ = mask(dsm, [mapping(clipped)], crop=True, filled=False)
                    vals = np.asarray(arr[0].compressed(), dtype=float)
                    vals = vals[np.isfinite(vals)]
                    p10 = float(np.percentile(vals, 10)) if len(vals) >= 3 else None
                    pixels = int(len(vals))
                except ValueError:
                    p10, pixels = None, 0
                def line_length(frame: gpd.GeoDataFrame) -> float:
                    if frame.empty:
                        return 0.0
                    indexes = list(frame.sindex.query(clipped, predicate="intersects"))
                    return float(sum(frame.geometry.iloc[i].intersection(clipped).length for i in indexes))
                existing_m = line_length(existing)
                proposal_m = line_length(proposals)
                area_km2 = clipped.area / 1_000_000
                road_name = None
                if not named_roads.empty:
                    distances = named_roads.geometry.distance(clipped.centroid)
                    nearest_idx = distances.idxmin()
                    raw_name = named_roads.loc[nearest_idx, "name"]
                    road_name = str(raw_name[0] if isinstance(raw_name, (list, tuple, np.ndarray)) and len(raw_name) else raw_name)
                rows.append({
                    "cell_id": f"FS-R{row + 1:02d}C{col + 1:02d}",
                    "geometry": clipped,
                    "area_km2": area_km2,
                    "dsm_p10_m": p10,
                    "dsm_valid_pixels": pixels,
                    "existing_drain_length_m": existing_m,
                    "proposal_drain_length_m": proposal_m,
                    "existing_drain_density_km_per_km2": existing_m / 1000 / area_km2,
                    "proposal_drain_density_km_per_km2": proposal_m / 1000 / area_km2,
                    "nearest_named_road": road_name,
                })
    valid_elev = [r["dsm_p10_m"] for r in rows if r["dsm_p10_m"] is not None]
    valid_drain = [r["existing_drain_density_km_per_km2"] for r in rows]
    elev_q25 = float(np.percentile(valid_elev, 25))
    drain_q25 = float(np.percentile(valid_drain, 25))
    for item in rows:
        low_elevation = item["dsm_p10_m"] is not None and item["dsm_p10_m"] <= elev_q25
        low_mapped_drains = item["existing_drain_density_km_per_km2"] <= drain_q25
        item["low_relative_terrain"] = bool(low_elevation)
        item["low_existing_drain_density"] = bool(low_mapped_drains)
        item["review_candidate"] = bool(low_elevation and low_mapped_drains)
        item["screen_label"] = "Review first" if item["review_candidate"] else "Context only"
    to_wgs84 = Transformer.from_crs(CRS_METRIC, "EPSG:4326", always_xy=True).transform
    features = [{"type": "Feature", "geometry": mapping(transform(to_wgs84, r.pop("geometry"))), "properties": r} for r in rows]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({"type": "FeatureCollection", "name": "F/S relative terrain and mapped drain evidence screen", "features": features}, separators=(",", ":")), encoding="utf-8")
    candidates = [r for r in rows if r["review_candidate"]]
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_inputs": ["provisional MCGM F/S boundary", "Copernicus GLO-30 DSM, 30 m", "MCGM storm-water drains, status Existing/Proposal retained", "OSM named roads for location cues only"],
        "cell_size_m_nominal": CELL_M,
        "cell_count": len(rows),
        "review_candidate_count": len(candidates),
        "dsm_p10_q25_m": round(elev_q25, 3),
        "existing_drain_density_q25_km_per_km2": round(drain_q25, 4),
        "candidate_cell_ids": [r["cell_id"] for r in candidates],
        "method": "Flag cells whose DSM 10th-percentile elevation is at/below the ward-grid 25th percentile and whose mapped Existing-drain length per clipped cell area is at/below its ward-grid 25th percentile. Proposal drains are measured and shown separately and excluded from the screen. This is an evidence-gap review shortlist, not a flood-risk score or impact prediction.",
        "limitations": ["DSM is a surface model with buildings/vegetation and 30 m nominal spacing; it is not an engineering bare-earth or hydrologically conditioned model.", "Drain lines are mapped records, not proof of capacity, connectivity, current condition, or operation. Missing mapped lines do not prove no drainage exists.", "250 m cells and relative ward percentiles are exploratory reporting bins; thresholds are not calibrated flood thresholds.", "Nearest OSM road is a location cue, not an official locality name.", "No verified temporary-shelter capacity, open status, safe route, or operational evacuation destination is available in the local data."]
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"cells": len(rows), "candidates": len(candidates), "terrain_q25_m": round(elev_q25, 3), "existing_drain_density_q25_km_per_km2": round(drain_q25, 4), "candidate_cells": [r["cell_id"] for r in candidates]}, indent=2))


if __name__ == "__main__":
    main()
