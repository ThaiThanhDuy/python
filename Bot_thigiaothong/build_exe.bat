@echo off
REM Build lai file BotThiGiaoThong.exe (dist\BotThiGiaoThong.exe) tu code
REM hien tai. Chay file nay moi khi sua gui.py/main.py xong muon dong goi
REM lai. Can venv da cai du thu vien trong requirements.txt (xem
REM install_app.bat neu chua co venv).
setlocal
set "DIR=%~dp0"
set "PY=%DIR%venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [LOI] Khong tim thay venv tai "%DIR%venv".
    echo Hay chay: python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Dang kiem tra/cai PyInstaller...
"%PY%" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    "%PY%" -m pip install pyinstaller
)

echo.
echo Dang build BotThiGiaoThong.exe (co the mat vai phut vi easyocr/torch kha nang)...
cd /d "%DIR%"
"%PY%" -m PyInstaller --noconfirm --onefile --windowed ^
    --name "BotThiGiaoThong" ^
    --distpath dist --workpath build --specpath . ^
    gui.py

if errorlevel 1 (
    echo.
    echo [LOI] Build that bai, xem log ben tren.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build xong: %DIR%dist\BotThiGiaoThong.exe
echo  detected_questions.json va question_images\ se tu tao ra
echo  ngay canh file .exe nay khi chay lan dau.
echo ============================================================
pause
