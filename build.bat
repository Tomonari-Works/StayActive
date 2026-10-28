@echo off
setlocal
cd /d "%~dp0"
set "STAYACTIVE_PYTHON=python"
if not "%~1"=="" set "STAYACTIVE_PYTHON=%~1"
set "STAYACTIVE_DIST=dist"
if not "%~2"=="" set "STAYACTIVE_DIST=%~2"
REM Build only inside the project venv. Never modify shared Python packages.
if not exist ".venv\Scripts\python.exe" (
    "%STAYACTIVE_PYTHON%" -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m unittest discover -v
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\make_icon.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\prepare_licenses.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --distpath "%STAYACTIVE_DIST%" StayActive.spec
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\check_exe.py "%STAYACTIVE_DIST%\StayActive.exe"
if errorlevel 1 exit /b 1
echo Built: %STAYACTIVE_DIST%\StayActive.exe
endlocal
