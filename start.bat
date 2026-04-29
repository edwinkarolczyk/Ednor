@echo off
setlocal
cd /d "%~dp0"
start "" /b pythonw "%~dp0gui_cutting.py"
endlocal
