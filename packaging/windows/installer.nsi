; AVAC Desktop per-user offline installer. No elevation or dependency downloads.
Unicode True
ManifestDPIAware True
RequestExecutionLevel user
SetCompressor zlib
CRCCheck force
Name "AVAC Desktop ${AVAC_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir ""
BrandingText "AVAC Desktop - free scientific software"
VIProductVersion "0.1.0.1"
VIAddVersionKey /LANG=1033 "ProductName" "AVAC Desktop"
VIAddVersionKey /LANG=1033 "FileDescription" "AVAC Desktop preview offline installer"
VIAddVersionKey /LANG=1033 "FileVersion" "0.1.0.1"
VIAddVersionKey /LANG=1033 "LegalCopyright" "AVAC Desktop contributors; third-party notices included"

!include MUI2.nsh
!include LogicLib.nsh
!include WinVer.nsh
!include x64.nsh
!include FileFunc.nsh

!define PRODUCT_ID "AVAC.Desktop.Preview"
!define REGKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AVACDesktop"
!define PROGID "AVACDesktop.Project"
!define MUI_ICON "${__FILEDIR__}\assets\AVACDesktop.ico"
!define MUI_UNICON "${__FILEDIR__}\assets\AVACDesktop.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Install AVAC Desktop"
!define MUI_WELCOMEPAGE_TEXT "Avalanche and lake-wave modelling.$\r$\n$\r$\nThis offline installer includes the application, Python, GIS libraries and both native solvers. No Python, QGIS, compiler or administrator account is required.$\r$\n$\r$\nDevelopment preview for Windows 11 x64 (Intel/AMD). Results require independent scientific validation."
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_HEADER_TEXT "Scientific-use notice"
!define MUI_LICENSEPAGE_TEXT_TOP "Read the modelling limitations and warranty/liability notice. This notice does not restrict your free-software rights."
!define MUI_LICENSEPAGE_BUTTON "Next >"
!insertmacro MUI_PAGE_LICENSE "${STAGE}\DISCLAIMER.txt"
!define MUI_PAGE_HEADER_TEXT "Free software license"
!define MUI_LICENSEPAGE_TEXT_TOP "AVAC Desktop is AGPL-3.0-or-later. Third-party licenses are included. Receiving or running this software does not require accepting additional terms."
!define MUI_LICENSEPAGE_BUTTON "Next >"
!insertmacro MUI_PAGE_LICENSE "${STAGE}\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE ValidateDirectory
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\AVACDesktop.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\INSTALL.txt"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Var PreviousDir
Var RegisteredDir
Var SetDefaultAssociation

Function .onInit
  SetShellVarContext current
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_OK|MB_ICONSTOP "This installer requires Windows 11 x64 on an Intel/AMD processor. ARM and 32-bit Windows are not supported by this build." /SD IDOK
    SetErrorLevel 1633
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin11}
    MessageBox MB_OK|MB_ICONSTOP "This first installer supports Windows 11 (build 22000 or later)." /SD IDOK
    SetErrorLevel 1633
    Abort
  ${EndIf}
  SetRegView 64
  ${DisableX64FSRedirection}
  IfFileExists "$SYSDIR\mfplat.dll" MediaPresent
    ${EnableX64FSRedirection}
    MessageBox MB_OK|MB_ICONSTOP "Standard Windows multimedia components are missing. On Windows N, install Microsoft's Media Feature Pack from Windows Optional Features, then run Setup again. No third-party download is required for standard Windows 11 editions." /SD IDOK
    SetErrorLevel 1633
    Abort
  MediaPresent:
  ${EnableX64FSRedirection}
  ReadRegStr $PreviousDir HKCU "${REGKEY}" "InstallLocation"
  ${If} $INSTDIR == ""
    StrCpy $INSTDIR $PreviousDir
  ${EndIf}
  ${If} $INSTDIR == ""
    StrCpy $INSTDIR "$LOCALAPPDATA\Programs\AVAC Desktop"
  ${EndIf}
FunctionEnd

