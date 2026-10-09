/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WARD_BOUNDARY_URL?: string;
  readonly VITE_WARD_BOUNDARY_NAME?: string;
  readonly VITE_WARD_BOUNDARY_ATTRIBUTION?: string;
  readonly VITE_TERRAIN_URL?: string;
  readonly VITE_TERRAIN_ATTRIBUTION?: string;
  readonly VITE_LOCAL_SOURCE_PREVIEW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const CESIUM_BASE_URL: string;
