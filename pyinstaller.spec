# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Employee Cash Advance Manager.

Build command:
    pyinstaller pyinstaller.spec
"""
import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[
        ("data_files/seed_data.json",        "data_files"),
        ("data_files/import_samples",        "data_files/import_samples"),
        ("src/data/migrations",              "src/data/migrations"),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "sqlite3",
        "bcrypt",
        "rapidfuzz",
        "rapidfuzz.fuzz",
        "rapidfuzz.process",
        "openpyxl",
        "openpyxl.styles",
        "requests",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["flask", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="CashAdvanceManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No console window (GUI app)
    icon=None,              # Add path to .ico file here if available
)
