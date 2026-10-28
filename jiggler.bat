@echo off
cd /d "%~dp0"
if exist "dist\StayActive.exe" (
    start "" "%~dp0dist\StayActive.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
) else (
    python "%~dp0main.py"
)
