# Windows smoke check — run on native Windows (not Wine).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path (Split-Path $PSScriptRoot))

function Ensure-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) { return }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Set-Alias python py
        return
    }
    throw "Python not found. Install Python 3.12+ from python.org or: winget install Python.Python.3.12"
}

Ensure-Python

Write-Host "1. pip install dependencies..."
python -m pip install -U pip wheel
pip install -r requirements-dev.txt
pip install -e .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. pytest (protocol/hub/discovery)..."
python -m pytest tests/test_protocol.py tests/test_hub.py tests/test_discovery.py -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. CLI help..."
python -m babblecast.cli --help
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "4. PyQt imports..."
python -c "from babblecast.client.qt.main_window import MainWindow; print('imports ok')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "5. PyInstaller build..."
pyinstaller packaging/windows/babblecast.spec --noconfirm
if (-not (Test-Path dist/BabbleCast.exe)) { throw "dist/BabbleCast.exe missing" }
(Get-Item dist/BabbleCast.exe).Length | Out-Host

Write-Host "ALL WINDOWS SMOKE CHECKS PASSED"
