@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo EDNOR - build portable EXE
echo ==========================================

if not exist ".venv" (
    echo [INFO] Tworze venv...
    py -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo [INFO] Aktualizuje pip...
python -m pip install --upgrade pip

echo [INFO] Instaluje PyInstaller...
python -m pip install pyinstaller

echo [INFO] Buduje Ednor.exe...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name Ednor ^
  gui_cutting.py

echo.
echo ==========================================
echo GOTOWE
echo Plik:
echo dist\Ednor.exe
echo ==========================================
echo.
echo TEST PORTABLE:
echo 1. Skopiuj dist\Ednor.exe do pustego folderu.
echo 2. Uruchom Ednor.exe.
echo 3. Program ma utworzyc Ednor_data obok EXE.
echo 4. Dodaj surowiec, transport i rozkroj.
echo 5. Zamknij i uruchom ponownie.
echo 6. Dane maja zostac w Ednor_data.
echo.
pause
