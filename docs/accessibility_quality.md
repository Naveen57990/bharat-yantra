# OSM accessibility graph: quality notes

- **Status:** local exploratory analysis, not independently validated.
- **Source snapshot:** OpenStreetMap via OSMnx/Overpass, retrieved 2026-10-07.
- **Ward:** provisional MCGM F/S boundary; boundary vintage and reuse terms remain unresolved.

## Snapshot and graph checks

| Check | Result |
|---|---:|
| Road graph nodes in the 1 km buffered extract | 2,314 |
| Directed road-edge records in the extract | 4,957 |
| Road-edge records intersecting the provisional ward polygon | 2,004 |
| Road graph nodes inside the provisional ward | 877 |
| Weakly connected components in the buffered directed graph | 18 |
| Strongly connected components in the buffered directed graph | 70 |
| Ward nodes in the largest weakly connected component | 867 / 877 |
| OSM-mapped health features inside the ward (hospital, clinic, doctors) | 28 |
| Health features represented as points / polygons | 20 / 8 |
| Unique road nodes used to represent those 28 facilities | 24 |
| Facility representative-point snap distance to nearest road node | median 49.7 m; p90 81.5 m; max 164.8 m |
| Baseline ward nodes with a directed route to at least one mapped health feature | 862 / 877 (98.29%) |

The graph uses OSMnx `drive` network edges and their stored metre-length weights. The median absolute relative difference between those edge lengths and projected line-geometry lengths was 0.17%; the 95th percentile was 0.43%. This is an internal consistency check, not an external validation of road position or length.

## What the analysis measures

For each road-graph node inside the provisional ward, the API finds the shortest directed path to the nearest OSM-mapped hospital, clinic, or doctors feature inside the ward. Each road node counts once. It does not represent residents, trips, demand, road capacity, traffic, speed, travel time, emergency priority, an actual closure, or a verified facility inventory.

A what-if closure removes every directed OSM edge record with the selected road name whose geometry intersects the ward polygon. The red overlay shows the corresponding mapped line geometry, with exact duplicate geometries drawn once; the persisted run retains the directed edge IDs. It is an explicit scenario assumption, not a live road status.

The run also returns a point feature for each ward road-graph node that was reachable in the baseline but is unreachable after the hypothetical closure. The app draws these as ground-clamped markers and identifies them as road-network nodes, not people, households, or demand. The Acharya Donde Marg example returns 44 such point features. They are an explanatory visualization of the model output, not a count of affected residents.

## Quality limits and next checks

- Ten ward road nodes lie outside the largest weakly connected component; directionality and incomplete mapping can also prevent routes inside the largest component.
- The 28 health features include 8 polygons. Their representative points are only a consistent snapping proxy; actual public entrances and driveways are not identified. The maximum snap distance is about 165 m.
- The 1 km buffered extract can truncate a detour that would leave the downloaded graph extent.
- OSM completeness/currentness and MCGM boundary currentness are not verified. Municipal and ODbL-derived data reuse terms remain under review; do not publish the run artifacts until the provenance review clears them.
- No observed journeys, facility access records, field-verified closures, population/trip demand, or authoritative facility inventory are available to validate this result.

Before using these metrics in a decision, inspect disconnected components and facility snaps against authoritative/local evidence, acquire a wider road graph if boundary detours matter, and define validation against observed access or route data. The output should remain an exploratory what-if until those checks exist.

## Scenario overlay check

The Acharya Donde Marg UI scenario was manually exercised after adding the newly-unreachable node overlay. It returned 57 directed edge IDs, 55 unique displayed closure lines, and 44 newly-unreachable node points; the browser showed the baseline/scenario comparison and no Cesium render error. Closure strokes are thick screen-space lines; impact nodes use ground-clamped ellipses. Browser rendering was checked on the current local app only and is not a cross-device performance validation.

## Local AI explanation check

The device has Ollama and the `qwen3:8b` model installed. The API status endpoint confirmed the local model was ready. A tool-grounded request to explain a saved Acharya Donde Marg run successfully called `get_current_accessibility_run`. The first model answer incorrectly called a mean distance change a median, so the assistant was changed to avoid all numerical claims in generated prose and to retry/reject answers that contain numbers or numeric terms. Exact numeric facts remain in deterministic UI fields and are not authored by the model. A second local answer passed the guard. This reduces one observed failure mode but does not guarantee that all qualitative model statements are correct; use the saved run and its caveats as evidence.
