Unicode true
Name "NanoCut 1.1.0.1"
OutFile "..\dist\NanoCut-1.1.0.1-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\NanoCut"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
VIProductVersion "1.1.0.1"
VIAddVersionKey "ProductName" "NanoCut"
VIAddVersionKey "FileDescription" "NanoCut 1.1.0.1 Setup"
VIAddVersionKey "FileVersion" "1.1.0.1"
VIAddVersionKey "ProductVersion" "1.1.0.1"
VIAddVersionKey "LegalCopyright" "NanoCut"
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"
Var Models
Var Background
!define MUI_COMPONENTSPAGE_TEXT_TOP "Choose the local AI tools and speech models to prepare on this computer. Setup reuses compatible installed components."
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\NanoCut.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Section "NanoCut editor and download tools" Core
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "..\dist\host\*.*"
  File "..\NanoCut.py"
  File "..\requirements*.txt"
  File "..\README.md"
  SetOutPath "$INSTDIR\nanocut"
  File "..\nanocut\*.py"
  SetOutPath "$INSTDIR\web"
  File "..\web\*.js"
  File "..\web\*.css"
  File "..\web\*.html"
  File "..\web\*.svg"
  SetOutPath "$INSTDIR\packaging"
  File "setup.ps1"
  File "models.py"
SectionEnd

Section "Local background removal" FG
  StrCpy $Background "-Background"
SectionEnd
!macro Whisper VAR NAME OPTIONAL
Section ${OPTIONAL} "Whisper ${NAME}" ${VAR}
  StrCpy $Models "$Models${NAME},"
SectionEnd
!macroend
SectionGroup "Whisper speech models (all selected)" SpeechModels
!insertmacro Whisper Tiny tiny ""
!insertmacro Whisper Base base ""
!insertmacro Whisper Small small ""
!insertmacro Whisper Medium medium ""
!insertmacro Whisper Large large-v3 ""
!insertmacro Whisper Turbo turbo ""
SectionGroupEnd

Function .onInit
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/COREONLY" $1
  IfErrors checkBase
  !insertmacro UnselectSection ${Base}
  !insertmacro UnselectSection ${FG}
  Goto smaller
  checkBase:
  ClearErrors
  ${GetOptions} $0 "/BASEAI" $1
  IfErrors done
  smaller:
  !insertmacro UnselectSection ${Tiny}
  !insertmacro UnselectSection ${Small}
  !insertmacro UnselectSection ${Medium}
  !insertmacro UnselectSection ${Large}
  !insertmacro UnselectSection ${Turbo}
  done:
FunctionEnd

Section "-Prepare and register"
  SetOutPath "$INSTDIR"
  StrCpy $2 ""
  StrCmp $Models "" ready
  StrCpy $2 '-Models "$Models"'
  ready:
  DetailPrint "Checking installed components and preparing selected features..."
  nsExec::ExecToLog '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\packaging\setup.ps1" $2 $Background'
  Pop $0
  StrCmp $0 "0" success
  SetErrorLevel 1
  DetailPrint "Setup could not finish. See the details above and rerun the installer."
  Abort
  success:
  Delete "$SMPROGRAMS\NanoCut\Install local AI.lnk"
  Delete "$INSTDIR\Setup.cmd"
  Delete "$INSTDIR\NanoCut.cmd"
  Delete "$INSTDIR\Install-AI.cmd"
  CreateDirectory "$SMPROGRAMS\NanoCut"
  CreateShortcut "$SMPROGRAMS\NanoCut\NanoCut.lnk" "$INSTDIR\NanoCut.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NanoCut" "DisplayName" "NanoCut"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NanoCut" "DisplayVersion" "1.1.0.1"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NanoCut" "UninstallString" '"$INSTDIR\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NanoCut"
  Delete "$SMPROGRAMS\NanoCut\NanoCut.lnk"
  RMDir "$SMPROGRAMS\NanoCut"
  Delete "$INSTDIR\NanoCut.exe*"
  Delete "$INSTDIR\Microsoft.Web.WebView2.*"
  Delete "$INSTDIR\WebView2Loader.dll"
  Delete "$INSTDIR\NanoCut.py"
  Delete "$INSTDIR\requirements*.txt"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\packaging\setup.ps1"
  Delete "$INSTDIR\packaging\models.py"
  RMDir "$INSTDIR\packaging"
  Delete "$INSTDIR\nanocut\*.py"
  RMDir "$INSTDIR\nanocut"
  Delete "$INSTDIR\web\*.js"
  Delete "$INSTDIR\web\index.html"
  Delete "$INSTDIR\web\style.css"
  Delete "$INSTDIR\web\icon.svg"
  RMDir "$INSTDIR\web"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
