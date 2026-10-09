# Flood lab: current method and evidence limits

## What the current what-if answers

The interface accepts a rainfall depth (mm) and duration (hours). It computes:

- Mean rainfall rate = entered depth / entered duration.
- Gross rainfall volume = entered depth in metres × area of the local provisional F/S polygon in square metres.

The local polygon area is measured after projection to EPSG:32643 and is approximately 9.631 km². The calculation assumes that the entered rainfall depth is spatially uniform across that polygon. Thus 150 mm over 8 hours yields a mean rate of 18.75 mm/hour and approximately 1,444,631 m³ of gross rain over the polygon. These are arithmetic screening values, not runoff, drain inflow, stored water, flood depth, or a predicted inundation extent.

The rainfall amount/duration are user-selected what-if inputs. The app does not assert that this storm occurred or is forecast.

## Municipal AWS source availability

BMC's Disaster Management public site exposes a station selector labeled “Last 15 minutes data” and rainfall accumulations for 1, 3, 6 and 24 hours. On 7 October 2026, the selector `Hindmata Cinema` resolved to station `F South Ward Office` and displayed zero rainfall in those windows. The same page showed weather values but no exact sensor observation timestamp. The station map popup for that station displayed zeros in all weather fields, conflicting with the home-page station selector. A manually transcribed snapshot and the conflicting view are documented in `data/raw/mcgm/weather/aws_public_ui_snapshot_2026-10-07.json`; neither is used in the rainfall calculations. A complete, timestamped station history or documented data endpoint and reuse terms are needed before BMC AWS observations can drive a model or be added as a live integration. BMC's 2024–25 Environment Status Report describes 120 installed AWS and weather parameters refreshed every 15 minutes; this establishes service capacity, not access to a historical ward series. See the official [BMC Disaster Management page](https://dm.mcgm.gov.in/) and [Environment Status Report 2024–25](https://r3app.mcgm.gov.in/irj/go/km/docs/documents/MCGM%20Department%20List/Environment/Docs/Environment%20Status%20Report%20%202024-25%20%28English%29.pdf).

## Relative terrain/drain field-review screen

The local processing script divides the provisional polygon into clipped cells with a nominal 250 m grid. For each cell it measures the Copernicus DSM 10th percentile (P10), valid pixel count, mapped MCGM `Existing` drain-line length and mapped `Proposal` drain-line length separately. It also records the nearest named OSM road as a location cue. The app flags a cell only when its P10 is at or below the ward-grid 25th percentile and its mapped Existing-drain length density is at or below that metric's ward-grid 25th percentile. Proposal drains are never counted as Existing coverage.

Current run: 194 cells; terrain P10 lower-quartile threshold 4.700 source metres; mapped Existing-drain-density lower-quartile threshold 0.000 km/km²; 36 cells meet both criteria. One low-P10 example is cell `FS-R02C13`, nearest named OSM road cue `Messent Road`, P10 about 0.49 source metres, with zero mapped Existing and Proposal drain-line length inside that clipped cell. This describes only the local evidence pattern. It does not establish a flood-prone location; the DSM datum is unresolved, the DSM includes buildings/vegetation, and zero mapped drain length can be a data-coverage gap.

The rainfall input does not change which cells rank highest by terrain and mapped-drain evidence, but it changes how many top-ranked cells are shown. The demo shortlist count is `ceil(total rainfall mm / 50) + floor(duration hours / 4)`, capped at available cells and 20. This ensures that, for a fixed rainfall total, increasing duration never reduces the number of review locations. It is a simple illustrative screening rule, not a prolonged-wetting model calibrated to soil saturation, drainage capacity, or observed flood outcomes. These are “review first” cells for field verification, not “affected” cells for the chosen storm. The UI and downloadable report recompute each candidate cell's **gross rainfall volume** as `rainfall_mm × clipped_cell_area_km² × 1,000`, and its mean gross rainfall rate by dividing that volume by scenario duration. These values assume uniform rainfall over each cell. They do not account for infiltration, measured runoff, drainage capacity, storage, ponding, or boundary conditions, and must not be interpreted as flood depth or impact likelihood. The report records the scenario input, per-cell gross load and rate, thresholds, per-cell source values, name cues, and cautions.

## Assumption-based model demonstration

An additional opt-in button runs a deliberately simplified water-budget stress test on all 194 cells. It joins actual local clipped-cell areas, DSM P10 values, mapped MCGM Existing drain lengths, and nearest named OSM road cues with two **editable demonstration assumptions**: runoff fraction (default 0.70) and notional drain removal capacity (default 2,500 m³/hour per mapped Existing-drain kilometre). These defaults are placeholders, not measurements, locally calibrated values, or recommended engineering parameters.

For each cell with at least some mapped Existing-drain line, the arithmetic is:

```text
gross rain (m³) = rainfall (mm) × cell area (km²) × 1,000
estimated runoff (m³) = gross rain × assumed runoff fraction
notional removal budget (m³) = mapped Existing drain length (km)
                            × assumed capacity (m³/hour/km) × duration (hour)
residual runoff load (m³) = max(0, estimated runoff − notional removal budget)
residual-equivalent depth (mm) = residual runoff / cell area (m²) × 1,000
```

Cells with zero mapped Existing-drain length are marked **capacity unknown** and excluded from modeled exceedance counts; their drain capacity is not set to zero. The grid currently has both evaluable cells and cells with unknown capacity. Evaluable cells rank by a demonstrative index: `residual-equivalent depth × terrain factor`, where the relative terrain factor runs from 1 at the highest valid DSM P10 to 2 at the lowest. This deliberately gives lower DSM cells more weight, but the multiplier is arbitrary and uncalibrated. Unknown-capacity cells follow as data gaps. Positive residual means only that the assumed runoff budget exceeds the assumed drain-removal budget in this arithmetic. It is not a predicted flood, ponding, water depth, or impact. No spatial flow routing, storage, sewer backwater, tide/outfall, drain cross-section, blockage, pump, building damage, or population exposure is modeled. The app surfaces all assumptions and limitations and can export a text report.

This demonstration shows how local rainfall, terrain, drainage, and scenario parameters can be combined into a reproducible cell-level model result. Before it can support predictions, replace placeholder parameters with measured/corroborated inputs, use an appropriate hydrologic/hydraulic solver, calibrate against observed events, validate on independent events, quantify uncertainty, and obtain operational review. Never call this demo output a flood prediction or use it for evacuation decisions.

### Reproducibility, sensitivity, and municipal-record spatial check

Each run of this assumption-based demonstration is now persisted under `data/runs/flood/` as `scenario_type=assumption_based_cell_water_budget`, with inputs, outputs, model version, UTC time, source dataset identifiers, and SHA-256 checksums for the ward boundary and review grid. The assistant receives the exact selected run ID and full saved output as deterministic context; it must describe the values as assumption-based arithmetic and not as flood impacts. The ordinary rainfall-run history lists only gross-rainfall runs, so these different run types are not confused in that UI.

The result includes a nine-case deterministic sensitivity sweep. Runoff fraction and notional drain-removal rate are independently varied by ±25% around the entered values, clipped to the allowed input range. This is a transparent scenario range, not a probability distribution, confidence interval, parameter calibration, or uncertainty estimate for real flood outcomes. Large changes in residual arithmetic indicate that the result depends on the entered assumptions.

`GET /api/v1/flood/record-overlap-diagnostic` reports geometric intersections between the existing 36 relative terrain/drain review cells and the 34 usable geometries from the local MCGM F/S Flooding Spots snapshot. The current local result is one municipal record intersecting two review cells. This is a context overlap only: MCGM records have no confirmed event dates or depth units, may include stale/deletion-marked entries, and are not independent observations for the entered rainfall. Do not calculate accuracy, precision, recall, calibration, or claim validation from this overlap.

## Real data shown for context

- An IMD/NWIC district-daily CSV snapshot, filtered to Mumbai City and Suburban Mumbai. The snapshot spans 2026-08-19 through 2026-10-06 with 49 daily records per district. This is not ward-scale or sub-hourly data and is not a real-time feed. The source resource page provides no license, so the file and derived display remain local and marked hold.
- A Copernicus GLO-30 digital surface model clipped to F/S. It is 30 m regional surface-elevation context; it includes surface objects, has nodata areas, and is not hydrologically conditioned or a verified engineering bare-earth model.
- MCGM drain and manhole records with source status retained as Existing or Proposal. Identifier matching is a diagnostic only; it does not verify connected flow, condition, dimensions, capacity, or operations.
- A provisional local F/S polygon used for the arithmetic area. Its authoritative vintage and reuse terms remain unresolved.

Source details and release states are maintained in `data/provenance/dataset_registry.csv` and the source manifest next to the local rainfall CSV. No source with `publication_status=hold` should be redistributed.

## What users can consider

The interface offers planning options, not an impact forecast: review maintenance/blockage records for mapped Existing drains; keep Proposal records distinct from operating assets; consult official IMD and BMC updates during actual events; and plan an approved, time-stamped collection of rainfall, water level, tide/outfall, and drain condition observations. The BMC Disaster Management Plan discusses pre-monsoon drain cleaning and preparedness measures. That supports general planning context, not a claim that a specific intervention will prevent flooding at a given location.

## Why no flooded roads/buildings are drawn

Required inputs are not yet available in verified form: ward-scale sub-hourly rainfall; engineering terrain and vertical datum; verified drainage geometry, cross-sections, capacities, connectivity, condition and operations; water-level/tide/outfall boundary conditions; and independent historic flood extent/depth observations for calibration and validation. Accordingly, the app must not infer affected properties from rainfall volume, DSM color, mapped drains, or district rainfall history.

## Gates before a flood-depth model

The local project now contains an F/S-only snapshot from MCGM's public GIS REST service: 34 Flooding Spots polygons (layer 344) and 45 Temporary Shelters points (layer 232), retrieved 7 October 2026. The app can draw the registered flood locations and listed shelter locations as separate map layers. Flooding Spots schema metadata aliases `DEPTH` as “Depth” but provides no unit; all 34 `HEIGHT_TO_MSL` values are null. Fourteen records are coded “Remedial measures done,” two “in progress,” three “not possible,” and 15 have no subtype. The `AFFECT_POPULATION` field is populated for only 13 records and has no reference period or de-duplication method, so these values must not be summed or called scenario exposure. Record-created/edit dates are not flood event dates, and 19 names contain a deletion marker. Shelter schema has staff/equipment/working-hours fields but no capacity or current-operation field; all queried working-hour values are blank. The records do not establish flood safety, accessibility, or route safety. These layers add municipal context but do not validate the rainfall screen or forecast impact. Source-specific reuse terms are not stated in the service metadata and remain for the user to confirm before publication. Do not assign evacuation destinations or recommend moving people from these records.

1. **Data:** obtain documented, sufficiently resolved rainfall, engineering terrain, drainage and boundary conditions.
2. **Licensing:** resolve processing, display, derived-output and redistribution terms for every input and model output.
3. **Simulation:** select and document a fit-for-purpose hydrologic/hydraulic model and reproducible parameters.
4. **Validation:** compare against independent observed events and report error, spatial coverage, and uncertainty.
5. **Decision utility:** only then test intervention comparisons such as drain maintenance, storage, or access consequences, with explicit assumptions and decision limits.

For real emergencies, follow official municipal and IMD advisories; INDIA SIM is not a warning, evacuation, or operational control system.
