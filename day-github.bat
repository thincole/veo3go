@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

cd /d "%~dp0"

echo ======================================================================
echo                CAP NHAT CODE LEN GITHUB (VEO3GO)
echo ======================================================================
echo.

set REPO_URL=https://github.com/thincole/veo3go.git
set VER_FILE=version.txt

REM 1. Kiem tra va khoi tao Git repository
if not exist ".git" (
    echo [1/6] Khoi tao Git repository...
    git init
) else (
    echo [1/6] Git repository da san sang.
)

REM 2. Cau hinh Remote Origin
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [2/6] Dang them remote origin: %REPO_URL%
    git remote add origin %REPO_URL%
) else (
    echo [2/6] Remote origin hien tai: %REPO_URL%
    git remote set-url origin %REPO_URL%
)

REM Cau hinh user git neu chua co
git config user.name >nul 2>&1
if errorlevel 1 (
    git config user.name "thincole"
)
git config user.email >nul 2>&1
if errorlevel 1 (
    git config user.email "thincole@users.noreply.github.com"
)

REM 3. Xu ly va tang phien ban (Version)
if not exist "%VER_FILE%" (
    set NEW_VER=1.0.1
    echo [3/6] Khoi tao phien ban ban dau: 1.0.1
) else (
    set /p OLD_VER=<"%VER_FILE%"
    set OLD_VER=!OLD_VER: =!
    for /f "tokens=1,2,3 delims=." %%a in ("!OLD_VER!") do (
        set /a PATCH=%%c+1
        set NEW_VER=%%a.%%b.!PATCH!
    )
    if "!NEW_VER!"=="" set NEW_VER=1.0.1
    echo [3/6] Phien ban cu: !OLD_VER! -^> Phien ban moi: !NEW_VER!
)

<nul set /p="!NEW_VER!">"%VER_FILE%"

echo.
REM 4. Nhap ghi chu commit
echo [4/6] Ghi chu cap nhat (Commit message):
set "USER_MSG="
set /p USER_MSG="  Nhap mo ta thay doi (Enter de dung mac dinh 'Update code v!NEW_VER!'): "
if "!USER_MSG!"=="" (
    set "COMMIT_MSG=Update code v!NEW_VER!"
) else (
    set "COMMIT_MSG=[v!NEW_VER!] !USER_MSG!"
)

echo.
echo [5/6] Dang gom file va commit...
git add .
git commit -m "!COMMIT_MSG!"

REM Tao git tag cho phien ban moi
git tag -a "v!NEW_VER!" -m "Version !NEW_VER!" >nul 2>&1

echo.
echo [6/6] Dang day code len GitHub (%REPO_URL%)...
git branch -M main
git push -u origin main --tags

if errorlevel 1 (
    echo.
    echo Co the can pull ve truoc khi push... Dang thu rebase:
    git pull origin main --rebase >nul 2>&1
    git push -u origin main --tags
)

echo.
echo ======================================================================
if %ERRORLEVEL% EQU 0 (
    echo    DA CAP NHAT CODE THANH CONG LEN GITHUB!
    echo    Phien ban hien tai: v!NEW_VER!
    echo    Repo: %REPO_URL%
) else (
    echo    CO THE CAN DANG NHAP GITHUB HOAC KIEM TRA QUYEN PUSH!
)
echo ======================================================================
echo.
pause
