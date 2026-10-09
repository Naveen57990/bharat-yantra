import { useEffect, useMemo, useRef, useState } from "react";
import {
  BoundingSphere,
  CesiumTerrainProvider,
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  ArcGisMapServerImageryProvider,
  Cartesian3,
  Cartesian2,
  Cartographic,
  EllipseGraphics,
  EllipsoidTerrainProvider,
  GeoJsonDataSource,
  HeightReference,
  HeadingPitchRange,
  JulianDate,
  PolylineOutlineMaterialProperty,
  Math as CesiumMath,
  Rectangle,
  SingleTileImageryProvider,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Viewer,
} from "cesium";

type SceneState = "loading" | "ready" | "empty" | "error";
type LayerId = "boundary" | "roads" | "buildings" | "openBuildings" | "satellite" | "terrainContext" | "facilities" | "existingDrains" | "proposedDrains" | "manholes" | "mcgmFloodRecords" | "mcgmShelters";
type AccessMetrics = {
  road_nodes_evaluated: number;
  road_nodes_with_route: number;
  road_nodes_without_route: number;
  route_coverage_percent: number;
  mean_network_distance_m: number | null;
  median_network_distance_m: number | null;
  p90_network_distance_m: number | null;
  mapped_facility_features: number;
  unique_snapped_road_nodes: number;
  median_facility_snap_distance_m: number | null;
  maximum_facility_snap_distance_m: number | null;
};
type AccessSummary = {
  source: string;
  source_retrieved_at: string;
  source_checksum: string;
  boundary_status: string;
  road_graph_nodes_buffered: number;
  road_graph_directed_edges_buffered: number;
  road_edges_intersecting_ward: number;
  road_nodes_inside_ward: number;
  weakly_connected_components_buffered: number;
  strongly_connected_components_buffered: number;
  ward_nodes_in_largest_weak_component: number;
  mapped_health_facilities_inside_ward: number;
  health_facility_geometry_types: Record<string, number>;
  baseline: AccessMetrics;
  metric_definition: string;
  validation_status: string;
  limitations: string[];
};
type ClosureOption = { road_name: string; directed_edges_intersecting_ward: number; highway_classes: string[] };
type FacilityRoute = { osm_id: string | null; name: string; amenity: string | null; healthcare: string | null; distance_m: number; baseline_distance_m: number | null; distance_change_m: number | null; is_nearest: boolean; geometry_type: string | null; snap_distance_m: number | null };
type FacilityRoutesResult = { selected_point: { longitude: number; latitude: number }; snapped_point: { longitude: number; latitude: number }; snap_distance_m: number; radius_m: number; facilities_found: number; nearest_facility_osm_id: string; facilities: FacilityRoute[]; applied_closures: string[]; closed_edges_geojson: Record<string, unknown>; routes_geojson: { type: "FeatureCollection"; features: Array<{ geometry: { type: "LineString"; coordinates: number[][] }; properties: { is_nearest: boolean } }> }; facilities_geojson: { type: "FeatureCollection"; features: Array<{ geometry: { type: "Point"; coordinates: number[] }; properties: { is_nearest: boolean } }> }; source_retrieved_at: string; assumptions: string[] };
type AccessRunResult = {
  run_id: string;
  created_at: string;
  scenario_label: string;
  facility_type: string;
  road_name: string;
  road_names: string[];
  closed_directed_edges: number;
  closed_edge_ids: string[];
  baseline: AccessMetrics;
  scenario: AccessMetrics;
  change: {
    newly_unreachable_road_nodes: number;
    newly_reachable_road_nodes: number;
    common_reachable_road_nodes: number;
    mean_distance_change_on_common_nodes_m: number;
  };
  closed_edges_geojson: Record<string, unknown>;
  newly_unreachable_nodes_geojson: Record<string, unknown>;
  source_retrieved_at: string;
  source_checksum: string;
  assumptions: string[];
  limitations: string[];
};
type LocalAgentStatus = { provider: string; model: string; ready: boolean; message: string };
type LocalAgentResponse = { answer: string; run_id: string | null; new_run: AccessRunResult | null; evidence_data: { features?: Array<{ osm_id: string | null; name: string | null; amenity: string | null; healthcare: string | null; geometry_type: string | null }>; retrieved_at?: string; limitations?: string[] } | null; flood_scenario: RainfallScreening | null; flood_run_record: SavedFloodRun | null; flood_model_run_record: SavedFloodRun | null; preparedness_plan_record?: PreparednessPlan | null; decision_record?: DecisionRecord | null; investment_option?: { name: string; summary: string; supported_basis: string; unknowns: string; estimated_cost_inr: number; remaining_budget_inr: number; planned_count: number; available_count: number } | null; flood_area_screening: { summary: { review_candidate_count: number; cell_count: number }; candidate_cells: Array<{ cell_id: string; nearest_named_road: string | null; dsm_p10_m: number | null; existing_drain_length_m: number }>; destination_readiness: { verified_evacuation_sites_available: boolean; message: string } } | null; model: string; provider: string; tools_used: string[]; model_tools_invoked: string[]; evidence_sources: string[] };
type RainfallRecord = { date: string; observed_mm: number; normal_mm: number; category: string | null };
type FloodReadiness = {
  ward: { name: string; status: string; area_km2: number; area_method: string };
  flood_simulation_available: boolean;
  simulation_status: string;
  rainfall: { dataset: { retrieved_at_utc: string; sha256: string; license: string; file: string }; districts: Record<string, { record_count: number; start_date: string | null; end_date: string | null }>; overall_start_date: string | null; overall_end_date: string | null; limitations: string[] };
  terrain: { dataset: string; nominal_resolution_m: number; valid_elevation_range_m: [number, number]; bounds_wgs84: { west: number; south: number; east: number; north: number }; use: string; limitations: string[] };
  drainage: { dataset: string; drain_lines: number; drain_status_counts: Record<string, number>; manholes: number; endpoint_id_matches: number; limitations: string[] };
  missing_for_flood_depth: string[];
  attribution_and_release: string;
};
type RainfallSeries = { district: string; unit: string; source: { retrieved_at_utc: string }; spatial_scale: string; records: RainfallRecord[] };
type RainfallScreening = { rainfall_mm: number; duration_hours: number; mean_intensity_mm_per_hour: number; provisional_ward_area_km2: number; gross_rainfall_volume_m3: number; interpretation: string; not_calculated: string[] };
type SavedFloodRun = { run_id: string; created_at_utc: string; scenario_type: string; model_version: string; inputs: { rainfall_mm: number; duration_hours: number }; outputs: RainfallScreening; source_dataset_ids: string[]; source_checksums?: Record<string, string>; status: string };
type PreparednessWorkstream = { workstream: string; action: string; source: string; available_count: number; planned_count: number; unit_allowance_inr: number; estimated_allocation_inr: number; feature_collection: { type: "FeatureCollection"; features: Array<{ type: "Feature"; geometry: Record<string, unknown>; properties: Record<string, unknown> }> } };
type PreparednessOption = { id: string; name: string; summary: string; workstreams: PreparednessWorkstream[]; estimated_allocation_inr: number; unallocated_inr: number; over_budget_inr: number; mapped_actions: number };
type PreparednessPlan = { run_id: string; created_at_utc: string; scenario_type: string; model_version: string; status: string; inputs: { rainfall_mm: number; duration_hours: number; budget_crore: number; budget_inr: number; cell_review_rate_inr: number; record_verification_rate_inr: number; shelter_audit_rate_inr: number; allowance_basis: string }; rainfall_screening: { field_check_locations_shown: number; mean_intensity_mm_per_hour: number; rule: string }; method: string; options: PreparednessOption[]; selected_option_id: string; sources: Record<string, { path: string; count: number; sha256: string }>; limitations: string[] };
type InvestmentOption = { id: "drainage" | "streetlights" | "health_access"; workstream: string; name: string; summary: string; supported_basis: string; unknowns: string; available_count: number; planned_count: number; unit_allowance_inr: number; rate_basis: string; estimated_cost_inr: number; remaining_budget_inr: number; feature_collection: { type: "FeatureCollection"; features: Array<{ type: "Feature"; geometry: Record<string, unknown>; properties: Record<string, unknown> }> } };
type InvestmentPlan = { run_id: string; created_at_utc: string; scenario_type: string; model_version: string; inputs: { budget_crore: number; budget_inr: number; drainage_site_allowance_inr: number; streetlight_site_allowance_inr: number; health_access_site_allowance_inr: number; streetlight_spacing_m: number; allowance_basis: string }; options: InvestmentOption[]; method: string; limitations: string[]; sources: Record<string, { path: string; sha256: string; candidate_count?: number; road_node_count?: number; mapped_health_feature_count?: number; retrieved_at_utc?: string }> };
type DecisionRecord = { decision_id: string; created_at_utc: string; decision_type: "road_closure" | "preparedness"; title: string; source_run_id: string; option_id: string | null; outputs: Record<string, unknown>; pros_supported_by_outputs: string[]; cons_and_unknowns: string[]; limitations: string[] };
type WardActionStatus = "To inspect" | "In progress" | "Done";
type WardActionItem = { id: string; workstream: string; title: string; location: string; reason: string; source: string; geometry: Record<string, unknown> };
const WARD_ACTION_STATUS_KEY = "bharat-yantra-ward-action-status-v1";

type FloodReviewFeature = { type: "Feature"; geometry: Record<string, unknown>; properties: { cell_id: string; area_km2: number; dsm_p10_m: number | null; dsm_valid_pixels: number; existing_drain_length_m: number; proposal_drain_length_m: number; existing_drain_density_km_per_km2: number; proposal_drain_density_km_per_km2: number; nearest_named_road: string | null; low_relative_terrain: boolean; low_existing_drain_density: boolean; review_candidate: boolean; screen_label: string } };
type FloodScreeningAreas = { type: "FeatureCollection"; name: string; features: FloodReviewFeature[]; all_cells: FloodReviewFeature[]; summary: { cell_size_m_nominal: number; cell_count: number; review_candidate_count: number; dsm_p10_q25_m: number; existing_drain_density_q25_km_per_km2: number; method: string; limitations: string[] }; destination_readiness: { verified_evacuation_sites_available: boolean; message: string } };
type RainfallPriorityArea = FloodReviewFeature & { priority_score: number; terrain_score: number; drainage_score: number };
type IllustrativeFloodModel = { model_name: string; status: string; saved_run: SavedFloodRun; scenario: { rainfall_mm: number; duration_hours: number; mean_intensity_mm_per_hour: number }; assumptions: { runoff_fraction: number; drain_capacity_m3_per_hour_per_km: number }; summary: { cell_count: number; modelled_exceedance_cell_count: number; evaluable_cell_count: number; capacity_unknown_cell_count: number; gross_rain_m3: number; assumed_runoff_m3: number; assumed_drain_capacity_m3: number; modelled_residual_runoff_m3: number }; sensitivity: { method: string; interpretation: string; cases: Array<{ runoff_fraction_assumption: number; drain_capacity_assumption_m3_per_hour_per_km: number; residual_arithmetic_total_m3: number; cells_above_assumed_capacity: number }> }; method: string; limitations: string[]; features: Array<{ cell_id: string; geometry?: Record<string, unknown>; nearest_named_road: string | null; area_km2: number; dsm_p10_m: number | null; existing_drain_length_m: number; gross_rain_m3: number; assumed_runoff_m3: number; assumed_drain_capacity_m3: number | null; modelled_residual_runoff_m3: number | null; residual_runoff_equivalent_mm: number | null; relative_terrain_factor: number; terrain_weighted_screening_index: number | null; model_rank: number; model_flag: boolean; capacity_unknown: boolean }> };
type MunicipalContextFeature = { type: "Feature"; id?: string | number; geometry: Record<string, unknown> | null; properties: Record<string, string | number | null> };
type MunicipalFloodContext = { snapshot: { retrieved_at_utc: string; records: { flooding_spots: { feature_count: number }; temporary_shelters: { feature_count: number } } }; flood_records: { type: "FeatureCollection"; name: string; features: MunicipalContextFeature[] }; shelters: { type: "FeatureCollection"; name: string; features: MunicipalContextFeature[] }; summary: { flood_record_count: number; flood_records_by_category: Record<string, number>; records_with_name_marked_delete: number; shelter_record_count: number; shelters_by_source_type: Record<string, number>; verified_shelter_capacity_field_available: boolean; verified_open_status_available: boolean }; limitations: string[] };

function readableServiceMessage(error: unknown, fallback: string) {
  if (error instanceof Error && /failed to fetch|networkerror|load failed/i.test(error.message)) return fallback;
  if (error instanceof SyntaxError || error instanceof Error && /unexpected token|not valid json|json parse/i.test(error.message)) return "The planning service is not connected to this deployment yet. Map layers can still be viewed.";
  return error instanceof Error ? error.message : fallback;
}

function readableStatusMessage(message: string, fallback: string) {
  return /failed to fetch|networkerror|load failed/i.test(message) ? fallback : message;
}
const layerDefinitions: Array<{ id: LayerId; label: string; color: string }> = [
  { id: "boundary", label: "Ward boundary", color: "#e8b85a" },
  { id: "terrainContext", label: "Copernicus DSM · elevation context", color: "#8daa78" },
  { id: "roads", label: "OSM roads", color: "#263238" },
  { id: "buildings", label: "OSM buildings · tagged 3D", color: "#b36e52" },
  { id: "openBuildings", label: "Open Buildings · 6,881 detected", color: "#e7c178" },
  { id: "satellite", label: "Satellite imagery · Esri", color: "#71a6bb" },
  { id: "facilities", label: "Mapped facilities", color: "#f1a28a" },
  { id: "existingDrains", label: "Existing drains", color: "#00695c" },
  { id: "proposedDrains", label: "Proposed drains", color: "#805000" },
  { id: "manholes", label: "Manholes", color: "#f2d27f" },
  { id: "mcgmFloodRecords", label: "MCGM registered flood locations", color: "#c9473d" },
  { id: "mcgmShelters", label: "MCGM listed shelter locations", color: "#79b8d5" },
];

const boundaryUrl = import.meta.env.VITE_WARD_BOUNDARY_URL?.trim();
const terrainUrl = import.meta.env.VITE_TERRAIN_URL?.trim();
const localSourcePreview = import.meta.env.DEV || import.meta.env.VITE_LOCAL_SOURCE_PREVIEW === "true";
const wardUrl = boundaryUrl || (localSourcePreview ? "/local-data/fs-ward.geojson" : undefined);
const wardName = import.meta.env.VITE_WARD_BOUNDARY_NAME?.trim() || (localSourcePreview ? "F/S Ward · Stage 1 testbed" : "Ward not selected");
// Use the same-origin Vite API proxy in local development. An explicit API URL
// remains available for a deployed frontend/API pair.
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "";

function getFeatureCenter(geometry: Record<string, unknown>): [number, number] | null {
  const coordinates: Array<[number, number]> = [];
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && typeof value[1] === "number") coordinates.push([value[0], value[1]]);
    else value.forEach(visit);
  };
  visit(geometry.coordinates);
  if (!coordinates.length) return null;
  const xs = coordinates.map(([x]) => x);
  const ys = coordinates.map(([, y]) => y);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
}

