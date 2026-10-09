import { createReadStream, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const projectRoot = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const localDataFiles: Record<string, string> = {
  "/local-data/fs-ward.geojson": "data/raw/mcgm/fs_ward_boundary.geojson",
  "/local-data/osm-roads.geojson": "data/raw/osm/roads.geojson",
  "/local-data/osm-buildings-ward.geojson": "data/processed/fs_ward/buildings_ward.geojson",
  "/local-data/open-buildings-ward.geojson": "data/processed/fs_ward/open_buildings_ward.geojson",
  "/local-data/osm-emergency-facilities.geojson": "data/raw/osm/emergency_facilities.geojson",
  "/local-data/mcgm-drains.geojson": "data/raw/mcgm/drainage/storm_water_drains.geojson",
  "/local-data/mcgm-manholes.geojson": "data/raw/mcgm/drainage/storm_water_manholes.geojson",
  "/local-data/copernicus-dsm-context.png": "data/processed/fs_ward/copernicus_dsm_context.png",
};

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesiumStatic/"),
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  plugins: [
    react(),
    {
      name: "india-sim-local-source-preview",
      configureServer(server) {
        server.middlewares.use(serveLocalSource);
      },
      configurePreviewServer(server) {
        server.middlewares.use(serveLocalSource);
      },
    },
  ],
});

function serveLocalSource(request: any, response: any, next: any) {
          if (request.method !== "GET") return next();
          const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
          const relativePath = localDataFiles[pathname];
          if (!relativePath) return next();

          const filePath = resolve(projectRoot, relativePath);
          if (!filePath.startsWith(`${projectRoot}/`) || !existsSync(filePath)) {
            response.statusCode = 404;
            response.end("Local source file is unavailable.");
            return;
          }
          response.setHeader("Content-Type", pathname.endsWith(".png") ? "image/png" : "application/geo+json; charset=utf-8");
          response.setHeader("Cache-Control", "no-store");
          const stream = createReadStream(filePath);
          stream.on("error", () => {
            response.statusCode = 500;
            response.end("Unable to read local source file.");
          });
          stream.pipe(response);
}
