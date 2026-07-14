@echo off
REM Removes the auto-start entry and stops any running instance.
set TASK_NAME=StatStrip

schtasks /Delete /TN "%TASK_NAME%" /F
taskkill /IM statstrip-collector.exe /F >nul 2>&1
taskkill /IM statstrip-display.exe /F >nul 2>&1

echo Uninstalled auto-start. Run "pip uninstall statstrip" to remove the package too.
pause
