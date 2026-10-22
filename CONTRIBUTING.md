# Contributing

Please open an issue for a problem or proposed feature, or submit a focused
pull request. Describe the intended behaviour, the reason for the change and
how you checked it. For a bug, include the application/Python version, Windows
version, reproduction steps and relevant error text. Share only input data you
have permission to publish, and keep large project datasets out of Git.

Use the environment and source launch instructions in [README.md](README.md).
[Architecture](docs/ARCHITECTURE.md) maps the main modules, and
[building](docs/BUILDING.md) covers the native solvers and Windows distribution.
The clean repository intentionally has no test suite or historical development
artifacts. Validate a contribution with the affected user workflow and explain
the result in the pull request; do not imply a numerical change is scientifically
validated just because the interface starts.

Keep scientific computation separate from display. A display overview, palette
or rescaled image must never become solver input. Preserve terrain coordinates,
units, precision, provenance and the relationship between AVAC and WAVE runs.
Changes to numerical formulas, grid conventions, rheology or coupling need a
clear scientific rationale and appropriate quantitative validation.

Keep long work off the GUI thread, preserve cancellation and avoid modifying
original imported inputs or completed solver results. Preserve `.avacproj`
compatibility or explicitly version a format change. Some metadata names retain
their historical `avac_qgis` spelling for compatibility; they are not a QGIS
runtime dependency.

Include required source, assets and documentation for a change. Do not commit
local environments, credentials, native binaries, runtime archives, installer
outputs, downloaded tutorial data or simulation results. Keep existing
third-party copyright/license notices. Contributions to project-owned code
are provided under the project's AGPL-3.0-or-later license.
