from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import rasterio
from fastapi import HTTPException
from pydantic import BaseModel, Field
from rasterio.warp import transform_bounds
from shapely.geometry import shape


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAIN_PATH = PROJECT_ROOT / "data" / "raw" / "imd" / "rainfall_districtwise_daily_imd.csv"
RAIN_MANIFEST_PATH = PROJECT_ROOT / "data" / "raw" / "imd" / "rainfall_manifest.json"
TERRAIN_PATH = PROJECT_ROOT / "data" / "processed" / "fs_ward" / "copernicus_glo30_dsm_utm43n.tif"
TERRAIN_MANIFEST_PATH = TERRAIN_PATH.with_suffix(TERRAIN_PATH.suffix + ".manifest.json")
WARD_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "fs_ward_boundary.geojson"
DRAINAGE_SUMMARY_PATH = PROJECT_ROOT / "data" / "reports" / "mcgm_drainage_quality_summary.json"
SCREEN_GRID_PATH = PROJECT_ROOT / "data" / "processed" / "fs_ward" / "relative_flood_screen.geojson"
SCREEN_SUMMARY_PATH = PROJECT_ROOT / "data" / "processed" / "fs_ward" / "relative_flood_screen.json"
MCGM_FLOOD_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "disaster" / "flooding_spots_fs.geojson"


class RainfallScenarioRequest(BaseModel):
    rainfall_mm: float = Field(gt=0, le=1000)
    duration_hours: float = Field(gt=0, le=168)


class IllustrativeFloodModelRequest(RainfallScenarioRequest):
    runoff_fraction: float = Field(default=0.7, gt=0, le=1)
    assumed_drain_capacity_m3_per_hour_per_km: float = Field(default=2500, ge=0, le=10000)


def _required_json(path: Path, description: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail=f"Local {description} metadata is unavailable.") from error


def _rainfall_records() -> dict[str, list[dict[str, Any]]]:
    if not RAIN_PATH.is_file():
        raise HTTPException(status_code=503, detail="The local IMD rainfall snapshot is unavailable.")
    grouped: dict[str, list[dict[str, Any]]] = {"MUMBAI CITY": [], "SUBURBAN MUMBAI": []}
    try:
        with RAIN_PATH.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                district = (row.get("District") or "").strip().upper()
                if district not in grouped:
                    continue
                try:
                    observed = float((row.get("Daily Actual") or "").strip())
                    normal = float((row.get("Daily Normal") or "").strip())
                    parsed_date = date.fromisoformat((row.get("Date") or "").strip())
                except (ValueError, TypeError):
                    continue
                if not math.isfinite(observed) or not math.isfinite(normal) or observed < 0:
                    continue
                grouped[district].append({
                    "date": parsed_date.isoformat(),
                    "observed_mm": observed,
                    "normal_mm": normal,
                    "category": (row.get("Daily Category") or "").strip() or None,
                })
    except OSError as error:
        raise HTTPException(status_code=503, detail="The local IMD rainfall snapshot could not be read.") from error
    for rows in grouped.values():
        rows.sort(key=lambda item: item["date"])
    return grouped


def _ward_area_m2() -> float:
    try:
        ward = gpd.read_file(WARD_PATH)
        if ward.empty or ward.geometry.isna().all():
            raise ValueError("empty ward")
        area = float(ward.to_crs("EPSG:32643").geometry.union_all().area)
    except Exception as error:
        raise HTTPException(status_code=503, detail="The local provisional ward boundary could not be measured.") from error
    if not math.isfinite(area) or area <= 0:
        raise HTTPException(status_code=503, detail="The local provisional ward has no measurable area.")
    return area


