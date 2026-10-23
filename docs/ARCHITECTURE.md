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
`conserve_depth_amr`. WAVE uses a uniform grid. After t=0 the existing
speed/energy criteria apply. `mesh_view.py` batches the static initial patches
into one graphics item, clips against the viewport and bounds cell-line work.
A patch and all its cell lines are hidden when cells occupy less than seven
pixels, or its line budget is exhausted; no coarse patch outlines substitute
for invisible cells.
The overlay is removed on entering Analyze. Results readers, frame workers
and video export have no mesh path, mesh time index or mesh cache.

## Mesh controls and physical-time AMR

`computation.cell_size_reference: finest` identifies the current mesh schema.
`cell_size` is the smallest requested cell width, `refinement` counts levels
including the base grid, and all spatial/time refinement ratios are two.
The base width is `cell_size * 2**(refinement - 1)`. Older configurations with
an absent reference field are migrated from the former base-width convention,
preserving the finest width implied by their old 2/4/4 ratios. Existing results
are read as recorded; migration affects new preparation only.

Whole base cells are fitted symmetrically inside the original DEM bounds,
removing less than one base cell of total border width per axis. The source
DEM samples and qinit sampling grid remain intact. GeoClaw integrates the
terrain and initial depths over the independently positioned solver cells;
DEM resolution need not divide mesh spacing. Fixed result grids use the
smallest requested spacing. WAVE inherits that spacing with one uniform level;
fractional terrain overlaps use separable area-weighted integration, while
fractional lake boundaries use sampled polygon coverage.

`computation.regrid_seconds` defaults to 5 simulated seconds. `avac_amr.data`
passes it to AVAC. The scheduler lands on these deadlines and rebuilds the
hierarchy only at synchronized base steps, independently of output times.
Initial snow is refined at rest; subsequent flags use moving-snow speed and
resolved kinetic energy. The existing 0.05 m/s threshold suppresses numerical
noise. Static terrain elevations do not flag snow cells.

Before flagging each level, a buffer is sized from current maximum snow and
gravity-wave speeds plus a gravity acceleration allowance over the requested
interval. Long intervals therefore enlarge refined regions and can cost more;
the interval is not a guarantee of faster execution. Flag-array storage above
512 MiB is rejected with a request to reduce the interval. Terrain refinement
caching and conservative depth transfer remain active. A single level disables
AMR updates. WAVE always has one level.

`NativeJob` writes the desktop version, runtime location, solver and thread
count into `desktop_solver.log` before starting either solver, and records the
desktop version in the run marker.

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

## Interface language and numeric presentation

`i18n.py` loads the selected English-key JSON catalog from
`resources/translations` at startup. English is the source language and default.
Call `tr` for display text and `trf` for translated numeric templates; preserve
placeholder indices and format specifications in translations. Keep storage
keys, palette IDs, paths, user names and scientific metadata untranslated.
Qt's own translations handle standard buttons and dialogs; the Windows bundle
explicitly includes the four matching `qtbase` catalogs from PySide6.

Per-user QSettings store `interface/language` and `interface/decimal_separator`.
Language changes require restart; decimal presentation uses an independent
QLocale, with grouping disabled, and refreshes immediately. Numeric table cells
store floats and use `NumericDelegate`; charts use `NumericAxis`. Do not change
Python/C process locale or localize numerical serialization. Both numerical
settings and scientific files remain independent of interface translations.

`resources/legal` contains localized licensing information and the complete
scientific-use notice. The original English AGPL in `LICENSE` remains governing.
The installer uses `packaging/windows/languages.nsh` for custom text and embeds
each notice offline. The source package includes the same catalogs and notices.

## Defaults and installation cleanup

The factory configuration starts with one AVAC level. Older saved preference
snapshots are read with one level until a user explicitly saves mesh defaults
in Settings (`defaults/amr_levels_explicit`). This migration applies to new
projects only; project/imported configurations keep their recorded levels.

Normal Windows uninstallation removes the complete owned installation folder
and fixed Desktop app-data roots, then clears its settings and registration.
`packaging/windows/cleanup.nsh` validates the absolute installation path and
its final filesystem location, rejects system/personal roots, and recursively
enumerates owned directories without traversing reparse points. It retains
the ownership marker and uninstaller on failure, and leaves its working
directory before deleting folders. `/UPDATE` uses generated recorded-file
removals and retains app data and the marker for replacement/recovery. Setup
can recover an unregistered default folder containing only empty directories
or generated bytecode below `_internal`; unknown files and links are not claimed.
