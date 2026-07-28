@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo Virtual environment belum dibuat.
    echo Klik kanan setup.ps1 -^> Run with PowerShell, lalu coba lagi.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo ubx2rinex - konversi log mentah u-blox UBX ke RINEX .YYo / .YYn
    echo.
    echo   Seret satu atau beberapa file .ubx ^(atau sebuah folder^) ke convert.bat
    echo.
    echo   Atau dari terminal:
    echo     convert.bat C:\path\ke\data
    echo     convert.bat a.ubx b.ubx
    echo.
    pause
    exit /b 0
)

"%PY%" "%HERE%ubx2rinex.py" %*

echo.
pause
