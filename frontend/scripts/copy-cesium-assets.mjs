import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const source = resolve("node_modules/cesium/Build/Cesium");
const target = resolve("public/cesiumStatic");

if (!existsSync(source)) {
  throw new Error("Cesium package assets are missing. Install the frontend dependencies first.");
}

mkdirSync(resolve("public"), { recursive: true });
cpSync(source, target, { recursive: true, force: true });
console.log("Prepared CesiumJS static assets.");
