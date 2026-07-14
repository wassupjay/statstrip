@echo off
REM One-shot installer: installs the package (adds statstrip-collector / statstrip-display
REM to PATH), registers a Task Scheduler entry so it auto-starts every login,
REM then starts it immediately. Run once, no admin required.

set SCRIPT_DIR=%~dp0
set TASK_NAME=StatStrip

echo Installing statstrip...
pip install "%SCRIPT_DIR%."
if %ERRORLEVEL% NEQ 0 (
  echo pip install failed. Make sure Python + pip are on PATH.
  pause
  exit /b 1
)

echo Registering auto-start at login...
schtasks /Create /TN "%TASK_NAME%" ^
  /TR "wscript.exe \"%SCRIPT_DIR%start_monitor.vbs\"" ^
  /SC ONLOGON /RL LIMITED /F

if %ERRORLEVEL% EQU 0 (
  echo Installed. "%TASK_NAME%" will launch the monitor at every login.
  echo Starting it now...
  schtasks /Run /TN "%TASK_NAME%"
) else (
  echo Failed to register scheduled task. Try running this .bat as Administrator.
)
pause
