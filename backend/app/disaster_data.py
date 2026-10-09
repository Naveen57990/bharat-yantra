from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FLOOD_RECORDS_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "disaster" / "flooding_spots_fs.geojson"
SHELTERS_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "disaster" / "temporary_shelters_fs.geojson"
MANIFEST_PATH = PROJECT_ROOT / "data" / "raw" / "mcgm" / "disaster" / "manifest.json"


def _read_features(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        collection = json.loads(path.read_text(encoding="utf-8"))
        if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
            raise ValueError("not a feature collection")
        return collection["features"]
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=f"The saved MCGM {label} snapshot is unavailable.") from error


def _date_from_esri_millis(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _feature_collection(features: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return {"type": "FeatureCollection", "name": name, "features": features}


def municipal_flood_context() -> dict[str, Any]:
    raw_floods = _read_features(FLOOD_RECORDS_PATH, "flood-spot")
    raw_shelters = _read_features(SHELTERS_PATH, "temporary-shelter")
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="The MCGM disaster-layer source manifest is unavailable.") from error

    flood_features: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}
    name_marked_delete = 0
    for feature in raw_floods:
        source = feature.get("properties") or {}
        name = source.get("NAME") or "Unnamed MCGM record"
        source_type = source.get("TYPE")
        category = {1: "Chronic flooding spot", 2: "Flooding spot"}.get(source_type, "MCGM flood record")
        record_flag = "Name contains a deletion marker" if "delete" in name.lower() else "Source status not stated"
        if "delete" in name.lower():
            name_marked_delete += 1
        type_counts[category] = type_counts.get(category, 0) + 1
        properties = {
            "record_id": source.get("FEATUREID") or str(feature.get("id") or source.get("OBJECTID") or ""),
            "name": name,
            "category": category,
            "location": source.get("LOCATION"),
            "affected_area_label": source.get("AFFECT_AREA"),
            "source_record_flag": record_flag,
            "source_remarks": source.get("REMARKS"),
            "source_created_date": _date_from_esri_millis(source.get("CREATED_DATE")),
            "source_last_edited_date": _date_from_esri_millis(source.get("LAST_EDITED_DATE")),
        }
        flood_features.append({"type": "Feature", "id": feature.get("id"), "geometry": feature.get("geometry"), "properties": properties})

    shelter_features: list[dict[str, Any]] = []
    shelter_types: dict[str, int] = {}
    for feature in raw_shelters:
        source = feature.get("properties") or {}
        source_type = source.get("TYPE")
        category = {1: "Municipal", 2: "Central government", 3: "State government", 4: "Private", 5: "Special"}.get(source_type, "Unspecified")
        shelter_types[category] = shelter_types.get(category, 0) + 1
        shelter_features.append({
            "type": "Feature",
            "id": feature.get("id"),
            "geometry": feature.get("geometry"),
            "properties": {
                "record_id": str(source.get("OBJECTID") or feature.get("id") or ""),
                "name": source.get("NAME") or "Unnamed listed location",
                "category": category,
                "location": source.get("LOCATION"),
                "working_hours": source.get("WORKING_HRS"),
                "working_hours_start": source.get("WORKING_HRS_STR"),
                "working_hours_end": source.get("WORKING_HRS_STP"),
            },
        })

    return {
        "snapshot": manifest,
        "flood_records": _feature_collection(flood_features, "MCGM F/S flooding records"),
        "shelters": _feature_collection(shelter_features, "MCGM F/S temporary-shelter records"),
        "summary": {
            "flood_record_count": len(flood_features),
            "flood_records_by_category": type_counts,
            "records_with_name_marked_delete": name_marked_delete,
            "shelter_record_count": len(shelter_features),
            "shelters_by_source_type": shelter_types,
            "verified_shelter_capacity_field_available": False,
            "verified_open_status_available": False,
        },
        "limitations": [
            "MCGM's Flooding Spots layer is a municipal record layer; the API does not provide a confirmed event date for each recorded location.",
            "Some source names contain a deletion marker. They are preserved and identified, not silently treated as active or removed records.",
            "The shelter layer identifies listed locations, but its exposed records do not establish current operation, capacity, flood safety, accessibility, or a safe route.",
            "This snapshot is contextual evidence only. It is not the output of the entered rainfall scenario and does not identify current or future impacts.",
        ],
    }
