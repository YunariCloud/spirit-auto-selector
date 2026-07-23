$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptRoot

$python = Join-Path $scriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $python -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m PyInstaller --noconfirm --clean SpiritAutoSelector.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$output = Join-Path $scriptRoot "dist\SpiritAutoSelector.exe"
Write-Host "Build completed: $output"
