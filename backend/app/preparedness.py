from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import shape

from .flood import SCREEN_GRID_PATH
from .paths import PROJECT_ROOT, RUNS_ROOT

FLOOD_RECORDS_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "disaster" / "flooding_spots_fs.geojson"
SHELTERS_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "disaster" / "temporary_shelters_fs.geojson"
RUNS_PATH = RUNS_ROOT / "preparedness"


class PreparednessPlanRequest(BaseModel):
    rainfall_mm: float = Field(gt=0, le=1000)
    duration_hours: float = Field(gt=0, le=168)
    budget_crore: float = Field(gt=0, le=1000)
    cell_review_rate_inr: float = Field(gt=0, le=100_000_000)
    record_verification_rate_inr: float = Field(gt=0, le=100_000_000)
    shelter_audit_rate_inr: float = Field(gt=0, le=100_000_000)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail=f"Local {label} source is unavailable.") from error
    if not isinstance(result, dict) or not isinstance(result.get("features"), list):
        raise HTTPException(status_code=503, detail=f"Local {label} source has an unexpected format.")
    return result


def _with_geometry(feature: dict[str, Any], action: str, source: str) -> dict[str, Any] | None:
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        return None
    props = feature.get("properties") or {}
    return {"type": "Feature", "geometry": geom, "properties": {"action": action, "source": source, **{str(k): v for k, v in props.items() if isinstance(v, (str, int, float, bool)) or v is None}}}


