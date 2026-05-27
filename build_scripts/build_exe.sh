#!/usr/bin/env bash
set -e
echo "Building Employee Cash Advance Manager .exe ..."
cd "$(dirname "$0")/.."

pip install -r requirements.txt
rm -rf build dist

pyinstaller pyinstaller.spec

echo ""
echo "Build complete! Executable is at: dist/CashAdvanceManager.exe"
