@echo off
REM Removes the auto-start entry and stops any running instance.
set STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StatStrip.lnk

if exist "%STARTUP_LNK%" del "%STARTUP_LNK%"
REM Older versions registered a scheduled task instead of a Startup shortcut.
schtasks /Delete /TN "StatStrip" /F >nul 2>&1
REM Kill running instances. Match on command line, not image name, so
REM "pythonw -m statstrip.*" launches are caught too, not just the
REM statstrip-*.exe entry points.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'statstrip' -and ($_.Name -like 'python*' -or $_.Name -like 'statstrip*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo Uninstalled auto-start. Run "pip uninstall statstrip" to remove the package too.
pause
