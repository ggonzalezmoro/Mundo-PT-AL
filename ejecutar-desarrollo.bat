@echo off
REM Arranca la aplicación desde el código (sin empaquetar). Requiere haber ejecutado build.bat una vez.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
)
.venv\Scripts\python.exe -m mundoptal %*
