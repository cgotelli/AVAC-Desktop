# Third-party notices

AVAC Desktop's project-owned code is AGPL-3.0-or-later. The following
dependencies retain their own copyright and license terms.

## Numerical source included in this repository

`native/clawpack-v5.14.0/` contains the Clawpack source subset needed to build
and run this application. The original BSD license and component licenses
are retained at its root and under `amrclaw`, `classic`, `clawutil`, `geoclaw`,
`pyclaw`, `riemann` and `visclaw`. Upstream:
[Clawpack](https://github.com/clawpack/clawpack), version 5.14.0.

The selected numerical and Python sources were preserved from AVAC-QGIS's
existing source tree, including its local Windows build and WAVE fast-path
support. This is not a claim that the subset is an unmodified upstream release.
The PyClaw initializer additionally omits its unconditional `IOTest` import;
the upstream test suite is excluded from this source subset.
Desktop also modifies `geoclaw/src/2d/shallow/flag2refine2.f90` to refine wet
AVAC release cells at initialization, and `amr2.f90` to provide an optional
initialization-only patch geometry export before output or time stepping.
See [native source notes](native/README.md).

## Windows native runtime libraries

Runtime packaging uses WinLibs GCC 13.2.0 / MinGW-w64 11.0.1 UCRT POSIX SEH r8.
The exact unmodified DLL hashes, source links, recipe revision and notice-file
hashes are recorded in `tools/windows_runtime_licenses/manifest.json`.

- GCC `libgcc_s`, `libgfortran` and `libgomp`: GPL notices and GCC Runtime
  Library Exception in `gcc-COPYING3` and `gcc-COPYING.RUNTIME`.
- `libquadmath`: distinct Library/Lesser GPL notices in
  `gcc-COPYING.LIB` and `libquadmath-COPYING.LIB`.
- MinGW-w64/winpthreads: `mingw-w64-COPYING` and `winpthreads-COPYING`.
- dlfcn-win32 1.4.1 (`libdl.dll`): `dlfcn-win32-COPYING` and the corresponding
  unmodified `dlfcn-win32-dlfcn.c`.

These texts are retained under `tools/windows_runtime_licenses/` and copied
into each built native runtime. The DLL binaries themselves are not tracked.
Packaging rejects a different DLL set without updated reviewed records.

## Python, UI and geospatial dependencies

The Windows application additionally uses Python, PySide6/Qt 6.8.3,
GDAL/PROJ, NumPy/OpenBLAS, Matplotlib, pyqtgraph, PyYAML and their dependencies.
MP4 export uses Qt Multimedia, its FFmpeg 7.1 libraries and Windows multimedia
services. Qt/PySide6 and FFmpeg remain dynamically linked. Their license rights
include applicable library replacement and debugging modifications.
Microsoft C/C++ redistributable libraries are included app-locally in frozen
builds under their own terms. PyInstaller and NSIS are build tools.

`tools/desktop_distribution.py` stages dependency license/copyright texts,
Qt attribution files, source archives and available conda recipes/patches for
the offline installer. The build-time source hashes are pinned in
`packaging/windows/distribution-sources.lock.json`. Installed `Licenses/`,
`Source/third-party/SOURCES.json` and `INSTALLATION_FILES.json` describe a
particular distribution. Source availability and notice completeness must be
preserved when changing how binaries are distributed.

The optional tutorial downloader obtains pinned terrain/release inputs from
the separate [AVAC-QGIS repository](https://github.com/cgotelli/AVAC-QGIS).
Those datasets are not included in this repository. Online map backgrounds
carry their provider attribution in the application and are not bundled.
