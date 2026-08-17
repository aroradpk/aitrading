# Windows setup for aitrading (run in PowerShell from repo root)
# Usage:  cd D:\aitrading
#         powershell -ExecutionPolicy Bypass -File .\scripts\windows-install.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

# Prefer Python 3.12 (pandas/pyarrow wheels); 3.14 may fail to install deps
$py = $null
foreach ($candidate in @("py -3.12", "py -3.11", "python")) {
    try {
        $ver = Invoke-Expression "$candidate -c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')`""
        if ($ver -match "^3\.(11|12)$") {
            $py = $candidate
            break
        }
    } catch { }
}
if (-not $py) {
    Write-Host "ERROR: Install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "       Check 'Add python.exe to PATH'. Then re-run this script."
    exit 1
}

Write-Host "Using: $py"
if (-not (Test-Path .venv)) {
    Invoke-Expression "$py -m venv .venv"
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt

Write-Host ""
Write-Host "Done. Offline start (no API pulls — uses committed data\):" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
Write-Host ""
Write-Host "Optional rebuild watchlist from disk only (offline_mode: true in config/settings.yaml):"
Write-Host "  python scripts\run_pipeline.py"
Write-Host ""
Write-Host "To refresh from the web: set offline_mode: false, then run_pipeline.py"
