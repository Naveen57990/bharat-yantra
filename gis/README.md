# GIS input inspector

The inspector reads local vector layers and a raster DEM and writes a JSON report with CRS, bounds, feature count, geometry-type summary, null counts, raster shape, resolution, nodata and valid-data fraction. It performs read-only inspection; it does not repair geometry, reproject, clip, assess licensing, infer accuracy, or declare a dataset suitable for flood modeling.

## Requirements

Python 3.12 isolated environment is installed at `.venv/`. Direct dependency ranges are in `requirements.txt`; the captured working environment is pinned in `requirements.lock.txt`.

To recreate the GIS environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r gis/requirements.lock.txt
```

## Usage

```sh
python gis/inspect_inputs.py \
  --vector data/raw/ward_boundary.gpkg \
  --vector data/raw/roads.gpkg \
  --raster data/raw/terrain.tif \
  --output data/reports/input_quality.json
```

The local F/S boundary, OSM extracts, MCGM drainage snapshots and Copernicus DEM source tiles are under `data/raw/` and are excluded from version control. Their local-use/publication status is recorded in `data/provenance/dataset_registry.csv`; MCGM and OSM copies are on hold pending terms review.

Prepare a projected, buffered DSM clip for visualization:

```sh
.venv/bin/python gis/prepare_copdem_terrain.py \
  --ward data/raw/mcgm/fs_ward_boundary.geojson \
  --tiles data/raw/copernicus/copernicus_dem_N18_E072.tif data/raw/copernicus/copernicus_dem_N19_E072.tif \
  --output data/processed/fs_ward/copernicus_glo30_dsm_utm43n.tif
```

This creates a GeoTIFF for GIS analysis, not Cesium terrain tiles or a validated flood surface. The output manifest records checksums, attribution and limitations. `data/reports/` contains structural inspections and a first-pass drainage field summary.

Prepare the OSM footprint layer used by the local Cesium preview:

```sh
.venv/bin/python gis/prepare_osm_buildings_ward.py \
  --ward data/raw/mcgm/fs_ward_boundary.geojson \
  --buildings data/raw/osm/buildings.geojson \
  --output data/processed/fs_ward/buildings_ward.geojson
```

This preserves every polygonal OSM building footprint intersecting the ward and clips it to the boundary; it does not invent heights. The generated GeoJSON and manifest stay under ignored `data/processed/` pending source-term review. The browser renders point features as ground-clamped ellipses and caps GeoJSON line strokes at 1 px for broad WebGL compatibility.

Acquire and prepare the supplemental Google Open Buildings v3 footprints through Overture Maps:

```sh
.venv/bin/overturemaps download \
  --release 2026-09-23.1 \
  --bbox=72.832890,18.978379,72.869691,19.016923 \
  -f geojson --type=building \
  -o data/raw/overture/fs_buildings.geojson
.venv/bin/python gis/prepare_overture_open_buildings.py \
  --ward data/raw/mcgm/fs_ward_boundary.geojson \
  --buildings data/raw/overture/fs_buildings.geojson \
  --output data/processed/fs_ward/open_buildings_ward.geojson \
  --overture-release 2026-09-23.1
```

The preparation step retains only features identified as Google Open Buildings, clips them to F/S, and preserves source confidence and record IDs. The current output has 6,881 footprints with no height/floor fields. No local confidence threshold is applied. The source is machine-detected and may omit, falsely add, or offset buildings; it is supplemental visual context, not a surveyed building inventory. The raw query and processed output are ignored by git and remain on hold pending final license/attribution review.

Local MCGM acquisition command (keeps results in ignored `data/raw/`; source rights remain unresolved):

```sh
.venv/bin/python gis/acquire_mcgm_drainage.py \
  --ward data/raw/mcgm/fs_ward_boundary.geojson \
  --output-dir data/raw/mcgm/drainage
```

Keep raw files immutable. Do not publish any source or derivative until its terms and attribution obligations are cleared.