def flood_evidence() -> dict[str, Any]:
    rain_manifest = _required_json(RAIN_MANIFEST_PATH, "rainfall")
    terrain = _required_json(TERRAIN_MANIFEST_PATH, "terrain")
    drainage = _required_json(DRAINAGE_SUMMARY_PATH, "drainage")
    rainfall = _rainfall_records()
    all_rain = [item for rows in rainfall.values() for item in rows]
    dates = [item["date"] for item in all_rain]
    drain_summary = drainage.get("drains", {})
    manhole_summary = drainage.get("manholes", {})
    connectivity = drainage.get("connectivity_diagnostic", {})
    with rasterio.open(TERRAIN_PATH) as source:
        terrain_bounds = transform_bounds(source.crs, "EPSG:4326", *source.bounds, densify_pts=21)
    area = _ward_area_m2()
    return {
        "ward": {
            "name": "F/S Ward, Mumbai",
            "status": "provisional candidate; authority, vintage and reuse terms unresolved",
            "area_km2": round(area / 1_000_000, 3),
            "area_method": "Area of the local boundary polygon projected to EPSG:32643; not an officially confirmed ward area.",
        },
        "flood_simulation_available": False,
        "simulation_status": "No calibrated hydraulic/hydrologic flood simulation is available.",
        "rainfall": {
            "dataset": rain_manifest,
            "districts": {district: {"record_count": len(rows), "start_date": rows[0]["date"] if rows else None, "end_date": rows[-1]["date"] if rows else None} for district, rows in rainfall.items()},
            "overall_start_date": min(dates) if dates else None,
            "overall_end_date": max(dates) if dates else None,
            "limitations": ["District-level daily observations do not show ward-scale rainfall variation or sub-hourly storm peaks.", "This dated local snapshot is not a live feed and the source portal lists no license for its CSV resource."],
        },
        "terrain": {
            "dataset": "Copernicus DEM GLO-30 Public 2021 digital surface model, local F/S clip",
            "nominal_resolution_m": terrain.get("spatial_resolution_metres_nominal"),
            "crs": terrain.get("crs"),
            "valid_elevation_range_m": terrain.get("valid_elevation_range_metres"),
            "valid_pixels": terrain.get("valid_pixel_count"),
            "nodata_pixels": terrain.get("nodata_pixel_count"),
            "bounds_wgs84": {"west": terrain_bounds[0], "south": terrain_bounds[1], "east": terrain_bounds[2], "north": terrain_bounds[3]},
            "limitations": terrain.get("limitations", []),
            "use": "Regional elevation context only; not a street-level flood depth or validated water-flow surface.",
        },
        "drainage": {
            "dataset": "MCGM storm-water drains and manholes local F/S intersection",
            "drain_lines": drain_summary.get("count"),
            "drain_status_counts": drain_summary.get("status"),
            "manholes": manhole_summary.get("count"),
            "endpoint_id_matches": connectivity.get("drain_records_with_both_endpoints_matching_manhole"),
            "limitations": [connectivity.get("warning", "Identifier matching is not topology validation."), "Source terms, survey vintage, vertical datum, hydraulic capacity, current condition, blockages and outfall/tide operation are not verified."],
        },
        "missing_for_flood_depth": [
            "High-resolution bare-earth or engineering terrain with verified vertical datum and hydrologic conditioning.",
            "Ward-scale sub-hourly rainfall and storm distribution.",
            "Verified drain cross-sections, capacity, connectivity, condition, pump/outfall operations and tide or receiving-water boundary levels.",
            "Observed historical flood extent/depth with time and location for independent model calibration and validation.",
        ],
        "attribution_and_release": "Local exploratory use only. Check dataset_registry.csv before redistribution; IMD NWIC rainfall resource has no license specified and MCGM/Copernicus source-specific terms remain under review.",
    }


def rainfall_series(district: str) -> dict[str, Any]:
    selected = district.strip().upper()
    if selected not in {"MUMBAI CITY", "SUBURBAN MUMBAI"}:
        raise HTTPException(status_code=422, detail="Choose Mumbai City or Suburban Mumbai.")
    manifest = _required_json(RAIN_MANIFEST_PATH, "rainfall")
    records = _rainfall_records()[selected]
    return {"district": selected, "unit": "mm/day", "source": manifest, "spatial_scale": "district, not ward", "records": records}


def calculate_rainfall_scenario(request: RainfallScenarioRequest) -> dict[str, Any]:
    area_m2 = _ward_area_m2()
    rainfall_m = request.rainfall_mm / 1000
    volume_m3 = rainfall_m * area_m2
    return {
        "rainfall_mm": request.rainfall_mm,
        "duration_hours": request.duration_hours,
        "mean_intensity_mm_per_hour": round(request.rainfall_mm / request.duration_hours, 2),
        "provisional_ward_area_km2": round(area_m2 / 1_000_000, 3),
        "gross_rainfall_volume_m3": round(volume_m3),
        "interpretation": "Gross rain falling over the provisional ward polygon, assuming the entered depth is spatially uniform. It is not runoff, water stored, drain inflow, flood depth, or an inundation footprint.",
        "not_calculated": ["runoff", "infiltration", "drain capacity", "tide interaction", "flood depth", "affected roads or buildings"],
    }


