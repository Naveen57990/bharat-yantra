from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .flood import WARD_PATH, SCREEN_GRID_PATH, RainfallScenarioRequest, IllustrativeFloodModelRequest, calculate_rainfall_scenario, illustrative_flood_model


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_PATH = PROJECT_ROOT / "data" / "runs" / "flood"


class FloodRunRecord(BaseModel):
    run_id: str
    created_at_utc: str
    scenario_type: str
    model_version: str
    inputs: dict[str, float]
    outputs: dict[str, Any]
    source_dataset_ids: list[str]
    source_checksums: dict[str, str] = Field(default_factory=dict)
    status: str


def create_rainfall_run(request: RainfallScenarioRequest) -> FloodRunRecord:
    record = FloodRunRecord(
        run_id=str(uuid.uuid4()),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        scenario_type="uniform_rainfall_volume",
        model_version="gross-rainfall-volume-v1",
        inputs={"rainfall_mm": request.rainfall_mm, "duration_hours": request.duration_hours},
        outputs=calculate_rainfall_scenario(request),
        source_dataset_ids=["bmc_fs_boundary"],
        source_checksums={"bmc_fs_boundary": hashlib.sha256(WARD_PATH.read_bytes()).hexdigest()},
        status="DETERMINISTIC RAINFALL VOLUME · NOT FLOOD PREDICTION",
    )
    try:
        RUNS_PATH.mkdir(parents=True, exist_ok=True)
        destination = RUNS_PATH / f"{record.run_id}.json"
        temporary = RUNS_PATH / f".{record.run_id}.tmp"
        temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(destination)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Could not save the rainfall scenario record.") from error
    return record


def create_illustrative_model_run(request: IllustrativeFloodModelRequest) -> FloodRunRecord:
    """Persist the exact assumption-based result so the UI and agent can cite it."""
    result = illustrative_flood_model(request)
    record = FloodRunRecord(
        run_id=str(uuid.uuid4()),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        scenario_type="assumption_based_cell_water_budget",
        model_version="illustrative-cell-water-budget-v1",
        inputs={
            "rainfall_mm": request.rainfall_mm,
            "duration_hours": request.duration_hours,
            "runoff_fraction": request.runoff_fraction,
            "assumed_drain_capacity_m3_per_hour_per_km": request.assumed_drain_capacity_m3_per_hour_per_km,
        },
        outputs=result,
        source_dataset_ids=["bmc_fs_boundary", "bmc_municipal_gis_layers", "copernicus_dem_glo30_fs"],
        source_checksums={
            "bmc_fs_boundary": hashlib.sha256(WARD_PATH.read_bytes()).hexdigest(),
            "fs_relative_flood_screen": hashlib.sha256(SCREEN_GRID_PATH.read_bytes()).hexdigest(),
        },
        status="ASSUMPTION-BASED DEMONSTRATION · NOT A FLOOD PREDICTION",
    )
    try:
        RUNS_PATH.mkdir(parents=True, exist_ok=True)
        destination = RUNS_PATH / f"{record.run_id}.json"
        temporary = RUNS_PATH / f".{record.run_id}.tmp"
        temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(destination)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Could not save the illustrative flood model run.") from error
    return record


def list_flood_runs(limit: int = 20) -> list[FloodRunRecord]:
    if not RUNS_PATH.is_dir():
        return []
    records: list[FloodRunRecord] = []
    try:
        for path in sorted(RUNS_PATH.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                record = FloodRunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if record.scenario_type != "uniform_rainfall_volume":
                continue
            records.append(record)
            if len(records) >= limit:
                break
    except OSError as error:
        raise HTTPException(status_code=503, detail="Saved rainfall scenarios could not be listed.") from error
    return records


def read_flood_run(run_id: str) -> FloodRunRecord:
    try:
        canonical_id = str(uuid.UUID(run_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Rainfall scenario record was not found.") from error
    path = RUNS_PATH / f"{canonical_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Rainfall scenario record was not found.")
    try:
        return FloodRunRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Rainfall scenario record could not be read.") from error
