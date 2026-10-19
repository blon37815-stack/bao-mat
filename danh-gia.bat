@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Chay cai-dat.bat truoc.
    pause
    exit /b 1
)
echo Se thu ca JSON data_basic 10 lan bang Ollama tren may.
echo Viec nay co the lau. Giu Ollama mo; dung app va cac phien chat khac de so lieu de so sanh.
echo Ket qua nam trong data\evaluations. Khong chay ma do bot tao.
choice /c YN /n /m "Bat dau danh gia? (Y/N): "
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" evaluate.py --case data_basic --repeat 10 --run
echo Ma ket thuc: %errorlevel% (0: tat ca dat; 1: co ca chua dat; 130: da dung).
pause
