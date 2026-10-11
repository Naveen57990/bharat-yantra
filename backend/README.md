# Bharat Yantra backend

This local FastAPI service exposes ward/dataset provenance, exploratory OSM road-network diagnostics, and an evidence-grounded local assistant. Ollama runs at `127.0.0.1:11434`; the default model is `qwen3:8b`, configurable with `INDIA_SIM_LOCAL_MODEL`. Questions and map evidence stay on this device. There is no fine-tuning: the assistant is grounded by `docs/agent_knowledge.md` and deterministic data retrieval.

The assistant can explain map symbols and data limits, retrieve actual locally mapped health features, read exact road options, inspect selected saved road or rainfall runs, and execute a named hypothetical road-closure run only when the user explicitly requests a simulation/test and names exactly one available road. Selected rainfall explanations include the stored values and boundary checksum; scope-violating model prose is replaced with a factual explanation. It returns the saved road run and GeoJSON so the frontend can update the map. It has no arbitrary file, shell, or external tool access.

The map assistant does not make flood, travel-time, emergency-response, operational-facility, or official policy claims. OSM roads/facilities and municipal layers remain locally held pending source-specific rights and data-quality review. Road nodes are not residents or demand. The F/S municipal-context endpoint returns a sanitized snapshot of 34 MCGM flooding-spot records and 45 listed temporary shelters. These are not confirmed event observations or current operational facilities; no verified capacity, opening status, safe route, or flood prediction is supplied. A deterministic gross-rainfall calculation can be saved as a versioned local run; it does not simulate runoff or flooding. The optional runoff-budget demonstration remains assumption-based, and independent flood validation is not implemented.

## Run locally

From the project root:

```sh
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

The service binds to loopback by default. API documentation is available at `http://127.0.0.1:8000/docs`.

## Deterministic workflow tests

From the repository root, run:

```sh
./.venv/bin/python -m unittest discover -s backend/tests -v
./.venv/bin/python -m compileall -q backend/app backend/tests
```

The suite uses the checked-in local extracts and temporary directories for run records. It makes no external calls. It verifies core calculations and route behavior, not source accuracy, facility operations, flood model validity, or emergency readiness. These local data derivatives remain subject to the held source terms in `data/provenance/dataset_registry.csv`.

## Current endpoints

- `GET /api/v1/health` — service status and flood-output availability.
- `GET /api/v1/flood/municipal-context` — local MCGM F/S flooding-spot and listed temporary-shelter records with provenance and limitations.
- `POST /api/v1/flood/runs` — calculate and persist uniform gross rainfall volume with input values, model version, boundary dataset ID, and boundary checksum.
- `GET /api/v1/flood/runs?limit=20` — list recent local rainfall runs (limit 1–100).
- `GET /api/v1/flood/runs/{run_id}` — retrieve one saved rainfall run.
- `GET /api/v1/wards` — F/S as a provisional candidate, with unresolved readiness items.
- `GET /api/v1/datasets` — provenance registry rows.
- `GET /api/v1/agent/capabilities` — available and blocked assistant capabilities.
- `GET /api/v1/accessibility/summary` — baseline directed road-network distance diagnostics.
- `GET /api/v1/accessibility/closure-options` — exact local named-road options.
- `POST /api/v1/accessibility/runs` — compute and persist a named hypothetical closure run.
- `GET /api/v1/accessibility/runs/{run_id}` — retrieve a locally stored manifest.
- `GET /api/v1/agent/status` — report local Ollama readiness.
- `POST /api/v1/agent/ask` — ask about the map, a selected run, facilities, or explicitly request a named hypothetical road test; `run_id` is optional.

Run manifests are stored under `data/runs/accessibility/` and remain local. Data-derived publication status is governed by `data/provenance/dataset_registry.csv`.
Flood rainfall run records are stored under `data/runs/flood/`; each record contains its inputs and deterministic output and is explicitly labelled as not a flood prediction.
