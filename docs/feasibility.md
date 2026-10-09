# Initial data feasibility note

- **Checked:** 7 October 2026
- **Status:** Preliminary desk review with local-only F/S boundary and drainage extracts, OSM road/building/facility data, Copernicus GLO-30 DSM, and a Google Open Buildings v3 footprint subset via Overture. No MCGM reuse rights or flood-validation pathway cleared.

## Finding

The first vertical slice can begin with source acquisition, structural inspection and Cesium display preparation, but neither the ward nor flood model inputs are ready to be declared. Publicly visible web services are evidence of a possible source, not permission to reuse or redistribute the underlying data. Acquired MCGM/OSM source snapshots are excluded from version control pending per-source licensing review.

## Ward boundary leads

- BMC/MCGM publishes an F/S ward plan as a PDF. It is an official reference lead, but the file is not yet established as a current machine-readable boundary, and its terms for digitizing, deriving and redistributing geometry need confirmation.
- MCGM’s official GIS REST service exposes a `Wards` polygon layer in EPSG:32643 and a `Storm Water Drainage` group with `Storm Water Manholes` and `Storm Water Drains` sublayers. The service description says its data source changed 26 June 2021 and credits “MCGM, Esri India.” The F/S polygon has been queried to local GeoJSON (one feature, `NAME=F/S`, output in WGS 84). The exact boundary vintage remains unconfirmed; rights are unresolved and it is excluded from version control. Drainage layer metadata and a local intersecting extract are now inspected; see below.
- A public ArcGIS `Mumbai_Ward_Boundary` feature layer exposes polygon features and fields including ward/area/population-like attributes. Its metadata says it was last edited in 2019; the hosting/source relationship to BMC and its license are not clear from the layer description. Do not publish or use as canonical boundary until source ownership, date, boundary definition and rights are confirmed. Attribute names alone do not establish the population data’s vintage or meaning.
- A university catalog lists Mumbai ward boundaries linked to Census 2011, but marks access as restricted. It is not a public fallback.

**Working-testbed decision (7 October 2026):** F/S Ward is selected for Stage 1 implementation because the existing local workspace contains one of the strongest assembled ward-level combinations available in this project: a municipal ward polygon, MCGM drainage/manhole records, MCGM flooding-spot and shelter context, OSM roads/buildings/health features, and a Copernicus DSM clip. This selection is for engineering focus and continuity; it is not a completed multi-ward scoring exercise, a claim that the local boundary is current or canonical, or a declaration that any source is approved for redistribution. Intersecting the current F/S polygon returns 1,971 MCGM manholes and 2,044 drain line features (1,048 marked `Existing`, 996 `Proposal`). The schema provides node IDs, conduit dimensions and invert-level values; 1,994 drain records have both end IDs represented in the manhole ID set. This is only an ID diagnostic, not proof of geometric connectivity, completeness, commission status or valid engineering elevations. MCGM terms, source vintage and meaning/datum of `mTHD` remain unresolved. The data and licensing gates therefore remain open. Do not treat electoral/prabhag boundaries, Census 2011 ward units and current administrative wards as interchangeable.

## Flood inputs and model readiness

An official Government of India overview of iFLOWS-Mumbai describes its design and 2020 pilot/testing phase, and reports use of a 20 cm DEM, 120 rain gauges, river-level data, land-use/infrastructure layers, bathymetry, drainage and coupled hydrologic/hydraulic/2D hydrodynamic modelling. This establishes that the documented system design depended on inputs materially richer than a generic public DEM. It does **not** establish the system’s current operating status or that its data, model configurations, outputs or rights are available to INDIA SIM.

Copernicus DEM GLO-30 Public 2021 tiles covering F/S were acquired from the public AWS bucket and clipped to a 1 km ward buffer in EPSG:32643. The source is explicitly a DSM including buildings, infrastructure and vegetation, at nominal 30 m. The local clip is 198 × 210 cells with 30 m pixels and 72.2% valid pixels within its rectangular output bounds. It is suitable for 3D/regional terrain context only, not street-scale drainage or flood depth. Required DLR/Airbus/EU/ESA attribution is recorded with the raster; full redistribution terms still need confirmation. NRSC’s public CartoDEM page says 30 m or coarser may be free to download, while finer postings have additional restrictions. Bhuvan/Bhoonidhi terms must be checked for the exact product and intended display/redistribution.

