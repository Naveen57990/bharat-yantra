from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .accessibility import read_access_run
from .preparedness import read_preparedness_plan
from .paths import PROJECT_ROOT, RUNS_ROOT

RUNS_PATH = RUNS_ROOT / "decisions"


class DecisionSaveRequest(BaseModel):
    decision_type: Literal["road_closure", "preparedness"]
    source_run_id: str = Field(min_length=36, max_length=36)
    option_id: str | None = None


def create_decision_record(request: DecisionSaveRequest) -> dict[str, Any]:
    if request.decision_type == "road_closure":
        run = read_access_run(request.source_run_id)
        baseline, proposal = run.baseline.model_dump(), run.scenario.model_dump()
        delta = {
            "route_coverage_percentage_points": round(proposal["route_coverage_percent"] - baseline["route_coverage_percent"], 2),
            "newly_unreachable_road_nodes": run.change.get("newly_unreachable_road_nodes", 0),
            "mean_network_distance_change_m_on_common_nodes": run.change.get("mean_distance_change_on_common_nodes_m", 0),
        }
        title = f"Test closing {run.road_name}"
        outputs = {"baseline": baseline, "proposal": proposal, "measured_change": delta, "comparison_basis": "Shortest directed OSM road-network distance from each ward road node to the nearest mapped health feature; road nodes equally weighted."}
        pros = [f"The selected closure test changes modelled route coverage by {delta['route_coverage_percentage_points']:+.2f} percentage points for mapped road nodes."]
        cons = [f"{delta['newly_unreachable_road_nodes']} mapped road nodes lose a directed path to an OSM-mapped health feature in this hypothetical network test."]
        limitations = [*run.assumptions, *run.limitations, "Road nodes are not people or households; distance is not travel time; mapped facilities are not verified operational.", "This is not a live road closure or an official recommendation."]
        source_run_id = run.run_id
    else:
        if not request.option_id:
            raise HTTPException(status_code=422, detail="Choose a preparedness option before saving the decision.")
        plan = read_preparedness_plan(request.source_run_id)
        option = next((item for item in plan["options"] if item["id"] == request.option_id), None)
        if option is None:
            raise HTTPException(status_code=404, detail="Preparedness option was not found in this saved plan.")
        budget = plan["inputs"]["budget_inr"]
        outputs = {"budget_inr": budget, "estimated_allocation_inr": option["estimated_allocation_inr"], "unallocated_inr": option["unallocated_inr"], "mapped_check_count": option["mapped_actions"], "workstreams": [{"name": work["workstream"], "planned_count": work["planned_count"], "available_count": work["available_count"], "estimated_allocation_inr": work["estimated_allocation_inr"]} for work in option["workstreams"]]}
        title = option["name"]
        pros = [f"This option maps {option['mapped_actions']} source-backed checks for field verification.", f"It leaves ₹{option['unallocated_inr']:,.0f} unallocated within the entered budget."]
        cons = ["This option does not estimate avoided losses, flood reduction, people protected, safe routes, or shelter readiness.", "Cost allowances are editable demonstration assumptions, not verified municipal rates."]
        limitations = [*plan["limitations"], plan["method"]]
        source_run_id = plan["run_id"]
    record = {"decision_id": str(uuid.uuid4()), "created_at_utc": datetime.now(timezone.utc).isoformat(), "decision_type": request.decision_type, "title": title, "source_run_id": source_run_id, "option_id": request.option_id, "outputs": outputs, "pros_supported_by_outputs": pros, "cons_and_unknowns": cons, "limitations": limitations}
    try:
        RUNS_PATH.mkdir(parents=True, exist_ok=True)
        path = RUNS_PATH / f"{record['decision_id']}.json"
        temporary = RUNS_PATH / f".{record['decision_id']}.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        raise HTTPException(status_code=503, detail="Could not save the decision comparison.") from error
    return record


def read_decision_record(decision_id: str) -> dict[str, Any]:
    try:
        canonical_id = str(uuid.UUID(decision_id))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Decision comparison was not found.") from error
    path = RUNS_PATH / f"{canonical_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Decision comparison was not found.")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail="Decision comparison could not be read.") from error
    return record