def _ranked_cells(cells: list[dict[str, Any]], flood_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable_records = []
    for feature in flood_features:
        try:
            if feature.get("geometry"):
                usable_records.append(shape(feature["geometry"]))
        except (TypeError, ValueError):
            continue
    ranked = []
    for feature in cells:
        props = feature.get("properties") or {}
        if not props.get("review_candidate"):
            continue
        try:
            geom = shape(feature["geometry"])
            overlap = sum(geom.intersects(record) for record in usable_records)
        except (KeyError, TypeError, ValueError):
            overlap = 0
        dsm = props.get("dsm_p10_m")
        density = props.get("existing_drain_density_km_per_km2")
        ranked.append(((-overlap, dsm if isinstance(dsm, (int, float)) else math.inf, density if isinstance(density, (int, float)) else math.inf, str(props.get("cell_id", ""))), feature, overlap))
    ranked.sort(key=lambda item: item[0])
    result = []
    for _, feature, overlap in ranked:
        item = dict(feature)
        item["properties"] = {**(feature.get("properties") or {}), "intersecting_registered_record_geometries": overlap}
        result.append(item)
    return result


def create_preparedness_plan(request: PreparednessPlanRequest) -> dict[str, Any]:
    grid = _load(SCREEN_GRID_PATH, "relative terrain/drainage review-cell")
    flood = _load(FLOOD_RECORDS_PATH, "MCGM registered flood-location")
    shelters = _load(SHELTERS_PATH, "MCGM listed shelter-location")
    ranked_cells = _ranked_cells(grid["features"], flood["features"])
    rainfall_intensity = request.rainfall_mm / request.duration_hours
    # Demonstration screening rule: rainfall depth sets the base count; every
    # completed four-hour period adds one candidate. Thus, for the same rainfall
    # amount, a longer duration cannot reduce the shortlist. This is not a
    # calibrated soil-saturation or hydraulic model.
    review_limit = min(20, len(ranked_cells), max(1, math.ceil(request.rainfall_mm / 50) + math.floor(request.duration_hours / 4)))
    cells = ranked_cells[:review_limit]
    records = [feature for feature in flood["features"] if feature.get("geometry")]
    shelter_features = [feature for feature in shelters["features"] if feature.get("geometry")]
    budget = request.budget_crore * 10_000_000
    rates = {
        "field_review": request.cell_review_rate_inr,
        "record_verification": request.record_verification_rate_inr,
        "shelter_audit": request.shelter_audit_rate_inr,
    }
    sources = {
        "relative_review_cells": {"path": str(SCREEN_GRID_PATH.relative_to(PROJECT_ROOT)), "count": len(grid["features"]), "sha256": hashlib.sha256(SCREEN_GRID_PATH.read_bytes()).hexdigest()},
        "mcgm_flood_location_records": {"path": str(FLOOD_RECORDS_PATH.relative_to(PROJECT_ROOT)), "count": len(flood["features"]), "sha256": hashlib.sha256(FLOOD_RECORDS_PATH.read_bytes()).hexdigest()},
        "mcgm_listed_shelters": {"path": str(SHELTERS_PATH.relative_to(PROJECT_ROOT)), "count": len(shelters["features"]), "sha256": hashlib.sha256(SHELTERS_PATH.read_bytes()).hexdigest()},
    }

    definitions = [
        ("drainage_survey", "Drainage and terrain field review", "field_review", cells, "Review candidate cells in order. Verify mapped Existing-drain condition, connectivity and outfall; where mapping is sparse, verify the network rather than assuming none exists.", "relative terrain/drainage cells"),
        ("record_verification", "Registered-location verification", "record_verification", records, "Verify each mapped MCGM record's currentness, event date, depth meaning, exact location and resolution status before treating it as an active concern.", "MCGM registered flood-location records"),
        ("shelter_audit", "Listed shelter readiness audit", "shelter_audit", shelter_features, "Confirm whether each listed site is currently designated and open, its usable capacity, accessibility, flood safety and approved access arrangements. This plan does not direct people to a destination.", "MCGM listed temporary-shelter records"),
    ]

    def make_work(key: str, features: list[dict[str, Any]], action: str, source: str, allowance: float, budget_slice: float) -> dict[str, Any]:
        affordable = max(0, min(len(features), math.floor(budget_slice / allowance)))
        selected = features[:affordable]
        geo_features = [_with_geometry(feature, action, source) for feature in selected]
        geo_features = [feature for feature in geo_features if feature is not None]
        cost = affordable * allowance
        return {"workstream": key, "action": action, "source": source, "available_count": len(features), "planned_count": len(geo_features), "unit_allowance_inr": allowance, "estimated_allocation_inr": cost, "feature_collection": {"type": "FeatureCollection", "features": geo_features}}

    options = []
    for slug, name, key, features, action, source in definitions:
        work = make_work(key, features, action, source, rates[key], budget)
        options.append({"id": slug, "name": name, "summary": action, "workstreams": [work], "estimated_allocation_inr": work["estimated_allocation_inr"], "unallocated_inr": budget - work["estimated_allocation_inr"], "over_budget_inr": 0, "mapped_actions": work["planned_count"]})

    equal_slice = budget / len(definitions)
    balanced_work = [make_work(key, features, action, source, rates[key], equal_slice) for _, _, key, features, action, source in definitions]
    balanced_cost = sum(work["estimated_allocation_inr"] for work in balanced_work)
    options.append({"id": "balanced_review", "name": "Balanced verification programme", "summary": "Split the planning envelope evenly across the three verification workstreams; this is a planning choice, not an optimized benefit allocation.", "workstreams": balanced_work, "estimated_allocation_inr": balanced_cost, "unallocated_inr": budget - balanced_cost, "over_budget_inr": max(0, balanced_cost - budget), "mapped_actions": sum(work["planned_count"] for work in balanced_work)})

    record = {
        "run_id": str(uuid.uuid4()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_type": "ward_flood_preparedness_action_plan",
        "model_version": "evidence-linked-review-plan-v1",
        "status": "PLANNING SCENARIO · NOT FLOOD PREDICTION OR EVACUATION ADVICE",
        "inputs": {**request.model_dump(), "budget_inr": budget, "allowance_basis": "User-editable illustrative planning allowances; not official MCGM rates or quotations."},
        "method": f"The entered rainfall controls how many terrain/drainage cells appear in the field-check list using a demonstration rule ({review_limit} locations for this scenario): ceil(total rainfall mm / 50) plus one location per completed four-hour period, capped by available cells and 20. For the same rainfall amount, increasing duration can only keep the list the same size or add locations. This rule is illustrative and is not calibrated to measured soil saturation, drainage capacity, or observed floods. The list does not say those places will flood. Municipal flood records and shelter records remain static. No flood depth, affected area, risk, benefit, or safe destination is calculated. The balanced option splits the envelope equally by workstream and is not optimized.",
        "rainfall_screening": {"rainfall_mm": request.rainfall_mm, "duration_hours": request.duration_hours, "mean_intensity_mm_per_hour": round(rainfall_intensity, 2), "field_check_locations_shown": review_limit, "rule": "min(20, available candidate cells, max(1, ceil(total rainfall mm / 50) + floor(duration hours / 4)))"},
        "options": options,
        "selected_option_id": "balanced_review",
        "sources": sources,
        "limitations": [
            "The terrain/drainage cells are relative field-review candidates, not predicted flood locations or risk levels.",
            "The four-hour duration increment is an illustrative screening rule, not a measured soil-saturation or drainage model.",
            "MCGM flood-location records have no verified event dates or flood-depth interpretation for this planner; some names contain deletion markers.",
            "Shelter records do not verify current designation, operation, capacity, flood safety, or routes.",
            "Per-action costs are user-entered illustrative allowances, not official MCGM rates or procurement estimates.",
            "No lives protected, flood reduction, avoided loss, travel-time benefit, evacuation destination, or safety claim is calculated.",
        ],
    }
    try:
        RUNS_PATH.mkdir(parents=True, exist_ok=True)
        path = RUNS_PATH / f"{record['run_id']}.json"
        temporary = RUNS_PATH / f".{record['run_id']}.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Could not save the preparedness action plan.") from error
    return record


def read_preparedness_plan(run_id: str) -> dict[str, Any]:
    try:
        canonical_id = str(uuid.UUID(run_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Preparedness plan was not found.") from error
    path = RUNS_PATH / f"{canonical_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Preparedness plan was not found.")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="Preparedness plan could not be read.") from error
    if record.get("scenario_type") != "ward_flood_preparedness_action_plan":
        raise HTTPException(status_code=422, detail="The selected run is not a preparedness action plan.")
    return record
