Unicode True

!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "2.5"
!endif
!ifndef APP_FILE_VERSION
  !define APP_FILE_VERSION "2.5.0.0"
!endif
!ifndef PROJECT_ROOT
  !define PROJECT_ROOT "..\.."
!endif

!define PRODUCT_NAME "SanWich"
!define PRODUCT_PUBLISHER "WiKiVibe"
!define PRODUCT_REG_KEY "Software\WiKiVibe\SanWich"
!define PRODUCT_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\SanWich"

Var IsUpdate

Name "${PRODUCT_NAME}"
Caption "${PRODUCT_NAME} v${APP_VERSION} Setup"
BrandingText "${PRODUCT_PUBLISHER}"
OutFile "${PROJECT_ROOT}\release\SanWich_Setup_v${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\SanWich"
InstallDirRegKey HKCU "${PRODUCT_REG_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
SetDatablockOptimize on
SetDateSave on
ShowInstDetails nevershow
ShowUninstDetails nevershow

VIProductVersion "${APP_FILE_VERSION}"
VIAddVersionKey /LANG=1028 "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=1028 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1028 "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=1028 "FileDescription" "${PRODUCT_NAME} Setup"
VIAddVersionKey /LANG=1028 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1028 "LegalCopyright" "Copyright (c) ${PRODUCT_PUBLISHER}"

!define MUI_ICON "${PROJECT_ROOT}\assets\images\_LOGO.ico"
!define MUI_UNICON "${PROJECT_ROOT}\assets\images\_LOGO.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\SanWich.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch SanWich"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "TradChinese"

Function .onInit
  SetShellVarContext current
  StrCpy $IsUpdate "0"
  ${GetParameters} $0
  ${GetOptions} $0 "/UPDATE=" $1
  StrCmp $1 "1" 0 readPreviousInstall
  StrCpy $IsUpdate "1"
readPreviousInstall:
  ReadRegStr $0 HKCU "${PRODUCT_REG_KEY}" "InstallDir"
  StrCmp $0 "" done
  StrCpy $INSTDIR $0
done:
FunctionEnd

Section "Install" SEC_MAIN
  SetShellVarContext current
  SetOverwrite on
  StrCmp $IsUpdate "1" 0 writeFiles
  IfFileExists "$INSTDIR\SanWich.exe" 0 writeFiles
  IfFileExists "$INSTDIR\Uninstall.exe" 0 writeFiles
  Delete "$INSTDIR\SanWich.exe"
  RMDir /r "$INSTDIR\_internal"
writeFiles:
  SetOutPath "$INSTDIR"
  File /r "${PROJECT_ROOT}\dist\SanWich\*.*"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\SanWich"
  CreateShortcut "$SMPROGRAMS\SanWich\SanWich.lnk" "$INSTDIR\SanWich.exe" "" "$INSTDIR\SanWich.exe" 0
  CreateShortcut "$SMPROGRAMS\SanWich\Uninstall SanWich.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\SanWich.lnk" "$INSTDIR\SanWich.exe" "" "$INSTDIR\SanWich.exe" 0

  WriteRegStr HKCU "${PRODUCT_REG_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\SanWich.exe"
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKCU "${PRODUCT_UNINSTALL_KEY}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${PRODUCT_UNINSTALL_KEY}" "EstimatedSize" 81920
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$DESKTOP\SanWich.lnk"
  Delete "$SMPROGRAMS\SanWich\SanWich.lnk"
  Delete "$SMPROGRAMS\SanWich\Uninstall SanWich.lnk"
  RMDir "$SMPROGRAMS\SanWich"

  DeleteRegKey HKCU "${PRODUCT_UNINSTALL_KEY}"
  DeleteRegValue HKCU "${PRODUCT_REG_KEY}" "InstallDir"

  RMDir /r "$INSTDIR"
SectionEnd
