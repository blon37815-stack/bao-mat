@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Chua cai moi truong. Hay chay cai-dat.bat truoc.
    pause
    exit /b 1
)
echo Giu Ollama dang chay neu dung AI tren may.
echo Khi thay "Bot team listening", mo http://127.0.0.1:8000 trong trinh duyet.
echo Giu cua so nay mo. Nhan Ctrl+C de dung.
echo Neu da mo app o cua so khac, dung cua so do truoc.
".venv\Scripts\python.exe" launch_app.py run
if errorlevel 1 (
    echo Ung dung da dung. Neu thieu thu vien, chay lai cai-dat.bat.
    pause
    exit /b 1
)