def relative_screening_areas() -> dict[str, Any]:
    """Return terrain/drain evidence cells, explicitly not predicted flood impacts."""
    grid = _required_json(SCREEN_GRID_PATH, "relative flood screening grid")
    summary = _required_json(SCREEN_SUMMARY_PATH, "relative flood screening summary")
    all_features = grid.get("features", [])
    features = [feature for feature in all_features if (feature.get("properties") or {}).get("review_candidate") is True]
    return {
        "type": "FeatureCollection",
        "name": grid.get("name", "F/S relative evidence screen"),
        "features": features,
        "all_cells": all_features,
        "summary": summary,
        "destination_readiness": {
            "verified_evacuation_sites_available": False,
            "message": "No verified current shelter capacity, open status, flood safety, or route data is loaded. Do not recommend or direct transfers from this screening.",
        },
    }


def illustrative_flood_model(request: IllustrativeFloodModelRequest) -> dict[str, Any]:
    """Transparent rainfall/runoff budget demonstration with explicitly assumed drain capacity.

    This is not a hydraulic model: it does not route water between cells or estimate flood depth.
    """
    grid = _required_json(SCREEN_GRID_PATH, "relative flood screening grid")
    summary = _required_json(SCREEN_SUMMARY_PATH, "relative flood screening summary")
    valid_p10 = [float((feature.get("properties") or {}).get("dsm_p10_m")) for feature in grid.get("features", []) if (feature.get("properties") or {}).get("dsm_p10_m") is not None]
    min_p10 = min(valid_p10) if valid_p10 else 0.0
    max_p10 = max(valid_p10) if valid_p10 else 0.0
    p10_span = max_p10 - min_p10
    rows = []
    for feature in grid.get("features", []):
        props = feature.get("properties") or {}
        area_km2 = float(props.get("area_km2") or 0)
        area_m2 = area_km2 * 1_000_000
        existing_km = float(props.get("existing_drain_length_m") or 0) / 1000
        gross_rain_m3 = request.rainfall_mm * area_m2 / 1000
        runoff_m3 = gross_rain_m3 * request.runoff_fraction
        capacity_is_unknown = existing_km <= 0
        assumed_capacity_m3 = None if capacity_is_unknown else existing_km * request.assumed_drain_capacity_m3_per_hour_per_km * request.duration_hours
        residual_m3 = None if assumed_capacity_m3 is None else max(0.0, runoff_m3 - assumed_capacity_m3)
        residual_equivalent_mm = None if residual_m3 is None or not area_m2 else residual_m3 / area_m2 * 1000
        p10 = props.get("dsm_p10_m")
        terrain_factor = 1 + ((max_p10 - float(p10)) / p10_span if p10 is not None and p10_span > 0 else 0)
        terrain_weighted_index = residual_equivalent_mm * terrain_factor if residual_equivalent_mm is not None else None
        rows.append({
            "cell_id": props.get("cell_id"),
            "nearest_named_road": props.get("nearest_named_road"),
            "geometry": feature.get("geometry"),
            "area_km2": area_km2,
            "dsm_p10_m": p10,
            "existing_drain_length_m": float(props.get("existing_drain_length_m") or 0),
            "proposal_drain_length_m": float(props.get("proposal_drain_length_m") or 0),
            "gross_rain_m3": round(gross_rain_m3, 1),
            "assumed_runoff_m3": round(runoff_m3, 1),
            "assumed_drain_capacity_m3": round(assumed_capacity_m3, 1) if assumed_capacity_m3 is not None else None,
            "modelled_residual_runoff_m3": round(residual_m3, 1) if residual_m3 is not None else None,
            "residual_runoff_equivalent_mm": round(residual_equivalent_mm, 2) if residual_equivalent_mm is not None else None,
            "relative_terrain_factor": round(terrain_factor, 3),
            "terrain_weighted_screening_index": round(terrain_weighted_index, 2) if terrain_weighted_index is not None else None,
            "review_candidate": bool(props.get("review_candidate")),
            "capacity_unknown": capacity_is_unknown,
        })
    rows.sort(key=lambda item: (
        item["capacity_unknown"],
        -(item["terrain_weighted_screening_index"] if item["terrain_weighted_screening_index"] is not None else 0),
        item["dsm_p10_m"] if item["dsm_p10_m"] is not None else float("inf"),
        item["cell_id"] or "",
    ))
    for rank, row in enumerate(rows, 1):
        row["model_rank"] = rank
        row["model_flag"] = row["modelled_residual_runoff_m3"] is not None and row["modelled_residual_runoff_m3"] > 0
    flagged_count = sum(row["model_flag"] for row in rows)
    unknown_capacity_count = sum(row["capacity_unknown"] for row in rows)
    evaluable_rows = [row for row in rows if not row["capacity_unknown"]]
    runoff_levels = sorted({round(max(0.01, min(1.0, request.runoff_fraction * factor)), 4) for factor in (0.75, 1.0, 1.25)})
    capacity_levels = sorted({round(max(0.0, min(10000.0, request.assumed_drain_capacity_m3_per_hour_per_km * factor)), 2) for factor in (0.75, 1.0, 1.25)})
    sensitivity_cases = []
    for runoff_fraction in runoff_levels:
        for drain_capacity in capacity_levels:
            residual_total = 0.0
            exceedance_count = 0
            for row in evaluable_rows:
                gross = row["gross_rain_m3"]
                capacity = row["existing_drain_length_m"] / 1000 * drain_capacity * request.duration_hours
                residual = max(0.0, gross * runoff_fraction - capacity)
                residual_total += residual
                exceedance_count += residual > 0
            sensitivity_cases.append({
                "runoff_fraction_assumption": runoff_fraction,
                "drain_capacity_assumption_m3_per_hour_per_km": drain_capacity,
                "residual_arithmetic_total_m3": round(residual_total, 1),
                "cells_above_assumed_capacity": exceedance_count,
            })
    return {
        "model_name": "Illustrative cell water-budget stress test",
        "status": "ASSUMPTION-BASED DEMONSTRATION · NOT CALIBRATED OR VALIDATED",
        "scenario": {
            "rainfall_mm": request.rainfall_mm,
            "duration_hours": request.duration_hours,
            "mean_intensity_mm_per_hour": round(request.rainfall_mm / request.duration_hours, 2),
        },
        "assumptions": {
            "runoff_fraction": request.runoff_fraction,
            "drain_capacity_m3_per_hour_per_km": request.assumed_drain_capacity_m3_per_hour_per_km,
            "rainfall_spatial_distribution": "uniform over each clipped cell",
            "unmapped_drain_capacity": "unknown and excluded from capacity-exceedance counts; missing mapped lines do not prove drains are absent",
        },
        "summary": {
            "cell_count": len(rows),
            "modelled_exceedance_cell_count": flagged_count,
            "evaluable_cell_count": len(evaluable_rows),
            "capacity_unknown_cell_count": unknown_capacity_count,
            "gross_rain_m3": round(sum(row["gross_rain_m3"] for row in rows), 1),
            "assumed_runoff_m3": round(sum(row["assumed_runoff_m3"] for row in rows), 1),
            "assumed_drain_capacity_m3": round(sum(row["assumed_drain_capacity_m3"] or 0 for row in evaluable_rows), 1),
            "modelled_residual_runoff_m3": round(sum(row["modelled_residual_runoff_m3"] or 0 for row in evaluable_rows), 1),
            "relative_terrain_review_cell_count": summary.get("review_candidate_count"),
        },
        "sensitivity": {
            "method": "Nine deterministic cases vary the two editable assumptions independently by ±25% of the entered value, clipped to each input's allowed range; this is a scenario sweep, not a probability interval or confidence range.",
            "runoff_fraction_values": runoff_levels,
            "drain_capacity_values_m3_per_hour_per_km": capacity_levels,
            "cases": sensitivity_cases,
            "interpretation": "If results move substantially across these assumption cases, the ranking is assumption-sensitive. This sensitivity sweep does not make the underlying arithmetic a calibrated flood model.",
        },
        "method": "Per cell, estimated runoff = uniform gross rainfall volume × user-set runoff fraction. For cells with mapped Existing drain length > 0, a notional drain removal budget = mapped line kilometres × user-set capacity per kilometre per hour × duration; residual runoff is clipped at zero. Where no mapped Existing line intersects a cell, drainage capacity and residual are unknown and excluded from the modeled exceedance count. Evaluated cells rank by a demonstrative screening index = residual runoff-equivalent depth × relative terrain factor, where the factor ranges from 1 (highest valid DSM P10) to 2 (lowest valid DSM P10) across this ward grid. This multiplier is illustrative and not calibrated. Cells with unknown capacity follow as data gaps.",
        "limitations": [
            "Runoff fraction and drain capacity are editable demonstration assumptions, not measured local parameters.",
            "Mapped drain-line length is not verified hydraulic capacity or connectivity; assumed removal is not a hydraulic calculation.",
            "Cells with zero mapped Existing length are marked capacity unknown, not assumed to have no drainage, and are not included in capacity-exceedance counts.",
            "No water is routed between cells and no ponding, flood depth, inundation footprint, building impact, or affected population is calculated.",
            "DSM P10 is a surface-elevation cue with unresolved datum, not a hydrologically conditioned flow path or depression-storage model.",
            "The terrain multiplier is an illustrative ranking choice, not a calibrated relationship between elevation and flood impact.",
            "The output is not calibrated or validated and must not guide real evacuation or emergency response.",
        ],
        "features": rows,
    }


