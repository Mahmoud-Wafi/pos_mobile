@echo off
rem Build the Windows folder app. Run from the repo root in a venv with requirements.txt installed.
pip install pyinstaller || exit /b 1
pyinstaller --noconfirm --clean packaging\pos_mobile.spec || exit /b 1
echo Done: dist\POS_Mobile\POS_Mobile.exe
