@echo off
REM Build Windows BabbleCast executable
setlocal
cd /d %~dp0..\..
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -U pip wheel
pip install -r requirements-dev.txt
pip install -e .
pyinstaller packaging\windows\babblecast.spec --noconfirm
echo Output: dist\BabbleCast.exe
echo Use Inno Setup with packaging\windows\installer.iss for full installer.
