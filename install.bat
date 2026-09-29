@echo off
:: ==========================================================
::  Cai dat va KIEM TRA moi truong chay AutoPromt
:: ==========================================================
setlocal enabledelayedexpansion
title Cai dat moi truong AutoPromt
cd /d "%~dp0"
cls

set THIEU=0
set CANHBAO=0

echo ==========================================================
echo        CAI DAT MOI TRUONG CHAY PHAN MEM AUTOPROMT
echo ==========================================================
echo.

:: ---------- 1. Python ----------
echo [*] Kiem tra Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python trong PATH.
    echo.
    echo   1. Tai Python 3.12 tro len: https://www.python.org/downloads/
    echo   2. Khi cai, BAT BUOC tick vao o "Add python.exe to PATH"
    echo   3. Chay lai file install.bat nay.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%I in ('python --version 2^>^&1') do set PY_VER=%%I
echo     [OK] Python !PY_VER!
echo.

:: ---------- 2. Thu vien Python ----------
echo [*] Cai dat thu vien can thiet...
python -m pip install --upgrade pip >nul 2>&1

:: Dung "install" chu khong phai "--upgrade": chi cai khi thieu,
:: khong tu y nang cap lam xao tron may dang chay on dinh.
echo     - PySide6 (giao dien)...
python -m pip install PySide6 >nul 2>&1
echo     - websockets (ket noi server)...
python -m pip install websockets >nul 2>&1
echo.

:: ---------- 3. XAC MINH thu vien that su dung duoc ----------
echo [*] Xac minh thu vien...
python -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo     [THIEU] PySide6 - cai that bai
    set /a THIEU+=1
) else (
    for /f %%V in ('python -c "import PySide6;print(PySide6.__version__)" 2^>nul') do echo     [OK] PySide6 %%V
)

python -c "import websockets" >nul 2>&1
if %errorlevel% neq 0 (
    echo     [THIEU] websockets - cai that bai
    set /a THIEU+=1
) else (
    for /f %%V in ('python -c "import websockets;print(websockets.__version__)" 2^>nul') do echo     [OK] websockets %%V
)
echo.

:: ---------- 4. Cong cu ffmpeg / ffprobe ----------
echo [*] Kiem tra cong cu xu ly video...
if exist "bin\ffmpeg.exe" (
    echo     [OK] ffmpeg  - bin\ffmpeg.exe
) else (
    where ffmpeg >nul 2>&1
    if !errorlevel! equ 0 (
        echo     [OK] ffmpeg  - tim thay trong PATH
    ) else (
        echo     [THIEU] ffmpeg - khong the xoa logo va ghep anh 12s
        echo             Tai tai https://www.gyan.dev/ffmpeg/builds/ roi chep ffmpeg.exe vao thu muc bin\
        set /a THIEU+=1
    )
)

if exist "bin\ffprobe.exe" (
    echo     [OK] ffprobe - bin\ffprobe.exe
) else (
    where ffprobe >nul 2>&1
    if !errorlevel! equ 0 (
        echo     [OK] ffprobe - tim thay trong PATH
    ) else (
        echo     [CANH BAO] Thieu ffprobe.
        echo                Chuc nang "Ghep anh 12s" van chay nhung se doan sai thong so:
        echo                mac dinh 1080x1920 30fps va coi nhu video KHONG co tieng.
        echo                Khac phuc: chep ffprobe.exe vao thu muc bin\ ^(di kem ffmpeg^)
        set /a CANHBAO+=1
    )
)
echo.

:: ---------- 5. File chuong trinh va tai nguyen ----------
echo [*] Kiem tra file chuong trinh...
for %%F in (AutoPromt.py shopee_db_helper.py run_AutoPromt.bat) do (
    if exist "%%F" (
        echo     [OK] %%F
    ) else (
        echo     [THIEU] %%F
        set /a THIEU+=1
    )
)
if exist "resources\brand.txt" (
    echo     [OK] resources\brand.txt
) else (
    echo     [CANH BAO] Thieu resources\brand.txt - se dung brand mac dinh "vanthe"
    set /a CANHBAO+=1
)
echo.

:: ---------- 6. Thu nap chuong trinh ----------
echo [*] Thu nap AutoPromt.py...
python -c "import importlib.util,sys;sys.argv=['x'];s=importlib.util.spec_from_file_location('AP','AutoPromt.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)" >nul 2>&1
if %errorlevel% neq 0 (
    echo     [LOI] Khong nap duoc AutoPromt.py. Chi tiet loi:
    python -c "import importlib.util,sys;sys.argv=['x'];s=importlib.util.spec_from_file_location('AP','AutoPromt.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)"
    set /a THIEU+=1
) else (
    echo     [OK] Nap thanh cong
)
echo.

:: ---------- Ket qua ----------
echo ==========================================================
if %THIEU% gtr 0 (
    echo   CHUA DU DIEU KIEN CHAY - con %THIEU% muc bi thieu
    echo   Xem cac dong [THIEU] o tren de khac phuc.
) else (
    if %CANHBAO% gtr 0 (
        echo   CO THE CHAY DUOC - nhung co %CANHBAO% canh bao
        echo   Xem cac dong [CANH BAO] o tren.
    ) else (
        echo   DAY DU - san sang chay phan mem
    )
    echo.
    echo   Khoi chay bang file:  run_AutoPromt.bat
)
echo ==========================================================
echo.
pause
if %THIEU% gtr 0 exit /b 1
exit /b 0
