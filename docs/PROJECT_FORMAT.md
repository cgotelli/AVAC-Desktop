# AVAC Desktop project format v1

`.avacproj` is bounded JSON with `format: avac-desktop-project`,
`schema_version: 1`, project ID/name, workspace, inputs, configuration references,
source hashes, selected runs, optional WAVE setup and UI state. Unsupported
versions are rejected without rewriting the source. Relative paths resolve
against the manifest directory, never the current working directory. Required references
in newly saved projects stay inside the project folder. Older manifests may
reference external files; opening remains read only, and Save copies required
external data into the project folder. Opening never executes referenced content.

`configuration.avac_yaml` references a **complete** native AVAC configuration,
or an empty mapping for a new case whose parameters have not been loaded.
Unknown advanced keys survive edits. Each save creates an immutable uniquely
named YAML snapshot in `<project>.config/`, then atomically replaces the JSON
manifest. A failed replacement leaves the previous manifest/config pair intact.
Snapshots are deliberately retained rather than risking deletion of referenced
data; garbage collection is not implemented.

Save and Save As set `project_name` to the manifest filename stem. Optional
`geometry.sketch_lines` contains finite projected XY polylines in the terrain
CRS. `geometry.release_edited` marks project-owned polygon edits. Edited release
geometry receives an immutable, validated GeoJSON snapshot in `<project>.config/`
before manifest replacement. Original imported files are never overwritten.
Deleting every release stores a null release reference; such a project is valid
to save and open, but cannot be prepared until release areas are supplied.

Optional `geometry.sampling_shapefiles` references point-gauge and line-profile
shapefiles, relative to the project. New drawings are written
immediately under `analysis_inputs/` with unique names; the project references
them rather than embedding coordinates or copying result arrays. Save copies
external shapefiles and all their sidecars into owned input directories. Preserve all
shapefile sidecars. Multiple features are selectable independently, and their
source CRS is required. Imported geometries are transformed into the current
map CRS in memory. Saving/reopening reloads the same disk-backed geometries.

`inputs` references AVAC DEM, release polygons and optional lake polygon.
An absent DEM CRS stays absent in copied inputs, run metadata and raster/vector
exports. Coordinates and elevations are treated as metres in a local XY plane.
Reopening retains this interpretation, warns in the Console and disables online
backgrounds; imported geometry is not reprojected into an invented CRS.
Optional `inputs.release_export_source` retains the original release filename
for the export chooser, even when edited geometry uses an owned snapshot.
`provenance` stores SHA-256 hashes of imported terrain/release files. A mismatch
on reopen is visible and invalidates preparation. Save snapshots external GIS
inputs under `inputs/<unique>/`; already local inputs stay in place. Raster
sidecars and shapefile components travel together. Virtual rasters are
materialized as GeoTIFFs without resampling or changing sample precision, and
their exact grids are checked. The manifest records the owned terrain/release
hashes. Original imported datasets are never overwritten.

Save As in another folder copies explicitly referenced runs and project-owned
history, including incomplete runs, plus derived sampling caches. It copies
individual run trees, never the entire old workspace or unrelated projects.
Conflicting run names receive unique destinations. Only after successful copies
and atomic manifest replacement does the live session adopt the new paths.
Failed saves preserve the previous manifest and live session; orphaned partial
copies can remain, like unreferenced configuration snapshots.

WAVE markers use optional `source_avac_run_relative`, resolved against the
scenario directory, ahead of the legacy absolute `source_avac_run` provenance.
Save upgrades the desktop link; Save As adjusts it in the destination scenario.
New preparations already write the relative link. Scientific input/output bytes
are preserved. Absolute historical paths in native provenance/control snapshots
are informational for Desktop result reading; the application provides its own
managed runtime. Move the whole project folder, then open its `.avacproj`.
The optional original release-export chooser location is not a required input.

