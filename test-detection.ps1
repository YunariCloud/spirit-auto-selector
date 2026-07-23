$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    Write-Host "First run: creating the Python environment..."
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& ".venv\Scripts\python.exe" main.py --dry-run
exit $LASTEXITCODE
