# Judge guide

## Open the prototype

**Live demo:** [bharat-yantra.vercel.app](https://bharat-yantra.vercel.app/)  
**Source code:** [github.com/Naveen57990/bharat-yantra](https://github.com/Naveen57990/bharat-yantra)

Bharat Yantra is a Mumbai ward-planning prototype. It puts a map beside practical what-if tools so a planner can inspect mapped evidence, compare a scenario, and see which assumptions remain uncertain.

## A five-minute guided test

Use a desktop browser and allow the map a few seconds to load. The app can also be run locally using [the setup guide](../README.md#run-locally).

1. **Orient on the map.** Open the F/S Ward map and expand Layers. Toggle visible map layers and point out that the study area and source status are provisional.
2. **Try rainfall screening.** Open Rainfall planning, use 150 mm over 8 hours, and run the screening. The app ranks locations for field inspection using an illustrative terrain-and-drainage rule and highlights those locations on the map. They are not predicted flood locations.
3. **Compare an access disruption.** Open Emergency access, choose a named road closure, and run it. Compare the mapped-road network diagnostic with the baseline, then inspect the closure and affected network points on the map. Graph nodes are not people; the result is not travel time or emergency response performance.
4. **Inspect facility access.** Select a mapped origin and nearby mapped health features. Review the displayed network distances and route overlays. These are community-mapped locations; current operations, capacity, and real travel conditions are unverified.
5. **Make a planning comparison.** Open Budget planner, change the envelope and a work quantity/rate, and compare candidate work locations. The rates are editable planning assumptions; no benefit or official recommendation is inferred.
6. **Review a decision.** Save or open an action tracker item and use its map highlight/status controls. Optionally ask the Map assistant a short question about the visible result; if its local model is unavailable, the deterministic tools remain usable.

## How to verify the prototype

The backend workflow tests use the local snapshot and make no external calls:

```sh
./.venv/bin/python -m unittest discover -s backend/tests -v
./.venv/bin/python -m compileall -q backend/app backend/tests
cd frontend && pnpm install --frozen-lockfile && pnpm build
```

For an API smoke check, start the backend using [the local setup instructions](../README.md#run-locally), then visit `/api/v1/health`, `/api/v1/datasets`, `/api/v1/accessibility/closure-options`, and `/api/v1/flood/evidence` on `http://127.0.0.1:8000`. The automated checks cover deterministic calculations and endpoint behavior; they do not verify source accuracy, dataset permission, shelter readiness, or flood-model validity.

## Read the results correctly

| Feature | What the prototype calculates or displays | What it does not establish |
| --- | --- | --- |
| Rainfall screening | A ranked field-review shortlist from an illustrative rule and mapped terrain/drain evidence | Flood extent, depth, timing, affected homes, or a forecast |
| Road closure | A change in connectivity across a local mapped road graph | Residents affected, vehicle travel time, live closure status, or emergency response |
| Health access | Routes/distances in that graph to mapped health features | Facility operation, capacity, clinical suitability, or a safe evacuation destination |
| Budget planner | Arithmetic over user-entered quantities and editable rates, with candidate map locations | Tender prices, optimized works, or measured benefits |
| Preparedness and action tracker | Review tasks and local status tracking | Official assignments, shelter readiness, or authorization to act |
| Map assistant | Evidence retrieval and bounded explanations; optional local Ollama model | Independent verification, a trained municipal model, or authority to recommend policy |

This is a demonstration for discussion and field review. It is not an emergency warning, flood forecast, evacuation instruction, validated engineering analysis, official budget recommendation, or operational government service. Use current official information and qualified departments for real decisions.

## Data and publication status

The map is a local source preview. Its layers have different sources, dates, quality, and terms. See [`data/provenance/dataset_registry.csv`](../data/provenance/dataset_registry.csv) and the [data limitations](../README.md#data-and-responsible-use). The registry currently marks all 19 records `hold`; some derived files are tracked in the public repository and served to the prototype. The code's MIT license does not grant rights to those datasets. Public redistribution and operational use must not be inferred from the availability of the site or repository. This status needs to be resolved by the project owner before representing the data bundle as rights-cleared.

## Project and implementation

- **Project:** Bharat Yantra — *An indigenous engineering engine for India*.
- **Prototype scope:** one provisional Mumbai F/S Ward testbed; React/TypeScript and CesiumJS client; FastAPI/Python service; deterministic scenario calculations; local road-graph diagnostics; optional local Ollama assistant.
- **Evidence discipline:** modelled outputs, mapped records, assumptions, and unknowns are labelled separately. The assistant is not fine-tuned on municipal data.
- **Architecture and setup:** [README](../README.md), [backend guide](../backend/README.md), [frontend guide](../frontend/README.md), [flood method](flood_method.md), [decision log](DECISIONS.md).

