# Using AVAC Desktop

The application has two main modes: **Model & Run** for preparing a simulation,
and **Analyze** for exploring its results. **Edit > Settings** changes defaults
for future projects and switches between light and dark appearance. Each saved
project retains its own configuration.

## Prepare and run

1. Import a terrain DEM in **Terrain & release**. It must be north-up and have
   square cells. A projected metre CRS is supported, and a DEM without a CRS
   is treated as local XY coordinates with coordinates/elevations assumed to
   be metres. The Console warns and backgrounds are disabled in that case.
   Fill/remove NoData before computation. Desktop does not automatically
   reproject or resample the terrain.
2. Import release polygons from GeoJSON, a single-layer GeoPackage or a complete
   shapefile, or draw releases on the map. Importing preserves the original
   source. Edited geometry is saved separately in the project.
3. Set release conditions, material/rheology, numerics, duration and output
   interval. Complete native YAML configurations can also be imported/exported
   through **File**.
4. Save an `.avacproj` in a dedicated project folder. **Prepare** offers Save As
   if the project has not yet been saved.
5. Choose **Prepare**, then **Run**. The console reports progress and errors;
   **Stop** requests cancellation. A source checkout requires the native
   runtimes to have been built first, as explained in [building](BUILDING.md).

Click to add drawing vertices, then double-click, press Enter or use the finish
control. Escape cancels an unfinished shape. Select the pencil to move vertices
or the bin to delete the selected feature. Sketch lines are annotations, not
solver boundaries or analysis profiles. Use scroll to zoom, drag to pan and
Fit domain to return to the terrain.

**Extensions > Activate Impulse Wave** adds lake/wave setup to the same project.
The coupled workflow runs AVAC first, then prepares and runs WAVE. A completed
avalanche with exactly matching inputs/configuration can be reused. Otherwise,
it is recalculated. Avalanche and wave durations are independent and must each
be divisible by the selected uniform output interval. WAVE uses its own timeline;
the combined animation spans that timeline.

## Save and reopen

Save copies required inputs into the project folder, including shapefile
sidecars. Configuration snapshots, run folders and sampling files stay beside
the `.avacproj`. Completed calculations are linked automatically; after closing
the application, use **File > Open project** to see the existing results without
rerunning them. Parameter/geometry edits still need Save.

Move or back up the entire folder. Moving only the `.avacproj` does not move its
data. Save As to another folder copies project-owned inputs and results. Older
projects that still refer to external inputs need one Save while those inputs
remain available. See [project format](PROJECT_FORMAT.md) for details.

## Analyze

Select the result variable and frame/time. The map palette, opacity, limits and
zero transparency affect display only. The lower-left layer list controls map
visibility, including profiles and gauges. Online backgrounds require internet
access and a geographic CRS and carry provider attribution; numerical terrain
stays unchanged. Without a CRS, releases, lakes, profiles and gauges are read in
their existing XY coordinates without transformation. Ensure they align with
the DEM. Unreferenced saved inputs and exported results retain an absent CRS.

**Layers > Mesh** works in both modes and is off by default. During preparation
it shows the AVAC base grid and, when enabled, the WAVE base grid using their
configured cell sizes and fitted domains. It updates when parameters change;
future adaptive refinement develops during the simulation and is not predicted
in this preview.

In Analyze, the overlay reads the actual saved native solver patches, including
AMR refinement levels, and follows the selected time/frame and playback.
AVAC uses blue/cyan and WAVE orange, with different colours for refinement
levels. Combined views show both meshes and hold the avalanche's final mesh
after its duration. The label reports each mesh's actual saved time. If native
mesh snapshots are less frequent than result frames, the latest earlier mesh
is held; geometry is never interpolated or guessed.

Patch boundaries stay visible at normal zoom; individual cell lines appear
when the cells are large enough on screen. Only visible lines are generated,
with a drawing budget and bounded header cache. Very dense views ask you to
zoom in. Mesh headers are read in the background, only while the layer is on;
the overlay does not read additional solution or auxiliary arrays. Its choice
persists with the project and is included in map images/videos. Time summaries
such as maximum depth have no single corresponding adaptive mesh; select a
time-dependent field to view it. Older runs without native binary patch headers
show an availability message rather than an invented mesh.

Create/import profile lines and point gauges from their analysis panels.
Geometry is stored in shapefiles; keep all sidecars together. A `.prj` is not
required for an unreferenced project. Profiles sample a
line through the current result. Gauges show time-dependent results at a point;
a maximum-over-time product does not provide a gauge time series. Sampling
geometry persists and can be reused with another valid result variable.

The application supports raster, CSV, geometry and figure exports. Map and
profile animations can be exported to MP4 using available Windows multimedia
components. There is no gauge MP4 export. Combined views distinguish snow from
water rather than summing their physical values.

Read [limitations](LIMITATIONS.md) and the [scientific-use notice](../DISCLAIMER.txt)
when interpreting results.
