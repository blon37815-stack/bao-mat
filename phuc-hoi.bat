@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Chay cai-dat.bat truoc de co Python.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" restore_app.py
pause
