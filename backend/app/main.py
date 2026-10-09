from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .agent import explain_saved_run, local_model_status
from .disaster_data import municipal_flood_context
from .flood import IllustrativeFloodModelRequest, RainfallScenarioRequest, calculate_rainfall_scenario, flood_evidence, municipal_record_overlap_diagnostic, rainfall_series, relative_screening_areas
from .flood_runs import FloodRunRecord, create_illustrative_model_run, create_rainfall_run, list_flood_runs, read_flood_run
from .preparedness import PreparednessPlanRequest, create_preparedness_plan, read_preparedness_plan
from .investments import InvestmentPlanRequest, create_investment_plan
from .decisions import DecisionSaveRequest, create_decision_record, read_decision_record

from .accessibility import (
    AccessRunRequest,
    AccessRunResult,
    AccessSummary,
    ClosureOption,
    FacilityRoutesRequest,
    FacilityRoutesResult,
    get_closure_options,
    get_nearby_facility_routes,
    get_summary,
    read_access_run,
    run_road_closure,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "data" / "provenance" / "dataset_registry.csv"


class DatasetStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dataset_id: str
    title: str
    provider: str
    source_version_or_date: str
    retrieved_at: str
    license_name: str
    attribution: str
    processing_permission: str
    redistribution_permission: str
    publication_status: str
    geometry_or_raster: str
    crs_or_datum: str
    spatial_resolution: str
    temporal_coverage: str
    quality_notes: str


class WardCandidate(BaseModel):
    id: str
    name: str
    status: Literal["candidate", "selected"]
    boundary_dataset_id: str
    flood_validation: Literal["not_verified", "available"]
    readiness: list[str]


class ToolCapability(BaseModel):
    name: str
    status: Literal["available", "blocked"]
    reason: str


class ServiceStatus(BaseModel):
    status: str
    flood_simulation_outputs_available: bool
    exploratory_accessibility_available: bool
    ai_agent_enabled: bool


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=800)
    run_id: str | None = Field(default=None, min_length=36, max_length=36)
    flood_run_id: str | None = Field(default=None, min_length=36, max_length=36)
    flood_model_run_id: str | None = Field(default=None, min_length=36, max_length=36)
    preparedness_run_id: str | None = Field(default=None, min_length=36, max_length=36)
    investment_run_id: str | None = Field(default=None, min_length=36, max_length=36)
    investment_option_id: str | None = Field(default=None, max_length=40)
    decision_id: str | None = Field(default=None, min_length=36, max_length=36)


class AgentAskResponse(BaseModel):
    answer: str
    run_id: str | None = None
    new_run: dict | None = None
    model: str
    provider: str
    tools_used: list[str]
    model_tools_invoked: list[str] = Field(default_factory=list)
    evidence_sources: list[str]
    evidence_data: dict | None = None
    flood_scenario: dict | None = None
    flood_area_screening: dict | None = None
    flood_run_record: dict | None = None
    flood_model_run_record: dict | None = None
    preparedness_plan_record: dict | None = None
    decision_record: dict | None = None
    investment_option: dict | None = None


