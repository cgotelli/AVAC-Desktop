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
VIProductVersion "0.1.9.1"
VIAddVersionKey /LANG=1033 "ProductName" "AVAC Desktop"
VIAddVersionKey /LANG=1033 "FileDescription" "AVAC Desktop preview offline installer"
VIAddVersionKey /LANG=1033 "FileVersion" "0.1.9.1"
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
!define MUI_WELCOMEPAGE_TITLE "$(AvacText0)"
!define MUI_WELCOMEPAGE_TEXT "$(AvacText1)"
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_HEADER_TEXT "$(AvacText2)"
!define MUI_LICENSEPAGE_TEXT_TOP "$(AvacText3)"
!define MUI_LICENSEPAGE_TEXT_BOTTOM "$(AvacText6)"
!define MUI_LICENSEPAGE_BUTTON "$(^NextBtn)"
!insertmacro MUI_PAGE_LICENSE "$(AvacLicenseNotice)"
!define MUI_PAGE_HEADER_TEXT "$(AvacText4)"
!define MUI_LICENSEPAGE_TEXT_TOP "$(AvacText5)"
!define MUI_LICENSEPAGE_TEXT_BOTTOM "$(AvacText6)"
!define MUI_LICENSEPAGE_BUTTON "$(^NextBtn)"
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
!define MUI_UNCONFIRMPAGE_TEXT_TOP "$(AvacUninstallNotice)"
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "German"
!include "${__FILEDIR__}\languages.nsh"
!define MUI_LANGDLL_ALLLANGUAGES
!define MUI_LANGDLL_WINDOWTITLE "AVAC Desktop — Language"
!define MUI_LANGDLL_INFO "Choose a language / Choisissez une langue / Elija un idioma / Scegli una lingua / Sprache wählen"


Var PreviousDir
Var RegisteredDir
Var SetDefaultAssociation
Var IsUpgrade
Var CleanupFailed
Var HadDesktopShortcut
Var ResidueSafe
!include "${__FILEDIR__}\cleanup.nsh"

Function .onInit
  StrCpy $LANGUAGE ${LANG_ENGLISH}
  !insertmacro MUI_LANGDLL_DISPLAY
  SetShellVarContext current
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText10)" /SD IDOK
    SetErrorLevel 1633
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin11}
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText11)" /SD IDOK
    SetErrorLevel 1633
    Abort
  ${EndIf}
  SetRegView 64
  ${DisableX64FSRedirection}
  IfFileExists "$SYSDIR\mfplat.dll" MediaPresent
    ${EnableX64FSRedirection}
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText12)" /SD IDOK
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
  !insertmacro AVAC_CHECK_INSTALL_PATH DirectoryUnsafe
  IfFileExists "$INSTDIR\*.*" 0 DirectoryOK
  ReadINIStr $0 "$INSTDIR\avac-installation.ini" "AVAC" "Product"
  ${If} $0 != "${PRODUCT_ID}"
    ${If} $PreviousDir == ""
    ${AndIf} $INSTDIR == "$LOCALAPPDATA\Programs\AVAC Desktop"
      StrCpy $ResidueSafe 1
      Push $INSTDIR
      Call CheckLegacyResidue
      ${If} $ResidueSafe == 1
        WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "Product" "${PRODUCT_ID}"
        Goto DirectoryOK
      ${EndIf}
    ${EndIf}
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText14)" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  DirectoryOK:
    Return
  DirectoryUnsafe:
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText13)" /SD IDOK
    SetErrorLevel 1603
    Abort
FunctionEnd

Function CheckPreviousInstallation
  ${If} $PreviousDir != ""
    ReadINIStr $0 "$PreviousDir\avac-installation.ini" "AVAC" "Product"
    ${If} $0 != "${PRODUCT_ID}"
      MessageBox MB_OK|MB_ICONSTOP "$(AvacText15)" /SD IDOK
      SetErrorLevel 1603
      Abort
    ${EndIf}
    ClearErrors
    FileOpen $0 "$PreviousDir\AVACDesktop.exe" a
    IfErrors PreviousInUse
    FileClose $0
    ExecWait '$\"$PreviousDir\Uninstall.exe$\" /S /UPDATE _?=$PreviousDir' $0
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "$(AvacText16)" /SD IDOK
      SetErrorLevel 1603
      Abort
    ${EndIf}
    Delete "$PreviousDir\Uninstall.exe"
    RMDir "$PreviousDir"
    Return
    PreviousInUse:
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText17)" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
FunctionEnd

Section "$(AvacText7)" MainSection
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
  WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "InstallerLanguage" "$LANGUAGE"
  ; The explicit installer choice seeds a first launch. Keep existing app preferences.
  ClearErrors
  ReadRegStr $0 HKCU "Software\AVAC\AVAC Desktop\interface" "language"
  ${If} ${Errors}
    WriteRegStr HKCU "Software\AVAC\AVAC Desktop\interface" "language" "$(AvacLanguageCode)"
  ${EndIf}
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
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText18)" /SD IDOK
    SetErrorLevel 1603
    Abort
  InstallDone:
