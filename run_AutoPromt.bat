@echo off
title AutoPromt Launcher
echo Launching AutoPromt.py...
python "%~dp0AutoPromt.py"
if %errorlevel% neq 0 (
    echo.
    echo Application exited with an error (code %errorlevel%).
    pause
)
