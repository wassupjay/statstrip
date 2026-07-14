@echo off
REM One-shot installer: installs the package (adds statstrip-collector / statstrip-display
REM to PATH), drops a shortcut in the per-user Startup folder so it auto-starts
REM every login, then starts it immediately. Run once, no admin required.

set "SCRIPT_DIR=%~dp0"
set "STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StatStrip.lnk"

echo Installing statstrip...
pip install "%SCRIPT_DIR%."
if %ERRORLEVEL% NEQ 0 (
  echo pip install failed. Make sure Python + pip are on PATH.
  pause
  exit /b 1
)

REM Resolve absolute paths now, in the environment where pip just worked, so
REM the login-time launch doesn't depend on PATH (pip's Scripts dir often
REM isn't on it for per-user installs).
for /f "usebackq delims=" %%i in (`python -c "import sysconfig; print(sysconfig.get_path('scripts'))"`) do set "SCRIPTS_DIR=%%i"
for /f "usebackq delims=" %%i in (`python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"`) do set "PYTHONW=%%i"
set "COLLECTOR_EXE=%SCRIPTS_DIR%\statstrip-collector.exe"
set "DISPLAY_EXE=%SCRIPTS_DIR%\statstrip-display.exe"

echo Registering auto-start at login...
powershell -NoProfile -Command "$q=[char]34; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:STARTUP_LNK); $s.TargetPath='wscript.exe'; $s.Arguments=($q + $env:SCRIPT_DIR + 'start_monitor.vbs' + $q + ' ' + $q + $env:COLLECTOR_EXE + $q + ' ' + $q + $env:DISPLAY_EXE + $q + ' ' + $q + $env:PYTHONW + $q); $s.WorkingDirectory=$env:SCRIPT_DIR; $s.Save()"

if %ERRORLEVEL% EQU 0 (
  echo Installed. StatStrip will launch at every login.
  echo Stopping any running instance...
  powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'statstrip*') -and $_.CommandLine -match '-m statstrip\.(collector|display)|statstrip-(collector|display)\.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  echo Starting it now...
  wscript.exe "%SCRIPT_DIR%start_monitor.vbs" "%COLLECTOR_EXE%" "%DISPLAY_EXE%" "%PYTHONW%"
) else (
  echo Failed to create the Startup shortcut at:
  echo   %STARTUP_LNK%
)
pause
