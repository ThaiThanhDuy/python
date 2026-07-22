@echo off
REM One-time setup: registers "Mouse Corner Macro" as a Start Menu shortcut,
REM and pre-downloads the OCR models so the app never has to fetch them later.
setlocal
set "DIR=%~dp0"

if exist "%DIR%venv\Scripts\python.exe" (
    echo Dang tai san mo hinh OCR (chi 1 lan)...
    "%DIR%venv\Scripts\python.exe" "%DIR%download_ocr_models.py"
) else (
    echo [CANH BAO] Khong tim thay venv, bo qua buoc tai mo hinh OCR.
    echo Hay chay: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%install_app.ps1"
pause