`selected_runs.avac` and `.wave` preserve source/result relationships.
Successful native completion atomically updates these links and a default
Results view without replacing the saved configuration, input or geometry
references. Optional `execution` stores the exact latest launched run, kind
(`AVAC`/`WAVE`) and `registered` state. It is written before native launch;
completion marks it registered. An unregistered reference whose marker says
completed can restore the session on open after an interrupted completion update.
Other statuses retain the previous completed selection with a console notice.
Loading remains read only; a subsequent manual Save commits recovered state.
New native markers include `desktop_project_id` for ownership checks. When saved
result references are absent or unavailable, loading checks the project's own
`runs/` and `wave_runs/`, plus a declared older workspace. Completed AVAC markers
must match the project ID, or (without an ID) the exact saved Desktop input
signature. WAVE must reference that same eligible avalanche and must not identify
another project. Existing valid saved selections remain authoritative; otherwise
the latest eligible pair is restored. Loading/discovery does not rewrite the
manifest or native markers. `session.runs` is populated from eligible AVAC history.
`wave_extension` contains the explicit optional enable flag and existing WAVE
setup values; prepared native WAVE YAML still lives in the independent run.
Optional `wave_extension.setup.duration` stores the independent wave duration
in seconds. Missing/null legacy values initially use the avalanche duration;
the UI then retains the wave value independently when avalanche timing changes.
Each duration must be divisible by the shared output interval. New WAVE markers
record source/wave durations and interval counts separately, and reference their
run-owned `lake.geojson` outline. Existing core callers retain source timing
unless they explicitly request the new optional timing arguments.
Legacy CFL entries in WAVE setup are retained for compatibility but ignored;
the effective WAVE values always inherit `computation.cfl_target` and `.cfl_max`
from AVAC. Coupled preparation plans are intentionally session-only. Reopening
requires Prepare again, which can reuse a completed matching avalanche using
its `desktop_input_signature` and actual discoverable output. Reuse never
re-stages or writes into that completed AVAC run.
The project's containing directory now determines `workspace`; new manifests
write `workspace: "."`. Older explicit workspace references are ignored for
future preparations, without moving or changing their existing run directories.
Default scientific parameters and appearance live in per-user Qt settings;
loading a project always uses that project's YAML snapshot, not those defaults.
`ui` holds last mode, analysis kind, variable, frame, extent, layer flags and
thread choice. These are presentation settings, not another physics schema.
`ui.raster_styles` persists per-raster palettes, optional manual limits,
exact-zero transparency and opacity. These settings never change numerical
inputs or exported scientific arrays. Limits and opacity are checked on load.
Each style can also store `legend_visible`. Global `ui.layers` additionally
stores `lake`, `legends`, `scale` and `north` visibility.
The `ui.layers.profiles` and `ui.layers.gauges` flags independently hide their
map geometries and default to visible in older projects. They do not affect
stored shapefiles or computed samples.
`ui.layers.mesh` controls only the initial AVAC mesh in Preparation & Run and
defaults to false when absent. Analyze ignores this flag, including in older
projects that enabled results meshes. An optional generated
`runs/<run>/AVAC/initial_mesh.txt` contains the initialized patch geometry;
neither geometry nor solution arrays are embedded in the project manifest.
Prepared-run state is session-local; reopening a project requires preparation
again to inspect a new initial mesh. Completed results reopen as usual.
Optional `ui.result_page` selects Map (`analyze`), Profiles or Gauges, and
`ui.analysis_kind` also accepts `combined`. The shared field/frame selection
remains independent of this layout.
Combined selections now normalize older field choices to `surface_displacement`;
other fields remain available in Avalanche and Waves. Combined samples share
Waves' water-source cache identity because land snow affects only the map overlay.

`analysis_results/<key>/samples.npz` and `figure.png` are regenerable derived
products outside the native result tree. The key identifies sampling geometry,
source run paths and file stat identities, field, frame/time and sampling-rule
version. NPZ preserves the exact computed arrays without pickle. First-rendered
figures are saved once; live charts redraw from saved arrays. Projects do not
embed these caches; Save As copies them with the project. Relocation can change
their path-based identities and causes safe recomputation on first use.

Missing paths produce an actionable diagnostic; reimport can repair them.
Recent-project menus, complete-case legacy GUI YAML import and automatic schema
migrations are still pending. The current YAML import supports the complete
native AVAC schema, not every historical full-GUI case wrapper.

Each newly prepared run also receives `desktop_execution_paths.json` (format 1).
It records run-local input targets, short execution-relative references, and
SHA-256 identities of execution-copy `.data` files and their inputs. This avoids
existing 150-character Fortran filename limits without changing original inputs
or coefficients. Input-integrity checks run before launching prepared jobs.

Prepared AVAC terrain files may have a `.avacbin` sibling containing the same
nodal samples as the retained `.asc` file. This is a generated native-read
cache inside the run folder, not a project input replacement. Execution
integrity manifests additionally store optional `compatibility_inputs` hashes
for the ASCII partners; older manifests without this field remain readable.
Keep the whole run/project folder together as usual.

Mesh configuration now stores `computation.cell_size_reference: finest` and
`computation.regrid_seconds` (default 5 s). Loading older YAML converts its
base cell size to the previous finest spacing; saving records that migration.
New preparation uses fixed 1:2 AVAC ratios and uniform WAVE cells at the same
finest spacing. Completed results retain their original grids and run files.
