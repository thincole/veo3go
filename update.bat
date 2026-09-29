@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Cap nhat AutoPromt Veo3go

REM Neu dang chay che do worker tu thu muc TEMP thi nhay den :DO_UPDATE
if "%~1"=="--worker" goto :DO_UPDATE

REM ======================================================================
REM BUOC 0: Chay qua file tam trong TEMP de tranh xung dot khi Git reset
REM ======================================================================
copy /y "%~f0" "%TEMP%\veo3go_updater.bat" >nul 2>&1
if exist "%TEMP%\veo3go_updater.bat" (
    call "%TEMP%\veo3go_updater.bat" --worker "%~dp0"
    exit /b !errorlevel!
)

:DO_UPDATE
set "TARGET_DIR=%~2"
if "%TARGET_DIR%"=="" set "TARGET_DIR=%~dp0"
cd /d "%TARGET_DIR%"

echo ======================================================================
echo                CAP NHAT PHAN MEM AUTOPROMT VEO3GO
echo ======================================================================
echo.

set "REPO_URL=https://github.com/thincole/veo3go.git"
set "ZIP_URL=https://github.com/thincole/veo3go/archive/refs/heads/main.zip"

REM 1. Doc phien ban hien tai tren may
set "CUR_VER=Chua ro"
if exist "version.txt" (
    set /p CUR_VER=<version.txt
    set CUR_VER=!CUR_VER: =!
)
echo [*] Phien ban hien tai tren may: v!CUR_VER!
echo.

REM 2. Tim Git tren may
set "GIT_CMD="
where git >nul 2>&1
if !errorlevel! equ 0 (
    set "GIT_CMD=git"
    goto :DO_GIT
)
if exist "C:\Program Files\Git\cmd\git.exe" (
    set "GIT_CMD=C:\Program Files\Git\cmd\git.exe"
    goto :DO_GIT
)
if exist "C:\Program Files (x86)\Git\cmd\git.exe" (
    set "GIT_CMD=C:\Program Files (x86)\Git\cmd\git.exe"
    goto :DO_GIT
)
if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" (
    set "GIT_CMD=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
    goto :DO_GIT
)

echo [THONG BAO] May nay chua cai Git trong he thong.
echo [*] Tu dong chuyen sang tai ban cap nhat truc tiep tu GitHub...
echo.
goto :FALLBACK_ZIP

:DO_GIT
echo [*] Tim thay Git: !GIT_CMD!
echo [*] Dang dong bo ma nguon moi nhat tu GitHub...
echo.

if not exist ".git" goto :GIT_FIRST_TIME

REM May da co kho git, cap nhat
"!GIT_CMD!" remote set-url origin !REPO_URL! >nul 2>&1
"!GIT_CMD!" fetch origin main --tags
"!GIT_CMD!" reset --hard origin/main
if !errorlevel! neq 0 (
    echo.
    echo [CANH BAO] Khong the cap nhat qua Git. Dang thu tai ZIP truc tiep...
    goto :FALLBACK_ZIP
)
goto :UPDATE_SUCCESS

:GIT_FIRST_TIME
echo [*] Khoi tao ket noi Git lan dau...
"!GIT_CMD!" init >nul 2>&1
"!GIT_CMD!" remote add origin !REPO_URL! >nul 2>&1
"!GIT_CMD!" fetch origin main --tags
"!GIT_CMD!" checkout -f -B main origin/main
if !errorlevel! neq 0 (
    echo.
    echo [CANH BAO] Khoi tao Git that bai. Dang thu tai ZIP truc tiep...
    goto :FALLBACK_ZIP
)
goto :UPDATE_SUCCESS

:FALLBACK_ZIP
set "TEMP_ZIP=%TEMP%\veo3go_latest.zip"
set "TEMP_EXTRACT=%TEMP%\veo3go_latest_extracted"

if exist "!TEMP_ZIP!" del /f /q "!TEMP_ZIP!" >nul 2>&1
if exist "!TEMP_EXTRACT!" rmdir /s /q "!TEMP_EXTRACT!" >nul 2>&1

echo [*] Dang tai ban cap nhat tu GitHub...
where curl >nul 2>&1
if !errorlevel! equ 0 goto :USE_CURL
powershell -Command "Invoke-WebRequest -Uri '!ZIP_URL!' -OutFile '!TEMP_ZIP!'"
goto :AFTER_DOWNLOAD

:USE_CURL
curl -L -s -o "!TEMP_ZIP!" "!ZIP_URL!"

:AFTER_DOWNLOAD
if not exist "!TEMP_ZIP!" (
    echo.
    echo [LOI] Khong the tai ban cap nhat tu GitHub!
    echo Vui long kiem tra ket noi Internet.
    echo.
    pause
    exit /b 1
)

echo [*] Dang giai nen ban cap nhat...
where tar >nul 2>&1
if !errorlevel! equ 0 goto :USE_TAR
powershell -Command "Expand-Archive -Path '!TEMP_ZIP!' -DestinationPath '!TEMP_EXTRACT!' -Force"
goto :AFTER_EXTRACT

:USE_TAR
mkdir "!TEMP_EXTRACT!" >nul 2>&1
tar -xf "!TEMP_ZIP!" -C "!TEMP_EXTRACT!"

:AFTER_EXTRACT
if exist "!TEMP_EXTRACT!\veo3go-main" (
    echo [*] Dang ghi de cac file ma nguon moi...
    xcopy /s /e /y /q "!TEMP_EXTRACT!\veo3go-main\*" "%TARGET_DIR%" >nul 2>&1
    del /f /q "!TEMP_ZIP!" >nul 2>&1
    rmdir /s /q "!TEMP_EXTRACT!" >nul 2>&1
) else (
    echo.
    echo [LOI] Giai nen that bai hoac ban cap nhat khong hop le.
    echo.
    pause
    exit /b 1
)

:UPDATE_SUCCESS
echo.
REM 4. Doc phien ban moi sau khi cap nhat
set "NEW_VER=1.0.1"
if exist "version.txt" (
    set /p NEW_VER=<version.txt
    set NEW_VER=!NEW_VER: =!
)

REM 5. Kiem tra Python va cac thu vien
where python >nul 2>&1
if !errorlevel! equ 0 (
    python -c "import PySide6, websockets" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [*] Dang cai dat thu vien PySide6 va websockets...
        python -m pip install PySide6 websockets
    )
) else (
    echo [CANH BAO] Khong tim thay Python tren he thong.
    echo Hay cai dat Python tu https://www.python.org neu can chay phan mem.
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

REM 6. Hoi nguoi dung khoi chay
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
where python >nul 2>&1
if !errorlevel! equ 0 (
    start "" python "%TARGET_DIR%AutoPromt.py"
) else (
    echo [LOI] Khong tim thay Python de khoi dong phan mem.
    echo Ban hay mo run_AutoPromt.bat sau khi da cai Python.
    pause
)
exit /b 0
