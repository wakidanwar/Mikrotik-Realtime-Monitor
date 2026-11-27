@echo off
setlocal
cd /d "%~dp0"

rem Console/debug mode: shows a window and pauses on error.
rem For a windowless launch, use run.vbs instead.
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in this folder.
    echo.
    echo Create it first:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py %*
set "rc=%errorlevel%"

if not "%rc%"=="0" (
    echo.
    echo The monitor exited with an error, code %rc%. See the message above.
    pause
)

exit /b %rc%
