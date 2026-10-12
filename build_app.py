"""Build a standalone, double-clickable executable with PyInstaller.

    pip install pyinstaller
    python build_app.py

The result is dist/WormGearDesigner (dist/WormGearDesigner.exe on Windows).
It runs without Python installed. PyInstaller builds for the system it runs
on, so build on Windows to get the .exe (or use the GitHub Actions workflow).
"""

import os                     # os.pathsep separates source and destination in --add-data

import PyInstaller.__main__   # the build is driven through PyInstaller's own API

# Equivalent to running the pyinstaller command with these arguments.
PyInstaller.__main__.run([
    "app.py",                       # the entry point to freeze
    "--name", "WormGearDesigner",   # name of the executable
    "--onefile",                    # bundle everything into a single file
    "--console",  # the console window shows the URL; closing it quits the app
    # Ship the dashboard's HTML: "<source><sep><destination inside the bundle>".
    # app.py finds it again through sys._MEIPASS.
    "--add-data", f"static{os.pathsep}static",
    "--clean",                      # discard any cached build files first
    "--noconfirm",                  # overwrite dist/ without prompting
])
