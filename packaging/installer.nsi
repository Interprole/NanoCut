Unicode true
Name "NanoCut"
OutFile "..\dist\NanoCut-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\NanoCut"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!include "MUI2.nsh"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchEditor
!define MUI_FINISHPAGE_RUN_TEXT "Set up and open NanoCut"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"
Section
  SetOutPath "$INSTDIR"
  File "..\NanoCut.py"
  File "..\NanoCut.cmd"
  File "..\Setup.cmd"
  File "..\Install-AI.cmd"
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
  SetOutPath "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\NanoCut"
  CreateShortCut "$SMPROGRAMS\NanoCut\NanoCut.lnk" "$INSTDIR\NanoCut.cmd"
  CreateShortCut "$SMPROGRAMS\NanoCut\Install local AI.lnk" "$INSTDIR\Install-AI.cmd"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd
Function LaunchEditor
  ExecShell "open" "$INSTDIR\NanoCut.cmd"
FunctionEnd
Section "Uninstall"
  Delete "$SMPROGRAMS\NanoCut\NanoCut.lnk"
  Delete "$SMPROGRAMS\NanoCut\Install local AI.lnk"
  RMDir "$SMPROGRAMS\NanoCut"
  Delete "$INSTDIR\NanoCut.py"
  Delete "$INSTDIR\NanoCut.cmd"
  Delete "$INSTDIR\Setup.cmd"
  Delete "$INSTDIR\Install-AI.cmd"
  Delete "$INSTDIR\requirements.txt"
  Delete "$INSTDIR\requirements-ai.txt"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\packaging\setup.ps1"
  RMDir "$INSTDIR\packaging"
  Delete "$INSTDIR\nanocut\*.py"
  RMDir "$INSTDIR\nanocut"
  Delete "$INSTDIR\web\index.html"
  Delete "$INSTDIR\web\app.js"
  Delete "$INSTDIR\web\timeline.js"
  Delete "$INSTDIR\web\style.css"
  Delete "$INSTDIR\web\icon.svg"
  RMDir "$INSTDIR\web"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd

