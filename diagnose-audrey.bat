@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title AUDREY — Diagnostics

set "ROOT=%~dp0"
set "ROOT_DRIVE=%~d0"
set "OUT_DIR=%ROOT%diagnostics"
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%" >nul 2>&1

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%t"
set "OUT_FILE=%OUT_DIR%\audrey-diagnostic-%STAMP%.txt"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

(
echo ================================================
echo AUDREY Diagnostics
echo Timestamp: %DATE% %TIME%
echo Root     : %ROOT%
echo ================================================
echo.
echo [SYSTEM]
ver
powershell -NoProfile -Command "$os = Get-CimInstance Win32_OperatingSystem; $cs = Get-CimInstance Win32_ComputerSystem; Write-Output ('OS: ' + $os.Caption); Write-Output ('RAM_GB: ' + [int][math]::Round($cs.TotalPhysicalMemory / 1GB, 0)); Write-Output ('DiskFree_GB: ' + [int][math]::Round((Get-PSDrive -Name '%ROOT_DRIVE:~0,1%').Free / 1GB, 0))"
echo.
echo [PYTHON]
where python
python --version
py -3 --version
if exist "%VENV_PY%" (
  echo VENV_PY: %VENV_PY%
  "%VENV_PY%" --version
  "%VENV_PY%" -m pip list
) else (
  echo VENV_PY: NOT_FOUND
)
echo.
echo [DEEPSEEK]
if exist "%ROOT%.env" (
  findstr /B /C:"AUDREY_DEFAULT_BACKEND=" /C:"DEEPSEEK_BASE_URL=" /C:"DEEPSEEK_MODEL=" /C:"DEEPSEEK_API_KEY=" "%ROOT%.env"
) else (
  echo .env NOT_FOUND
)
echo.
echo [OLLAMA]
where ollama
ollama --version
curl.exe -fsS http://127.0.0.1:11434/api/version
ollama list
echo.
echo [MODEL_SMOKE]
if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import ollama; print((ollama.generate(model='medgemma:4b', prompt='Jawab satu kata: OK').get('response') or '').strip())"
) else (
  echo SKIPPED_NO_VENV
)
echo.
echo [ENV]
if exist "%ROOT%.env" (
  findstr /B /C:"TELEGRAM_BOT_TOKEN=" /C:"TELEGRAM_CHAT_ID=" "%ROOT%.env"
) else (
  echo .env NOT_FOUND
)
) > "%OUT_FILE%" 2>&1

echo.
echo  [OK] Laporan diagnostik dibuat:
echo      %OUT_FILE%
echo.
pause