def municipal_record_overlap_diagnostic() -> dict[str, Any]:
    """Compare the review shortlist with MCGM record geometry, not model skill."""
    grid = _required_json(SCREEN_GRID_PATH, "relative flood screening grid")
    records = _required_json(MCGM_FLOOD_PATH, "MCGM flooding spots")
    candidate_cells = []
    for feature in grid.get("features", []):
        props = feature.get("properties") or {}
        if props.get("review_candidate") and feature.get("geometry"):
            try:
                candidate_cells.append((props.get("cell_id"), shape(feature["geometry"])))
            except (TypeError, ValueError):
                continue
    matched = []
    usable_record_count = 0
    for feature in records.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            record_geometry = shape(geometry)
        except (TypeError, ValueError):
            continue
        if record_geometry.is_empty or not record_geometry.is_valid:
            continue
        usable_record_count += 1
        cells = [cell_id for cell_id, cell_geometry in candidate_cells if record_geometry.intersects(cell_geometry)]
        if cells:
            props = feature.get("properties") or {}
            matched.append({
                "record_id": props.get("FEATUREID") or props.get("OBJECTID") or feature.get("id"),
                "name": props.get("NAME") or "Unnamed MCGM record",
                "intersecting_review_cells": cells,
            })
    return {
        "diagnostic_name": "Municipal record and relative review-cell spatial overlap",
        "status": "SPATIAL CONTEXT CHECK · NOT FLOOD-MODEL VALIDATION",
        "summary": {
            "usable_municipal_record_geometries": usable_record_count,
            "records_intersecting_relative_review_cells": len(matched),
            "relative_review_cell_count": len(candidate_cells),
            "matched_review_cell_count": len({cell_id for record in matched for cell_id in record["intersecting_review_cells"]}),
        },
        "matched_records": matched,
        "interpretation": "This reports geometry overlap between the current terrain/drain evidence shortlist and MCGM's registered flooding-location geometries. The MCGM records have no verified flood event dates or depth units, so overlap cannot establish event correspondence, predictive skill, calibration, or validation.",
        "limitations": [
            "MCGM points/polygons are context records, not independently dated event observations for a rainfall scenario.",
            "Record status is mixed or unclear; some names contain a deletion marker and all records are preserved in this diagnostic.",
            "Intersection is a geometric comparison only; it does not assess flood frequency, depth, cause, model error, or causality.",
            "No conclusion should be drawn from a record that does not intersect the shortlist; data completeness and positional accuracy are not verified.",
        ],
        "source": "Local MCGM F/S Flooding Spots snapshot; source manifest and caveats are retained with the source data.",
    }
