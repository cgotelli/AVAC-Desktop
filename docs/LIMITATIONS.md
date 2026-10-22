# Current limitations

AVAC Desktop is an early scientific application preview. Windows 11 x64
(Intel/AMD) is the current distribution target. Linux, macOS and Windows ARM
installers, remote execution and integrated CLI/HPC/MPI workflows are not
provided. Microsoft Store submission and certification remain unfinished.

Terrain must be north-up, square-cell and projected in metres, with no NoData
in the computational DEM. Automatic clipping, reprojection and resampling are
not provided. The exact raster reader has a 100-million-cell allocation guard;
it is not a tiled/out-of-core numerical reader. Multilayer vector containers
should be exported to a selected single layer before import.

Profile and gauge files support single-line and single-point features. Split
multipart features first and retain a known CRS and all shapefile sidecars.
Derived sampling caches may regenerate after a project is moved. Native solver
restart/resume and single-file project archives are not implemented.

Output uses uniform time intervals. Avalanche and wave durations must each be
divisible by that interval. The combined animation uses the WAVE duration;
avalanche frames beyond it remain available in the avalanche view. Display
overviews and combined maps do not change the numerical grids or add snow and
water quantities.

Extended GPU/high-DPI/codec coverage, independent clean-machine installation
acceptance and complete scientific benchmark equivalence remain outstanding.
Short successful runs are not proof of scientific accuracy. Deep Windows paths
and some Unicode/locale combinations can exceed native toolchain constraints.
Keep compiler/runtime paths short. Windows N requires the Media Feature Pack
for multimedia export.

Volume-history/coupling-ledger panels, two-run comparison, integrated 3D views
and high-resolution print layouts are not implemented. Online background
providers require network access and may change availability or terms; there
is no offline-area download.

Read [DISCLAIMER.txt](../DISCLAIMER.txt) before relying on model outputs.
