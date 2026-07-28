@echo off
setlocal
set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo Virtual environment not found.
    echo Right-click setup.ps1 -^> Run with PowerShell, then try again.
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo ubx2rinex - convert raw u-blox UBX logs to RINEX .YYo / .YYn
    echo.
    echo   Drag one or more .ubx files ^(or a folder^) onto convert.bat
    echo.
    echo   Or from a terminal:
    echo     convert.bat C:\path\to\data
    echo     convert.bat a.ubx b.ubx
    echo.
    pause
    exit /b 0
)

"%PY%" "%HERE%ubx2rinex.py" %*

echo.
pause