SectionEnd

Section "$(AvacText8)" DesktopSection
  CreateShortcut "$DESKTOP\AVAC Desktop.lnk" "$INSTDIR\AVACDesktop.exe"
  WriteINIStr "$INSTDIR\avac-installation.ini" "AVAC" "DesktopShortcut" "1"
SectionEnd

Section "$(AvacText9)" AssociationSection
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
  StrCpy $IsUpgrade 0
  StrCpy $CleanupFailed 0
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} "$0" "/UPDATE" $1
  ${IfNot} ${Errors}
    StrCpy $IsUpgrade 1
  ${EndIf}
  ReadINIStr $LANGUAGE "$INSTDIR\avac-installation.ini" "AVAC" "InstallerLanguage"
  ${If} $LANGUAGE == ""
    StrCpy $LANGUAGE ${LANG_ENGLISH}
  ${EndIf}
  SetShellVarContext current
  SetRegView 64
  !insertmacro AVAC_CHECK_INSTALL_PATH UninstallUnsafePath
  ReadINIStr $0 "$INSTDIR\avac-installation.ini" "AVAC" "Product"
  ${If} $0 != "${PRODUCT_ID}"
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText19)" /SD IDOK
    SetErrorLevel 1603
    Abort
  ${EndIf}
  FileOpen $0 "$INSTDIR\AVACDesktop.exe" a
  IfErrors UninstallInUse
  FileClose $0
  Return
  UninstallUnsafePath:
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText13)" /SD IDOK
    SetErrorLevel 1603
    Abort
  UninstallInUse:
    MessageBox MB_OK|MB_ICONSTOP "$(AvacText20)" /SD IDOK
    SetErrorLevel 1603
    Abort
FunctionEnd

Section "Uninstall"
  ReadRegStr $RegisteredDir HKCU "${REGKEY}" "InstallLocation"
  ReadINIStr $SetDefaultAssociation "$INSTDIR\avac-installation.ini" "AVAC" "SetDefaultAssociation"
  ReadINIStr $HadDesktopShortcut "$INSTDIR\avac-installation.ini" "AVAC" "DesktopShortcut"
  ; Leave the installation directory before removing it.
  SetOutPath "$TEMP"
  ${If} $IsUpgrade == 1
    ; Updates preserve app data, preferences and unrecorded files. Keep the
    ; ownership marker so an interrupted update remains repairable.
    !include "${UNINSTALL_FILES}"
    Goto UninstallDone
  ${EndIf}
  ${If} $RegisteredDir == $INSTDIR
  ${OrIf} $RegisteredDir == ""
    GetFullPathName $0 "$APPDATA\AVAC Desktop\runtime\desktop"
    Push $0
    Call un.RemoveOwnedTree
    GetFullPathName $0 "$LOCALAPPDATA\AVAC\AVAC Desktop"
    Push $0
    Call un.RemoveOwnedTree
    GetFullPathName $0 "$LOCALAPPDATA\AVAC Desktop"
    Push $0
    Call un.RemoveOwnedTree
    GetFullPathName $0 "$APPDATA\AVAC\AVAC Desktop"
    Push $0
    Call un.RemoveOwnedTree
  ${EndIf}
  InitPluginsDir
  CopyFiles /SILENT "$INSTDIR\avac-installation.ini" "$PLUGINSDIR\avac-installation.ini"
  Push $INSTDIR
  Call un.RemoveOwnedTree
  ${If} $CleanupFailed == 1
    Goto UninstallFailed
  ${EndIf}
  ClearErrors
  Delete "$INSTDIR\Uninstall.exe"
  IfErrors UninstallFailed
  Delete "$INSTDIR\avac-installation.ini"
  RMDir "$INSTDIR"
  ${If} ${Errors}
    ; Keep a usable uninstaller and ownership evidence when cleanup cannot
    ; finish. Never report success after leaving an unmarked occupied folder.
    CopyFiles /SILENT "$PLUGINSDIR\avac-installation.ini" "$INSTDIR\avac-installation.ini"
    CopyFiles /SILENT "$EXEPATH" "$INSTDIR\Uninstall.exe"
    Goto UninstallFailed
  ${EndIf}
  ${If} $RegisteredDir == $INSTDIR
  ${OrIf} $RegisteredDir == ""
    DeleteRegKey HKCU "Software\AVAC\AVAC Desktop"
    RMDir "$APPDATA\AVAC Desktop\runtime"
    RMDir "$APPDATA\AVAC Desktop"
    RMDir "$LOCALAPPDATA\AVAC"
    RMDir "$APPDATA\AVAC"
  ${EndIf}
  ${If} $RegisteredDir == $INSTDIR
    ${If} $HadDesktopShortcut == "1"
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
  Goto UninstallDone
  UninstallFailed:
    MessageBox MB_OK|MB_ICONSTOP "$(AvacCleanupError)" /SD IDOK
    SetErrorLevel 1603
    Abort
  UninstallDone:
SectionEnd
