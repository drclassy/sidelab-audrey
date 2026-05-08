REM Architected and built by classy+.
@echo off
setlocal
chcp 65001 >nul
title SIDELAB — Clinical AI
set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "EMBEDDED_PY=%ROOT%runtime\python\python.exe"
set "APP_ENTRY=%ROOT%sidelab.py"
set "PYTHONPYCACHEPREFIX=%ROOT%.cache\pycache"
set "INSTALLER=%ROOT%install.bat"
set "BOOTSTRAP_POST_INSTALL=%ROOT%bootstrap\post_install.ps1"
set "PYTHON_EXE="

if exist "%VENV_PY%" (
    set "PYTHON_EXE=%VENV_PY%"
) else if exist "%EMBEDDED_PY%" (
    set "PYTHON_EXE=%EMBEDDED_PY%"
) else if exist "%BOOTSTRAP_POST_INSTALL%" (
    echo.
    echo   [!] Runtime hasil installer belum siap.
    echo       Jalankan ulang installer atau diagnose-sidelab.bat.
    echo.
    pause
    exit /b 1
) else if not exist "%INSTALLER%" (
    echo.
    echo   [!] File install.bat tidak ditemukan.
    echo.
    pause
    exit /b 1
)

if not defined PYTHON_EXE (
    echo.
    echo   [!] Runtime SIDELAB belum siap.
    echo       Setup SIDELAB akan dijalankan otomatis.
    echo.
    call "%INSTALLER%"
    if exist "%VENV_PY%" (
        set "PYTHON_EXE=%VENV_PY%"
    ) else if exist "%EMBEDDED_PY%" (
        set "PYTHON_EXE=%EMBEDDED_PY%"
    ) else (
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
"%PYTHON_EXE%" "%APP_ENTRY%"
if errorlevel 1 (
    echo.
    echo   [!] SIDELAB gagal dijalankan.
    echo       Jalankan diagnose-sidelab.bat untuk mengumpulkan laporan.
    echo.
    pause
    exit /b 1
)
echo.
echo   Session ended.
echo.
set /p "reconnect=  Kasus baru? (y/n): "
if /i "%reconnect%"=="y" goto reconnect
echo.
echo   Goodbye.
echo.
pause
