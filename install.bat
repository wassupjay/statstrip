@echo off
REM One-shot installer: installs the package (adds statstrip-collector / statstrip-display
REM to PATH), drops a shortcut in the per-user Startup folder so it auto-starts
REM every login, then starts it immediately. Run once, no admin required.

set SCRIPT_DIR=%~dp0
set STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StatStrip.lnk

echo Installing statstrip...
pip install "%SCRIPT_DIR%."
if %ERRORLEVEL% NEQ 0 (
  echo pip install failed. Make sure Python + pip are on PATH.
  pause
  exit /b 1
)

echo Registering auto-start at login...
powershell -NoProfile -Command "$q=[char]34; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:STARTUP_LNK); $s.TargetPath='wscript.exe'; $s.Arguments=$q + $env:SCRIPT_DIR + 'start_monitor.vbs' + $q; $s.WorkingDirectory=$env:SCRIPT_DIR; $s.Save()"

if %ERRORLEVEL% EQU 0 (
  echo Installed. StatStrip will launch at every login.
  echo Starting it now...
  wscript.exe "%SCRIPT_DIR%start_monitor.vbs"
) else (
  echo Failed to create the Startup shortcut at:
  echo   %STARTUP_LNK%
)
pause
