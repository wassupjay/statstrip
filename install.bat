@echo off
REM One-shot installer: finds (or auto-installs) Python, installs the package,
REM drops a shortcut in the per-user Startup folder so it auto-starts every
REM login, then starts it immediately. Run once, no admin required.

set "SCRIPT_DIR=%~dp0"
set "STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StatStrip.lnk"

REM --- Find a usable Python. A bare "python" can be the Microsoft Store
REM --- stub, which exists even when no Python is installed — so actually
REM --- run it instead of just checking it's there.
set "PYTHON=python"
python -c "import sys" >nul 2>&1
if %ERRORLEVEL% EQU 0 goto have_python

REM Installed but not on PATH? (the python.org installer's "Add to PATH"
REM checkbox is easy to miss). Covers both the classic and the new
REM python.org install layouts.
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%LOCALAPPDATA%\Python\pythoncore-3*") do set "PYTHON=%%d\python.exe"
if not "%PYTHON%"=="python" if exist "%PYTHON%" goto have_python

echo Python is not installed. Downloading it now - this can take a few minutes...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%LOCALAPPDATA%\Python\pythoncore-3*") do set "PYTHON=%%d\python.exe"
if exist "%PYTHON%" goto have_python

echo.
echo Could not install Python automatically. Please install it yourself from
echo   https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" in the installer), then run install.bat again.
pause
exit /b 1

:have_python
echo Using Python: %PYTHON%
echo Installing statstrip...
"%PYTHON%" -m pip install "%SCRIPT_DIR%."
if %ERRORLEVEL% NEQ 0 (
  echo pip install failed.
  pause
  exit /b 1
)

REM Resolve absolute paths now, against the Python that pip just installed
REM into, so the login-time launch doesn't depend on PATH at all.
"%PYTHON%" -c "import sysconfig; print(sysconfig.get_path('scripts'))" > "%TEMP%\statstrip-tmp.txt"
set /p SCRIPTS_DIR=<"%TEMP%\statstrip-tmp.txt"
"%PYTHON%" -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))" > "%TEMP%\statstrip-tmp.txt"
set /p PYTHONW=<"%TEMP%\statstrip-tmp.txt"
del "%TEMP%\statstrip-tmp.txt"
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
