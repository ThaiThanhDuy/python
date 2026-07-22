@echo off
REM Launches the Mouse Corner Macro GUI app (Windows).
setlocal
set "DIR=%~dp0"
set "PYTHONW=%DIR%venv\Scripts\pythonw.exe"
set "PY=%DIR%venv\Scripts\python.exe"

if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%DIR%gui.py"
    goto :eof
)

if exist "%PY%" (
    start "" "%PY%" "%DIR%gui.py"
    goto :eof
)

echo [ERROR] Khong tim thay virtual environment tai "%DIR%venv".
echo Hay chay cac lenh sau roi thu lai:
echo   python -m venv venv
echo   venv\Scripts\pip install -r requirements.txt
pause
exit /b 1
