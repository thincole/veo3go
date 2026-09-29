@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Cap nhat AutoPromt Veo3go
cd /d "%~dp0"

echo ======================================================================
echo                CAP NHAT PHAN MEM AUTOPROMT VEO3GO
echo ======================================================================
echo.

set REPO_URL=https://github.com/thincole/veo3go.git

REM 1. Kiem tra Git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] May tinh nay chua cai dat Git!
    echo.
    echo Vui long tai va cai dat Git tai: https://git-scm.com/download/win
    echo (Khi cai dat chi can bam Next lien tuc roi mo lai file update.bat nay).
    echo.
    pause
    exit /b 1
)

REM 2. Hien thi phien ban hien tai
set "CUR_VER=Chua co"
if exist "version.txt" (
    set /p CUR_VER=<version.txt
    set CUR_VER=!CUR_VER: =!
)
echo [*] Phien ban hien tai tren may: v!CUR_VER!
echo [*] Dang ket noi toi GitHub: %REPO_URL%
echo.

REM 3. Kiem tra va khoi tao Git neu may moi chua co .git
if not exist ".git" (
    echo [*] Khoi tao ket noi kho luu tru lan dau...
    git init >nul 2>&1
    git remote add origin %REPO_URL% >nul 2>&1
    git fetch origin main --tags
    git checkout -f -B main origin/main
) else (
    echo [*] Dang tai ban cap nhat moi nhat tu GitHub...
    git remote set-url origin %REPO_URL% >nul 2>&1
    git fetch origin main --tags
    git reset --hard origin/main
)

if %errorlevel% neq 0 (
    echo.
    echo [LOI] Khong the tai ban cap nhat tu GitHub!
    echo Vui long kiem tra lai ket noi Internet hoac thu muc.
    echo.
    pause
    exit /b 1
)

REM 4. Doc phien ban moi sau khi cap nhat
set "NEW_VER=1.0.1"
if exist "version.txt" (
    set /p NEW_VER=<version.txt
    set NEW_VER=!NEW_VER: =!
)

REM 5. Kiem tra va cai dat thu vien neu thieu
python -c "import PySide6, websockets" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [*] Dang cai dat thu vien PySide6 va websockets...
    python -m pip install PySide6 websockets
)

echo.
echo ======================================================================
echo    DA CAP NHAT THANH CONG!
echo.
echo    Phien ban cu : v!CUR_VER!
echo    Phien ban moi: v!NEW_VER!
echo.
echo    (Cac file veo3_accounts.json va cai dat ca nhan duoc giu nguyen)
echo ======================================================================
echo.

REM 6. Hoi nguoi dung co muon khoi chay luon khong
set "RUN_NOW="
set /p RUN_NOW="Ban co muon khoi dong phan mem ngay bay gio? (Y/N, Enter de chay): "
if /i "!RUN_NOW!"=="N" (
    echo.
    echo Ban co the khoi chay phan mem sau bang file: run_AutoPromt.bat
    echo.
    pause
    exit /b 0
)

echo.
echo [*] Dang khoi dong AutoPromt v!NEW_VER!...
start "" python "%~dp0AutoPromt.py"
exit /b 0
