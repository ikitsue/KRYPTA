@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Environnement Python introuvable. Consultez le README.md pour installer Ciphera.
    exit /b 1
)
".venv\Scripts\python.exe" main.py
