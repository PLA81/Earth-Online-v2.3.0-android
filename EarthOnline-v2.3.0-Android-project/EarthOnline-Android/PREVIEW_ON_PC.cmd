@echo off
setlocal
cd /d "%~dp0"
if not exist ".preview_venv\Scripts\python.exe" (
  py -3 -m venv .preview_venv
  if errorlevel 1 python -m venv .preview_venv
)
".preview_venv\Scripts\python.exe" -m pip install --upgrade pip
".preview_venv\Scripts\python.exe" -m pip install "PySide6-Essentials>=6.10.1,<6.12"
".preview_venv\Scripts\python.exe" main.py
if errorlevel 1 pause
