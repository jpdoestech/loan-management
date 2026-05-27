@echo off
echo Building Employee Cash Advance Manager .exe ...
cd /d "%~dp0\.."

:: Install deps
pip install -r requirements.txt

:: Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

:: Build
pyinstaller pyinstaller.spec

echo.
echo Build complete! Executable is at: dist\CashAdvanceManager.exe
pause
