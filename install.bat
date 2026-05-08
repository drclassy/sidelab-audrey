REM Architected and built by classy+.
@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title SIDELAB — Setup

set "ROOT=%~dp0"
set "ROOT_DRIVE=%~d0"
set "VENV_DIR=%ROOT%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "PYTHON_CMD="

echo.
echo  ================================================
echo   SIDELAB Setup — Clinical AI untuk Puskesmas
echo  ================================================
echo.

call :detect_python
if not defined PYTHON_CMD (
    echo  [!] Python tidak ditemukan.
    echo      Download dari: https://www.python.org/downloads/
    echo      Centang "Add Python to PATH" saat install.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VERSION=%%v"
echo  [OK] !PYTHON_VERSION!

echo.
echo  Pemeriksaan awal perangkat...
for /f %%m in ('powershell -NoProfile -Command "[int][math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 0)"') do set "RAM_GB=%%m"
for /f %%d in ('powershell -NoProfile -Command "[int][math]::Round((Get-PSDrive -Name '%ROOT_DRIVE:~0,1%').Free / 1GB, 0)"') do set "FREE_GB=%%d"
echo    RAM terpasang : !RAM_GB! GB
echo    Disk kosong   : !FREE_GB! GB
if defined RAM_GB if !RAM_GB! LSS 16 (
    echo  [!] Peringatan: RAM di bawah 16 GB. Mode lokal mungkin berat.
    echo      Jika sering error saat inferensi, pertimbangkan 1 PC host Ollama
    echo      dan PC lain hanya sebagai client SideLab.
)
if defined FREE_GB if !FREE_GB! LSS 10 (
    echo  [!] Disk kosong kurang dari 10 GB. Install model bisa gagal.
    pause
    exit /b 1
)

:: Check Ollama
ollama --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Ollama tidak ditemukan.
    echo      Download dari: https://ollama.com/download
    echo      Install, lalu jalankan install.bat ini lagi.
    echo.
    pause
    exit /b 1
)

echo  [OK] Ollama ditemukan.

if not exist "%VENV_PY%" (
    echo.
    echo  Membuat virtual environment...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [!] Gagal membuat virtual environment.
        pause
        exit /b 1
    )
)
echo  [OK] Virtual environment siap.

echo.
echo  Menginstall Python packages...
"%VENV_PY%" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo  [!] Gagal memperbarui pip di virtual environment.
    pause
    exit /b 1
)
"%VENV_PIP%" install -r "%ROOT%requirements.txt" --quiet
if errorlevel 1 (
    echo  [!] Gagal install packages. Cek koneksi internet.
    pause
    exit /b 1
)
echo  [OK] Packages terinstall.

if not exist "%ROOT%.env" if exist "%ROOT%.env.example" (
    copy /Y "%ROOT%.env.example" "%ROOT%.env" >nul
    echo  [OK] File .env dibuat dari .env.example
    echo      Isi TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, dan DEEPSEEK_API_KEY bila ingin memakai DeepSeek dan /send.
)

echo.
echo  Memeriksa Ollama (opsional untuk mode Local)...
curl.exe -fsS http://127.0.0.1:11434/api/version >nul 2>&1
if errorlevel 1 (
    echo  [i] Ollama belum merespons. Ini tidak masalah bila Anda ingin memakai DeepSeek.
    echo      Mode Local tetap bisa diaktifkan nanti jika Ollama dipasang.
    echo.
) else (
    echo  [OK] Service Ollama aktif.
)
echo.
echo  DeepSeek menjadi backend default saat runtime.
echo  Jika ingin mode Local, pasang Ollama lalu pilih Local saat SIDELAB berjalan.

echo.
echo  ================================================
echo   Setup selesai. Jalankan SIDELAB.bat untuk memulai.
echo  ================================================
echo.
echo  [i] Jika /send ingin dipakai, isi file .env lebih dulu.
echo  [i] Jika nanti ada error di PC lain, jalankan diagnose-sidelab.bat
echo      dan kirim file laporan dari folder diagnostics.
echo.
pause
exit /b 0

:detect_python
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :eof
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
)
goto :eof
