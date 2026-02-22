@echo off
echo === Hook-to-Short Build ===
echo.

REM Check for ffmpeg
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] ffmpeg not found in PATH — video features need ffmpeg.exe in dist folder
)

REM Install PyInstaller if needed
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building .exe...
pyinstaller hook-to-short.spec --noconfirm

if %errorlevel% equ 0 (
    echo.
    echo === Build complete ===
    echo Output: dist\Hook-to-Short\Hook-to-Short.exe
    echo.
    echo Before distributing:
    echo   1. Copy .env.example to dist\Hook-to-Short\.env and fill in API keys
    echo   2. Copy client_secrets.json to dist\Hook-to-Short\ for YouTube upload
    echo   3. Ensure ffmpeg.exe is in PATH or in dist\Hook-to-Short\
) else (
    echo.
    echo === Build FAILED ===
)
pause
