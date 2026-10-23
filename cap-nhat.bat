@echo off
setlocal
cd /d "%~dp0"
echo Truoc khi cap nhat, dung app dang chay bang Ctrl+C, roi Y neu duoc hoi.
echo Giu nguyen Ollama. Khong can tat Ollama.
if not exist ".venv\Scripts\python.exe" (
    echo Chua co moi truong Python. Hay chay cai-dat.bat truoc.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" launch_app.py update
if errorlevel 1 (
    pause
    exit /b 1
)
choice /c YN /n /m "Mo doi bot ngay? (Y/N): "
if errorlevel 2 exit /b 0
call "%~dp0chay.bat"
