# Building on Windows

Use Windows 11 x64 on an Intel/AMD processor. Start with the activated Python
3.12 environment in [README.md](../README.md). Keep source/compiler paths short
and free of spaces when compiling Fortran, because GNU Make source lists use
space-separated paths. Project data can be stored elsewhere.

## Native solvers

Install [Git for Windows](https://gitforwindows.org/) including Git Bash, and
the exact [WinLibs GCC 13.2.0 / MinGW-w64 11.0.1 UCRT POSIX SEH r8 toolchain](https://github.com/brechtsanders/winlibs_mingw/releases/tag/13.2.0posix-18.1.5-11.0.1-ucrt-r8).
Extract its `mingw64` directory to a short location. The compiler needs
`gfortran`, `mingw32-make` and `strip`; Git Bash supplies `sh`, `rm` and other
shell tools used by Make. This compiler is a build requirement, not an
end-user installation prerequisite.

In an activated desktop environment, replace these example paths with your
toolchain and Git installation:

```powershell
$toolchainBin = 'C:\tools\mingw64\bin'
$gitShell = 'C:\Program Files\Git\usr\bin\sh.exe'
$env:PATH = "$toolchainBin;$env:PATH"
python tools/build_windows_solvers.py --shell $gitShell
python tools/build_desktop_runtimes.py --toolchain $toolchainBin
python -m avac_desktop
```

The first command compiles both `native/src/*/xgeoclaw.exe` executables with
the included common sources. The second writes two `.tar.gz` archives and
updates `avac_desktop/resources/avac-runtime.json` and `wave-runtime.json`.
Use a new `--version` when producing a new runtime; existing archives are not
overwritten. Runtime descriptors must travel with their matching archives.
The packaged native writers and Clawpack code are loaded from these archives,
so rebuild them after changing those sources.

`tools/windows_runtime_licenses/manifest.json` pins the exact reviewed compiler
DLLs and license texts. Packaging rejects different DLL bytes; selecting a
different compiler requires updating the component/license/source records
after review. It must not be bypassed by silently substituting new hashes.

## Standalone application folder

After building both runtimes, install the freezer and build:

```powershell
python -m pip install -e '.[build]' --no-deps
python -m pip install pyinstaller==6.22.3
.\packaging\windows\build.ps1
```

The output is `dist/AVACDesktop/AVACDesktop.exe` and its adjacent dependency
folder. Keep the whole output directory together. The root launch `.cmd`
opens that executable. The build scripts fetch and verify the pinned tutorial
terrain and release inputs and include them in the application. For a direct
PyInstaller invocation, first run `python tools/fetch_tutorial.py`; the spec
rejects missing or changed tutorial files. End users need no tutorial download.

## Offline installer

Install [NSIS 3.13](https://nsis.sourceforge.io/Download). Its `makensis.exe`
must be on PATH, or pass its full path with `-MakeNSIS`:

```powershell
.\packaging\windows\build_installer.ps1 -MakeNSIS 'C:\tools\NSIS\makensis.exe'
```

This stages dependency license texts, source archives, available conda build
recipes/patches and a matching application source snapshot, freezes the app,
and creates `dist/AVACDesktop-0.1.5-preview.1-Setup-x64.exe` plus its SHA-256
file. Source downloads are pinned by
`packaging/windows/distribution-sources.lock.json`; build caches/logs go under
ignored `build/`. Internet access is needed for initial dependency/source
downloads. Do not use `-SkipFreeze` or `-SkipLegal` after relevant source or
dependency changes.

The current all-in-one installer deliberately includes offline source archives
as well as executable dependencies, so it is substantially larger than this
Git repository. Source files, source archives, tutorial downloads and setup
binaries are separate distribution concerns; none of the generated archives
belong in Git.

The installer is per-user and includes Python, Qt, GIS dependencies and native
runtime DLLs. End users need neither QGIS nor a compiler. Windows N editions
need Microsoft's Media Feature Pack for multimedia. See
[`INSTALL.txt`](../packaging/windows/INSTALL.txt) for prerequisites and behaviour.

Building an installer does not sign it, publish it or certify it for the
Microsoft Store. Check installation and the actual preparation/run/reopen
workflow on a clean PC before releasing a new binary. Retain all required
notices and matching corresponding source when distributing dependencies.
