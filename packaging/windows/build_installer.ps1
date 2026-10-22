[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$MakeNSIS = "makensis.exe",
    [switch]$SkipFreeze,
    [switch]$SkipLegal
)
$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$stage = Join-Path $root "build\desktop-distribution"
$logs = Join-Path $root "build\installer-logs"
New-Item -ItemType Directory -Force -Path $stage,$logs | Out-Null
function Invoke-LoggedCommand {
    param([string]$Log, [string]$Executable, [string[]]$CommandArgs)
    # Capture at the OS pipe level: Windows PowerShell otherwise treats normal
    # native stderr progress (including PyInstaller INFO) as terminating errors.
    & $Python -c 'import subprocess,sys; output=open(sys.argv[1],''wb''); result=subprocess.run(sys.argv[2:],stdout=output,stderr=subprocess.STDOUT); output.close(); sys.exit(result.returncode)' $Log $Executable @CommandArgs
    if ($LASTEXITCODE -ne 0) { throw "Build command failed ($LASTEXITCODE). See $Log" }
}
Push-Location -LiteralPath $root
try {
    $compiler = (Get-Command $MakeNSIS -ErrorAction Stop).Source
    $env:AVAC_NSIS_DIR = Split-Path -Parent $compiler
    & $Python -c "import pathlib,sys; assert not list((pathlib.Path(sys.prefix)/'conda-meta').glob('mkl-*.json')), 'Use the OpenBLAS installer environment'; from PySide6 import QtCore; from osgeo import gdal; print(QtCore.qVersion(),gdal.VersionInfo())"
    if ($LASTEXITCODE -ne 0) { throw "Activate the OpenBLAS installer environment first." }
    if (-not $SkipLegal) {
        Invoke-LoggedCommand -Log (Join-Path $logs "legal-build.txt") -Executable $Python -CommandArgs @("tools/desktop_distribution.py", "legal")
    }
    foreach ($required in @("Source\third-party\SOURCES.json","Licenses\COMPONENTS.json","DISCLAIMER.txt","LICENSE")) {
        if (-not (Test-Path -LiteralPath (Join-Path $stage $required))) { throw "Missing distribution asset: $required" }
    }
    if (-not $SkipFreeze) {
        Invoke-LoggedCommand -Log (Join-Path $logs "freeze.txt") -Executable $Python -CommandArgs @("-m", "PyInstaller", "--clean", "--noconfirm", "AVACDesktop.spec")
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "INSTALL.txt") -Destination (Join-Path $stage "INSTALL.txt") -Force
    Invoke-LoggedCommand -Log (Join-Path $logs "source-snapshot.txt") -Executable $Python -CommandArgs @("tools/desktop_distribution.py", "source")
    Invoke-LoggedCommand -Log (Join-Path $logs "payload.txt") -Executable $Python -CommandArgs @("tools/desktop_distribution.py", "installer-files")
    $sizeKiB = (Get-Content -LiteralPath (Join-Path $stage "size-kib.txt") -Raw).Trim()
    $outputFile = Join-Path $root "dist\AVACDesktop-0.1.1-preview.1-Setup-x64.exe"
    Invoke-LoggedCommand -Log (Join-Path $logs "installer-build.txt") -Executable $compiler -CommandArgs @("/WX", "/V3", "/DAVAC_VERSION=0.1.1-preview.1", "/DBUNDLE=$root\dist\AVACDesktop", "/DSTAGE=$stage", "/DOUTPUT_FILE=$outputFile", "/DUNINSTALL_FILES=$stage\uninstall-files.nsh", "/DINSTALLED_KIB=$sizeKiB", (Join-Path $PSScriptRoot "installer.nsi"))
    $hash = (Get-FileHash -LiteralPath $outputFile -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath ($outputFile+".sha256") -Encoding ASCII -Value ($hash+"  "+[IO.Path]::GetFileName($outputFile))
    [ordered]@{version="0.1.1-preview.1"; installer=$outputFile; sha256=$hash; bytes=(Get-Item -LiteralPath $outputFile).Length; signed=$false; scope="Per-user offline Windows 11 x64 preview; clean-VM acceptance remains separate"} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logs "installer.json") -Encoding UTF8
    Write-Output "Installer: $outputFile"
    Write-Output "SHA-256: $hash"
} finally { Pop-Location }