The official MCGM service exposes storm-water drain and manhole layers; intersecting feature counts and attributes have been inspected, but permission to reuse them, layer vintage, engineering accuracy and network completeness are not verified. OSM provided a 1 km buffered graph with 2,314 nodes/4,957 directed road edges, 4,886 building features and 98 mapped emergency-facility features. These are community-mapped, not authoritative or operational inventories. No independently usable ward-level observed inundation extent/depth, rainfall time series, river/tide boundary series, or road-closure observation has yet been verified for a selected ward. Therefore:

The ward-clipped OSM building preview contains 1,869 polygon footprints. Only 183 have `building:levels`, and only one has an explicit `height` tag. The map uses the explicit height where present, displays level-tagged structures as estimated massing at 3 m per mapped level, and leaves untagged footprints flat. This estimate is labeled in the interface and is not surveyed building height. Street-level imagery may help inspect visible conditions, but it cannot supply flood depths, drainage condition below ground, or current operational status. Mapillary is the preferred candidate for an imagery coverage audit; exact F/S coverage still needs checking with a developer access token. Google Street View is not suitable for display beside the Cesium map under the relevant non-Google map restriction, and its API requires a key and billing.

### BMC 3D city-model lead

BMC's 2023 tender for a city-scale 3D model describes a 3D reality mesh and LOD3 vector buildings, with aerial photogrammetry, LiDAR, terrestrial/mobile LiDAR and panoramic street imagery among the methods. The MyBMC app listing also describes the municipal 3D city-model initiative. These confirm a source-owner program exists, not that model files, F/S coverage, accuracy metadata or reuse rights are available to this project. No BMC 3D asset has been acquired. Treat this as a source-owner inquiry lead; do not scrape the app, infer building heights from screenshots, or use its imagery/model until the owner confirms access and permitted processing, display, derivative and redistribution uses.

### Acquired supplemental building footprints

Using the official Overture CLI and its latest catalog release (`2026-09-23.1`), a bounding-box query returned 13,034 building records; exact intersection with the provisional F/S polygon retained 8,749 features, of which 6,881 are sourced to Google Open Buildings v3 and 1,868 to OpenStreetMap. The new supplemental layer intentionally contains only the Google Open Buildings subset to avoid duplicating the separate OSM buildings layer. Its original record-level confidence values range from 0.65 to 0.9627; no local threshold has been applied. Google describes these as machine-detected footprints, reports omission/commission and alignment errors, and recommends location-specific confidence thresholds for target precision. None of the selected features carries height or floor attributes, so they render as flat footprints. The data contains no source imagery and is not street view. Raw and clipped files are local-only, `publication_status=hold`, with source and processing manifests under `data/`.

A query to the same release's `building_part` type returned one OSM-sourced record in the F/S bounding rectangle, tagged with 36 floors. Exact spatial intersection with the F/S boundary retained zero parts, so it is not used in the scene. Do not count nearby features as ward coverage.

### Satellite imagery context

The local Cesium preview now has an optional Esri World Imagery ArcGIS MapServer layer. The service returned tiles and source credits in browser testing; reported service credits are “Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community.” The imagery date, resolution and providers vary by location. It is a remote satellite/aerial imagery basemap, not street-level panorama imagery, a real-time feed, a building-height source, or flood-validation evidence. Tiles are not downloaded or cached by this project. Keep the layer optional and review the Esri service/product terms and attribution requirements before a public deployment.

- No Mumbai flood-depth simulation is currently authorized by the evidence in hand.
- No validation result or flood prediction claim is permitted.
- Keep the Cesium preview local-only while boundary, terrain and dataset rights are reviewed. The map is a source inspection surface; displaying a layer locally does not clear it for public distribution.
- Keep flood model choice open until the input inventory is real. SWMM or HEC-RAS cannot compensate for missing boundary conditions, drainage geometry or observations.

## Immediate acquisition tasks

1. MCGM Disaster Management layers 344 (Flooding Spots) and 232 (Temporary Shelters) have now been queried for F/S and saved as immutable GeoJSON snapshots in `data/raw/mcgm/disaster/`. The manifest records retrieval time, query, limitations and checksums. The local API/UI displays them as municipal context only. The source metadata did not establish reuse terms; review before publication.
2. Ask MCGM/Esri India for terms permitting processing and public derived outputs, plus source vintage, vertical datum, engineering definitions and completeness/commission status for layers 6 and 7.
3. Compare at least two wards with F/S against the criteria in the master spec, emphasizing independently dated historical flood evidence and permitted model inputs.
4. Contact the relevant official data owners for iFLOWS/MCGM terrain, rainfall, water levels and historical event observations; request permission scope covering processing, derived outputs, screenshots/video and repository release.
5. Identify a higher-resolution bare-earth/engineering terrain source, datum, vertical accuracy, posting, access route and terms. Reject flood modeling based only on the acquired DSM.
6. Freeze a dataset manifest and run `inspect_inputs.py` on approved files before model selection.

