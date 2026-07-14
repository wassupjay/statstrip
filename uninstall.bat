@echo off
REM Removes the auto-start entry and stops any running instance.
set "STARTUP_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StatStrip.lnk"

if exist "%STARTUP_LNK%" del "%STARTUP_LNK%"
REM Older versions registered a scheduled task instead of a Startup shortcut.
schtasks /Delete /TN "StatStrip" /F >nul 2>&1
REM Kill running instances. Match the exact launch forms on the command line
REM (not just the substring "statstrip") so unrelated python work in this
REM repo — a pytest run, a scratch script — isn't force-killed too.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'statstrip*') -and $_.CommandLine -match '-m statstrip\.(collector|display)|statstrip-(collector|display)\.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo Uninstalled auto-start. Run "pip uninstall statstrip" to remove the package too.
pause
