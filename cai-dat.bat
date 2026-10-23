@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if errorlevel 1 goto python_error
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_error
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto install_error
echo.
".venv\Scripts\python.exe" launch_app.py reset-environment
if errorlevel 1 goto install_error
echo Cai dat thanh cong. Mo chay.bat de khoi dong.
pause
exit /b 0
:python_error
echo Can cai Python 3.12 va Python Launcher tu python.org.
pause
exit /b 1
:install_error
echo Cai dat chua thanh cong. Giu cua so nay va gui noi dung loi de kiem tra.
pause
exit /b 1
