@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Cap nhat AutoPromt Veo3go
cd /d "%~dp0"

echo ======================================================================
echo             🚀 CẬP NHẬT PHẦN MỀM AUTOPROMT VEO3GO
echo ======================================================================
echo.

set REPO_URL=https://github.com/thincole/veo3go.git

REM 1. Kiem tra Git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Chưa cài đặt Git trên máy tính này!
    echo.
    echo Vui lòng tải và cài đặt Git tại: https://git-scm.com/download/win
    echo Khi cài đặt, chọn mặc định và mở lại file update.bat này.
    echo.
    pause
    exit /b 1
)

REM 2. Hien thi phien ban hien tai
set "CUR_VER=Chưa có"
if exist "version.txt" (
    set /p CUR_VER=<version.txt
    set CUR_VER=!CUR_VER: =!
)
echo [*] Phiên bản hiện tại trên máy: v!CUR_VER!
echo [*] Đang kết nối tới máy chủ GitHub: %REPO_URL%
echo.

REM 3. Dong ung dung AutoPromt cu neu dang mo de cap nhat sach se
taskkill /F /FI "WINDOWTITLE eq AutoPromt*" >nul 2>&1
powershell -NoProfile -Command "Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*AutoPromt*' } | Stop-Process -Force" >nul 2>&1

REM 4. Kiem tra va khoi tao Git neu may moi chua co .git
if not exist ".git" (
    echo [*] Khởi tạo kết nối kho lưu trữ lần đầu...
    git init >nul 2>&1
    git remote add origin %REPO_URL% >nul 2>&1
    git fetch origin main --tags
    git checkout -f -B main origin/main
) else (
    echo [*] Đang kiểm tra và lấy phiên bản mới nhất từ GitHub...
    git remote set-url origin %REPO_URL% >nul 2>&1
    git fetch origin main --tags
    git reset --hard origin/main
)

if %errorlevel% neq 0 (
    echo.
    echo ❌ Có lỗi xảy ra trong quá trình tải cập nhật!
    echo Vui lòng kiểm tra lại kết nối mạng Internet.
    echo.
    pause
    exit /b 1
)

REM 5. Doc phien ban moi sau khi cap nhat
set "NEW_VER=1.0.1"
if exist "version.txt" (
    set /p NEW_VER=<version.txt
    set NEW_VER=!NEW_VER: =!
)

REM 6. Kiem tra va cai dat bo sung thu vien neu thieu
python -c "import PySide6, websockets" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [*] Đang tự động kiểm tra và cài đặt thư viện cần thiết...
    python -m pip install PySide6 websockets >nul 2>&1
)

echo.
echo ======================================================================
echo    🎉 CẬP NHẬT THÀNH CÔNG!
echo.
echo    📌 Phiên bản cũ : v!CUR_VER!
echo    📌 Phiên bản mới: v!NEW_VER!
echo.
echo    (Các file tài khoản veo3_accounts.json và cài đặt cá nhân
echo     được bảo toàn tuyệt đối, không bị ghi đè.)
echo ======================================================================
echo.

REM 7. Hoi nguoi dung co muon khoi chay luon khong
set /p RUN_NOW="Bạn có muốn khởi động phần mềm ngay bây giờ không? (Y/N, mặc định Y): "
if /i "!RUN_NOW!"=="N" (
    echo.
    echo Bạn có thể khởi chạy phần mềm sau bằng file: run_AutoPromt.bat
    pause
    exit /b 0
)

echo.
echo [*] Đang khởi động AutoPromt v!NEW_VER!...
start "" python "%~dp0AutoPromt.py"
exit /b 0
