# Bharat Yantra frontend

React + TypeScript with CesiumJS. The interface is branded Bharat Yantra, “An indigenous engineering engine for India.” The local scene previews the selected Stage 1 working testbed's provisional F/S boundary, OSM roads/building footprints/facilities, MCGM drains/manholes, separately identified MCGM flood/shelter records, and relative terrain/drain review cells. Rainfall input produces saved uniform-rain gross-volume arithmetic; the optional runoff-budget panel remains an explicit assumption demonstration. Neither is a validated flood prediction. The budget planner saves multiple options on this device, compares their costs and planned quantities, and draws only the selected option's proposed works on the map. The Ward Action Tracker turns selected preparedness-plan outputs into up to eight map-linked tasks with browser-local status labels; it does not create official assignments. Local-source routes read from the project `data/` directory at request time in development or local-demo preview; the GeoJSON/raster files are not copied into the production bundle. The globe still uses Cesium's ellipsoid because the acquired DSM has not yet been converted to Cesium terrain tiles. Exact dependency versions are installed with pnpm and recorded in `pnpm-lock.yaml`.

## Local setup

```sh
pnpm install --frozen-lockfile
```

Optional hosted-source variables can be set in `.env.local` only after a dataset and its intended use are approved:

```dotenv
VITE_WARD_BOUNDARY_URL=/data/approved-ward.geojson
VITE_WARD_BOUNDARY_NAME=Verified ward name
VITE_WARD_BOUNDARY_ATTRIBUTION=Required attribution text
VITE_TERRAIN_URL=/terrain/approved-terrain
VITE_TERRAIN_ATTRIBUTION=Required terrain attribution
```

`VITE_TERRAIN_URL` must point to a Cesium terrain service (Quantized Mesh or Height Map) and be authorized for the deployment. The current Copernicus clip is a DSM GeoTIFF, not a terrain service; conversion and data-layer integration remain a build task. The app only shows configured attribution text; the dataset owner must supply the exact required notice. Do not set a URL merely to make the scene look complete.

Run with `pnpm dev` for the local source preview. The production build now includes the current F/S ward map package under `public/local-data/` and enables it through `.env.production`, so a static host such as Vercel can show the boundary, roads, building footprints, facilities, drains, manholes, and display-only elevation context. These public files are served to every site visitor; review `data/provenance/dataset_registry.csv` and confirm applicable terms before public release. The map data remains a dated snapshot, not a live feed.

The interactive simulation, routing, saved plans, and assistant still require a separately hosted FastAPI service. Set `VITE_API_BASE_URL` to that service in the hosting project's build environment and configure its CORS allowlist for the deployed site. A frontend-only Vercel deployment cannot run local Ollama or use local `data/` paths. See the parent Bharat Yantra README and `docs/feasibility.md` for source status and limitations.

The local preview binds to `127.0.0.1` and displays MCGM/Esri and OpenStreetMap attribution. MCGM source rights, boundary vintage, drainage vertical datum and source completeness remain unverified; the preview is for local inspection, not publication or operational use.
