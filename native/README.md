# Numerical source

`src/AVAC` contains the avalanche backend and `src/WAVE` the impulse-wave
backend. Each has Fortran sources, native `setrun.py` controls and Makefiles.
The default AVAC YAML is included with the AVAC source; the application-owned
UI default is under `avac_desktop/resources/`.

`clawpack-v5.14.0` is a selected source subset from the existing
[AVAC-QGIS](https://github.com/cgotelli/AVAC-QGIS) working tree. It includes:

- Common Fortran modules/sources referenced by the AVAC and WAVE Makefiles.
- The common Makefile and source-list helper.
- Clawpack Python packages needed for native control writing and result reading.
- The upstream root and component license texts.

Examples, tests, generated files, notebooks and unused solver trees are
excluded. Numerical source bytes are retained, including existing local
Windows-build/WAVE support changes. Preserve those changes when updating from
upstream [Clawpack 5.14.0](https://github.com/clawpack/clawpack/tree/v5.14.0).
Third-party files retain their original licenses.

The PyClaw package initializer has one additional packaging change: its
unconditional `IOTest` import/export is removed, because the upstream test suite
is not distributed here. Its numerical algorithms and result readers are unchanged.

Build through `tools/build_windows_solvers.py`, then
`tools/build_desktop_runtimes.py`; see [building](../docs/BUILDING.md). The
Desktop uses the resulting versioned runtime archive rather than executing
files directly from this directory. Updating `setrun.py` or a common Python
reader therefore also requires rebuilding the runtime archive. Compilation
products and runtime archives remain outside version control.
