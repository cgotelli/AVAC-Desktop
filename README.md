# AVAC Desktop

AVAC Desktop is a free, open-source application for preparing, running and
exploring avalanche and avalanche-generated lake-wave simulations. Its native
Windows interface brings terrain, release areas, model parameters and results
into a single project.

The application runs independently of QGIS. For the QGIS plugin, see
[AVAC-QGIS](https://github.com/cgotelli/AVAC-QGIS), from which the shared
scientific services and solver sources originated.

## What it does

- Import projected terrain and release polygons, or draw and edit releases.
- Configure avalanche rheology, numerical settings and simulation output.
- Run the native AVAC solver and optionally its coupled WAVE solver.
- View results on a map, step through time, and sample profiles and gauges.
- Inspect the initial AVAC mesh before running, including refinement around
  snow releases. Cell lines appear as you zoom in.
- Export result rasters, figures, sample data and map/profile videos.
- Keep inputs, configuration, sampling geometry and results together in a
  project folder. Completed results reopen automatically with the project.
- Use light or dark appearance, hillshade and optional online map backgrounds.
- Choose English, French, Spanish, Italian or German and a decimal point or
  comma in Settings; both choices are remembered.
- Set the smallest mesh size, AVAC AMR levels and refinement update interval.
  WAVE uses a uniform mesh at the smallest size.

This is an early preview. Windows 11 x64 on Intel/AMD is the current target;
Linux, macOS and Windows ARM distributions are not provided. Scientific results
need independent validation. Read [limitations](docs/LIMITATIONS.md) and the
[scientific-use and warranty notice](DISCLAIMER.txt) before using model output.

## Windows installer

Download the setup EXE and its SHA-256 checksum from
[the latest preview release](https://github.com/cgotelli/AVAC-Desktop/releases/tag/v0.1.9-preview.1).
The offline installer includes Python, GIS/UI libraries and both native solvers.
It is unsigned; Windows may show an unknown-publisher notice.

DEMs without a CRS are supported as local XY grids with metres assumed. The
Console reports a warning and turns off online backgrounds for those grids.
Imported geometries must already use the same coordinates; no CRS is invented
and no reprojection is performed in an unreferenced project.

## Run from source

Install [Miniforge](https://github.com/conda-forge/miniforge) or
[micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html),
then use a Windows PowerShell terminal with conda/micromamba initialized:

```powershell
git clone https://github.com/cgotelli/AVAC-Desktop.git
cd AVAC-Desktop
micromamba create -f packaging/windows/environment.yml
micromamba activate avac-desktop
python -m pip install -e . --no-deps
python -m avac_desktop
```

With conda, replace the creation/activation commands with
`conda env create -f packaging/windows/environment.yml` and
`conda activate avac-desktop`. GDAL and PROJ come from conda-forge; do not try
to build GDAL with pip on Windows. Keep the environment activated when running
the application.

The interface can open before native solvers are built. **Prepare** and **Run**
require the AVAC/WAVE runtime archives: follow [building](docs/BUILDING.md) to
compile and package the included native source. These archives and installers
are build outputs, not tracked repository files. Setup binaries are distributed
through GitHub Releases separately from the source tree.

The Windows installer includes the terrain and release tutorial for offline use:
choose **Help > Load tutorial**, then save a project in your own folder.
For a source checkout, fetch the same pinned inputs separately:

```powershell
python tools/fetch_tutorial.py
python -m avac_desktop --tutorial
```

The downloader retrieves the pinned terrain and release inputs from AVAC-QGIS
and verifies their SHA-256 hashes. You can also import your own data. See the
[user guide](docs/USER_GUIDE.md).

## Source layout

| Location | Purpose |
| --- | --- |
| `avac_desktop/` | PySide6 interface, maps, execution, projects and analysis |
| `avac_desktop/core/` | GUI-independent configuration, preparation and result services |
| `avac_desktop/resources/` | Icons, control artwork, defaults and runtime descriptors |
| `native/src/AVAC/` | Avalanche solver and native run-control writer |
| `native/src/WAVE/` | Impulse-wave solver and native run-control writer |
| `native/clawpack-v5.14.0/` | Required Clawpack numerical/Python source subset and licenses |
| `packaging/windows/` | Dependency environment, application assets and installer recipe |
| `tools/` | Native runtime, application distribution and tutorial build helpers |
| `docs/` | Usage, architecture, project format and build documentation |

Start with [architecture](docs/ARCHITECTURE.md) to understand the code and
[contributing](CONTRIBUTING.md) to modify it. The repository is a fresh source
snapshot: plugin code, previous Git history, tests, development experiments,
generated results and build reports are excluded.

## License

Project-owned code is licensed under **AGPL-3.0-or-later**; see [LICENSE](LICENSE).
Third-party components retain their own licenses and attribution in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). AVAC Desktop is provided
without warranty to the extent permitted by applicable law. The
[scientific-use notice](DISCLAIMER.txt) explains modelling uncertainty and
the warranty/liability provisions; it does not restrict free-software rights.