### MCGM disaster-context records retrieved — 7 October 2026

The official [MCGM GIS service](https://prsrvgisapp.mcgm.gov.in/server/rest/services/mcgm/MCGMGIS_Departments_Master_All_Layers/MapServer) returned 34 F/S flooding-spot polygons and 45 F/S temporary-shelter points. The flood feature record dates are not verified event dates; 19 names contain a deletion marker; the layer's depth units are unresolved. Shelter capacity, current status, flood safety and route safety are unavailable in the exposed schema. Accordingly, the interface labels them as records and listed locations, with no affected-area, open-shelter, or evacuation claims. See `data/raw/mcgm/disaster/manifest.json` and D-028 in `docs/DECISIONS.md`.

## Source references

- [MCGM F/S Ward plan](https://www.mcgm.gov.in/irj/go/km/docs/documents/MCGM%20Department%20List/Chief%20Engineer%20%28Development%20Plan%29/Sanctioned%20Revised%20Development%20Plan%201991/FS_WARD.pdf)
- [Official MCGM GIS MapServer](https://prsrvgisapp.mcgm.gov.in/server/rest/services/mcgm/MCGMGIS_Departments_Master_All_Layers/MapServer) and [layer catalog](https://prsrvgisapp.mcgm.gov.in/server/rest/services/mcgm/MCGMGIS_Departments_Master_All_Layers/MapServer/layers) — Wards, storm-water drains/manholes and service-level attribution/date metadata; no reuse authorization inferred.
- [Mumbai ward boundary ArcGIS service metadata](https://services9.arcgis.com/HITJUUAoBZFxCLou/ArcGIS/rest/services/Mumbai_Ward_Boundary/FeatureServer/layers)
- [Princeton catalog: Mumbai ward boundaries and 2011 census (restricted)](https://geo.nyu.edu/catalog/princeton-gb19f9251)
- [Government of India / NCCR overview of iFLOWS-Mumbai (PDF)](https://www.nccr.gov.in/sites/default/files/webpages_Mumbai.pdf)
- [NRSC CartoDEM product policy](https://www.nrsc.gov.in/nrscnew/Dataproducts_Thematic_cartodem.php?lang_code=en)
- [Bhoonidhi data terms](https://bhoonidhi.nrsc.gov.in/bhoonidhi/registration.html)
- [OpenStreetMap copyright/license](https://www.openstreetmap.org/copyright)
- [BMC 3D city model tender (2023)](https://www.mcgm.gov.in/irj/go/km/docs/documents/Tenders/ETH/ETH_8000054009_231023.pdf) — evidence of tender scope, not a dataset or reuse grant.
- [MyBMC 3D Mumbai app listing](https://play.google.com/store/apps/details?id=com.bmc3dmumbai.mapping) — evidence of a public-facing app/program, not permission to extract or reuse its content.
- [Overture Maps official catalog access](https://docs.overturemaps.org/getting-data/cloud-sources/) and [Python client](https://docs.overturemaps.org/getting-data/overturemaps-py/) — query methods and release structure.
- [Google Open Buildings v3](https://sites.research.google/gr/open-buildings/) — fields, coverage, licensing options, confidence thresholds, and known limitations.
- [Overture building schema](https://docs.overturemaps.org/schema/reference/buildings/building/) — semantics of footprint, height, and floor fields.
- [Cesium ArcGIS MapServer imagery provider](https://cesium.com/learn/cesiumjs/ref-doc/ArcGisMapServerImageryProvider.html) — supported provider and attribution behavior.
- [Esri World Imagery MapServer](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer) — tested layer endpoint and service metadata.
- [Esri service terms](https://www.esri.com/en-us/legal/terms/web-site-service) and [data attribution terms](https://www.esri.com/en-us/legal/terms/data-attributions) — review before public use.

Recheck terms on the specific resource before acquisition; this note is a dated source review, not legal advice.