Function ValidateDirectory
  ; NSIS already validates absolute /D and directory-page paths. Its
  ; GetFullPathName rejects some not-yet-created folders; do not require
  ; the installation directory to exist before first installation.
  ClearErrors
  ${If} $INSTDIR == ""
  ${OrIf} $INSTDIR == "$PROFILE"
  ${OrIf} $INSTDIR == "$DOCUMENTS"
  ${OrIf} $INSTDIR == "$DESKTOP"
  ${OrIf} $INSTDIR == "$LOCALAPPDATA"
  ${OrIf} $INSTDIR == "$WINDIR"
  ${OrIf} $INSTDIR == "$PROGRAMFILES64"
  ${OrIf} $INSTDIR == "$TEMP"
    MessageBox MB_OK|MB_ICONSTOP "Choose a dedicated application subfolder, not a system or personal-data folder." /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  IfFileExists "$INSTDIR\*.*" 0 DirectoryOK
  ReadINIStr $0 "$INSTDIR\avac-installation.ini" "AVAC" "Product"
  ${If} $0 != "${PRODUCT_ID}"
    MessageBox MB_OK|MB_ICONSTOP "The chosen folder contains other files. Choose an empty application folder or the existing AVAC Desktop installation." /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  DirectoryOK:
FunctionEnd

Function CheckPreviousInstallation
  ${If} $PreviousDir != ""
    ReadINIStr $0 "$PreviousDir\avac-installation.ini" "AVAC" "Product"
    ${If} $0 != "${PRODUCT_ID}"
      MessageBox MB_OK|MB_ICONSTOP "The registered installation marker is missing. The existing folder was left untouched. Uninstall or repair the previous installation first." /SD IDOK
      SetErrorLevel 1603
      Abort
    ${EndIf}
    ClearErrors
    FileOpen $0 "$PreviousDir\AVACDesktop.exe" a
    IfErrors PreviousInUse
    FileClose $0
    ExecWait '$\"$PreviousDir\Uninstall.exe$\" /S _?=$PreviousDir' $0
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "The previous version could not be removed. Close AVAC Desktop and try again." /SD IDOK
      SetErrorLevel 1603
      Abort
    ${EndIf}
    Delete "$PreviousDir\Uninstall.exe"
    RMDir "$PreviousDir"
    Return
    PreviousInUse:
    MessageBox MB_OK|MB_ICONSTOP "Close AVAC Desktop before updating it, and check that its program folder is writable." /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
FunctionEnd

Section "Application, solvers, licenses and source (required)" MainSection
  SectionIn RO
  Call ValidateDirectory
  Call CheckPreviousInstallation
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ; This is an empty or already owned folder. Mark it before extraction so a
  ; failed copy can be retried without claiming unrelated pre-existing files.
  WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "Product" "${PRODUCT_ID}"
  ClearErrors
  File /r "${BUNDLE}\*.*"
  File "${STAGE}\INSTALL.txt"
  File "${STAGE}\DISCLAIMER.txt"
  File "${STAGE}\LICENSE"
  File "${STAGE}\THIRD_PARTY_NOTICES.md"
  File "${STAGE}\INSTALLATION_FILES.json"
  SetOutPath "$INSTDIR\Licenses"
  File /r "${STAGE}\Licenses\*.*"
  SetOutPath "$INSTDIR\Source"
  File /r "${STAGE}\Source\*.*"
  IfErrors InstallFailed
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "Product" "${PRODUCT_ID}"
  WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "Version" "${AVAC_VERSION}"
  WriteRegStr HKCU "${REGKEY}" "DisplayName" "AVAC Desktop (preview)"
  WriteRegStr HKCU "${REGKEY}" "DisplayVersion" "${AVAC_VERSION}"
  WriteRegStr HKCU "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${REGKEY}" "DisplayIcon" "$INSTDIR\AVACDesktop.exe,0"
  WriteRegStr HKCU "${REGKEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${REGKEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${REGKEY}" "EstimatedSize" ${INSTALLED_KIB}
  WriteRegDWORD HKCU "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGKEY}" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\AVAC Desktop"
  CreateShortcut "$SMPROGRAMS\AVAC Desktop\AVAC Desktop.lnk" "$INSTDIR\AVACDesktop.exe"
  CreateShortcut "$SMPROGRAMS\AVAC Desktop\Scientific-use notice.lnk" "$INSTDIR\DISCLAIMER.txt"
  CreateShortcut "$SMPROGRAMS\AVAC Desktop\Source and licenses.lnk" "$INSTDIR\Source"
  Goto InstallDone
  InstallFailed:
    MessageBox MB_OK|MB_ICONSTOP "Installation could not copy all files. Check available space and folder permissions, then run Setup again." /SD IDOK
    SetErrorLevel 1603
    Abort
  InstallDone:
