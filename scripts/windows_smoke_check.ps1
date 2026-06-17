# Windows smoke check — run inside a Windows VM or native Windows host.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path (Split-Path $PSScriptRoot))

Write-Host "1. pytest (protocol/hub/discovery)..."
python -m pytest tests/test_protocol.py tests/test_hub.py tests/test_discovery.py -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. CLI help..."
python -m babblecast.cli --help
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3. PyQt imports..."
python -c "from babblecast.client.qt.main_window import MainWindow; print('imports ok')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "4. PyInstaller build..."
pip install -q pyinstaller
pyinstaller packaging/windows/babblecast.spec --noconfirm
if (-not (Test-Path dist/BabbleCast.exe)) { throw "dist/BabbleCast.exe missing" }

Write-Host "ALL WINDOWS SMOKE CHECKS PASSED"
