@echo off
if exist "%~dp0dist\AVACDesktop\AVACDesktop.exe" (
  start "" "%~dp0dist\AVACDesktop\AVACDesktop.exe" %*
) else (
  echo Build the desktop package first. See docs\BUILDING.md.
  pause
)
