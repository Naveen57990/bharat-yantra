# Bharat Yantra

### An indigenous engineering engine for India

Bharat Yantra is a ward-scale decision laboratory for exploring public-service and emergency-planning choices on a mapped Mumbai testbed. It brings a 3D geospatial scene, transparent scenario tools, and an evidence-grounded assistant into one workspace.

> **Important:** This is an exploratory demonstration, not an operational government system. Its rainfall shortlist and runoff stress test are not flood forecasts. Shelter status, capacity, safety, and evacuation routes are not verified. Confirm all data and decisions with responsible authorities.

## What the demo can do

| Feature | What it shows | Important limit |
| --- | --- | --- |
| Ward digital twin | Provisional F/S Ward boundary, mapped roads, buildings, drains, facilities, terrain context, and map-linked overlays | Source currency, completeness, and reuse rights are still being reviewed |
| Rainfall screening | User-entered rainfall and duration change a ranked list of places for field inspection | Relative screening only; does not predict flooded places or water depth |
| Flood stress test | Transparent runoff arithmetic with adjustable assumptions | Illustrative assumptions; not a hydraulic simulation or validated flood model |
| Emergency access | Network-distance comparison under named hypothetical road closures | Road-node diagnostics, not travel-time, population-impact, or response forecasts |
| Budget planner | Compares candidate works, quantities, and editable cost assumptions on the map | Not an optimized investment recommendation; costs and benefits require validation |
| Health-facility access | Displays mapped health features and route options for exploration | Community-mapped data; operation and service capacity are not confirmed |
| Ward action tracker | Creates map-linked review tasks and records browser-local status | A planning checklist, not an official work-order system |
| Map assistant | Answers from project guidance and retrieved map evidence; can run a named road-closure scenario | No fine-tuning; it must not infer unavailable flood, safety, or operational facts |

The rainfall shortlist ranks mapped 250 m cells using relative terrain and mapped-drain evidence. Its demonstration count is `ceil(rainfall_mm / 50) + floor(duration_hours / 4)`, capped by available cells and 20. This makes the shortlist non-decreasing as duration grows for a fixed rainfall amount. The rule is illustrative, not calibrated to measured soil saturation or drainage capacity. See [the flood method](docs/flood_method.md).

## Architecture

```text
React + TypeScript + CesiumJS
             │
             ├── local geospatial source preview
             └── FastAPI service
                    ├── deterministic scenario calculations
                    ├── OSMnx / NetworkX road diagnostics
                    └── optional local Ollama assistant
```

Spatial preparation and quality inspection use Python GIS tools. Dataset provenance and known limitations are recorded in [`data/provenance/dataset_registry.csv`](data/provenance/dataset_registry.csv) and [`docs/feasibility.md`](docs/feasibility.md).

## Run locally

### Requirements

- Node.js and pnpm
- Python 3.11 or newer
- Optional: Ollama with a locally available model for the assistant

### Start the API

From the project root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

### Start the frontend

In another terminal:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

The local preview is intended for local inspection. See [`frontend/README.md`](frontend/README.md) and [`backend/README.md`](backend/README.md) for environment details and API endpoints.

## Repository guide

```text
backend/              FastAPI endpoints and deterministic planning logic
data/provenance/      Dataset inventory and provenance records
docs/                 Methods, feasibility, decisions, and assistant evidence rules
frontend/             React, TypeScript, and CesiumJS application
gis/                  GIS input inspection utilities
```

Large local datasets, generated reports, local run records, Cesium build assets, environment files, and machine-specific handoff notes are excluded from Git. The demo's source data may need to be acquired locally; see the provenance registry before using or redistributing any dataset.

## Data, licensing, and responsible use

- F/S Ward is a working development testbed, not a claim that the ward boundary is current or authoritative.
- Source-specific licensing, attribution, completeness, and publication status are recorded in the provenance materials. Sources marked `hold` and their derived outputs must not be published until reviewed.
- MCGM flood-location and temporary-shelter records are source records, not verified event observations or confirmation that a shelter is open, safe, or available.
- Never treat the app as an emergency warning, evacuation instruction, official budget recommendation, or operational system.
- This repository intentionally has no open-source license until the project owner has reviewed dataset and code publication rights.

## Project notes

- [Feasibility and data gates](docs/feasibility.md)
- [Flood methods and limitations](docs/flood_method.md)
- [Decision log](docs/DECISIONS.md)
- [Assistant evidence rules](docs/agent_knowledge.md)
- [Accessibility data quality](docs/accessibility_quality.md)
- [Backend setup and endpoints](backend/README.md)
- [Frontend setup](frontend/README.md)