function App() {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const layerSourcesRef = useRef<Partial<Record<LayerId, GeoJsonDataSource>>>({});
  const satelliteLayerRef = useRef<import("cesium").ImageryLayer | null>(null);
  const dsmContextLayerRef = useRef<import("cesium").ImageryLayer | null>(null);
  const floodReviewLayerRef = useRef<GeoJsonDataSource | null>(null);
  const preparednessLayersRef = useRef<GeoJsonDataSource[]>([]);
  const focusedActionEntityRef = useRef<import("cesium").Entity | null>(null);
  const closureLayerRef = useRef<GeoJsonDataSource | null>(null);
  const impactEntitiesRef = useRef<Array<import("cesium").Entity>>([]);
  const accessRouteEntitiesRef = useRef<Array<import("cesium").Entity>>([]);
  const accessRouteSvgRef = useRef<SVGSVGElement | null>(null);
  const accessRouteRenderListenerRef = useRef<(() => void) | null>(null);
  const satelliteRequestRef = useRef(0);
  const dsmContextRequestRef = useRef(0);
  const accessRunInFlightRef = useRef(false);
  const drainEntitiesRef = useRef<Array<{ entity: import("cesium").Entity; status: string }>>([]);
  const [sceneState, setSceneState] = useState<SceneState>("loading");
  const [sceneMessage, setSceneMessage] = useState("Preparing a source-empty 3D scene.");
  const [boundaryLoaded, setBoundaryLoaded] = useState(false);
  const [enabledLayers, setEnabledLayers] = useState<Record<LayerId, boolean>>({
    boundary: true,
    terrainContext: false,
    roads: true,
    buildings: false,
    openBuildings: false,
    satellite: false,
    facilities: false,
    existingDrains: false,
    proposedDrains: false,
    manholes: false,
    mcgmFloodRecords: false,
    mcgmShelters: false,
  });
  const [layersOpen, setLayersOpen] = useState(false);
  const [twoDimensional, setTwoDimensional] = useState(false);
  const [sceneModeChanging, setSceneModeChanging] = useState(false);
  const [accessSummary, setAccessSummary] = useState<AccessSummary | null>(null);
  const [closureOptions, setClosureOptions] = useState<ClosureOption[]>([]);
  const [selectedClosureRoads, setSelectedClosureRoads] = useState<string[]>([]);
  const [closureRoadSearch, setClosureRoadSearch] = useState("");
  const selectedClosureRoad = selectedClosureRoads[0] ?? "";
  const [facilityClosedRoads, setFacilityClosedRoads] = useState<string[]>([]);
  const [facilityClosureSearch, setFacilityClosureSearch] = useState("");
  const [accessRun, setAccessRun] = useState<AccessRunResult | null>(null);
  const [areaPickMode, setAreaPickMode] = useState(false);
  const [facilityRoutes, setFacilityRoutes] = useState<FacilityRoutesResult | null>(null);
  const [facilityRoutesLoading, setFacilityRoutesLoading] = useState(false);
  const [facilityRoutesError, setFacilityRoutesError] = useState("");
  const [facilityRouteRadius, setFacilityRouteRadius] = useState("1200");
  const [accessLoading, setAccessLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [accessError, setAccessError] = useState("");
  const [floodEvidence, setFloodEvidence] = useState<FloodReadiness | null>(null);
  const [rainfallSeries, setRainfallSeries] = useState<RainfallSeries | null>(null);
  const [rainfallDistrict, setRainfallDistrict] = useState("MUMBAI CITY");
  const [rainfallAmount, setRainfallAmount] = useState("150");
  const [rainfallDuration, setRainfallDuration] = useState("8");
  const [demoRunoffFraction, setDemoRunoffFraction] = useState("0.7");
  const [demoDrainCapacity, setDemoDrainCapacity] = useState("2500");
  const [illustrativeFloodModel, setIllustrativeFloodModel] = useState<IllustrativeFloodModel | null>(null);
  const [illustrativeModelLoading, setIllustrativeModelLoading] = useState(false);
  const [illustrativeModelError, setIllustrativeModelError] = useState("");
  const [rainfallScreening, setRainfallScreening] = useState<RainfallScreening | null>(null);
  const [savedFloodRuns, setSavedFloodRuns] = useState<SavedFloodRun[]>([]);
  const [savedFloodRunId, setSavedFloodRunId] = useState("");
  const [floodScreeningAreas, setFloodScreeningAreas] = useState<FloodScreeningAreas | null>(null);
  const [municipalFloodContext, setMunicipalFloodContext] = useState<MunicipalFloodContext | null>(null);
  const [recordOverlapDiagnostic, setRecordOverlapDiagnostic] = useState<{ status: string; summary: { usable_municipal_record_geometries: number; records_intersecting_relative_review_cells: number; relative_review_cell_count: number; matched_review_cell_count: number }; interpretation: string } | null>(null);
  const [floodReviewVisible, setFloodReviewVisible] = useState(false);
  const [policyBudgetCrore, setPolicyBudgetCrore] = useState("10");
  const [preparednessRates, setPreparednessRates] = useState({ cell: "100000", record: "50000", shelter: "75000" });
  const [preparednessPlan, setPreparednessPlan] = useState<PreparednessPlan | null>(null);
  const [preparednessOptionId, setPreparednessOptionId] = useState("balanced_review");
  const [preparednessLoading, setPreparednessLoading] = useState(false);
  const [preparednessError, setPreparednessError] = useState("");
  const [investmentRates, setInvestmentRates] = useState({ drainage: "2500000", streetlights: "45707", healthAccess: "500000" });
  const [investmentSpacingM, setInvestmentSpacingM] = useState("100");
  const [investmentPlan, setInvestmentPlan] = useState<InvestmentPlan | null>(null);
  const [investmentOptionId, setInvestmentOptionId] = useState<InvestmentOption["id"]>("health_access");
  const [investmentLoading, setInvestmentLoading] = useState(false);
  const [investmentError, setInvestmentError] = useState("");
  const [decisionMode, setDecisionMode] = useState<"preparedness" | "road_closure" | "investment">("investment");
  const [actionTrackerMode, setActionTrackerMode] = useState(false);
  const [selectedWardActionId, setSelectedWardActionId] = useState<string | null>(null);
  const [wardActionStatuses, setWardActionStatuses] = useState<Record<string, WardActionStatus>>(() => {
    try { return JSON.parse(localStorage.getItem(WARD_ACTION_STATUS_KEY) || "{}"); } catch { return {}; }
  });
  useEffect(() => {
    try { localStorage.setItem(WARD_ACTION_STATUS_KEY, JSON.stringify(wardActionStatuses)); } catch { /* Keep current-session tracking usable if browser storage is unavailable. */ }
  }, [wardActionStatuses]);
  const [decisionRecord, setDecisionRecord] = useState<DecisionRecord | null>(null);
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const selectedPreparednessOption = preparednessPlan?.options.find((option) => option.id === preparednessOptionId) ?? preparednessPlan?.options[0] ?? null;
  const selectedInvestmentOption = investmentPlan?.options.find((option) => option.id === investmentOptionId) ?? investmentPlan?.options[0] ?? null;
  const wardActionItems: WardActionItem[] = useMemo(() => (selectedPreparednessOption?.workstreams ?? []).flatMap((work) => work.feature_collection.features.map((feature, index) => {
    const properties = feature.properties;
    const featureName = String(properties.NAME ?? properties.name ?? "");
    if (work.workstream === "record_verification" && /delete|already tackled/i.test(`${featureName} ${String(properties.REMARKS ?? "")}`)) return null;
    const location = String(properties.cell_id ?? (featureName || properties.location) ?? `${work.workstream.replaceAll("_", " ")} ${index + 1}`);
    const workstreamName = work.workstream === "field_review" ? "Drainage and terrain check" : work.workstream === "record_verification" ? "Registered location check" : work.workstream === "shelter_audit" ? "Listed shelter check" : work.workstream.replaceAll("_", " ");
    const title = work.workstream === "field_review" ? "Review first" : work.workstream === "record_verification" ? `Verify record · ${featureName || `item ${index + 1}`}` : `Check listed shelter · ${featureName || `site ${index + 1}`}`;
    const locationText = String(properties.AFFECT_AREA ?? properties.LOCATION ?? "");
    const reason = work.workstream === "field_review" && properties.nearest_named_road
      ? `Review lower terrain and verify mapped drains near ${String(properties.nearest_named_road)}. A mapping gap does not prove a drain is absent.`
      : work.workstream === "record_verification"
        ? `Confirm this registered location’s current condition, event date and resolution status${locationText ? ` · ${locationText}` : ""}.`
        : work.workstream === "shelter_audit"
          ? "Confirm this listed site is active, accessible and suitable. Current opening and capacity are not verified."
          : String(properties.action ?? work.action);
    const uniqueFeatureId = String(properties.cell_id ?? properties.OBJECTID ?? properties.osm_id ?? location);
    return { id: `${work.workstream}:${uniqueFeatureId}`, workstream: workstreamName, title, location, reason, source: String(properties.source ?? work.source), geometry: feature.geometry };
  })).filter((item): item is WardActionItem => item !== null).slice(0, 8), [selectedPreparednessOption]);
  const actionStatusCounts = wardActionItems.reduce((counts, item) => { const status = wardActionStatuses[item.id] ?? "To inspect"; counts[status] += 1; return counts; }, { "To inspect": 0, "In progress": 0, Done: 0 });
  const activeMapPlanLayers = useMemo(() => decisionMode === "investment"
    ? (selectedInvestmentOption ? [selectedInvestmentOption] : [])
    : decisionMode === "preparedness" ? (selectedPreparednessOption?.workstreams ?? []).map((work) => actionTrackerMode
      ? { ...work, feature_collection: { ...work.feature_collection, features: work.feature_collection.features.filter((feature, index) => {
        const properties = feature.properties as Record<string, unknown>;
        const location = String(properties.cell_id ?? properties.NAME ?? properties.name ?? properties.location ?? `${work.workstream.replaceAll("_", " ")} ${index + 1}`);
        const key = String(properties.cell_id ?? properties.OBJECTID ?? properties.osm_id ?? location);
        const item = wardActionItems.find((candidate) => candidate.id === `${work.workstream}:${key}`);
        return Boolean(item && (!selectedWardActionId || item.id === selectedWardActionId));
      }) } }
      : work) : [],
  [decisionMode, actionTrackerMode, selectedWardActionId, selectedInvestmentOption, selectedPreparednessOption, wardActionItems]);
  const [floodLoading, setFloodLoading] = useState(true);
  const [floodScenarioLoading, setFloodScenarioLoading] = useState(false);
  const [floodReportLoading, setFloodReportLoading] = useState(false);
  const [floodError, setFloodError] = useState("");
  const [layerMessage, setLayerMessage] = useState("");
  const [closureLayerVisible, setClosureLayerVisible] = useState(true);
  const [agentStatus, setAgentStatus] = useState<LocalAgentStatus>({
    provider: "Ollama on this device",
    model: "qwen3:8b",
    ready: false,
    message: "Checking local model availability…",
  });
  const [agentQuestion, setAgentQuestion] = useState("");
  const [agentAnswer, setAgentAnswer] = useState<LocalAgentResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentError, setAgentError] = useState("");

  const enteredRainfallMm = Number(rainfallAmount);
  const enteredDurationHours = Number(rainfallDuration);
  const hasValidEnteredScenario = Number.isFinite(enteredRainfallMm) && enteredRainfallMm > 0 && enteredRainfallMm <= 1000
    && Number.isFinite(enteredDurationHours) && enteredDurationHours > 0 && enteredDurationHours <= 168;
  const rainfallPriorityAreas = useMemo<RainfallPriorityArea[]>(() => {
    const cells = floodScreeningAreas?.all_cells ?? [];
    if (!hasValidEnteredScenario) return [];
    const usable = cells.filter((feature) => feature.properties.dsm_p10_m !== null && Number.isFinite(feature.properties.dsm_p10_m) && feature.properties.area_km2 > 0);
    if (!usable.length) return [];
    const elevations = usable.map((feature) => feature.properties.dsm_p10_m as number);
    const minElevation = Math.min(...elevations);
    const elevationSpan = Math.max(...elevations) - minElevation;
    const drainDensities = usable.map((feature) => feature.properties.existing_drain_density_km_per_km2).filter(Number.isFinite).sort((a, b) => a - b);
    const upperDrainDensity = drainDensities[Math.floor((drainDensities.length - 1) * 0.75)] || 0;
    const intensity = enteredRainfallMm / enteredDurationHours;
    const drainageWeight = Math.min(0.65, Math.max(0.35, 0.35 + intensity / 60 * 0.3));
    const terrainWeight = 1 - drainageWeight;
    const ranked = usable.map((feature) => {
      const terrainScore = elevationSpan > 0 ? 1 - ((feature.properties.dsm_p10_m as number) - minElevation) / elevationSpan : 0.5;
      const drainageScore = upperDrainDensity > 0 ? 1 - Math.min(1, feature.properties.existing_drain_density_km_per_km2 / upperDrainDensity) : 1;
      return { ...feature, priority_score: terrainScore * terrainWeight + drainageScore * drainageWeight, terrain_score: terrainScore, drainage_score: drainageScore };
    }).sort((a, b) => b.priority_score - a.priority_score || (a.properties.dsm_p10_m ?? Infinity) - (b.properties.dsm_p10_m ?? Infinity));
    // Demo screening rule: rainfall depth sets the base count; every completed
    // four-hour period adds one candidate. This guarantees that, for the same
    // rainfall amount, increasing duration never reduces the shortlist.
    // It is an illustrative planning rule, not a calibrated soil/hydraulic model.
    const shortlistCount = Math.min(20, ranked.length, Math.max(1, Math.ceil(enteredRainfallMm / 50) + Math.floor(enteredDurationHours / 4)));
    return ranked.slice(0, shortlistCount);
  }, [floodScreeningAreas, hasValidEnteredScenario, enteredRainfallMm, enteredDurationHours]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      fetch(`${apiBaseUrl}/api/v1/accessibility/summary`).then(async (response) => { if (!response.ok) throw new Error("Road-access information could not be loaded."); return response.json() as Promise<AccessSummary>; }),
      fetch(`${apiBaseUrl}/api/v1/accessibility/closure-options`).then(async (response) => { if (!response.ok) throw new Error("Road options could not be loaded."); return response.json() as Promise<ClosureOption[]>; }),
    ]).then(([summary, options]) => { if (!cancelled) { setAccessSummary(summary); setClosureOptions(options); setAccessError(""); } }).catch((error: unknown) => { if (!cancelled) setAccessError(readableServiceMessage(error, "Road and health-facility information is unavailable right now.")); }).finally(() => { if (!cancelled) setAccessLoading(false); });
    void fetch(`${apiBaseUrl}/api/v1/flood/runs?limit=8`).then(async (response) => { if (!response.ok) throw new Error("Saved rainfall scenarios could not be loaded."); return response.json() as Promise<SavedFloodRun[]>; }).then((runs) => { if (!cancelled) setSavedFloodRuns(runs); }).catch(() => undefined);
    void Promise.all([
      fetch(`${apiBaseUrl}/api/v1/flood/evidence`).then(async (response) => { if (!response.ok) throw new Error("Flood evidence is unavailable."); return response.json() as Promise<FloodReadiness>; }),
      fetch(`${apiBaseUrl}/api/v1/flood/rainfall?district=${encodeURIComponent(rainfallDistrict)}`).then(async (response) => { if (!response.ok) throw new Error("Rainfall records are unavailable."); return response.json() as Promise<RainfallSeries>; }),
      fetch(`${apiBaseUrl}/api/v1/flood/screening-areas`).then(async (response) => { if (!response.ok) throw new Error("Review cells are unavailable."); return response.json() as Promise<FloodScreeningAreas>; }),
      fetch(`${apiBaseUrl}/api/v1/flood/municipal-context`).then(async (response) => { if (!response.ok) throw new Error("MCGM context is unavailable."); return response.json() as Promise<MunicipalFloodContext>; }),
    ]).then(([evidence, rainfall, areas, municipal]) => { if (!cancelled) { setFloodEvidence(evidence); setRainfallSeries(rainfall); setFloodScreeningAreas(areas); setMunicipalFloodContext(municipal); setFloodError(""); } }).catch((error: unknown) => { if (!cancelled) setFloodError(readableServiceMessage(error, "Flood and rainfall information is unavailable right now.")); }).finally(() => { if (!cancelled) setFloodLoading(false); });
    void fetch(`${apiBaseUrl}/api/v1/flood/record-overlap-diagnostic`).then(async (response) => { if (!response.ok) throw new Error("Record comparison is unavailable."); return response.json(); }).then((result) => { if (!cancelled) setRecordOverlapDiagnostic(result); }).catch(() => undefined);
    void fetch(`${apiBaseUrl}/api/v1/agent/status`).then(async (response) => { if (!response.ok) throw new Error("Assistant status is unavailable."); return response.json() as Promise<LocalAgentStatus>; }).then((status) => { if (!cancelled) setAgentStatus(status); }).catch(() => { if (!cancelled) setAgentStatus({ provider: "Ollama on this device", model: "qwen3:8b", ready: false, message: "Assistant unavailable" }); });
    return () => { cancelled = true; };
  }, [rainfallDistrict]);

  const showClosureOverlay = async (geojson: Record<string, unknown>) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    if (closureLayerRef.current) viewer.dataSources.remove(closureLayerRef.current, true);
    const source = await GeoJsonDataSource.load(geojson as never, { clampToGround: true, stroke: Color.fromCssColorString("#d94e43"), strokeWidth: 8 });
    for (const entity of source.entities.values) if (entity.polyline) entity.polyline.material = new PolylineOutlineMaterialProperty({ color: Color.fromCssColorString("#e65348"), outlineColor: Color.fromCssColorString("#311c1a"), outlineWidth: 2 });
    if (!viewer.isDestroyed()) { source.show = true; await viewer.dataSources.add(source); closureLayerRef.current = source; }
  };

  const clearFacilityRoutes = () => {
    const viewer = viewerRef.current;
    if (viewer && !viewer.isDestroyed() && accessRouteRenderListenerRef.current) viewer.scene.postRender.removeEventListener(accessRouteRenderListenerRef.current);
    accessRouteRenderListenerRef.current = null;
    accessRouteSvgRef.current?.remove();
    accessRouteSvgRef.current = null;
    if (viewer && !viewer.isDestroyed()) for (const entity of accessRouteEntitiesRef.current) viewer.entities.remove(entity);
    accessRouteEntitiesRef.current = [];
  };

  const drawFacilityRoutes = (result: FacilityRoutesResult) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    clearFacilityRoutes();
    clearRoadScenarioOverlays();
    if (result.applied_closures.length > 0) { setClosureLayerVisible(true); void showClosureOverlay(result.closed_edges_geojson); }
    const mapWrap = hostRef.current?.parentElement;
    if (!mapWrap) return;
    const svgNamespace = "http://www.w3.org/2000/svg";
    const routeSvg = document.createElementNS(svgNamespace, "svg");
    routeSvg.setAttribute("aria-hidden", "true");
    routeSvg.classList.add("facility-route-overlay");
    mapWrap.appendChild(routeSvg);
    accessRouteSvgRef.current = routeSvg;
    const routePaths = result.routes_geojson.features.map((feature, index) => {
      const outer = document.createElementNS(svgNamespace, "path");
      const inner = document.createElementNS(svgNamespace, "path");
      const nearest = feature.properties.is_nearest;
      outer.setAttribute("fill", "none");
      outer.setAttribute("stroke", "#14231f");
      outer.setAttribute("stroke-width", nearest ? "8" : "6");
      outer.setAttribute("stroke-linecap", "round");
      outer.setAttribute("stroke-linejoin", "round");
      inner.setAttribute("fill", "none");
      inner.setAttribute("stroke", nearest ? "#ffd166" : "#39dfbd");
      inner.setAttribute("stroke-width", nearest ? "4.5" : "3.5");
      inner.setAttribute("stroke-linecap", "round");
      inner.setAttribute("stroke-linejoin", "round");
      outer.setAttribute("pathLength", "1");
      outer.style.strokeDasharray = "1";
      outer.style.strokeDashoffset = "1";
      outer.style.animation = `facility-route-trace 1.8s ease-out ${index * 90}ms forwards`;
      inner.setAttribute("pathLength", "1");
      inner.style.strokeDasharray = "1";
      inner.style.strokeDashoffset = "1";
      inner.style.animation = `facility-route-trace 1.8s ease-out ${index * 90}ms forwards`;
      routeSvg.append(outer, inner);
      const worldPoints = feature.geometry.coordinates.map(([longitude, latitude]) => Cartesian3.fromDegrees(longitude, latitude, 0));
      return { outer, inner, worldPoints };
    });
    const updateRouteScreenPositions = () => {
      if (viewer.isDestroyed() || !accessRouteSvgRef.current) return;
      const width = mapWrap.clientWidth;
      const height = mapWrap.clientHeight;
      if (!width || !height) return;
      routeSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      routeSvg.setAttribute("width", String(width));
      routeSvg.setAttribute("height", String(height));
      for (const route of routePaths) {
        const screenPoints = route.worldPoints.map((point) => viewer.scene.cartesianToCanvasCoordinates(point, new Cartesian2()));
        let path = "";
        let drawing = false;
        for (const point of screenPoints) {
          if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) { drawing = false; continue; }
          path += `${drawing ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)} `;
          drawing = true;
        }
        route.outer.setAttribute("d", path);
        route.inner.setAttribute("d", path);
      }
    };
    accessRouteRenderListenerRef.current = updateRouteScreenPositions;
    viewer.scene.postRender.addEventListener(updateRouteScreenPositions);
    updateRouteScreenPositions();
    for (const feature of result.facilities_geojson.features) {
      const [longitude, latitude] = feature.geometry.coordinates;
      const nearest = feature.properties.is_nearest;
      const entity = viewer.entities.add({
        name: nearest ? "Nearest mapped health facility" : "Nearby mapped health facility",
        position: Cartesian3.fromDegrees(longitude, latitude),
        point: { pixelSize: nearest ? 19 : 12, color: Color.fromCssColorString(nearest ? "#ffd166" : "#f4f1e8"), outlineColor: Color.fromCssColorString("#18332c"), outlineWidth: nearest ? 3 : 2, heightReference: HeightReference.CLAMP_TO_GROUND },
      });
      accessRouteEntitiesRef.current.push(entity);
    }
    const selected = viewer.entities.add({
      name: "Selected area",
      position: Cartesian3.fromDegrees(result.selected_point.longitude, result.selected_point.latitude),
      point: { pixelSize: 12, color: Color.fromCssColorString("#83c8a3"), outlineColor: Color.WHITE, outlineWidth: 2, heightReference: HeightReference.CLAMP_TO_GROUND },
    });
    accessRouteEntitiesRef.current.push(selected);
    const overviewPoints = result.facilities_geojson.features.map((feature) => Cartesian3.fromDegrees(feature.geometry.coordinates[0], feature.geometry.coordinates[1]));
    overviewPoints.push(Cartesian3.fromDegrees(result.selected_point.longitude, result.selected_point.latitude));
    const routeBounds = BoundingSphere.fromPoints(overviewPoints);
    void viewer.camera.flyToBoundingSphere(routeBounds, { duration: 0.9, offset: new HeadingPitchRange(0, -1.12, Math.max(1800, routeBounds.radius * 2.5)) });
  };

  const showNewlyUnreachableOverlay = async (geojson: Record<string, unknown>) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    for (const entity of impactEntitiesRef.current) viewer.entities.remove(entity);
    impactEntitiesRef.current = [];
    const source = await GeoJsonDataSource.load(geojson as never, { clampToGround: true, markerColor: Color.fromCssColorString("#f1c75b"), markerSize: 12 });
    for (const entity of source.entities.values) {
      if (!entity.position) continue;
      entity.billboard = undefined;
      entity.point = undefined;
      entity.ellipse = new EllipseGraphics({ semiMajorAxis: new ConstantProperty(15), semiMinorAxis: new ConstantProperty(15), material: new ColorMaterialProperty(Color.fromCssColorString("#f1c75b")), heightReference: new ConstantProperty(HeightReference.CLAMP_TO_GROUND) });
      impactEntitiesRef.current.push(viewer.entities.add(entity));
    }
  };

  const clearRoadScenarioOverlays = () => {
    const viewer = viewerRef.current;
    if (viewer && !viewer.isDestroyed() && closureLayerRef.current) viewer.dataSources.remove(closureLayerRef.current, true);
    closureLayerRef.current = null;
    if (viewer && !viewer.isDestroyed()) for (const entity of impactEntitiesRef.current) viewer.entities.remove(entity);
    impactEntitiesRef.current = [];
    setAccessRun(null);
  };

  const toggleClosureOverlay = () => {
    setClosureLayerVisible((visible) => {
      const next = !visible;
      if (closureLayerRef.current) closureLayerRef.current.show = next;
      for (const entity of impactEntitiesRef.current) entity.show = next;
      return next;
    });
  };

  const runClosureScenario = async () => {
    if (!selectedClosureRoads.length || runLoading || accessRunInFlightRef.current) return;
    accessRunInFlightRef.current = true;
    setRunLoading(true);
    setAccessError("");
    setAgentAnswer(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/accessibility/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ road_names: selectedClosureRoads }) });
      const result = await response.json() as AccessRunResult | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Road-access scenario failed." : "Road-access scenario failed.");
      const run = result as AccessRunResult;
      setAccessRun(run);
      setClosureLayerVisible(true);
      await showClosureOverlay(run.closed_edges_geojson);
      await showNewlyUnreachableOverlay(run.newly_unreachable_nodes_geojson);
    } catch (error) {
      setAccessError(readableServiceMessage(error, "The road-access scenario could not be completed."));
    } finally {
      accessRunInFlightRef.current = false;
      setRunLoading(false);
    }
  };

  const downloadFloodFieldReport = async () => {
    setFloodReportLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/flood/evidence`);
      if (!response.ok) throw new Error("Flood field-screen report could not be assembled.");
      const evidence = await response.json() as FloodReadiness;
      const candidates = rainfallPriorityAreas;
      const lines = ["BHARAT YANTRA · WARD FLOOD PREPAREDNESS FIELD-SCREEN", "An indigenous engineering engine for India", `Ward: ${evidence.ward.name} · provisional testbed`, `Scenario input: ${rainfallAmount} mm over ${rainfallDuration} hours; average ${hasValidEnteredScenario ? (enteredRainfallMm / enteredDurationHours).toFixed(2) : "unknown"} mm/hour.`, `Demo shortlist: ${candidates.length} locations for first inspection, ranked using local terrain elevation and mapped drain density. The count uses an intensity rule plus one illustrative review location per completed four-hour interval; this is not measured soil saturation.`, "This is a relative field-screening demonstration, not a prediction of flooding or risk.", ...candidates.map((feature, index) => `${index + 1}. ${feature.properties.cell_id} | near road: ${feature.properties.nearest_named_road || "none"} | source elevation P10: ${feature.properties.dsm_p10_m ?? "missing"} m | mapped Existing drain length: ${feature.properties.existing_drain_length_m} m`), "", "Check currentness, drainage connectivity, outfalls, water-level observations, and source applicability in the field.", ...evidence.missing_for_flood_depth.map((item) => `NOT AVAILABLE: ${item}`), "No flood depth, affected streets, evacuation destinations, or safety conclusion is provided."];
      const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = "india-sim-ward-flood-field-screen.txt"; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setFloodError(readableServiceMessage(error, "The field-screen report could not be created.")); }
    finally { setFloodReportLoading(false); }
  };

  const askLocalAgent = async (questionOverride?: string) => {
    const question = (questionOverride ?? agentQuestion).trim();
    if (!question || agentLoading || !agentStatus.ready) return;
    setAgentLoading(true);
    setAgentError("");
    setAgentAnswer(null);
    try {
      const asksAboutSelectedRainfallRun = /\b(?:selected|saved)\b.*\brainfall run\b|\brainfall run\b/i.test(question);
      const asksAboutSelectedModelRun = /\b(?:selected|saved)\b.*\b(?:assumption|model) run\b|\b(?:assumption|model) run\b/i.test(question);
      const asksAboutPreparednessPlan = /\b(?:preparedness|action plan|planning option)\b/i.test(question);
      const asksAboutInvestment = /\binvestment option\b/i.test(question);
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, ...(decisionRecord ? { decision_id: decisionRecord.decision_id } : {}), ...(accessRun ? { run_id: accessRun.run_id } : {}), ...(savedFloodRunId && asksAboutSelectedRainfallRun ? { flood_run_id: savedFloodRunId } : {}), ...(asksAboutSelectedModelRun && illustrativeFloodModel?.saved_run?.run_id ? { flood_model_run_id: illustrativeFloodModel.saved_run.run_id } : {}), ...(preparednessPlan && asksAboutPreparednessPlan ? { preparedness_run_id: preparednessPlan.run_id } : {}), ...(investmentPlan && selectedInvestmentOption && asksAboutInvestment ? { investment_run_id: investmentPlan.run_id, investment_option_id: selectedInvestmentOption.id } : {}) }),
      });
      const result = await response.json() as LocalAgentResponse | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Local assistant request failed." : "Local assistant request failed.");
      const completed = result as LocalAgentResponse;
      setAgentAnswer(completed);
      if (completed.new_run) {
        setAccessRun(completed.new_run);
        setSelectedClosureRoads(completed.new_run.road_names.length ? completed.new_run.road_names : [completed.new_run.road_name]);
        setClosureLayerVisible(true);
        await showClosureOverlay(completed.new_run.closed_edges_geojson);
        await showNewlyUnreachableOverlay(completed.new_run.newly_unreachable_nodes_geojson);
      }
    } catch (error) {
      setAgentError(readableServiceMessage(error, "The assistant could not complete this request. Please try again."));
    } finally {
      setAgentLoading(false);
    }
  };

  const saveDecisionComparison = async () => {
    const sourceRunId = decisionMode === "road_closure" ? accessRun?.run_id : decisionMode === "preparedness" ? preparednessPlan?.run_id : undefined;
    if (!sourceRunId || decisionMode === "investment" || decisionSaving || (decisionMode === "preparedness" && !selectedPreparednessOption)) return;
    setDecisionSaving(true);
    setDecisionError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/decisions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision_type: decisionMode === "road_closure" ? "road_closure" : "preparedness", source_run_id: sourceRunId, ...(decisionMode === "preparedness" ? { option_id: selectedPreparednessOption?.id } : {}) }) });
      const result = await response.json() as DecisionRecord | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Could not save decision comparison." : "Could not save decision comparison.");
      setDecisionRecord(result as DecisionRecord);
      setAgentAnswer(null);
    } catch (error) { setDecisionError(readableServiceMessage(error, "Could not save decision comparison.")); }
    finally { setDecisionSaving(false); }
  };

  const explainSavedDecision = () => {
    if (!decisionRecord) return;
    const question = `Explain the pros, cons and unknowns in the saved decision comparison: ${decisionRecord.title}. Use only its recorded outputs.`;
    setAgentQuestion(question);
    void askLocalAgent(question);
  };

  const createPreparednessPlan = async () => {
    if (!hasValidEnteredScenario || !Number.isFinite(Number(policyBudgetCrore)) || Number(policyBudgetCrore) <= 0 || Object.values(preparednessRates).some((rate) => !Number.isFinite(Number(rate)) || Number(rate) <= 0)) return;
    setPreparednessLoading(true);
    setPreparednessError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/preparedness/plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rainfall_mm: enteredRainfallMm, duration_hours: enteredDurationHours, budget_crore: Number(policyBudgetCrore), cell_review_rate_inr: Number(preparednessRates.cell), record_verification_rate_inr: Number(preparednessRates.record), shelter_audit_rate_inr: Number(preparednessRates.shelter) }),
      });
      const result = await response.json() as PreparednessPlan | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Could not create the preparedness plan." : "Could not create the preparedness plan.");
      const plan = result as PreparednessPlan;
      setPreparednessPlan(plan);
      setPreparednessOptionId(plan.selected_option_id);
      setAgentAnswer(null);
      setAgentError("");
    } catch (error) {
      setPreparednessError(readableServiceMessage(error, "Could not create the plan. Check that the local API is running and try again."));
    } finally {
      setPreparednessLoading(false);
    }
  };

  const createInvestmentPlan = async () => {
    const rates = Object.values(investmentRates).map(Number);
    if (!Number.isFinite(Number(policyBudgetCrore)) || Number(policyBudgetCrore) <= 0 || rates.some((rate) => !Number.isFinite(rate) || rate <= 0) || !Number.isFinite(Number(investmentSpacingM)) || Number(investmentSpacingM) <= 0 || investmentLoading) return;
    setInvestmentLoading(true);
    setInvestmentError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/investments/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ budget_crore: Number(policyBudgetCrore), drainage_site_allowance_inr: Number(investmentRates.drainage), streetlight_site_allowance_inr: Number(investmentRates.streetlights), health_access_site_allowance_inr: Number(investmentRates.healthAccess), streetlight_spacing_m: Number(investmentSpacingM) }),
      });
      const result = await response.json() as InvestmentPlan | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Could not compare investment options." : "Could not compare investment options.");
      const plan = result as InvestmentPlan;
      setInvestmentPlan(plan);
      setInvestmentOptionId("health_access");
      setDecisionRecord(null);
      setAgentAnswer(null);
      setAgentError("");
    } catch (error) { setInvestmentError(readableServiceMessage(error, "Could not compare options. Check that the local planning service is running and try again.")); }
    finally { setInvestmentLoading(false); }
  };

  const runRainfallScreening = async () => {
    const rainfall = Number(rainfallAmount);
    const duration = Number(rainfallDuration);
    if (!Number.isFinite(rainfall) || !Number.isFinite(duration) || rainfall <= 0 || duration <= 0 || floodScenarioLoading) return;
    setFloodScenarioLoading(true);
    setFloodError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/flood/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rainfall_mm: rainfall, duration_hours: duration }),
      });
      const result = await response.json() as SavedFloodRun | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Rainfall calculation failed." : "Rainfall calculation failed.");
      const savedRun = result as SavedFloodRun;
      setRainfallScreening(savedRun.outputs);
      setSavedFloodRunId(savedRun.run_id);
      setSavedFloodRuns((runs) => [savedRun, ...runs.filter((run) => run.run_id !== savedRun.run_id)].slice(0, 8));
    } catch (error) {
      setFloodError(readableServiceMessage(error, "The rainfall calculation could not be completed. Please try again."));
    } finally {
      setFloodScenarioLoading(false);
    }
  };

  const openSavedFloodRun = async (runId: string) => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/flood/runs/${encodeURIComponent(runId)}`);
      const result = await response.json() as SavedFloodRun | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Saved scenario could not be opened." : "Saved scenario could not be opened.");
      const savedRun = result as SavedFloodRun;
      setRainfallAmount(String(savedRun.inputs.rainfall_mm));
      setRainfallDuration(String(savedRun.inputs.duration_hours));
      setRainfallScreening(savedRun.outputs);
      setSavedFloodRunId(savedRun.run_id);
      setFloodError("");
    } catch (error) {
      setFloodError(readableServiceMessage(error, "The saved scenario could not be opened."));
    }
  };

  const runIllustrativeFloodModel = async () => {
    const rainfall = Number(rainfallAmount);
    const duration = Number(rainfallDuration);
    const runoffFraction = Number(demoRunoffFraction);
    const drainCapacity = Number(demoDrainCapacity);
    if (!Number.isFinite(rainfall) || rainfall <= 0 || rainfall > 1000 || !Number.isFinite(duration) || duration <= 0 || duration > 168 || !Number.isFinite(runoffFraction) || runoffFraction <= 0 || runoffFraction > 1 || !Number.isFinite(drainCapacity) || drainCapacity < 0 || drainCapacity > 10000 || illustrativeModelLoading) {
      setIllustrativeModelError("Use rainfall 1–1000 mm, duration >0–168 hours, runoff fraction >0–1, and assumed drain capacity 0–10,000 m³/hour/km.");
      return;
    }
    setIllustrativeModelLoading(true);
    setIllustrativeModelError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/flood/illustrative-model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rainfall_mm: rainfall, duration_hours: duration, runoff_fraction: runoffFraction, assumed_drain_capacity_m3_per_hour_per_km: drainCapacity }),
      });
      const result = await response.json() as IllustrativeFloodModel | { detail?: string };
      if (!response.ok) throw new Error("detail" in result ? result.detail || "Illustrative model did not run." : "Illustrative model did not run.");
      setIllustrativeFloodModel(result as IllustrativeFloodModel);
    } catch (error) {
      setIllustrativeModelError(readableServiceMessage(error, "The scenario estimate could not be completed. Please try again."));
    } finally {
      setIllustrativeModelLoading(false);
    }
  };

  const downloadIllustrativeFloodReport = () => {
    if (!illustrativeFloodModel) return;
    const model = illustrativeFloodModel;
    const lines = [
      "BHARAT YANTRA · ASSUMPTION-BASED FLOOD MODEL DEMONSTRATION",
      model.status,
      `Saved run: ${model.saved_run.run_id} · model ${model.saved_run.model_version} · created ${model.saved_run.created_at_utc}`,
      `Source checksums: ${JSON.stringify(model.saved_run.source_checksums)}`,
      `Scenario: ${model.scenario.rainfall_mm} mm over ${model.scenario.duration_hours} hours (mean ${model.scenario.mean_intensity_mm_per_hour} mm/hour). Hypothetical input, not a forecast.`,
      `Assumptions: runoff fraction ${model.assumptions.runoff_fraction}; notional capacity ${model.assumptions.drain_capacity_m3_per_hour_per_km} m³/hour per mapped Existing-drain km.`,
      `Across ${model.summary.cell_count} cells: gross rain ${model.summary.gross_rain_m3} m³; estimated runoff ${model.summary.assumed_runoff_m3} m³. In ${model.summary.evaluable_cell_count} cells with mapped Existing lines, the assumed removal budget is ${model.summary.assumed_drain_capacity_m3} m³ and modeled residual runoff is ${model.summary.modelled_residual_runoff_m3} m³; ${model.summary.modelled_exceedance_cell_count} evaluated cells have positive residual. ${model.summary.capacity_unknown_cell_count} cells are excluded because mapped capacity is unknown.`,
      model.method,
      "Sensitivity sweep (deterministic ±25% input cases; not a probability interval):",
      ...model.sensitivity.cases.map((item) => `runoff=${item.runoff_fraction_assumption}; drain-capacity=${item.drain_capacity_assumption_m3_per_hour_per_km} m³/hour/km; residual-arithmetic=${item.residual_arithmetic_total_m3} m³; positive-residual cells=${item.cells_above_assumed_capacity}`),
      "These are illustrative model outputs, not observed flooding, flood depth, affected places, or evacuation guidance.",
      "Rank | cell | nearest named OSM road cue | DSM P10 source m | Existing line m | estimated runoff m³ | assumed removal m³ | residual runoff m³ | residual-equivalent mm",
      ...model.features.slice(0, 20).map((cell) => [cell.model_rank, cell.cell_id, cell.nearest_named_road || "no named cue", cell.dsm_p10_m?.toFixed(2) ?? "missing", cell.existing_drain_length_m.toFixed(0), cell.assumed_runoff_m3.toFixed(1), cell.assumed_drain_capacity_m3?.toFixed(1) ?? "capacity unknown", cell.modelled_residual_runoff_m3?.toFixed(1) ?? "not evaluated", cell.residual_runoff_equivalent_mm?.toFixed(2) ?? "unknown", cell.terrain_weighted_screening_index?.toFixed(2) ?? "unknown"].join(" | ")),
      "",
      ...model.limitations.map((limitation) => `LIMITATION: ${limitation}`),
      "Inputs include a provisional local F/S boundary, Copernicus GLO-30 DSM, and mapped MCGM drain lines. Source rights remain under review. Model assumptions are not local measurements.",
    ];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "india-sim-assumption-model-demonstration.txt";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const toggleFloodReviewOverlay = () => setFloodReviewVisible((visible) => !visible);

  useEffect(() => {
    let cancelled = false;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const previous = floodReviewLayerRef.current;
    if (previous) {
      viewer.dataSources.remove(previous, true);
      floodReviewLayerRef.current = null;
    }
    if (!floodReviewVisible || !floodScreeningAreas || sceneState !== "ready") return;
    const modelFeatures = illustrativeFloodModel?.features.filter((feature) => !feature.capacity_unknown && feature.geometry).slice(0, 8);
    const features = modelFeatures?.length
      ? modelFeatures.map((feature) => ({ type: "Feature", geometry: feature.geometry, properties: { name: feature.cell_id, model_rank: feature.model_rank } }))
      : rainfallPriorityAreas.map((feature, index) => ({ type: "Feature", geometry: feature.geometry, properties: { name: feature.properties.cell_id, priority_rank: index + 1 } }));
    void GeoJsonDataSource.load({ type: "FeatureCollection", features } as never, {
      clampToGround: true,
      stroke: Color.fromCssColorString(modelFeatures?.length ? "#e57559" : "#f1b94f"),
      fill: Color.fromCssColorString(modelFeatures?.length ? "#d85d4d" : "#f1b94f").withAlpha(0.24),
      strokeWidth: 2,
    }).then(async (source) => {
      if (cancelled || viewer.isDestroyed()) return;
      for (const entity of source.entities.values) {
        if (!entity.polygon) continue;
        entity.polygon.material = new ColorMaterialProperty(Color.fromCssColorString(modelFeatures?.length ? "#d85d4d" : "#f1b94f").withAlpha(0.24));
        entity.polygon.outline = new ConstantProperty(true);
        entity.polygon.outlineColor = new ConstantProperty(Color.fromCssColorString(modelFeatures?.length ? "#ffab91" : "#ffda83"));
      }
      source.show = true;
      await viewer.dataSources.add(source);
      if (!cancelled) floodReviewLayerRef.current = source;
      else viewer.dataSources.remove(source, true);
    }).catch((error: unknown) => console.warn("Could not synchronize flood review cells to map", error));
    return () => { cancelled = true; };
  }, [floodReviewVisible, floodScreeningAreas, rainfallPriorityAreas, illustrativeFloodModel, sceneState]);

  useEffect(() => {
    let cancelled = false;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const floodPrevious = layerSourcesRef.current.mcgmFloodRecords;
    const shelterPrevious = layerSourcesRef.current.mcgmShelters;
    if (floodPrevious) viewer.dataSources.remove(floodPrevious, true);
    if (shelterPrevious) viewer.dataSources.remove(shelterPrevious, true);
    delete layerSourcesRef.current.mcgmFloodRecords;
    delete layerSourcesRef.current.mcgmShelters;
    if (!municipalFloodContext || sceneState !== "ready") return;

    void (async () => {
      const floodLayer = await GeoJsonDataSource.load(municipalFloodContext.flood_records as never, {
        clampToGround: true,
        stroke: Color.fromCssColorString("#c94b40"),
        fill: Color.fromCssColorString("#c94b40").withAlpha(0.20),
        strokeWidth: 2.5,
      });
      for (const entity of floodLayer.entities.values) {
        const props = entity.properties;
        const name = props?.name?.getValue(JulianDate.now());
        const flag = props?.source_record_flag?.getValue(JulianDate.now());
        if (typeof name === "string") entity.name = name;
        if (!entity.polygon) continue;
        const markedForDeletion = typeof flag === "string" && flag.toLowerCase().includes("deletion");
        const color = Color.fromCssColorString(markedForDeletion ? "#93847a" : "#c94b40");
        entity.polygon.material = new ColorMaterialProperty(color.withAlpha(markedForDeletion ? 0.10 : 0.20));
        entity.polygon.outline = new ConstantProperty(true);
        entity.polygon.outlineColor = new ConstantProperty(color.withAlpha(markedForDeletion ? 0.85 : 1));
      }

      const shelterLayer = await GeoJsonDataSource.load(municipalFloodContext.shelters as never, {
        clampToGround: true,
        markerColor: Color.fromCssColorString("#79b8d5"),
        markerSize: 12,
      });
      for (const entity of shelterLayer.entities.values) {
        const name = entity.properties?.name?.getValue(JulianDate.now());
        if (typeof name === "string") entity.name = name;
        if (!entity.position) continue;
        entity.billboard = undefined;
        entity.point = undefined;
        entity.ellipse = new EllipseGraphics({
          semiMajorAxis: new ConstantProperty(12),
          semiMinorAxis: new ConstantProperty(12),
          material: new ColorMaterialProperty(Color.fromCssColorString("#79b8d5")),
          heightReference: new ConstantProperty(HeightReference.CLAMP_TO_GROUND),
        });
      }

      if (cancelled || viewer.isDestroyed()) return;
      floodLayer.show = enabledLayers.mcgmFloodRecords;
      shelterLayer.show = enabledLayers.mcgmShelters;
      await viewer.dataSources.add(floodLayer);
      await viewer.dataSources.add(shelterLayer);
      layerSourcesRef.current.mcgmFloodRecords = floodLayer;
      layerSourcesRef.current.mcgmShelters = shelterLayer;
    })().catch((error: unknown) => console.warn("Could not load MCGM disaster-management context", error));

    return () => {
      cancelled = true;
      if (!viewer.isDestroyed()) {
        const floodLayer = layerSourcesRef.current.mcgmFloodRecords;
        const shelterLayer = layerSourcesRef.current.mcgmShelters;
        if (floodLayer) viewer.dataSources.remove(floodLayer, true);
        if (shelterLayer) viewer.dataSources.remove(shelterLayer, true);
        delete layerSourcesRef.current.mcgmFloodRecords;
        delete layerSourcesRef.current.mcgmShelters;
      }
    };
  }, [municipalFloodContext, sceneState, enabledLayers.mcgmFloodRecords, enabledLayers.mcgmShelters]);

  useEffect(() => {
    let cancelled = false;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    for (const layer of preparednessLayersRef.current) viewer.dataSources.remove(layer, true);
    preparednessLayersRef.current = [];
    if (activeMapPlanLayers.length === 0) return;
    const colors: Record<string, string> = { field_review: "#f0c96c", record_verification: "#e97868", shelter_audit: "#72b8d5", drainage: "#168678", streetlights: "#d79b22", health_access: "#4b77a8" };
    void Promise.all(activeMapPlanLayers.map(async (work) => {
      if (work.feature_collection.features.length === 0) return null;
      const selectedTaskLayer = actionTrackerMode && Boolean(selectedWardActionId) && selectedWardActionId?.startsWith(`${work.workstream}:`);
      const color = Color.fromCssColorString(selectedTaskLayer ? "#ffe36e" : colors[work.workstream] || "#f0c96c");
      const candidateRadius = selectedTaskLayer ? 52 : work.workstream === "streetlights" ? 42 : work.workstream === "health_access" ? 34 : 18;
      const source = await GeoJsonDataSource.load(work.feature_collection as never, { clampToGround: true, stroke: color, strokeWidth: selectedTaskLayer ? 9 : 5, fill: color.withAlpha(selectedTaskLayer ? 0.72 : 0.27), markerColor: color, markerSize: selectedTaskLayer ? 20 : 13 });
      for (const entity of source.entities.values) {
        if (entity.polyline) entity.polyline.material = new PolylineOutlineMaterialProperty({ color, outlineColor: Color.fromCssColorString("#182b27"), outlineWidth: 2 });
        if (entity.polygon) { entity.polygon.material = new ColorMaterialProperty(color.withAlpha(selectedTaskLayer ? 0.68 : 0.24)); entity.polygon.outline = new ConstantProperty(true); entity.polygon.outlineColor = new ConstantProperty(color); }
        if (entity.position) {
          entity.billboard = undefined;
          entity.point = undefined;
          entity.ellipse = new EllipseGraphics({ semiMajorAxis: new ConstantProperty(candidateRadius), semiMinorAxis: new ConstantProperty(candidateRadius), material: new ColorMaterialProperty(color), outline: new ConstantProperty(true), outlineColor: new ConstantProperty(Color.fromCssColorString("#18332c")), outlineWidth: new ConstantProperty(2), heightReference: new ConstantProperty(HeightReference.CLAMP_TO_GROUND) });
        }
      }
      return source;
    })).then(async (sources) => {
      if (cancelled || viewer.isDestroyed()) return;
      for (const source of sources) {
        if (!source) continue;
        await viewer.dataSources.add(source);
        if (cancelled || viewer.isDestroyed()) { viewer.dataSources.remove(source, true); continue; }
        preparednessLayersRef.current.push(source);
      }
    }).catch((error: unknown) => console.warn("Could not draw preparedness plan features", error));
    return () => {
      cancelled = true;
      if (!viewer.isDestroyed()) for (const layer of preparednessLayersRef.current) viewer.dataSources.remove(layer, true);
      preparednessLayersRef.current = [];
    };
  }, [activeMapPlanLayers, actionTrackerMode, selectedWardActionId, sceneState]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!actionTrackerMode || !selectedWardActionId || !viewer || viewer.isDestroyed()) return;
    const selected = wardActionItems.find((item) => item.id === selectedWardActionId);
    const center = selected ? getFeatureCenter(selected.geometry) : null;
    if (!selected || !center) return;
    const highlight = Color.fromCssColorString("#ffe36e");
    const entity = viewer.entities.add({
      id: `ward-action-highlight-${selected.id}`,
      position: Cartesian3.fromDegrees(center[0], center[1]),
      point: { pixelSize: 30, color: highlight, outlineColor: Color.fromCssColorString("#18241d"), outlineWidth: 5, heightReference: HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      ellipse: new EllipseGraphics({ semiMajorAxis: new ConstantProperty(95), semiMinorAxis: new ConstantProperty(95), material: new ColorMaterialProperty(highlight.withAlpha(0.18)), outline: new ConstantProperty(true), outlineColor: new ConstantProperty(Color.WHITE), outlineWidth: new ConstantProperty(4), heightReference: new ConstantProperty(HeightReference.CLAMP_TO_GROUND) }),
    });
    focusedActionEntityRef.current = entity;
    viewer.scene.requestRender();
    return () => {
      if (!viewer.isDestroyed()) viewer.entities.remove(entity);
      if (focusedActionEntityRef.current === entity) focusedActionEntityRef.current = null;
    };
  }, [actionTrackerMode, selectedWardActionId, wardActionItems, sceneState]);

  useEffect(() => {
    if (!hostRef.current) return;

    const viewer = new Viewer(hostRef.current, {
      animation: false,
      baseLayer: false,
      baseLayerPicker: false,
      fullscreenButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      selectionIndicator: false,
      timeline: false,
      terrainProvider: new EllipsoidTerrainProvider(),
    });
    viewer.scene.backgroundColor = Color.fromCssColorString("#111d22");
    viewer.scene.globe.baseColor = Color.fromCssColorString("#213137");
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.globe.enableLighting = false;
    viewer.camera.setView({
      destination: Rectangle.fromDegrees(67, 5, 98, 36),
    });
    viewerRef.current = viewer;

    let cancelled = false;
    const loadConfiguredLayers = async () => {
      try {
        if (terrainUrl) {
          viewer.terrainProvider = await CesiumTerrainProvider.fromUrl(terrainUrl);
          if (cancelled) return;
        }
        if (wardUrl) {
          const source = await GeoJsonDataSource.load(wardUrl, {
            clampToGround: true,
            stroke: Color.fromCssColorString("#e8b85a"),
            strokeWidth: 3,
            fill: Color.fromCssColorString("#e8b85a").withAlpha(0.12),
          });
          if (cancelled) return;
          await viewer.dataSources.add(source);
          layerSourcesRef.current.boundary = source;
          await viewer.flyTo(source, { duration: 1.4 });
          setBoundaryLoaded(true);
        }

        if (localSourcePreview) {
          await loadLocalLayer("roads");
        }

        if (!cancelled) {
          setSceneState(wardUrl || terrainUrl ? "ready" : "empty");
          setSceneMessage(
            localSourcePreview
              ? "Local MCGM and OpenStreetMap source layers are displayed for inspection. Rights and source quality remain under review; no terrain or flood simulation is loaded."
              : boundaryUrl
              ? "The configured ward boundary is visible. Flood and accessibility outputs have not been added."
              : terrainUrl
                ? "Terrain is loaded, but no ward boundary is configured."
              : "No ward, imagery, or terrain source is configured. The globe is an ellipsoid only.",
          );
        }
      } catch (error) {
        if (cancelled) return;
        setSceneState("error");
        setSceneMessage(error instanceof Error ? error.message : "A configured layer could not be loaded.");
      }
    };

    void loadConfiguredLayers();
    return () => {
      cancelled = true;
      viewer.destroy();
      viewerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!areaPickMode || !viewer || viewer.isDestroyed()) return;
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((movement: { position: import("cesium").Cartesian2 }) => {
      const picked = viewer.camera.pickEllipsoid(movement.position, viewer.scene.globe.ellipsoid);
      if (!picked) { setFacilityRoutesError("Click a visible point inside the ward on the map."); return; }
      const cartographic = Cartographic.fromCartesian(picked);
      const longitude = CesiumMath.toDegrees(cartographic.longitude);
      const latitude = CesiumMath.toDegrees(cartographic.latitude);
      setAreaPickMode(false);
      setFacilityRoutesLoading(true);
      setFacilityRoutesError("");
      void fetch(`${apiBaseUrl}/api/v1/accessibility/routes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ longitude, latitude, radius_m: Number(facilityRouteRadius), closed_road_names: facilityClosedRoads }),
      }).then(async (response) => {
        const result = await response.json() as FacilityRoutesResult | { detail?: string };
        if (!response.ok) throw new Error("detail" in result ? result.detail || "Nearby routes could not be found." : "Nearby routes could not be found.");
        const routes = result as FacilityRoutesResult;
        setFacilityRoutes(routes);
        drawFacilityRoutes(routes);
      }).catch((error: unknown) => {
        setFacilityRoutes(null);
        clearFacilityRoutes();
        clearRoadScenarioOverlays();
        setFacilityRoutesError(readableServiceMessage(error, "Could not find mapped health facilities near that point."));
      }).finally(() => setFacilityRoutesLoading(false));
    }, ScreenSpaceEventType.LEFT_CLICK);
    return () => handler.destroy();
  }, [areaPickMode, facilityRouteRadius, facilityClosedRoads, sceneState]);

  const loadLocalLayer = async (id: LayerId): Promise<GeoJsonDataSource | undefined> => {
    const viewer = viewerRef.current;
    if (!viewer) return undefined;
    if (id === "boundary") return layerSourcesRef.current.boundary;
    if (id === "satellite") return undefined;
    const isDrainLayer = id === "existingDrains" || id === "proposedDrains";
    const existing = layerSourcesRef.current[id];
    if (existing) return existing;

    let url: string;
    let options: Record<string, unknown>;
    if (id === "roads") {
      url = "/local-data/osm-roads.geojson";
      options = { clampToGround: true, stroke: Color.fromCssColorString("#263238"), strokeWidth: 5.5 };
    } else if (id === "buildings") {
      url = "/local-data/osm-buildings-ward.geojson";
      options = { clampToGround: false, stroke: Color.TRANSPARENT, fill: Color.fromCssColorString("#b36e52").withAlpha(0.48) };
    } else if (id === "openBuildings") {
      url = "/local-data/open-buildings-ward.geojson";
      options = { clampToGround: true, stroke: Color.fromCssColorString("#e7c178").withAlpha(0.38), strokeWidth: 0.5, fill: Color.fromCssColorString("#e7c178").withAlpha(0.28) };
    } else if (id === "facilities") {
      url = "/local-data/osm-emergency-facilities.geojson";
      options = { clampToGround: true };
    } else if (isDrainLayer) {
      url = "/local-data/mcgm-drains.geojson";
      options = { clampToGround: true, stroke: Color.fromCssColorString("#00695c"), strokeWidth: 5.5 };
    } else {
      url = "/local-data/mcgm-manholes.geojson";
      options = { clampToGround: true };
    }

    const source = await GeoJsonDataSource.load(url, options);
    if (id === "roads") {
      for (const entity of source.entities.values) {
        if (!entity.polyline) continue;
        entity.polyline.width = new ConstantProperty(5.5);
        entity.polyline.material = new PolylineOutlineMaterialProperty({
          color: Color.fromCssColorString("#263238"),
          outlineColor: Color.fromCssColorString("#f3ead6").withAlpha(0.88),
          outlineWidth: 0.75,
        });
      }
    }
    if (id === "buildings") {
      for (const entity of source.entities.values) {
        if (!entity.polygon || !entity.properties) continue;
        const properties = entity.properties.getValue(JulianDate.now());
        const taggedHeight = positiveNumber(properties?.height);
        const taggedLevels = positiveNumber(properties?.["building:levels"]);
        const extrusionHeight = taggedHeight ?? (taggedLevels ? taggedLevels * 3 : undefined);
        if (extrusionHeight) entity.polygon.extrudedHeight = new ConstantProperty(extrusionHeight);
      }
    }
    if (id === "facilities" || id === "manholes") {
      const color = Color.fromCssColorString(id === "facilities" ? "#f1a28a" : "#f2d27f");
      for (const entity of source.entities.values) {
        if (!entity.position) continue;
        const radius = id === "facilities" ? 12 : 4;
        entity.billboard = undefined;
        entity.point = undefined;
        entity.ellipse = new EllipseGraphics({
          semiMajorAxis: new ConstantProperty(radius),
          semiMinorAxis: new ConstantProperty(radius),
          material: new ColorMaterialProperty(color),
          heightReference: new ConstantProperty(HeightReference.CLAMP_TO_GROUND),
        });
      }
    }
    await viewer.dataSources.add(source);
    if (isDrainLayer) {
      layerSourcesRef.current.existingDrains = source;
      layerSourcesRef.current.proposedDrains = source;
      for (const entity of source.entities.values) {
        if (!entity.polyline || !entity.properties) continue;
        const status = entity.properties.getValue(JulianDate.now())?.USER_TEXT2;
        const lineColor = Color.fromCssColorString(status === "Proposal" ? "#805000" : "#00695c");
        entity.polyline.width = new ConstantProperty(5.5);
        entity.polyline.material = new PolylineOutlineMaterialProperty({
          color: lineColor,
          outlineColor: Color.fromCssColorString("#f3ead6").withAlpha(0.9),
          outlineWidth: 0.75,
        });
        entity.show = status === "Proposal" ? enabledLayers.proposedDrains : enabledLayers.existingDrains;
        drainEntitiesRef.current.push({ entity, status });
      }
    } else {
      layerSourcesRef.current[id] = source;
    }
    return source;
  };

  const toggleLayer = (id: LayerId) => {
    const visible = !enabledLayers[id];
    setEnabledLayers((current) => ({ ...current, [id]: visible }));
    if (id === "mcgmFloodRecords" || id === "mcgmShelters") {
      const source = layerSourcesRef.current[id];
      if (source) source.show = visible;
      return;
    }
    if (id === "terrainContext") {
      const requestId = ++dsmContextRequestRef.current;
      void (async () => {
        const viewer = viewerRef.current;
        if (!viewer) return;
        if (dsmContextLayerRef.current) {
          dsmContextLayerRef.current.show = visible;
          return;
        }
        if (!visible) return;
        try {
          let evidence: FloodReadiness;
          if (floodEvidence) evidence = floodEvidence;
          else {
            const response = await fetch(`${apiBaseUrl}/api/v1/flood/evidence`);
            if (!response.ok) throw new Error("DSM display metadata could not be loaded.");
            evidence = await response.json() as FloodReadiness;
          }
          const bounds = evidence.terrain.bounds_wgs84;
          const provider = await SingleTileImageryProvider.fromUrl("/local-data/copernicus-dsm-context.png", {
            rectangle: Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north),
            credit: "Copernicus DEM GLO-30 DSM · © DLR / Airbus under Copernicus by EU and ESA",
          });
          if (requestId !== dsmContextRequestRef.current || viewer.isDestroyed()) return;
          const layer = viewer.imageryLayers.addImageryProvider(provider);
          layer.alpha = 0.68;
          layer.show = requestId === dsmContextRequestRef.current;
          dsmContextLayerRef.current = layer;
        } catch (error) {
          if (requestId !== dsmContextRequestRef.current) return;
          setEnabledLayers((current) => ({ ...current, terrainContext: false }));
          setLayerMessage(error instanceof Error ? `DSM context is unavailable: ${error.message}` : "DSM context is unavailable. Other map layers remain available.");
        }
      })();
      return;
    }
    if (id === "satellite") {
      const requestId = ++satelliteRequestRef.current;
      void (async () => {
        const viewer = viewerRef.current;
        if (!viewer) return;
        if (satelliteLayerRef.current) {
          satelliteLayerRef.current.show = visible;
          return;
        }
        if (!visible) return;
        try {
          const provider = await ArcGisMapServerImageryProvider.fromUrl(
            "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
          );
          if (viewer.isDestroyed()) return;
          const layer = viewer.imageryLayers.addImageryProvider(provider);
          layer.show = requestId === satelliteRequestRef.current;
          satelliteLayerRef.current = layer;
        } catch (error) {
          if (requestId !== satelliteRequestRef.current) return;
          setEnabledLayers((current) => ({ ...current, satellite: false }));
          setLayerMessage(error instanceof Error ? `Satellite imagery could not load: ${error.message}` : "Satellite imagery could not load. Local data layers remain available.");
        }
      })();
      return;
    }
    if (id === "existingDrains" || id === "proposedDrains") {
      void (async () => {
        const source = layerSourcesRef.current.existingDrains ?? (visible ? await loadLocalLayer(id) : undefined);
        if (!source) return;
        const wantedStatus = id === "proposedDrains" ? "Proposal" : "Existing";
        for (const item of drainEntitiesRef.current) if (item.status === wantedStatus) item.entity.show = visible;
      })().catch((error: unknown) => setLayerMessage(error instanceof Error ? `Drainage layer unavailable: ${error.message}` : "Could not load the drainage layer."));
    } else {
      void (async () => {
        const source = layerSourcesRef.current[id] ?? (visible ? await loadLocalLayer(id) : undefined);
        if (source) source.show = visible;
      })().catch((error: unknown) => {
        setEnabledLayers((current) => ({ ...current, [id]: false }));
        setLayerMessage(error instanceof Error ? `Selected map layer unavailable: ${error.message}` : "Could not load the selected layer. Other map layers remain available.");
      });
    }
  };

  const zoom = (direction: "in" | "out") => {
    const camera = viewerRef.current?.camera;
    if (!camera) return;
    if (direction === "in") camera.zoomIn(300);
    else camera.zoomOut(300);
  };

  const resetView = () => {
    const viewer = viewerRef.current;
    const boundary = layerSourcesRef.current.boundary;
    if (viewer && boundary) void viewer.flyTo(boundary, { duration: 0.8 });
    else viewer?.camera.flyTo({ destination: Rectangle.fromDegrees(72.82, 18.96, 72.89, 19.04), duration: 0.8 });
  };

  const toggleSceneMode = () => {
    const viewer = viewerRef.current;
    if (!viewer || sceneModeChanging) return;
    const boundary = layerSourcesRef.current.boundary;
    setSceneModeChanging(true);
    const onMorphComplete = () => {
      viewer.scene.morphComplete.removeEventListener(onMorphComplete);
      if (boundary) void viewer.flyTo(boundary, { duration: 0.7 }).finally(() => setSceneModeChanging(false));
      else setSceneModeChanging(false);
    };
    viewer.scene.morphComplete.addEventListener(onMorphComplete);
    if (twoDimensional) viewer.scene.morphTo3D(0.55);
    else viewer.scene.morphTo2D(0.55);
    setTwoDimensional(!twoDimensional);
  };

  const activateDecisionMode = (mode: "preparedness" | "road_closure" | "investment") => {
    setDecisionMode(mode);
    setActionTrackerMode(false);
    setDecisionRecord(null);
    setFloodReviewVisible(false);
    setEnabledLayers((current) => ({
      ...current,
      mcgmFloodRecords: false,
      mcgmShelters: false,
      facilities: mode === "road_closure" ? true : mode === "investment" ? false : current.facilities,
    }));
  };

  const updateWardActionStatus = (id: string, status: WardActionStatus) => {
    setWardActionStatuses((current) => ({ ...current, [id]: status }));
  };

  const focusWardAction = (action: WardActionItem) => {
    if (!viewerRef.current || viewerRef.current.isDestroyed()) return;
    setActionTrackerMode(true);
    setSelectedWardActionId(action.id);
    setLayerMessage(`${action.location} · ${action.title}`);
  };

  const navigateToSection = (id: string) => {
    if (id !== "access-baseline") {
      setAreaPickMode(false);
      setFacilityRoutes(null);
      clearFacilityRoutes();
    }
    if (id === "investment-planner") activateDecisionMode("investment");
    if (id === "readiness-planner") activateDecisionMode("preparedness");
    if (id === "road-closure-planner") activateDecisionMode("road_closure");
    if (id === "ward-action-tracker") activateDecisionMode("preparedness");
    if (id === "flood-lab") {
      setFloodReviewVisible(true);
      setEnabledLayers((current) => ({ ...current, mcgmFloodRecords: true, mcgmShelters: false, facilities: false }));
    }
    if (id === "access-baseline") {
      setFloodReviewVisible(false);
      setEnabledLayers((current) => ({ ...current, mcgmFloodRecords: false, mcgmShelters: false, facilities: true }));
    }
    const openAndScroll = () => {
      const section = document.getElementById(id);
      const disclosure = section?.closest("details") ?? section?.querySelector("details");
      disclosure?.setAttribute("open", "");
      const featureSection = section?.closest(".policy-lab, .flood-lab, .access-lab, .assistant-lab") ?? section;
      featureSection?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    requestAnimationFrame(() => requestAnimationFrame(openAndScroll));
  };

  const attribution = [
    import.meta.env.VITE_WARD_BOUNDARY_ATTRIBUTION,
    import.meta.env.VITE_TERRAIN_ATTRIBUTION,
    ...(localSourcePreview ? ["MCGM / Esri India · local source preview", "© OpenStreetMap contributors · ODbL", "Google Research · Open Buildings v3 via Overture Maps · CC BY 4.0 / ODbL review pending", ...(enabledLayers.satellite ? ["Satellite: Esri, Vantor, Earthstar Geographics, and GIS User Community"] : [])] : []),
    ...(localSourcePreview && enabledLayers.terrainContext ? ["Copernicus DEM GLO-30 · © DLR / Airbus under Copernicus by EU and ESA"] : []),
  ].filter(Boolean);

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Bharat Yantra home">
          <span className="brand-mark" aria-hidden="true">BY</span>
          <span className="brand-lockup"><span className="brand-name">BHARAT <strong>YANTRA</strong></span><span className="brand-tagline">An indigenous engineering engine for India</span></span>
        </a>
        <nav className="topbar-nav" aria-label="Project features">
          <button type="button" onClick={() => navigateToSection("flood-lab")}>Rainfall</button>
          <button type="button" onClick={() => navigateToSection("investment-planner")}>Budget planner</button>
          <button type="button" onClick={() => navigateToSection("readiness-planner")}>Flood readiness</button>
          <button type="button" onClick={() => navigateToSection("road-closure-planner")}>Road closure</button>
          <button type="button" onClick={() => navigateToSection("ward-action-tracker")}>Action tracker</button>
          <button type="button" onClick={() => navigateToSection("access-baseline")}>Facility access</button>
          <button type="button" onClick={() => navigateToSection("assistant-lab")}>Map assistant</button>
          <button type="button" onClick={() => navigateToSection("map-scene")}>Map</button>
        </nav>
      </header>

      <div className="workspace">
        <aside className="sidebar" id="overview">
          <div className="sidebar-heading">
            <span className="section-index">MUMBAI · F/S WARD</span>
            <h1>Choose what<br />you want to do.</h1>
            <p className="lede">Each section opens one planning feature. Results appear on the map.</p>
          </div>

          <section className="ward-card" aria-label="Ward selection status">
            <div className="card-label">TEST WARD</div>
            <div className="ward-name">{wardName}</div>
            <div className="ward-status"><span className={`status-pill ${localSourcePreview ? "selected" : "pending"}`} /> {localSourcePreview ? "Working testbed selected" : "Selection required"}</div>
            <p>F/S Ward is the current study area.</p>
          </section>

          <section className="flood-lab" id="flood-lab" aria-label="Flood evidence and rainfall scenario laboratory">
            <details className="lab-disclosure flood-disclosure" onToggle={(event) => {
              if (event.currentTarget.open) {
                setFloodReviewVisible(true);
                setEnabledLayers((current) => ({ ...current, mcgmFloodRecords: true, mcgmShelters: false, facilities: false }));
              }
            }}>
              <summary><span className="card-label">RAINFALL PLANNING</span><strong>Rainfall scenario</strong><span className="lab-summary-hint">Set rainfall and see which mapped areas to inspect first</span></summary>
            <div className="lab-disclosure-content">
            <div className="flood-blocked-banner"><strong>Planning screen, not a flood forecast</strong><span>Your rain amount and duration change a demo shortlist using terrain, mapped drains and a simple prolonged-rain assumption.</span></div>
            {floodLoading ? <div className="access-state">Reading local rainfall, terrain and drainage records…</div> : floodEvidence ? (
              <>
                <div className="flood-scenario-controls">
                  <label>Total rainfall <span><input aria-label="Total rainfall" type="number" min="1" max="1000" step="1" value={rainfallAmount} onChange={(event) => { setRainfallAmount(event.target.value); setIllustrativeFloodModel(null); }} /> mm</span></label>
                  <label>Time period <span><input aria-label="Rainfall time period" type="number" min="0.25" max="168" step="0.25" value={rainfallDuration} onChange={(event) => { setRainfallDuration(event.target.value); setIllustrativeFloodModel(null); }} /> hours</span></label>
                  <button type="button" disabled={floodScenarioLoading || !hasValidEnteredScenario} onClick={() => void runRainfallScreening()}>{floodScenarioLoading ? "Saving scenario…" : "Save this rainfall scenario"}</button>
                </div>
                {hasValidEnteredScenario && floodEvidence && (
                  <div className="flood-calculation" aria-live="polite">
                    <div><span>Average rain each hour</span><strong>{(enteredRainfallMm / enteredDurationHours).toLocaleString(undefined, { maximumFractionDigits: 2 })} mm/hour</strong></div>
                    <div><span>Rain falling across the ward</span><strong>{(enteredRainfallMm * floodEvidence.ward.area_km2 * 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })} m³</strong></div>
                    <p>Assumes the same rain across the provisional ward. This is rain volume, not water expected in streets.</p>
                    {rainfallScreening && savedFloodRunId && rainfallScreening.rainfall_mm === enteredRainfallMm && rainfallScreening.duration_hours === enteredDurationHours && <small>Saved locally · {savedFloodRunId.slice(0, 8)}</small>}
                  </div>
                )}
                {savedFloodRuns.length > 0 && <details className="flood-evidence-details saved-flood-runs">
                  <summary>Previous rainfall runs · {savedFloodRuns.length}</summary>
                  <div className="saved-flood-run-list">{savedFloodRuns.map((run) => <button key={run.run_id} type="button" onClick={() => void openSavedFloodRun(run.run_id)}><strong>{run.inputs.rainfall_mm.toLocaleString()} mm · {run.inputs.duration_hours.toLocaleString()} h</strong><span>{new Date(run.created_at_utc).toLocaleString()} · {run.outputs.gross_rainfall_volume_m3.toLocaleString()} m³ gross rain</span></button>)}</div>
                  <p>Saved scenario inputs and deterministic rainfall-volume results. These records do not represent observed storms or predicted flooding.</p>
                </details>}

                {floodScreeningAreas && (
                  <section className="flood-priority-screen" aria-label="Relative terrain and mapped drainage screening">
                    <div className="flood-subheading"><strong>Areas to inspect first</strong><span>{hasValidEnteredScenario ? `${enteredRainfallMm} mm over ${enteredDurationHours} hours` : "Enter a valid rainfall amount"}</span></div>
                    <p>{hasValidEnteredScenario ? `Check these ${rainfallPriorityAreas.length} places first. We rank lower areas with fewer mapped drains. Intense bursts and longer rain events can add checks; longer events use a simple saturation assumption, not measured soil data.` : "Enter rainfall from 1 to 1,000 mm and a time period up to 168 hours to create the shortlist."}</p>
                    <div className="flood-screen-summary"><strong>{rainfallPriorityAreas.length}</strong><span>areas on the map · ranked from {floodScreeningAreas.all_cells.filter((feature) => feature.properties.dsm_p10_m !== null).length} cells with elevation data</span></div>
                    {rainfallPriorityAreas.length > 0 && <div className="flood-candidate-list rainfall-priority-list">{rainfallPriorityAreas.map((feature, index) => <div key={feature.properties.cell_id}><strong>{index + 1}. {feature.properties.cell_id} · near {feature.properties.nearest_named_road || "unnamed road"}</strong><span>Ground-height reading: {feature.properties.dsm_p10_m?.toFixed(2)} m · mapped drain lines in this area: {feature.properties.existing_drain_length_m.toFixed(0)} m</span></div>)}</div>}
                    <div className="flood-screen-controls">
                      <button type="button" aria-pressed={floodReviewVisible} onClick={toggleFloodReviewOverlay}>{floodReviewVisible ? "Temporarily hide map layer" : "Show review cells on map"}</button>
                      <button type="button" disabled={floodReportLoading} onClick={() => void downloadFloodFieldReport()}>{floodReportLoading ? "Preparing report…" : "Download field-screen report"}</button>
                    </div>
                    <details className="flood-evidence-details">
                      <summary>How is the shortlist made?</summary>
                      <p>The shortlist ranks mapped 250 m areas by lower ground and fewer mapped drains. Rainfall sets the starting number; every completed four hours adds one place to inspect. So, for the same rainfall total, a longer duration never removes places from this list. This is a simple demo rule—not a measured soil, drainage or flood model. Up to 20 areas are shown.</p>
                    </details>
                    <div className="flood-destination-note"><strong>Listed shelter locations:</strong> {municipalFloodContext?.summary.shelter_record_count ?? 0} MCGM records are available for map review. Confirm current operation, capacity, flood safety and route safety with MCGM before including a location in an evacuation plan. <a href="https://prsrvgisapp.mcgm.gov.in/server/rest/services/mcgm/MCGMGIS_Departments_Master_All_Layers/MapServer/layers" target="_blank" rel="noreferrer">View the MCGM GIS catalog ↗</a></div>
                  </section>
                )}

                {municipalFloodContext && <details className="flood-evidence-details municipal-records-details">
                  <summary>Municipal records and shelters · {municipalFloodContext.summary.flood_record_count} flood records · {municipalFloodContext.summary.shelter_record_count} shelter records</summary>
                  <div className="municipal-context-card">
                    <div><strong>Municipal records for F/S Ward</strong><span>BMC map records · {municipalFloodContext.snapshot.retrieved_at_utc.slice(0, 10)}</span></div>
                    <p>{municipalFloodContext.summary.flood_record_count} registered flooding records and {municipalFloodContext.summary.shelter_record_count} listed shelter locations are available for map review. These are municipal records, not the result of the rainfall scenario.</p>
                    <div className="municipal-context-actions">
                      <button type="button" aria-pressed={enabledLayers.mcgmFloodRecords} onClick={() => toggleLayer("mcgmFloodRecords")}>{enabledLayers.mcgmFloodRecords ? "Hide registered flood locations" : "Show registered flood locations"}</button>
                      <button type="button" aria-pressed={enabledLayers.mcgmShelters} onClick={() => toggleLayer("mcgmShelters")}>{enabledLayers.mcgmShelters ? "Hide listed shelter locations" : "Show listed shelter locations"}</button>
                    </div>
                    <p className="municipal-context-limit">{municipalFloodContext.summary.records_with_name_marked_delete} flood-record names contain a deletion marker. The source does not provide confirmed flood-event dates. Shelter capacity, current operation, flood safety and safe routes are not verified.</p>
                  </div>
                </details>}
                {recordOverlapDiagnostic && <details className="flood-evidence-details"><summary>How municipal records compare with terrain cells</summary><div className="municipal-context-card">
                  <div><strong>{recordOverlapDiagnostic.status}</strong><span>Spatial context check</span></div>
                  <p>{recordOverlapDiagnostic.summary.records_intersecting_relative_review_cells} of {recordOverlapDiagnostic.summary.usable_municipal_record_geometries} municipal record geometries intersect {recordOverlapDiagnostic.summary.matched_review_cell_count} of {recordOverlapDiagnostic.summary.relative_review_cell_count} relative review cells.</p>
                  <p className="municipal-context-limit">{recordOverlapDiagnostic.interpretation}</p>
                </div></details>}

                {floodScreeningAreas && (
                  <section className="flood-priority-screen illustrative-model" aria-label="Try a flood stress test">
                    <div className="flood-subheading"><strong>Try a flood stress test</strong><span>Demo assumptions · not a forecast</span></div>
                    <p>Change the two assumptions, then run the same rainfall scenario. See how the estimated leftover runoff changes. This demo does not show flood depth or confirmed flooded places.</p>
                    <div className="flood-scenario-controls">
                      <label>Rain that runs off <span><input aria-label="Rain that runs off (percent)" type="number" min="1" max="100" step="5" value={Number(demoRunoffFraction) * 100} onChange={(event) => { setDemoRunoffFraction(String(Number(event.target.value) / 100)); setIllustrativeFloodModel(null); }} /> %</span></label>
                      <label>Drain capacity assumption <span><input aria-label="Drain capacity assumption" type="number" min="0" max="10000" step="100" value={demoDrainCapacity} onChange={(event) => { setDemoDrainCapacity(event.target.value); setIllustrativeFloodModel(null); }} /> m³/hour/km</span></label>
                      <button type="button" disabled={illustrativeModelLoading} onClick={() => void runIllustrativeFloodModel()}>{illustrativeModelLoading ? "Calculating…" : "Run this scenario"}</button>
                    </div>
                    {illustrativeModelError && <p className="flood-model-error" role="alert">{illustrativeModelError}</p>}
                    {illustrativeFloodModel && (
                      <div className="flood-model-results" aria-live="polite">
                        <strong>{illustrativeFloodModel.status}</strong>
                        <p><b>{illustrativeFloodModel.summary.modelled_residual_runoff_m3.toLocaleString(undefined, { maximumFractionDigits: 0 })} m³</b> estimated leftover runoff for {illustrativeFloodModel.scenario.rainfall_mm} mm over {illustrativeFloodModel.scenario.duration_hours} hours. {illustrativeFloodModel.summary.modelled_exceedance_cell_count} areas are above the assumed drain capacity. This is a calculation from demo assumptions, not a flood prediction.</p>
                        <p>Based on {Math.round(illustrativeFloodModel.assumptions.runoff_fraction * 100)}% runoff and a drain capacity assumption of {illustrativeFloodModel.assumptions.drain_capacity_m3_per_hour_per_km.toLocaleString()} m³/hour/km. {illustrativeFloodModel.summary.capacity_unknown_cell_count} areas lack mapped existing drains, so their capacity is unknown.</p>
                        <details><summary>Assumption sensitivity check</summary><p>{illustrativeFloodModel.sensitivity.interpretation} {illustrativeFloodModel.sensitivity.method}</p><div className="flood-candidate-list">{illustrativeFloodModel.sensitivity.cases.map((item) => <div key={`${item.runoff_fraction_assumption}-${item.drain_capacity_assumption_m3_per_hour_per_km}`}><strong>Runoff {item.runoff_fraction_assumption} · drain assumption {item.drain_capacity_assumption_m3_per_hour_per_km.toLocaleString()} m³/hour/km</strong><span>Arithmetic residual {item.residual_arithmetic_total_m3.toLocaleString()} m³ · {item.cells_above_assumed_capacity} cells above assumed capacity</span></div>)}</div></details>
                        <small>Saved run {illustrativeFloodModel.saved_run.run_id.slice(0, 8)} · inputs and output are stored locally with boundary and review-grid checksums.</small>
                        <button type="button" className="flood-model-report-button" onClick={downloadIllustrativeFloodReport}>Download model demonstration report</button>
                        <details className="flood-model-area-details"><summary>See ranked areas and data</summary><div className="flood-candidate-list">{illustrativeFloodModel.features.filter((cell) => !cell.capacity_unknown).slice(0, 8).map((cell) => <div key={cell.cell_id}><strong>Rank {cell.model_rank}: {cell.cell_id} · near {cell.nearest_named_road || "unnamed road"}</strong><span>Ground height {cell.dsm_p10_m?.toFixed(2) ?? "missing"} m · mapped existing drains {cell.existing_drain_length_m.toFixed(0)} m · estimated leftover runoff {cell.modelled_residual_runoff_m3?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "not calculated"} m³</span></div>)}</div><p>Ground-height values use the local digital surface model. Drain records may be incomplete.</p></details>
                        <p>Cells without mapped Existing drains are shown separately as unknown-capacity data gaps, not assumed to have zero real drainage.</p>
                        <details><summary>Model equations and limitations</summary><p>{illustrativeFloodModel.method}</p><ul>{illustrativeFloodModel.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
                      </div>
                    )}
                  </section>
                )}

                <div className="flood-subheading"><strong>Observed rainfall context</strong><span>IMD · NWIC snapshot, not live</span></div>
                <div className="rainfall-district-switch" role="group" aria-label="Select district rainfall series">
                  {["MUMBAI CITY", "SUBURBAN MUMBAI"].map((district) => <button key={district} type="button" aria-pressed={rainfallDistrict === district} onClick={() => setRainfallDistrict(district)}>{district === "MUMBAI CITY" ? "Mumbai City" : "Suburban Mumbai"}</button>)}
                </div>
                {rainfallSeries && rainfallSeries.records.length > 0 ? (
                  <>
                    <div className="rainfall-chart-caption">Daily actual rainfall · {rainfallSeries.records[0].date} to {rainfallSeries.records[rainfallSeries.records.length - 1].date} · mm/day</div>
                    <svg className="rainfall-chart" viewBox="0 0 320 104" role="img" aria-label={`Daily IMD district rainfall for ${rainfallSeries.district}`}>
                      <line x1="0" x2="320" y1="85" y2="85" stroke="rgba(219,231,220,.2)" />
                      {(() => {
                        const values = rainfallSeries.records;
                        const maxValue = Math.max(1, ...values.flatMap((record) => [record.observed_mm, record.normal_mm]));
                        const slot = 320 / values.length;
                        return values.map((record, index) => {
                          const barHeight = Math.max(record.observed_mm > 0 ? 1 : 0, (record.observed_mm / maxValue) * 72);
                          const normalY = 85 - (record.normal_mm / maxValue) * 72;
                          return <g key={record.date}><title>{record.date}: {record.observed_mm} mm observed; {record.normal_mm} mm normal</title><rect x={index * slot + 1} y={85 - barHeight} width={Math.max(1, slot - 2)} height={barHeight} fill="#e5b95f" opacity=".86" /><line x1={index * slot + 1} x2={index * slot + slot - 1} y1={normalY} y2={normalY} stroke="#93a9a0" strokeWidth="1" /></g>;
                        });
                      })()}
                    </svg>
                    <div className="rainfall-chart-legend"><span><i />Daily actual</span><span><i />IMD daily normal</span></div>
                  </>
                ) : <div className="access-state">No rows for this district in the downloaded snapshot.</div>}
                <div className="flood-source-note">District daily values cannot represent rainfall variation across F/S Ward or short intense bursts. NWIC lists no license for this CSV resource; the source stays local pending your review.</div>

                <details className="flood-evidence-details">
                  <summary>BMC ward station reading · source check only</summary>
                  <p>BMC’s public dashboard listed Hindmata Cinema under F South Ward Office. Its displayed rainfall was 0 mm for the last 15 minutes and 0 mm accumulated over 1, 3, 6 and 24 hours when checked on 7 October 2026. This is one manually captured dashboard reading; the station observation time is not shown, so it is not used to drive the scenario or establish current conditions.</p>
                  <p>The BMC map popup for the same station showed inconsistent values. Treat this reading as an integration check, not verified telemetry. A timestamped station history is needed before it can support model forcing or validation.</p>
                  <a href="https://dm.mcgm.gov.in/" target="_blank" rel="noreferrer">Open BMC Disaster Management dashboard ↗</a>
                </details>

                <details className="flood-evidence-details">
                  <summary>What data is here and what is missing?</summary>
                  <div className="flood-data-grid">
                    <div><strong>Rainfall</strong><span>IMD district daily · {floodEvidence.rainfall.overall_start_date} to {floodEvidence.rainfall.overall_end_date}</span></div>
                    <div><strong>Terrain context</strong><span>Copernicus GLO-30 DSM · nominal {floodEvidence.terrain.nominal_resolution_m} m · not bare earth</span></div>
                    <div><strong>Drainage records</strong><span>{floodEvidence.drainage.drain_lines.toLocaleString()} drain lines ({floodEvidence.drainage.drain_status_counts.Existing.toLocaleString()} Existing, {floodEvidence.drainage.drain_status_counts.Proposal.toLocaleString()} Proposal) · {floodEvidence.drainage.manholes.toLocaleString()} manholes</span></div>
                  </div>
                  <strong className="flood-missing-title">Needed before flood depth can be calculated</strong>
                  <ul>{floodEvidence.missing_for_flood_depth.map((item) => <li key={item}>{item}</li>)}</ul>
                  <p>{floodEvidence.drainage.limitations[0]} Drain identifiers matching manholes do not prove connected flow.</p>
                </details>

                <div className="flood-subheading"><strong>Useful planning actions</strong><span>Not an emergency instruction</span></div>
                <ul className="flood-actions">
                  <li><strong>Check drainage readiness.</strong> Review cleaning/blockage records for mapped Existing drains; keep Proposal lines separate from operating capacity.</li>
                  <li><strong>Use official updates during real rain.</strong> Cross-check IMD forecasts and BMC Disaster Management notices; this local scenario is not a warning feed.</li>
                  <li><strong>Make the next model verifiable.</strong> Record time-stamped rainfall, water depth/location, tide level and drain/outfall condition under an approved collection plan.</li>
                </ul>
                <div className="flood-official-links"><a href="https://dm.mcgm.gov.in/" target="_blank" rel="noreferrer">BMC Disaster Management ↗</a><a href="https://www.mcgm.gov.in/irj/go/km/docs/documents/AboutMCGM/DisasterManagement/VolumeFinal.pdf" target="_blank" rel="noreferrer">BMC Mumbai disaster plan ↗</a></div>
              </>
            ) : <div className="access-error" role="status">{readableStatusMessage(floodError || "", "Flood and rainfall information is unavailable right now. Please try again later.")}</div>}
            {floodError && floodEvidence && <div className="access-error" role="status">{readableStatusMessage(floodError, "Flood information is unavailable right now. Please try again later.")}</div>}
              </div>
            </details>
          </section>

          <section className="policy-lab" id="policy-lab" aria-label="Ward planning features">
            <details className="policy-disclosure">
              <summary><span className="card-label">PLANNING TOOLS</span><strong>Plan a ward decision</strong><span className="policy-summary-hint">Open budget, flood readiness or road closure planning</span></summary>
              <div className="policy-disclosure-content preparedness-planner">
                <p className="policy-intro">Choose a feature below.</p>
                <div className="decision-feature-list" role="group" aria-label="Planning features">
                  <button type="button" className={decisionMode === "investment" ? "active" : ""} aria-pressed={decisionMode === "investment"} onClick={() => activateDecisionMode("investment")}><strong>Budget planner</strong><span>Compare mapped drainage, lighting and health-access options.</span></button>
                  <button type="button" className={decisionMode === "preparedness" ? "active" : ""} aria-pressed={decisionMode === "preparedness"} onClick={() => activateDecisionMode("preparedness")}><strong>Flood readiness plan</strong><span>Use mapped records to plan field checks for a rainfall scenario.</span></button>
                  <button type="button" className={decisionMode === "road_closure" ? "active" : ""} aria-pressed={decisionMode === "road_closure"} onClick={() => activateDecisionMode("road_closure")}><strong>Road closure what-if</strong><span>See how a hypothetical closure changes mapped health-facility routes.</span></button>
                </div>
                {decisionMode === "road_closure" ? <div className="decision-template-card decision-feature-panel" id="road-closure-planner">
                  <h2>Road closure what-if</h2>
                  <p>Select one or more roads. The map removes all selected roads together for this what-if.</p>
                  <input className="road-search-input" type="search" aria-label="Find a road to close" placeholder="Find a road by name" value={closureRoadSearch} onChange={(event) => setClosureRoadSearch(event.target.value)} />
                  <div className="road-closure-options" role="group" aria-label="Roads to close in this scenario">
                    {closureOptions.filter((option) => option.road_name.toLowerCase().includes(closureRoadSearch.trim().toLowerCase())).map((option) => <label key={option.road_name}><input type="checkbox" checked={selectedClosureRoads.includes(option.road_name)} disabled={!selectedClosureRoads.includes(option.road_name) && selectedClosureRoads.length >= 8} onChange={(event) => { setSelectedClosureRoads((current) => event.target.checked ? [...current, option.road_name] : current.filter((name) => name !== option.road_name)); clearRoadScenarioOverlays(); setDecisionRecord(null); }} /><span>{option.road_name}</span></label>)}
                  </div>
                  <small className="road-selection-count">{selectedClosureRoads.length} of 8 roads selected</small>
                  <button type="button" className="preparedness-generate" disabled={!selectedClosureRoads.length || runLoading} onClick={() => void runClosureScenario()}>{runLoading ? "Comparing road network…" : "Compare selected closures"}</button>
                  {accessRun && <div className="decision-result-grid" aria-live="polite">
                    <div><span>Before: road points with a health-facility route</span><strong>{accessRun.baseline.route_coverage_percent.toFixed(1)}%</strong></div>
                    <div><span>After: road points with a health-facility route</span><strong>{accessRun.scenario.route_coverage_percent.toFixed(1)}%</strong></div>
                    <div><span>Change</span><strong>{(accessRun.scenario.route_coverage_percent - accessRun.baseline.route_coverage_percent).toFixed(1)} points</strong></div>
                    <div><span>Road points losing a route</span><strong>{accessRun.change.newly_unreachable_road_nodes}</strong></div>
                  </div>}
                  <p className="policy-comparison-note">This is a what-if, not a live closure. Road points are not people. Distance is not travel time, and facility opening status is unconfirmed.</p>
                  {accessRun && <label className="access-overlay-toggle"><input type="checkbox" checked={closureLayerVisible} onChange={toggleClosureOverlay} /> Show road effects on map</label>}
                </div> : decisionMode === "investment" ? <div className="investment-simulator decision-feature-panel" id="investment-planner">
                  <h2>Budget planner</h2>
                  <p className="investment-intro">Enter a budget to compare drainage, streetlight and health-access options. Choose one to see its planned locations on the map.</p>
                  <div className="preparedness-input-grid investment-budget-grid">
                    <label>Planning budget (₹ crore)<input type="number" min="0.01" step="0.5" value={policyBudgetCrore} onChange={(event) => setPolicyBudgetCrore(event.target.value)} /></label>
                  </div>
                  <details className="preparedness-rates">
                    <summary>Change cost estimates</summary>
                    <p>The solar-light allowance uses one 2023 BMC schedule item, before GST. Drainage and health-check costs are demo estimates, not quotes.</p>
                    <div className="preparedness-input-grid">
                      <label>One drainage review (₹)<input type="number" min="1" value={investmentRates.drainage} onChange={(event) => setInvestmentRates((current) => ({ ...current, drainage: event.target.value }))} /></label>
                      <label>One solar streetlight (₹)<input type="number" min="1" value={investmentRates.streetlights} onChange={(event) => setInvestmentRates((current) => ({ ...current, streetlights: event.target.value }))} /></label>
                      <label>One health-access review (₹)<input type="number" min="1" value={investmentRates.healthAccess} onChange={(event) => setInvestmentRates((current) => ({ ...current, healthAccess: event.target.value }))} /></label>
                      <label>Distance between lights (m)<input type="number" min="10" max="1000" step="10" value={investmentSpacingM} onChange={(event) => setInvestmentSpacingM(event.target.value)} /></label>
                    </div>
                  </details>
                  <button className="preparedness-generate" type="button" disabled={!Number.isFinite(Number(policyBudgetCrore)) || Number(policyBudgetCrore) <= 0 || !Number.isFinite(Number(investmentSpacingM)) || Number(investmentSpacingM) <= 0 || investmentLoading || Object.values(investmentRates).some((rate) => !Number.isFinite(Number(rate)) || Number(rate) <= 0)} onClick={() => void createInvestmentPlan()}>
                    {investmentLoading ? "Comparing mapped options…" : "Compare options"}
                  </button>
                  {investmentError && <div className="access-error" role="alert">{investmentError}</div>}
                  {investmentPlan && selectedInvestmentOption && <>
                    <div className="investment-result-note" role="status">Each option uses the same ₹{investmentPlan.inputs.budget_crore} crore budget. Choose one to see what it could cover and how much would remain.</div>
                    <div className="investment-options" aria-label="Government investment options">
                      {investmentPlan.options.map((option) => <button type="button" key={option.id} className={`investment-option ${option.id === selectedInvestmentOption.id ? "active" : ""}`} aria-pressed={option.id === selectedInvestmentOption.id} onClick={() => { setInvestmentOptionId(option.id); setAgentAnswer(null); setDecisionRecord(null); }}>
                        <span className="investment-option-title">{option.name}{option.id === selectedInvestmentOption.id ? " · on map" : ""}</span>
                        <strong>₹{option.estimated_cost_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</strong>
                        <span>{option.planned_count} of {option.available_count} candidate locations</span>
                        <small>₹{option.remaining_budget_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })} remains under this allowance</small>
                      </button>)}
                    </div>
                    <div className="investment-tradeoffs" aria-live="polite">
                      <h3>{selectedInvestmentOption.name}</h3>
                      <p>{selectedInvestmentOption.summary}</p>
                      <div><strong>What the map supports</strong><span>{selectedInvestmentOption.supported_basis}</span></div>
                      <div><strong>What is still unknown</strong><span>{selectedInvestmentOption.unknowns}</span></div>
                      <p className="investment-rate-note">₹{selectedInvestmentOption.unit_allowance_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })} per location · {selectedInvestmentOption.id === "streetlights" ? `${investmentPlan.inputs.streetlight_spacing_m} m demo spacing · ` : ""}{selectedInvestmentOption.rate_basis}</p>
                    </div>
                    <button type="button" className="preparedness-explain" disabled={!agentStatus.ready || agentLoading} onClick={() => { const question = `Explain the selected investment option ${selectedInvestmentOption.name} in two short sentences. State what the mapped evidence shows and one important unknown.`; setAgentQuestion(question); void askLocalAgent(question); }}>
                      {agentLoading ? "Reviewing this option…" : "Explain this option"}
                    </button>
                    {agentAnswer?.investment_option && <div className="investment-ai-answer" aria-live="polite">{agentAnswer.answer}</div>}
                    <details className="preparedness-sources"><summary>Data and limits</summary>
                      <p>{investmentPlan.method}</p>
                      <ul>{Object.entries(investmentPlan.sources).map(([key, source]) => <li key={key}>{key.replaceAll("_", " ")} · {source.candidate_count ?? source.road_node_count ?? source.mapped_health_feature_count ?? "local source"} features · {source.path} · SHA-256 {source.sha256.slice(0, 12)}…</li>)}</ul>
                      <ul>{investmentPlan.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                    </details>
                  </>}
                </div> : <div className="decision-feature-panel" id="readiness-planner">
                <h2>Flood readiness plan</h2>
                <div className="preparedness-input-grid">
                  <label>Rainfall scenario (mm)<input type="number" min="0.1" max="1000" step="1" value={rainfallAmount} onChange={(event) => setRainfallAmount(event.target.value)} /></label>
                  <label>Duration (hours)<input type="number" min="0.1" max="168" step="0.5" value={rainfallDuration} onChange={(event) => setRainfallDuration(event.target.value)} /></label>
                  <label>Planning envelope (₹ crore)<input type="number" min="0.01" step="0.5" value={policyBudgetCrore} onChange={(event) => setPolicyBudgetCrore(event.target.value)} /></label>
                </div>
                <details className="preparedness-rates">
                  <summary>Planning allowances · edit these assumptions</summary>
                  <p>These demo values help size a field-review programme. They are not official MCGM rates, quotes, or procurement estimates.</p>
                  <div className="preparedness-input-grid">
                    <label>Review one candidate cell (₹)<input type="number" min="1" value={preparednessRates.cell} onChange={(event) => setPreparednessRates((current) => ({ ...current, cell: event.target.value }))} /></label>
                    <label>Verify one MCGM record (₹)<input type="number" min="1" value={preparednessRates.record} onChange={(event) => setPreparednessRates((current) => ({ ...current, record: event.target.value }))} /></label>
                    <label>Audit one listed shelter (₹)<input type="number" min="1" value={preparednessRates.shelter} onChange={(event) => setPreparednessRates((current) => ({ ...current, shelter: event.target.value }))} /></label>
                  </div>
                </details>
                <button className="preparedness-generate" type="button" disabled={!hasValidEnteredScenario || Number(policyBudgetCrore) <= 0 || preparednessLoading || Object.values(preparednessRates).some((rate) => Number(rate) <= 0)} onClick={() => void createPreparednessPlan()}>
                  {preparednessLoading ? "Building the ward plan…" : "Build preparedness plan"}
                </button>
                {preparednessError && <div className="access-error" role="alert">{readableStatusMessage(preparednessError, "The plan service is unavailable. Please try again.")}</div>}
                {preparednessPlan && selectedPreparednessOption && <>
                  <div className="preparedness-run-note" role="status">For {preparednessPlan.inputs.rainfall_mm} mm over {preparednessPlan.inputs.duration_hours} hours, the demo lists {preparednessPlan.rainfall_screening.field_check_locations_shown} places to check. Rainfall sets the starting count; each completed four-hour period adds one place. The order uses terrain, mapped drains and municipal records. This is a demo screening rule, not a flood prediction or measured soil model.</div>
                  <div className="preparedness-options" aria-label="Preparedness plan options">
                    {preparednessPlan.options.map((option) => <button type="button" key={option.id} className={`policy-plan-card ${option.id === selectedPreparednessOption.id ? "active" : ""}`} aria-pressed={option.id === selectedPreparednessOption.id} onClick={() => setPreparednessOptionId(option.id)}>
                      <span className="policy-plan-card-title">{option.name}{option.id === selectedPreparednessOption.id ? " · shown on map" : ""}</span>
                      <strong>₹{option.estimated_allocation_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</strong>
                      <span>₹{option.unallocated_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })} unallocated</span>
                      <small>{option.mapped_actions} mapped checks · no predicted benefits</small>
                    </button>)}
                  </div>
                  <p className="policy-comparison-note">Choose an option to see its checks on the map. Costs use your editable estimates. The plan does not predict flood reduction, people protected or safe evacuation routes.</p>
                  <div className="preparedness-workstreams">{selectedPreparednessOption.workstreams.map((work) => <article key={work.workstream} className="preparedness-workstream">
                    <div><strong>{work.workstream === "field_review" ? "Drainage and terrain field review" : work.workstream === "record_verification" ? "Registered-location verification" : "Listed shelter readiness audit"}</strong><span>{work.planned_count} of {work.available_count} mapped checks · ₹{work.estimated_allocation_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span></div>
                    <p>{work.action}</p>
                  </article>)}</div>
                  <button type="button" className="preparedness-explain" disabled={!agentStatus.ready || agentLoading} onClick={() => { const question = `Explain the selected preparedness action plan for ${selectedPreparednessOption.name}, using only its saved evidence and limits.`; setAgentQuestion(question); void askLocalAgent(question); }}>
                    {agentLoading ? "Assistant is reviewing the saved plan…" : "Ask the assistant to explain this plan"}
                  </button>
                  <details className="preparedness-sources"><summary>Sources and important limits</summary>
                    <p>{preparednessPlan.method}</p>
                    <ul>{Object.entries(preparednessPlan.sources).map(([key, source]) => <li key={key}>{source.count} records · {source.path} · SHA-256 {source.sha256.slice(0, 12)}…</li>)}</ul>
                    <ul>{preparednessPlan.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                  </details>
                </>}
                </div>}
                {decisionError && <div className="access-error" role="alert">{readableStatusMessage(decisionError, "Could not save the decision comparison.")}</div>}
                {((decisionMode === "road_closure" && accessRun) || (decisionMode === "preparedness" && selectedPreparednessOption)) && <button type="button" className="decision-save" disabled={decisionSaving} onClick={() => void saveDecisionComparison()}>{decisionSaving ? "Saving comparison…" : decisionRecord ? "Save a new comparison" : "Save decision comparison"}</button>}
                {decisionRecord && <section className="decision-evaluation" aria-live="polite">
                  <div className="decision-evaluation-heading"><strong>What this choice means</strong><span>Saved · {decisionRecord.decision_id.slice(0, 8)}</span></div>
                  <div className="decision-pros-cons"><div><h3>What looks useful</h3><ul>{decisionRecord.pros_supported_by_outputs.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>What to watch</h3><ul>{decisionRecord.cons_and_unknowns.map((item) => <li key={item}>{item}</li>)}</ul></div></div>
                  <details><summary>How this was calculated</summary><ul>{decisionRecord.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
                  <button type="button" className="preparedness-explain" disabled={!agentStatus.ready || agentLoading} onClick={explainSavedDecision}>{agentLoading ? "Reading the results…" : "Ask AI to explain"}</button>
                </section>}
              </div>
            </details>
          </section>

          <section className="action-tracker-lab" id="ward-action-tracker" aria-label="Ward action tracker">
            <details className="lab-disclosure action-tracker-disclosure" onToggle={(event) => { if (event.currentTarget.open) activateDecisionMode("preparedness"); setActionTrackerMode(event.currentTarget.open); }}>
              <summary><span className="card-label">FROM PLAN TO ACTION</span><strong>Ward action tracker</strong><span className="lab-summary-hint">Turn the selected field-check plan into a simple task list</span></summary>
              <div className="lab-disclosure-content action-tracker-content">
                {preparednessPlan && selectedPreparednessOption ? <>
                  <div className="action-tracker-context"><strong>{selectedPreparednessOption.name}</strong><span>{preparednessPlan.inputs.rainfall_mm} mm over {preparednessPlan.inputs.duration_hours} hours · illustrative planning scenario</span></div>
                  <div className="action-tracker-counts" aria-label="Action status summary">
                    <div><strong>{actionStatusCounts["To inspect"]}</strong><span>To inspect</span></div>
                    <div><strong>{actionStatusCounts["In progress"]}</strong><span>In progress</span></div>
                    <div><strong>{actionStatusCounts.Done}</strong><span>Done</span></div>
                  </div>
                  <p className="action-tracker-note">Select “View on map” to locate a task. Change its status as your team reviews it. Statuses are saved in this browser only; this is not an official work order.</p>
                  {wardActionItems.length ? <div className="ward-action-list">{wardActionItems.map((action, index) => {
                    const status = wardActionStatuses[action.id] ?? "To inspect";
                    const isSelected = selectedWardActionId === action.id;
                    return <article className={`ward-action-card${isSelected ? " is-selected" : ""}`} key={action.id} aria-current={isSelected ? "location" : undefined}>
                      <div className="ward-action-heading"><span className="ward-action-number">{index + 1}</span><div><strong>{action.location}</strong><span>{action.workstream}</span></div></div>
                      <p>{action.reason}</p>
                      <small>Source: {action.source} · demo planning task</small>
                      <div className="ward-action-controls"><button type="button" aria-pressed={isSelected} onClick={() => focusWardAction(action)}>{isSelected ? "Highlighted on map" : "View on map"}</button><label><span className="sr-only">Status for {action.location}</span><select value={status} onChange={(event) => updateWardActionStatus(action.id, event.target.value as WardActionStatus)}><option>To inspect</option><option>In progress</option><option>Done</option></select></label></div>
                    </article>;
                  })}</div> : <p className="action-tracker-empty">This plan has no mapped tasks. Choose another plan in Flood readiness.</p>}
                </> : <div className="action-tracker-empty-state"><p>Build a flood readiness plan first. Its mapped checks will appear here as trackable tasks.</p><button type="button" className="preparedness-generate" onClick={() => navigateToSection("readiness-planner")}>Open flood readiness</button></div>}
              </div>
            </details>
          </section>

          <section className="access-lab" id="access-lab" aria-label="Mapped health-facility access">
            <details className="lab-disclosure access-disclosure" onToggle={(event) => {
              if (event.currentTarget.open) {
                setFloodReviewVisible(false);
                setEnabledLayers((current) => ({ ...current, mcgmFloodRecords: false, mcgmShelters: false, facilities: true }));
              }
            }}>
              <summary><span className="card-label">HEALTH ACCESS</span><strong>Health-facility access</strong><span className="lab-summary-hint">Pick a place and trace routes to nearby clinics and hospitals</span></summary>
              <div className="lab-disclosure-content">
            <p className="lab-intro">Choose roads to close for a what-if, then pick a place on the map. Routes will avoid those roads and show nearby mapped health facilities.</p>
            <div className="facility-route-controls">
              <label htmlFor="facility-route-radius">Search by road distance</label>
              <select id="facility-route-radius" value={facilityRouteRadius} onChange={(event) => setFacilityRouteRadius(event.target.value)}>
                <option value="1000">Within 1 km</option><option value="1200">Within 1.2 km</option><option value="2000">Within 2 km</option><option value="5000">Within 5 km</option><option value="10000">Within 10 km</option>
              </select>
                <button type="button" className="facility-pick-button" disabled={accessLoading || facilityRoutesLoading} onClick={() => { setFacilityRoutesError(""); setAreaPickMode((active) => !active); }}>
                {areaPickMode ? "Cancel map selection" : facilityRoutesLoading ? "Finding nearby facilities…" : "Choose area on map"}
              </button>
            </div>
            <details className="facility-closure-picker">
              <summary>Road closures for this route test · {facilityClosedRoads.length} selected</summary>
              <input className="road-search-input" type="search" aria-label="Find a road to avoid" placeholder="Find a road by name" value={facilityClosureSearch} onChange={(event) => setFacilityClosureSearch(event.target.value)} />
              <div className="road-closure-options" role="group" aria-label="Roads to avoid when finding facilities">
                {closureOptions.filter((option) => option.road_name.toLowerCase().includes(facilityClosureSearch.trim().toLowerCase())).map((option) => <label key={option.road_name}><input type="checkbox" checked={facilityClosedRoads.includes(option.road_name)} disabled={!facilityClosedRoads.includes(option.road_name) && facilityClosedRoads.length >= 8} onChange={(event) => { setFacilityClosedRoads((current) => event.target.checked ? [...current, option.road_name] : current.filter((name) => name !== option.road_name)); setFacilityRoutes(null); clearFacilityRoutes(); clearRoadScenarioOverlays(); setFacilityRoutesError(""); }} /><span>{option.road_name}</span></label>)}
              </div>
              <small>Choose up to 8. Select an area on the map again to recalculate.</small>
            </details>
            {areaPickMode && <div className="facility-pick-hint" role="status">Click a location inside F/S Ward on the map to find routes.</div>}
            {facilityRoutesError && <div className="access-error" role="status">{facilityRoutesError}</div>}
            {facilityRoutesLoading && <div className="access-state" role="status">Finding road routes to nearby mapped facilities…</div>}
            {facilityRoutes && <div className="facility-route-results" aria-live="polite">
              <div className="facility-route-summary"><strong>Closest mapped facility</strong><span>{facilityRoutes.facilities[0]?.name || "Unnamed mapped health facility"}</span><b>{formatDistance(facilityRoutes.facilities[0]?.distance_m ?? null)} by road</b></div>
              <p>{facilityRoutes.facilities_found} reachable mapped {facilityRoutes.facilities_found === 1 ? "facility" : "facilities"} within {facilityRoutes.radius_m / 1000} km. {facilityRoutes.applied_closures.length ? `Routes avoid: ${facilityRoutes.applied_closures.join(", ")}.` : "No road closures applied."} The closest reachable route is highlighted.</p>
              <div className="facility-route-list">{facilityRoutes.facilities.map((facility, index) => <div className={facility.is_nearest ? "nearest" : ""} key={facility.osm_id || `${facility.name}-${index}`}><span>{facility.is_nearest ? "Closest" : `Option ${index + 1}`} · {facility.name || "Unnamed mapped health facility"}</span><strong>{formatDistance(facility.distance_m)}</strong><small>{facility.amenity || facility.healthcare || "Mapped health location"}{facilityRoutes.applied_closures.length > 0 && facility.distance_change_m !== null ? ` · ${facility.distance_change_m > 0 ? "+" : ""}${formatDistance(facility.distance_change_m)} vs open roads` : ""}</small></div>)}</div>
              <small className="facility-route-caveat">Road distance only, not travel time. OSM mapping does not confirm opening, staffing, or services. Snapshot: {facilityRoutes.source_retrieved_at.slice(0, 10)}.</small>
            </div>}
            {accessLoading ? <div className="access-state">Loading local road and facility data…</div> : accessError && !accessSummary ? <div className="access-error" role="status">{readableStatusMessage(accessError, "Road and health-facility information is unavailable right now. Please try again later.")}</div> : accessSummary ? (
              <>
                <div className="access-facts" id="access-baseline">
                  <div><strong>{accessSummary.road_nodes_inside_ward.toLocaleString()}</strong><span>mapped road points</span></div>
                  <div><strong>{accessSummary.mapped_health_facilities_inside_ward}</strong><span>mapped health locations</span></div>
                  <div><strong>{accessSummary.baseline.route_coverage_percent.toFixed(1)}%</strong><span>road points with a facility route</span></div>
                  <div><strong>{formatDistance(accessSummary.baseline.mean_network_distance_m)}</strong><span>average mapped route distance</span></div>
                </div>
                <div className="access-baseline">
                  Before any closure: {accessSummary.baseline.road_nodes_without_route} of {accessSummary.road_nodes_inside_ward} mapped road points have no route to a mapped health location.
                </div>
                <details className="access-quality">
                  <summary>Data quality and method</summary>
                  <p>Mapped facility-to-road match distance: median {formatDistance(accessSummary.baseline.median_facility_snap_distance_m)}, maximum {formatDistance(accessSummary.baseline.maximum_facility_snap_distance_m)}. Polygon locations use representative points; entrances are not mapped.</p>
                  <p>{accessSummary.weakly_connected_components_buffered} weakly connected road groups in the buffered graph; {accessSummary.ward_nodes_in_largest_weak_component} of {accessSummary.road_nodes_inside_ward} ward nodes are in its largest connected group. One-way direction can still prevent a route.</p>
                  <p>Health features are mapped as {accessSummary.health_facility_geometry_types.Point || 0} points and {accessSummary.health_facility_geometry_types.Polygon || 0} polygons. Snapshot date: {accessSummary.source_retrieved_at.slice(0, 10)}.</p>
                  <p>Coverage counts road graph nodes equally, not residents or trips. It is not checked against observed journeys or an official facility list.</p>
                </details>
                <div className="access-disclaimer">This is a road-network estimate, not travel time or emergency-response performance. It counts road points equally, not residents or trips.</div>
              </>
            ) : <div className="access-error" role="status">{readableStatusMessage(accessError, "Road and health-facility information is unavailable right now. Please try again later.")}</div>}

              </div>
            </details>
          </section>

          <section className="assistant-lab" id="assistant-lab" aria-label="Map assistant feature">
            <details className="lab-disclosure assistant-disclosure">
              <summary><span className="card-label">HELP</span><strong>Map assistant</strong><span className="lab-summary-hint">Ask about map symbols, local records or saved results</span></summary>
              <div className="lab-disclosure-content">
            <section className="local-agent" aria-label="Map assistant">
              <div className="local-agent-heading">
                <div><strong>Ask the map assistant</strong><span>Get a short explanation of the map or a saved result.</span></div>
              </div>
              {agentStatus.ready ? <>
              <div className="agent-suggestions">
                {["What do the map markers mean?", "Which health places are mapped?", ...(decisionRecord ? ["Explain this decision"] : []), ...(selectedClosureRoad ? [`What if ${selectedClosureRoad} closes?`] : [])].map((suggestion) => <button key={suggestion} type="button" disabled={!agentStatus.ready || agentLoading} onClick={() => { if (suggestion === "Explain this decision" && decisionRecord) { setAgentQuestion(suggestion); void askLocalAgent(`Explain the pros and cons of ${decisionRecord.title} in simple language.`); } else setAgentQuestion(suggestion); }}>{suggestion}</button>)}
              </div>
              <form onSubmit={(event) => { event.preventDefault(); void askLocalAgent(); }}>
                <label htmlFor="scenario-question">Ask about the map or your decision</label>
                <textarea id="scenario-question" value={agentQuestion} onChange={(event) => setAgentQuestion(event.target.value)} maxLength={800} rows={2} placeholder="What changes if this road closes?" disabled={!agentStatus.ready || agentLoading} />
                <button type="submit" disabled={!agentStatus.ready || !agentQuestion.trim() || agentLoading}>{agentLoading ? "Checking…" : "Ask Bharat Yantra"}</button>
              </form>
              {agentError && <div className="agent-error" role="status">{readableStatusMessage(agentError, "The assistant could not complete this request. Please try again.")}</div>}
              </> : <p className="agent-unavailable">The assistant can’t answer right now. The other map features are still available.</p>}
              {agentAnswer && <div className="agent-answer" aria-live="polite"><p>{agentAnswer.answer}</p>{agentAnswer.flood_run_record && <small>Evidence: saved rainfall run {agentAnswer.flood_run_record.run_id.slice(0, 8)} · {agentAnswer.flood_run_record.model_version} · {new Date(agentAnswer.flood_run_record.created_at_utc).toLocaleString()}</small>}{agentAnswer.flood_model_run_record && <small>Evidence: saved assumption-model run {agentAnswer.flood_model_run_record.run_id.slice(0, 8)} · {agentAnswer.flood_model_run_record.model_version} · not validated</small>}{agentAnswer.flood_scenario && <div className="flood-calculation agent-flood-calculation"><div><span>Average rainfall rate</span><strong>{agentAnswer.flood_scenario.mean_intensity_mm_per_hour.toLocaleString(undefined, { maximumFractionDigits: 2 })} mm/hr</strong></div><div><span>Gross rain over provisional ward</span><strong>{agentAnswer.flood_scenario.gross_rainfall_volume_m3.toLocaleString()} m³</strong></div><p>{agentAnswer.flood_scenario.interpretation} This is not predicted flooding.</p></div>}{agentAnswer.flood_area_screening && <div className="agent-flood-review"><strong>{agentAnswer.flood_area_screening.summary.review_candidate_count} relative field-review cells</strong><span>These are lower-terrain / sparse mapped-drain evidence cells, not places predicted to flood. No verified transfer destination or safe route is available.</span><div>{agentAnswer.flood_area_screening.candidate_cells.slice().sort((a, b) => (a.dsm_p10_m ?? Infinity) - (b.dsm_p10_m ?? Infinity)).slice(0, 4).map((cell) => <small key={cell.cell_id}>{cell.cell_id} · near {cell.nearest_named_road || "unnamed road"}</small>)}</div></div>}{agentAnswer.evidence_data?.features && <div className="agent-evidence-list"><strong>Mapped health features · OSM snapshot {agentAnswer.evidence_data.retrieved_at?.slice(0, 10)}</strong>{agentAnswer.evidence_data.features.map((facility) => <div key={facility.osm_id || `${facility.name}-${facility.amenity}`}><span>{facility.name || "Unnamed mapped feature"}</span><small>{facility.amenity || facility.healthcare || "health feature"} · {facility.geometry_type || "geometry unrecorded"}</small></div>)}<small>Community mapped; this list does not confirm operation or completeness.</small></div>}</div>}
              <div className="agent-guardrail">Answers use the available map data. Confirm important decisions with the responsible team.</div>
            </section>
              </div>
            </details>
          </section>

          <div className="sidebar-footnote">
            <span className="footnote-line" />
            <p>For planning discussion only. Confirm data and operational decisions with the responsible departments.</p>
          </div>
        </aside>

        <section className="map-panel" id="map-scene" aria-label="3D geospatial scene">
          <div className="map-header">
            <div>
              <div className="map-kicker">WARD MAP <span>·</span> MUMBAI</div>
          <h2>F/S Ward map <span className="map-subtitle">/ Mumbai</span></h2>
            </div>
            <div className={`scene-badge scene-${sceneState}`}>
              <span className="scene-dot" />
              {sceneState === "ready" ? (localSourcePreview ? "LOCAL DATA" : "MAP DATA LOADED") : sceneState === "error" ? "MAP DATA ERROR" : "LOADING MAP"}
            </div>
          </div>

          <div className={`scene-wrap${areaPickMode ? " selecting-access-point" : ""}${actionTrackerMode && selectedWardActionId ? " action-location-selected" : ""}`}>
            <div ref={hostRef} className="cesium-host" aria-label="Cesium globe" />
            <div className="scene-tools" aria-label="Map controls">
              <div className="camera-tools">
                <button type="button" aria-label="Zoom in" title="Zoom in" onClick={() => zoom("in")}>+</button>
                <button type="button" aria-label="Zoom out" title="Zoom out" onClick={() => zoom("out")}>−</button>
                <button type="button" aria-label="Reset map view" title="Reset map view" onClick={resetView}>⌂</button>
                <button type="button" aria-label={`Switch to ${twoDimensional ? "3D" : "2D"}`} title={`Switch to ${twoDimensional ? "3D" : "2D"}`} onClick={toggleSceneMode} disabled={sceneModeChanging}>{twoDimensional ? "3D" : "2D"}</button>
              </div>
              <button className="layers-toggle" type="button" aria-expanded={layersOpen} onClick={() => setLayersOpen(!layersOpen)}>
                <span aria-hidden="true">▤</span> Layers <span className="layers-caret">{layersOpen ? "−" : "+"}</span>
              </button>
              {layersOpen && (
                <div className="layers-panel" aria-label="Map layers">
                  <div className="layers-panel-title">VISIBLE LAYERS</div>
                  {layerDefinitions.map((layer) => (
                    <label className="layer-option" key={layer.id}>
                      <input type="checkbox" checked={enabledLayers[layer.id]} onChange={() => toggleLayer(layer.id)} />
                      <span className="layer-swatch" style={{ backgroundColor: layer.color }} />
                      <span>{layer.label}</span>
                    </label>
                  ))}
                  <div className="layers-note">Open Buildings scores: 0.65–0.9627; no local confidence cutoff applied and no height data. OSM massing uses tagged heights or levels × 3 m (estimate). Copernicus DSM tint is elevation context only, not a terrain mesh or flood result.</div>
                </div>
              )}
            </div>
            {(floodReviewVisible && floodScreeningAreas || activeMapPlanLayers.some((work) => work.planned_count > 0) || facilityRoutes || accessRun && closureLayerVisible || enabledLayers.mcgmFloodRecords && municipalFloodContext || enabledLayers.mcgmShelters && municipalFloodContext) && (
              <div className="scenario-map-legend" role="status">
                {floodReviewVisible && floodScreeningAreas && <span className="scenario-legend-row"><span className="scenario-flood-swatch" /><span><strong>{illustrativeFloodModel ? "ASSUMPTION-MODEL RANKING" : "RAIN-BASED INSPECTION SCREEN"}</strong> · {illustrativeFloodModel ? "top 8 model-ranked cells; not flood extent" : `${rainfallPriorityAreas.length} areas ranked for this rainfall input; not predicted impacts`}</span></span>}
                {enabledLayers.mcgmFloodRecords && municipalFloodContext && <span className="scenario-legend-row"><span className="scenario-mcgm-flood-swatch" /><span><strong>MCGM REGISTERED FLOOD LOCATIONS</strong> · {municipalFloodContext.summary.flood_record_count} ward records · source records, not this scenario</span></span>}
                {enabledLayers.mcgmShelters && municipalFloodContext && <span className="scenario-legend-row"><span className="scenario-shelter-swatch" /><span><strong>MCGM LISTED SHELTER LOCATIONS</strong> · {municipalFloodContext.summary.shelter_record_count} locations · status/capacity not verified</span></span>}
                {facilityRoutes && <span className="scenario-legend-row"><span className="facility-route-nearest-swatch" /><span><strong>NEAREST FACILITY ROUTE</strong> · {facilityRoutes.facilities[0]?.name} · {formatDistance(facilityRoutes.facilities[0]?.distance_m ?? null)}</span></span>}
                {facilityRoutes?.applied_closures.length ? <span className="scenario-legend-row"><span className="scenario-line-swatch" /><span><strong>ROADS CLOSED FOR THIS WHAT-IF</strong> · {facilityRoutes.applied_closures.join(", ")}</span></span> : null}
                {facilityRoutes?.applied_closures.length ? <span className="scenario-legend-row"><span className="scenario-line-swatch" /><span><strong>ROADS CLOSED FOR THIS WHAT-IF</strong> · {facilityRoutes.applied_closures.join(", ")}</span></span> : null}
                {facilityRoutes && facilityRoutes.facilities_found > 1 && <span className="scenario-legend-row"><span className="facility-route-nearby-swatch" /><span>Routes to {facilityRoutes.facilities_found - 1} other nearby facilities</span></span>}
                {activeMapPlanLayers.map((work) => work.planned_count > 0 && <span className="scenario-legend-row" key={work.workstream}><span className={`preparedness-map-swatch ${work.workstream}`} /><span><strong>{actionTrackerMode ? `${work.workstream === "field_review" ? "TERRAIN / DRAINAGE" : work.workstream === "record_verification" ? "REGISTERED LOCATIONS" : "SHELTER LISTINGS"} · TRACKER` : work.workstream === "field_review" ? "FIELD REVIEW CELLS" : work.workstream === "record_verification" ? "REGISTERED MCGM LOCATIONS" : work.workstream === "shelter_audit" ? "LISTED SHELTER AUDITS" : work.workstream === "drainage" ? "DRAINAGE REVIEW CELLS" : work.workstream === "streetlights" ? "DEMO STREETLIGHT LOCATIONS" : "HEALTH ACCESS REVIEW POINTS"}</strong> · {actionTrackerMode ? `${work.feature_collection.features.length} selected tasks shown on map` : `${work.planned_count} ${decisionMode === "investment" ? "candidate locations · selected option" : "mapped checks · selected plan"}`}</span></span>)}
                {accessRun && closureLayerVisible && <><span className="scenario-legend-row"><span className="scenario-line-swatch" /><span><strong>HYPOTHETICAL CLOSURE</strong> · {accessRun.road_name} · not live status</span></span><span className="scenario-legend-row"><span className="scenario-point-swatch" /><span>{accessRun.change.newly_unreachable_road_nodes} road nodes newly without a route · not people</span></span></>}
              </div>
            )}
            {sceneModeChanging && <div className="scene-transition-notice" role="status">Reframing the ward…</div>}
            {layerMessage && <button type="button" className="map-layer-notice" onClick={() => setLayerMessage("")} aria-label="Dismiss map layer message">{layerMessage} <span>×</span></button>}
            {(sceneState === "error" || !boundaryLoaded) && (
              <div className="scene-empty-card" role="status">
                <span className="empty-icon" aria-hidden="true">◎</span>
                <div className="card-label">{sceneState === "error" ? "SOURCE LOAD ISSUE" : "REAL WARD BOUNDARY REQUIRED"}</div>
                <p>{sceneMessage}</p>
                <div className="empty-rule" />
                <span className="empty-meta">{boundaryLoaded ? "BOUNDARY LOADED · NO FLOOD OUTPUT" : "NO WARD BOUNDARY · NO FLOOD OUTPUT"}</span>
              </div>
            )}
            {attribution.length > 0 && <div className="source-credits">{attribution.join(" · ")}</div>}
          </div>

          <div className="map-footer">
            <div className="map-footer-note"><span className="legend-ring" />{enabledLayers.terrainContext ? " Copernicus GLO-30 DSM elevation tint · display context only · not water depth or a flood result." : enabledLayers.satellite && enabledLayers.openBuildings ? " Esri satellite imagery + detected footprints · imagery dates vary · no building heights or flood output." : enabledLayers.satellite ? " Esri satellite/aerial imagery · date varies · not street view or flood evidence." : enabledLayers.openBuildings ? " 6,881 satellite-detected footprints · flat only · no source imagery or flood output." : " The selected feature and locations appear on this map."}</div>
            <div className="map-footer-right">SCENE STATUS <strong>{boundaryLoaded ? "BOUNDARY READY" : "NO BOUNDARY"}</strong></div>
          </div>
        </section>
      </div>
    </main>
  );
}


function positiveNumber(value: unknown): number | undefined {
  if (typeof value !== "string" && typeof value !== "number") return undefined;
  const match = String(value).trim().match(/^([0-9]+(?:\.[0-9]+)?)(?:\s*m)?$/i);
  if (!match) return undefined;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function formatDistance(value: number | null): string {
  if (value === null) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} km` : `${Math.round(value)} m`;
}

export default App;
