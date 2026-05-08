REM Architected and built by classy+.
@echo off
setlocal
chcp 65001 >nul
title SIDELAB — Clinical AI
set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "PYTHONPYCACHEPREFIX=%ROOT%.cache\pycache"
set "INSTALLER=%ROOT%install.bat"

if not exist "%VENV_PY%" (
    echo.
    echo   [!] Virtual environment belum siap.
    if not exist "%INSTALLER%" (
        echo       File install.bat tidak ditemukan.
        echo.
        pause
        exit /b 1
    )
    echo       Setup SIDELAB akan dijalankan otomatis.
    echo.
    call "%INSTALLER%"
    if not exist "%VENV_PY%" (
        echo.
        echo   [!] Setup belum selesai atau gagal.
        echo       Jalankan diagnose-sidelab.bat jika masalah berulang.
        echo.
        pause
        exit /b 1
    )
)

:reconnect
cls
"%VENV_PY%" "%ROOT%medgemma_chat.py"
echo.
echo   Session ended.
echo.
set /p "reconnect=  Kasus baru? (y/n): "
if /i "%reconnect%"=="y" goto reconnect
echo.
echo   Goodbye.
echo.
pause
