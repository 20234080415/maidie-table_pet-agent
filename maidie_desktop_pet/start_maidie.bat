@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Installing Maidie dependencies...
  python -m venv .venv || goto :error
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
)
start "Maidie" .venv\Scripts\pythonw.exe main.py
exit /b 0

:error
echo Maidie could not start. Please install Python 3.10 or newer.
pause
exit /b 1