SectionEnd

Section "Desktop shortcut" DesktopSection
  CreateShortcut "$DESKTOP\AVAC Desktop.lnk" "$INSTDIR\AVACDesktop.exe"
  WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "DesktopShortcut" "1"
SectionEnd

Section "Open AVAC project files (.avacproj)" AssociationSection
  WriteRegStr HKCU "Software\Classes\${PROGID}" "" "AVAC Desktop project"
  WriteRegStr HKCU "Software\Classes\${PROGID}\DefaultIcon" "" "$INSTDIR\AVACDesktop.exe,0"
  WriteRegStr HKCU "Software\Classes\${PROGID}\shell\open\command" "" '$\"$INSTDIR\AVACDesktop.exe$\" $\"%1$\"'
  WriteRegStr HKCU "Software\Classes\.avacproj\OpenWithProgids" "${PROGID}" ""
  ReadRegStr $0 HKCU "Software\Classes\.avacproj" ""
  ${If} $0 == ""
    WriteRegStr HKCU "Software\Classes\.avacproj" "" "${PROGID}"
    WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "SetDefaultAssociation" "1"
  ${EndIf}
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  ReadINIStr $0 "$INSTDIR\avac-installation.ini" "AVAC" "Product"
  ${If} $0 != "${PRODUCT_ID}"
    MessageBox MB_OK|MB_ICONSTOP "AVAC installation marker not found. No files were removed." /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  FileOpen $0 "$INSTDIR\AVACDesktop.exe" a
  IfErrors UninstallInUse
  FileClose $0
  Return
  UninstallInUse:
    MessageBox MB_OK|MB_ICONSTOP "Close AVAC Desktop before uninstalling it." /SD IDOK
    SetErrorLevel 1603
    Abort
FunctionEnd

Section "Uninstall"
  ReadRegStr $RegisteredDir HKCU "${REGKEY}" "InstallLocation"
  ReadINIStr $SetDefaultAssociation "$INSTDIR\avac-installation.ini" "AVAC" "SetDefaultAssociation"
  ${If} $RegisteredDir == $INSTDIR
    ReadINIStr $0 "$INSTDIR\avac-installation.ini" "AVAC" "DesktopShortcut"
    ${If} $0 == "1"
      Delete "$DESKTOP\AVAC Desktop.lnk"
    ${EndIf}
    Delete "$SMPROGRAMS\AVAC Desktop\AVAC Desktop.lnk"
    Delete "$SMPROGRAMS\AVAC Desktop\Scientific-use notice.lnk"
    Delete "$SMPROGRAMS\AVAC Desktop\Source and licenses.lnk"
    RMDir "$SMPROGRAMS\AVAC Desktop"
    DeleteRegKey HKCU "${REGKEY}"
    ReadRegStr $0 HKCU "Software\Classes\${PROGID}\shell\open\command" ""
    ${If} $0 == '$\"$INSTDIR\AVACDesktop.exe$\" $\"%1$\"'
      DeleteRegKey HKCU "Software\Classes\${PROGID}"
      DeleteRegValue HKCU "Software\Classes\.avacproj\OpenWithProgids" "${PROGID}"
      ReadRegStr $0 HKCU "Software\Classes\.avacproj" ""
      ${If} $SetDefaultAssociation == "1"
      ${AndIf} $0 == "${PROGID}"
        DeleteRegValue HKCU "Software\Classes\.avacproj" ""
      ${EndIf}
      DeleteRegKey /ifempty HKCU "Software\Classes\.avacproj\OpenWithProgids"
      DeleteRegKey /ifempty HKCU "Software\Classes\.avacproj"
    ${EndIf}
    System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
  ${EndIf}
  ; Generated exact file deletions, then empty-directory removals. Never use
  ; recursive deletion: a user may have saved a project in this folder.
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\avac-installation.ini"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
