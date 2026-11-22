@echo off
rem Build the Windows folder app. Run from anywhere; it works from the repo root.
rem Needs Python 3.10+ on PATH. Creates .venv-build, installs requirements, builds, and makes a ZIP.
setlocal
cd /d "%~dp0\.."

where python >nul 2>nul || (echo ERROR: Python is not on PATH. Install Python 3.10+ first. & exit /b 1)

if not exist .venv-build (
    python -m venv .venv-build || exit /b 1
)
call .venv-build\Scripts\activate.bat || exit /b 1
python -m pip install --upgrade pip || exit /b 1
pip install -r requirements.txt pyinstaller || exit /b 1

rem The build must start from a clean state and must never include any shop data.
if exist build rmdir /s /q build
if exist dist\POS_Mobile rmdir /s /q dist\POS_Mobile

pyinstaller --noconfirm --clean packaging\pos_mobile.spec || exit /b 1

if not exist dist\POS_Mobile\POS_Mobile.exe (
    echo ERROR: build finished but POS_Mobile.exe is missing.
    exit /b 1
)

rem ZIP the whole folder: the exe does not run without the _internal folder next to it.
powershell -NoProfile -Command "Compress-Archive -Path 'dist\POS_Mobile' -DestinationPath 'dist\POS_Mobile.zip' -Force" || exit /b 1

echo.
echo Done:
echo   folder: dist\POS_Mobile\POS_Mobile.exe
echo   zip   : dist\POS_Mobile.zip   (give the customer the whole ZIP, not only the exe)
echo Test it on a clean computer before delivering. First run shows the activation screen.
endlocal
