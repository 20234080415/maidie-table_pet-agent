@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Checking the active Python environment...
python -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10 or newer is required'; print(sys.executable); print(sys.version)" || goto :error

echo [2/4] Installing runtime and packaging dependencies...
python -m pip install -r requirements.txt -r requirements-build.txt || goto :error

echo [3/4] Building Maidie...
python -m PyInstaller --noconfirm --clean maidie.spec || goto :error

echo [4/4] Build complete.
echo Output: %CD%\dist\Maidie\Maidie.exe
echo Keep the whole dist\Maidie folder together when copying or publishing it.
exit /b 0

:error
echo.
echo Maidie build failed. Review the error above and confirm the active Python environment.
echo Conda example: conda activate maidie
echo Then run: build_exe.bat
exit /b 1
