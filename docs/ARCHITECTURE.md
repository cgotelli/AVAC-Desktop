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
