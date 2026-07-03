@echo off
setlocal
cd /d "%~dp0"

set "MAIDIE_VERSION=%~1"
if not defined MAIDIE_VERSION set "MAIDIE_VERSION=0.1.0"

echo Rebuilding Maidie from the latest source code...
call build_exe.bat || goto :error

set "ISCC=%INNO_SETUP_COMPILER%"
if defined ISCC if exist "%ISCC%" goto :build
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if defined ISCC goto :build
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"
if defined ISCC goto :build

echo Inno Setup 6 was not found.
echo Install it from https://jrsoftware.org/isinfo.php
echo Or set INNO_SETUP_COMPILER to the full path of ISCC.exe.
exit /b 1

:build
echo Building Maidie installer version %MAIDIE_VERSION%...
"%ISCC%" /DMyAppVersion=%MAIDIE_VERSION% "packaging\maidie.iss" || goto :error
echo.
echo Installer created: %CD%\dist\installer\Maidie-Setup.exe
exit /b 0

:error
echo.
echo Maidie installer build failed. Review the error above.
exit /b 1
