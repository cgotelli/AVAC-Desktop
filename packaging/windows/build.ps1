[CmdletBinding()]
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
Push-Location -LiteralPath $root
try {
    & $Python -c "from PySide6 import QtCore; from osgeo import gdal; print(QtCore.qVersion(),gdal.VersionInfo())"
    if ($LASTEXITCODE -ne 0) { throw "Activate the desktop environment first." }
    & $Python -m PyInstaller --clean --noconfirm AVACDesktop.spec
    if ($LASTEXITCODE -ne 0) { throw "Desktop build failed." }
} finally { Pop-Location }
