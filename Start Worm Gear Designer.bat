@echo off
rem Double-click to open the Worm Gear Designer window (needs Python 3.9+ with Tk).
title Worm Gear Designer
cd /d "%~dp0"
rem pythonw starts the window without a console; errors are then not visible.
where pythonw >nul 2>nul && (start "" pythonw app.py & exit /b 0)
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH", or use the standalone WormGearDesigner.exe.
    pause
    exit /b 1
)
%PY% app.py
if errorlevel 1 pause
