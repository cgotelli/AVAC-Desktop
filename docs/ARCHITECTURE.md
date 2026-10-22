# Architecture

AVAC Desktop uses PySide6/Qt Widgets for its interface, pyqtgraph for map
interaction, GDAL/OGR/PROJ for geospatial I/O and transformations, NumPy for
arrays, and Matplotlib for scientific figures. Native AVAC and WAVE executables
perform the simulations. QGIS and its Python bindings are not dependencies.

## Interface and project state

`app.py` starts Qt, applies the theme and opens `shell.MainWindow`. `shell.py`
connects the Model & Run and Analyze modes to the application services.
`forms.py` and `settings_dialog.py` edit parameters; `theme.py`,
`window_chrome.py` and `resources/` provide presentation and artwork.

`project.py` owns `ProjectSession`, serialization and completed-run discovery.
`project_storage.py` makes saved inputs/results portable. `preferences.py`
stores user defaults separately from project-specific parameters.
See [project format](PROJECT_FORMAT.md) for the manifest and folder layout.

`map_view.py`, `geometry.py`, `raster_style.py` and `geo.py` handle map
interaction, geometry, display styling and exact dataset reading. The bounded
terrain overview is only a display product. `basemap.py` obtains optional
online background tiles; these never become numerical terrain input.

## Preparation and execution

```text
Terrain + release polygons + complete configuration
    -> simulation.py -> core/preprocessing.py -> project-owned AVAC run
    -> native runtime's setrun.py -> native .data control files
    -> execution.NativeJob -> AVAC solver -> completed raw results
    -> optional wave.py -> WAVE scenario -> WAVE solver
    -> project completion checkpoint -> reopening discovers results
```

`workers.py` schedules background tasks; `execution.py` owns native child
processes, logs, cancellation and completion. `workflow.py` coordinates a
coupled run and reuse of a matching completed avalanche. Preparation currently
uses a serial worker because the native control writer changes the working
directory.

`core/` contains the GUI-independent configuration, grid/geometry preparation,
workspace, runtime validation, coupling and result-reading services. These
modules were extracted from AVAC-QGIS; the QGIS layer adapters and plugin
execution classes are excluded. Historical on-disk markers such as
`.avac_qgis_run.json` and `.avac_qgis_wave_run.json`, and some result-directory
names, remain unchanged so existing saved Desktop projects can be read.

`runtime.py` installs the Desktop-owned AVAC/WAVE runtime archive on first use.
Each descriptor pins its runtime manifest; `core/runtime.py` checks paths,
required files and SHA-256 identities before use. Native libraries are cached
per user under `%APPDATA%/AVAC Desktop/runtime/desktop/`; simulations and results
belong to the project folder, not that cache.

## Results and sampling

`analysis.py` and `wave.py` read native Clawpack FGout results through the
corresponding `core/` services. `combined.py` coordinates avalanche and wave
display without adding unlike physical quantities or resampling their grids.
`analysis_shapes.py` persists profile lines and gauge points as shapefiles;
`sampling_cache.py` stores derived samples with source/geometry identities.
`video_export.py` uses Qt Multimedia for map and profile MP4 export.

`mesh.py` runs the verified AVAC executable with `AVAC_INITIAL_MESH_ONLY=1`
in an owned temporary sibling of `_output`, using copies of the prepared
controls and their existing relative input references. After normal native
grid initialization, `amr2.f90` writes seven geometry columns and exits before
`valout` or `tick`; it writes no solution arrays. Only `AVAC/initial_mesh.txt`
is retained. Cancellation terminates the owned process. Normal execution
removes the inspection environment flag. Inspection is opt-in and cached per
prepared run; changed inputs require preparation again.

At t=0, `flag2refine2.f90` refines wet AVAC release cells through the configured
levels even though their initial velocity is zero. The branch is guarded by
`conserve_depth_amr` and leaves WAVE criteria unchanged. After t=0 the existing
speed/energy criteria apply. `mesh_view.py` batches the static initial patches
into one graphics item, clips against the viewport and bounds cell-line work.
The overlay is removed on entering Analyze. Results readers, frame workers
and video export have no mesh path, mesh time index or mesh cache.

## Large-grid execution

Release coverage keeps the same 64-by-64 boundary samples and geometric union;
chunk bounds reject disjoint polygons before allocating point-level masks.
The sampled coverage and resulting initial depth remain unchanged.

AVAC preparation retains `Topo/topography.asc` (and any fine overlay) for
existing readers and external tools. It also writes a lossless `.avacbin`
copy. The native writer selects that copy when present, falling back to ASCII
for existing cases. `AVACTOP1` is an eight-byte magic followed by little-endian
int64 columns/rows, five float64 values (nodal x/y origin, x/y spacing, NoData),
then north-to-south row-major float64 samples. Its 64-byte header already has
the half-cell registration used by the ASCII reader. Native reading validates
magic, dimensions, size, coordinates and spacing before accepting samples.
No terrain samples are resampled or rounded. Execution integrity records hash
both the selected binary file and its retained ASCII partner.

`rheology_module` caches terrain nonplanarity classifications in a thread-safe
LRU, capped at 256 entries and 128 MiB. Reuse requires identical geometry,
boundary settings, shape and every bed sample including ghost cells. Changed
AMR stencils or moving terrain miss the cache and use the original classifier.
The cache contains no solution-dependent values and does not commit trial
CFL states. Exactly empty AVAC CFL probes and normal slices skip zero-wave
work only when every conserved component and ghost cell is zero. Shallow
films, residual momentum, NaNs and wet neighbouring ghosts retain the normal
path. Wet/dry tolerances, numerical schemes and timestep acceptance are unchanged.

Cell-independent loops follow contiguous x storage. Final FGmax output reuses
an exact formatted suffix for never-wet points with zero maxima/times and an
unset arrival time, preserving signed-zero handling and the original text
layout. Other points retain the original formatting. Output frequency,
resolution, diagnostic fields and native file compatibility are unchanged.

## Numerical source and distribution

`native/src/AVAC` and `native/src/WAVE` contain the application's Fortran solvers
and `setrun.py` writers. `native/clawpack-v5.14.0` retains the required common
Fortran sources, Python readers/writers and original licenses. It is a selected
source subset from the existing application, including its local Windows and
WAVE support changes; it is not an unmodified full Clawpack distribution.
The numerical source bytes were preserved during the repository separation.

`tools/build_windows_solvers.py` consolidates the native source lists and
invokes GNU Make/gfortran. `tools/build_desktop_runtimes.py` packages the
executables, native control writers, compact Clawpack Python packages and
reviewed compiler DLLs into versioned runtime archives. `AVACDesktop.spec`
freezes the UI and its dependencies; `packaging/windows/` creates the per-user
offline installer. License/source collection is part of packaging, not an
application startup task. See [building](BUILDING.md).
