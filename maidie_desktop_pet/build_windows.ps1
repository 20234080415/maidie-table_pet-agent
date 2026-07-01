param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

& $Python -m pip install --upgrade -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed." }

& $Python -m PyInstaller --noconfirm --clean maidie.spec
if ($LASTEXITCODE -ne 0) { throw "Maidie build failed." }

Write-Host "Build complete: $PSScriptRoot\dist\Maidie.exe"
