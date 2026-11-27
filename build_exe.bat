@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo Create it first: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --clean --onefile --windowed ^
    --name "Mikrotik-Realtime-Monitor" ^
    --icon "assets\icon.ico" ^
    --add-data "assets\icon.png;assets" ^
    --add-data "auidio-alarm.mp3;." ^
    --add-data "warning.mp3;." ^
    --collect-data qtawesome ^
    --hidden-import librouteros ^
    --hidden-import PySide6.QtMultimedia ^
    --exclude-module pytest ^
    --exclude-module pyinstaller ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

taskkill /IM "Mikrotik-Realtime-Monitor.exe" /F >nul 2>&1
copy /Y "dist\Mikrotik-Realtime-Monitor.exe" "Mikrotik-Realtime-Monitor.exe" >nul
if errorlevel 1 (
    echo [ERROR] Gagal menyalin EXE ke folder project. Tutup aplikasi lalu jalankan ulang.
    pause
    exit /b 1
)

rem --- Folder Release portable (Windows 10 1809+ / Windows 11, 64-bit) ---
if not exist "Release" mkdir "Release"
copy /Y "dist\Mikrotik-Realtime-Monitor.exe" "Release\Mikrotik-Realtime-Monitor.exe" >nul
copy /Y "config.example.yaml" "Release\config.example.yaml" >nul
if exist "RELEASE-README.txt" copy /Y "RELEASE-README.txt" "Release\README.txt" >nul
if exist "RELEASE-Demo.bat" copy /Y "RELEASE-Demo.bat" "Release\Demo.bat" >nul
if not exist "Release\routers.json" echo {"active": null, "profiles": []}> "Release\routers.json"

echo.
echo Build selesai:
echo   - Mikrotik-Realtime-Monitor.exe
echo   - Release\Mikrotik-Realtime-Monitor.exe (folder portable siap distribusi)
exit /b 0