app = FastAPI(
    title="Bharat Yantra Evidence API",
    version="0.1.0",
    description=(
        "Local development API for traceable ward/dataset status and exploratory OSM road-network analysis. "
        "No calibrated hydraulic flood prediction is available. Flood endpoints expose local rainfall/drainage/terrain evidence, relative field-review cells, rainfall-volume arithmetic, and an opt-in assumption-based runoff-budget demonstration. Demonstration outputs are not observed impacts, validated predictions, or evacuation instructions."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _read_registry() -> list[DatasetStatus]:
    if not REGISTRY_PATH.is_file():
        raise HTTPException(status_code=503, detail="Dataset provenance registry is unavailable.")

    try:
        with REGISTRY_PATH.open(encoding="utf-8", newline="") as registry_file:
            rows = csv.DictReader(registry_file)
            return [DatasetStatus.model_validate(row) for row in rows]
    except (OSError, csv.Error, ValueError) as error:
        raise HTTPException(status_code=503, detail="Dataset provenance registry could not be read.") from error


@app.get("/api/v1/health", response_model=ServiceStatus, tags=["service"])
def health() -> ServiceStatus:
    agent_status = local_model_status()
    return ServiceStatus(
        status="ready",
        flood_simulation_outputs_available=False,
        exploratory_accessibility_available=True,
        ai_agent_enabled=bool(agent_status["ready"]),
    )


@app.get("/api/v1/wards", response_model=list[WardCandidate], tags=["evidence tools"])
def list_wards() -> list[WardCandidate]:
    return [
        WardCandidate(
            id="fs-mumbai-provisional",
            name="F/S Ward, Mumbai",
            status="candidate",
            boundary_dataset_id="bmc_fs_boundary",
            flood_validation="not_verified",
            readiness=[
                "Boundary vintage and reuse terms are unresolved.",
                "Terrain product and vertical datum are not verified for flood modeling.",
                "No independent ward-level flood observations are available in this workspace.",
                "Rainfall, water-level boundary conditions, and drainage-network validity are unresolved.",
            ],
        )
    ]


@app.get("/api/v1/datasets", response_model=list[DatasetStatus], tags=["evidence tools"])
def get_dataset_status() -> list[DatasetStatus]:
    return _read_registry()


@app.get("/api/v1/accessibility/summary", response_model=AccessSummary, tags=["accessibility"])
def accessibility_summary() -> AccessSummary:
    return get_summary()


@app.get("/api/v1/flood/evidence", tags=["flood evidence"])
def flood_data_readiness() -> dict:
    return flood_evidence()


@app.get("/api/v1/flood/municipal-context", tags=["flood evidence"])
def flood_municipal_context() -> dict:
    return municipal_flood_context()


@app.get("/api/v1/flood/record-overlap-diagnostic", tags=["flood evidence"])
def flood_record_overlap_diagnostic() -> dict:
    return municipal_record_overlap_diagnostic()


@app.get("/api/v1/flood/rainfall", tags=["flood evidence"])
def flood_rainfall_series(district: str = "MUMBAI CITY") -> dict:
    return rainfall_series(district)


@app.post("/api/v1/flood/screening-scenario", tags=["flood evidence"])
def flood_rainfall_screening(request: RainfallScenarioRequest) -> dict:
    return calculate_rainfall_scenario(request)


@app.post("/api/v1/flood/runs", response_model=FloodRunRecord, tags=["flood scenarios"])
def create_saved_flood_run(request: RainfallScenarioRequest) -> FloodRunRecord:
    return create_rainfall_run(request)


@app.get("/api/v1/flood/runs", response_model=list[FloodRunRecord], tags=["flood scenarios"])
def get_saved_flood_runs(limit: int = 20) -> list[FloodRunRecord]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    return list_flood_runs(limit)


@app.get("/api/v1/flood/runs/{run_id}", response_model=FloodRunRecord, tags=["flood scenarios"])
def get_saved_flood_run(run_id: str) -> FloodRunRecord:
    return read_flood_run(run_id)


@app.get("/api/v1/flood/screening-areas", tags=["flood evidence"])
def flood_screening_areas() -> dict:
    return relative_screening_areas()


@app.post("/api/v1/flood/illustrative-model", tags=["flood evidence"])
def flood_illustrative_model(request: IllustrativeFloodModelRequest) -> dict:
    saved = create_illustrative_model_run(request)
    result = dict(saved.outputs)
    result["saved_run"] = saved.model_dump()
    return result


@app.post("/api/v1/preparedness/plans", tags=["preparedness planning"])
def create_preparedness_action_plan(request: PreparednessPlanRequest) -> dict:
    return create_preparedness_plan(request)


@app.get("/api/v1/preparedness/plans/{run_id}", tags=["preparedness planning"])
def get_preparedness_action_plan(run_id: str) -> dict:
    return read_preparedness_plan(run_id)


@app.post("/api/v1/investments/compare", tags=["government investment simulator"])
def compare_investment_options(request: InvestmentPlanRequest) -> dict:
    return create_investment_plan(request)


@app.post("/api/v1/decisions", tags=["decision simulator"])
def save_decision_comparison(request: DecisionSaveRequest) -> dict:
    return create_decision_record(request)


@app.get("/api/v1/decisions/{decision_id}", tags=["decision simulator"])
def get_decision_comparison(decision_id: str) -> dict:
    return read_decision_record(decision_id)


@app.get("/api/v1/accessibility/closure-options", response_model=list[ClosureOption], tags=["accessibility"])
def accessibility_closure_options() -> list[ClosureOption]:
    return get_closure_options()


@app.post("/api/v1/accessibility/routes", response_model=FacilityRoutesResult, tags=["accessibility"])
def nearby_facility_routes(request: FacilityRoutesRequest) -> FacilityRoutesResult:
    return get_nearby_facility_routes(request)


@app.post("/api/v1/accessibility/runs", response_model=AccessRunResult, tags=["accessibility"])
def create_accessibility_run(request: AccessRunRequest) -> AccessRunResult:
    return run_road_closure(request.road_names or request.road_name or [])


@app.get("/api/v1/accessibility/runs/{run_id}", response_model=AccessRunResult, tags=["accessibility"])
def get_accessibility_run(run_id: str) -> AccessRunResult:
    return read_access_run(run_id)


@app.get("/api/v1/agent/status", tags=["local AI agent"])
def get_agent_status() -> dict[str, str | bool]:
    return local_model_status()


@app.post("/api/v1/agent/ask", response_model=AgentAskResponse, tags=["local AI agent"])
def ask_agent(request: AgentAskRequest) -> AgentAskResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Enter a question about the map or a saved scenario.")
    from .agent import answer_map_question
    result = answer_map_question(question, request.run_id, request.flood_run_id, request.flood_model_run_id, request.preparedness_run_id, request.decision_id, request.investment_run_id, request.investment_option_id)
    return AgentAskResponse.model_validate(result)


@app.get("/api/v1/agent/capabilities", response_model=list[ToolCapability], tags=["agent contract"])
def agent_capabilities() -> list[ToolCapability]:
    agent_status = local_model_status()
    return [
        ToolCapability(name="get_map_guide", status="available" if agent_status["ready"] else "blocked", reason="Reads the curated map guide and local provenance registry; it cannot claim unresolved source rights are cleared."),
        ToolCapability(name="list_mapped_health_facilities", status="available" if agent_status["ready"] else "blocked", reason="Reads mapped OSM health features from the local ward extract; operational status is not verified."),
        ToolCapability(name="list_named_roads", status="available" if agent_status["ready"] else "blocked", reason="Reads exact closure options from the local road graph."),
        ToolCapability(name="screen_rainfall_load", status="available", reason="Deterministically calculates mean rainfall rate and gross rain volume from user-entered depth/duration and provisional ward area; it does not simulate flooding."),
        ToolCapability(name="get_saved_rainfall_run", status="available", reason="Reads the selected versioned rainfall-volume run and its exact inputs, output, method version, timestamp and boundary checksum; it does not report flood impacts."),
        ToolCapability(name="screen_relative_terrain_drainage", status="available", reason="Returns local relative terrain and mapped Existing-drain evidence cells for field verification only; it does not predict impacts or evacuation destinations."),
        ToolCapability(name="compare_government_investment_options", status="available", reason="Compares demo-budget options at mapped drainage-review cells, OSM road points and OSM health-access review points; rates and benefits are clearly limited and no public outcome is predicted."),
        ToolCapability(name="create_scenario", status="blocked", reason="No validated scenario schema or reproducible simulation baseline exists yet."),
        ToolCapability(name="run_flood_scenario", status="blocked", reason="No defensible flood model inputs or verified simulation engine are available."),
        ToolCapability(name="run_named_road_closure", status="available" if agent_status["ready"] else "blocked", reason="Runs only after the user explicitly asks to simulate/test a named hypothetical closure, and only for an exact locally available road name."),
        ToolCapability(
            name="get_current_accessibility_run",
            status="available" if agent_status["ready"] else "blocked",
            reason=(
                "The local model may inspect a user-selected saved run to explain its evidence and limitations."
                if agent_status["ready"] else str(agent_status["message"])
            ),
        ),
        ToolCapability(name="compare_runs", status="blocked", reason="No validated hydrologic simulation runs or performance outcomes exist to compare."),
        ToolCapability(name="get_validation", status="blocked", reason="Independent flood and road-closure validation evidence has not been verified."),
    ]
