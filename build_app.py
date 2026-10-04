"""Build a standalone, double-clickable executable with PyInstaller.

    pip install pyinstaller
    python build_app.py

The result is dist/WormGearDesigner (dist/WormGearDesigner.exe on Windows).
It runs without Python installed. PyInstaller builds for the system it runs
on, so build on Windows to get the .exe (or use the GitHub Actions workflow).
"""

import os

import PyInstaller.__main__

PyInstaller.__main__.run([
    "app.py",
    "--name", "WormGearDesigner",
    "--onefile",
    "--console",  # the console window shows the URL; closing it quits the app
    "--add-data", f"static{os.pathsep}static",
    "--clean",
    "--noconfirm",
])
