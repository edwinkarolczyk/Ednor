@echo off
cd /d "%~dp0"
echo ==========================================
echo EDNOR - test core / magazyn / FIFO
echo ==========================================
py check_ednor_core.py
echo.
pause
